"""M1.3: `ggdesk send`, with a fake build result and a fake connection (never USB)."""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import ggdesk.build as builder
from ggdesk import gate
from ggdesk import run as runmod
from ggdesk.build import BuildResult
from ggdesk.cli import main
from ggdesk.gate import Severity
from ggdesk.joblog import JobLog
from ggdesk.library import Selection, load_library, resolve
from ggdesk.library.model import Machine
from ggdesk.model.toolpath import Intent
from tests.conftest import DESKTOP
from tests.unit.test_run import CM1, JF, SEL, FakeConn, _Rule, gts, home_ok  # noqa: F401 - fixture

JOB = DESKTOP / "docs" / "examples" / "square-10mm.ggj"


class Env:
    def __init__(self, tmp: Path, data: bytes, report_text: str, conns: list[FakeConn]) -> None:
        self.tmp, self.data, self.conns = tmp, data, conns
        self.m20 = tmp / "job.m20"
        self.report = tmp / "job.gate.json"
        self.m20.write_bytes(data)
        self.report.write_text(report_text, encoding="utf-8")
        self.log = JobLog(tmp / "logs" / "jobs.jsonl")

    def argv(self, *extra: str) -> list[str]:
        return ["send", str(self.m20), "--report", str(self.report), "--job", str(JOB), *extra]


def _result(data: bytes, sel: Selection) -> BuildResult:
    text = JOB.read_text(encoding="utf-8")
    from ggdesk.formats import job as jf
    resolved = resolve(load_library(DESKTOP / "library"), jf.loads(text), sel)
    return BuildResult(data, Intent(()), (), resolved, hashlib.sha256(text.encode()).hexdigest(), 0.0, 0)


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home_ok: Any) -> Env:  # noqa: F811
    """A built job whose stored report matches what `ggdesk build` would write."""
    monkeypatch.setenv("GGDESK_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("GGDESK_USER_LIBRARY", str(tmp_path / "no-user-library"))
    monkeypatch.setattr(gate, "RULES", ())            # rules are slice M1.2's; this tests the send path
    data = gts()
    calls: list[tuple[Any, ...]] = []

    def fake_build(job: Any, lib: Any, sel: Selection, *, job_text: str | None = None) -> BuildResult:
        calls.append((job, sel, job_text))
        return _result(data, sel)

    monkeypatch.setattr(builder, "build", fake_build)
    result = _result(data, SEL)
    report_text = gate.run_gate(data, builder.gate_inputs(result, SEL)).to_json()
    conns: list[FakeConn] = []

    def fake_open() -> FakeConn:
        c = FakeConn()
        conns.append(c)
        return c

    monkeypatch.setattr(runmod, "open_connection", fake_open)
    e = Env(tmp_path, data, report_text, conns)
    e.build_calls = calls  # type: ignore[attr-defined]
    return e


def test_send_completed(env: Env, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(env.argv("--operator", "bench")) == 0
    (conn,) = env.conns
    assert conn.sent[1] == env.data and conn.disconnected
    assert "completed (!ET 7)" in capsys.readouterr().out
    events = [r["event"] for r in env.log.records()]
    assert events == ["sent", "completed"]
    assert env.log.records()[-1]["operator"] == "bench"
    (_, sel, job_text), = env.build_calls  # type: ignore[attr-defined]
    assert sel == SEL and job_text == JOB.read_text(encoding="utf-8")   # rebuilt from the report's selection


def test_dry_run_never_connects(env: Env, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(env.argv("--dry-run")) == 0
    assert env.conns == [] and env.log.records() == []
    assert "dry run" in capsys.readouterr().out


def test_dry_run_still_refuses(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "RULES", (_Rule("S9", Severity.SOFT, 2),))
    _rewrite_report(env)
    assert main(env.argv("--dry-run")) == 3
    assert main(env.argv("--dry-run", "--ack", "I ACCEPT 2 FLAGS")) == 0
    assert env.conns == []


def _rewrite_report(env: Env) -> None:
    result = _result(env.data, SEL)
    env.report.write_text(gate.run_gate(env.data, builder.gate_inputs(result, SEL)).to_json(), encoding="utf-8")


def _refused(env: Env, capsys: pytest.CaptureFixture[str], match: str, *extra: str) -> None:
    assert main(env.argv(*extra)) == 3
    assert match in capsys.readouterr().err
    assert all(c.sent == [] for c in env.conns)
    rec = env.log.records()[-1]
    assert rec["event"] == "refused" and match in rec["reason"]


def test_refuse_unbound_file(env: Env, capsys: pytest.CaptureFixture[str]) -> None:
    env.m20.write_bytes(env.data[:-1] + bytes([env.data[-1] ^ 1]))
    _refused(env, capsys, "not bound")
    assert env.conns == []


def test_refuse_failed_report(env: Env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(gate, "RULES", (_Rule("H1", Severity.HARD),))
    _rewrite_report(env)
    _refused(env, capsys, "did not pass")


def test_refuse_rebuild_differs(env: Env, monkeypatch: pytest.MonkeyPatch,
                                capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(builder, "build", lambda job, lib, sel, job_text=None: _result(gts(dx=2000), sel))
    _refused(env, capsys, "different bytes")
    assert env.conns == []


def test_refuse_build_error(env: Env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def broken(*a: Any, **k: Any) -> BuildResult:
        raise builder.BuildError("recipe unknown")

    monkeypatch.setattr(builder, "build", broken)
    _refused(env, capsys, "rebuilding the job failed")


def test_refuse_stale_report(env: Env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # the stored report was made before a rule existed: the fresh gate run differs
    monkeypatch.setattr(gate, "RULES", (_Rule("S9", Severity.SOFT, 1),))
    _refused(env, capsys, "stale or edited", "--ack", "I ACCEPT 1 FLAG")


@pytest.mark.parametrize("edit", ["residual", "passed", "estimate_s"])
def test_refuse_edited_report(edit: str, env: Env, capsys: pytest.CaptureFixture[str]) -> None:
    obj = json.loads(env.report.read_text(encoding="utf-8"))
    obj[edit] = {"residual": [], "passed": False, "estimate_s": 1.0}[edit]
    env.report.write_text(json.dumps(obj), encoding="utf-8")
    _refused(env, capsys, "stale or edited")


def test_refuse_send_disabled(env: Env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import ggdesk.commands.send as send_cmd

    real = send_cmd.load_library

    class Disabled:
        def __init__(self, lib: Any) -> None:
            self.lib = lib

        def get(self, kind: str, eid: str) -> Any:
            v = self.lib.get(kind, eid)
            return dataclasses.replace(v, send_enabled=False) if isinstance(v, Machine) else v

    monkeypatch.setattr(send_cmd, "load_library", lambda *a, **k: Disabled(real(*a, **k)))
    _refused(env, capsys, "send_enabled = false")
    assert env.conns == []


def test_refuse_wrong_ack_at_runner(env: Env, monkeypatch: pytest.MonkeyPatch,
                                    capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(gate, "RULES", (_Rule("S9", Severity.SOFT, 2),))
    _rewrite_report(env)
    _refused(env, capsys, "I ACCEPT 2 FLAGS", "--ack", "I ACCEPT 1 FLAG")
    assert env.conns[0].disconnected


def test_unconfirmed_exit_4(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    def no_et() -> FakeConn:
        c = FakeConn(script=(JF, CM1))
        env.conns.append(c)
        return c

    monkeypatch.setattr(runmod, "open_connection", no_et)
    monkeypatch.setattr(runmod.Runner, "__init__", _fast_settle(runmod.Runner.__init__))
    assert main(env.argv()) == 4
    assert env.log.records()[-1]["event"] == "unconfirmed"


def _fast_settle(init: Any) -> Any:
    def wrapped(self: Any, *a: Any, **k: Any) -> None:
        k["settle_s"] = 0.01
        init(self, *a, **k)
    return wrapped


def test_ctrl_c_aborts_exit_4(env: Env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def interrupted() -> FakeConn:
        c = FakeConn()
        c.raise_in_send = KeyboardInterrupt()
        env.conns.append(c)
        return c

    monkeypatch.setattr(runmod, "open_connection", interrupted)
    assert main(env.argv()) == 4
    assert env.conns[0].aborted == 1
    assert env.log.records()[-1]["event"] == "aborted"
    assert "ABORTED" in capsys.readouterr().out


def test_machine_not_found_exit_1(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    def absent() -> FakeConn:
        c = FakeConn()
        c.dev = None
        env.conns.append(c)
        return c

    monkeypatch.setattr(runmod, "open_connection", absent)
    assert main(env.argv()) == 1
    assert env.conns[0].sent == []


def test_driver_error_exit_1(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing() -> FakeConn:
        c = FakeConn()
        c.raise_in_send = RuntimeError("USB pipe error")
        env.conns.append(c)
        return c

    monkeypatch.setattr(runmod, "open_connection", failing)
    assert main(env.argv()) == 1
    assert env.conns[0].disconnected


def test_unreadable_report_exit_1(env: Env) -> None:
    env.report.write_text("{not json", encoding="utf-8")
    assert main(env.argv()) == 1
    env.report.unlink()
    assert main(env.argv()) == 1
    assert env.conns == []
