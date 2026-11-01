"""M1.3: the gated send path (ggdesk.run.Runner) and the job log, with a fake connection.

No machine is attached to CI: every test here uses FakeConn, which never touches USB. Its
packets go through the real driver parser (gts_api.GTSConnection._parse_rx_buf), so the taps
see exactly the dict shapes the driver emits for !JF, !CM and !ET.
"""
from __future__ import annotations

import dataclasses
import json
import re
import struct
import sys
import threading
import types
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import gts_api
import pytest

from ggdesk import joblog, paths
from ggdesk import run as runmod
from ggdesk.formats import job as jf
from ggdesk.gate import Finding, GateInputs, GateReport, Severity, run_gate
from ggdesk.joblog import JobLog
from ggdesk.library import Selection, load_library, resolve
from ggdesk.library.model import Machine
from ggdesk.run import Runner, SendRefused
from tests.conftest import DESKTOP

IQ = 0x020D            # m20-iq model_code in the seed library
SEL = Selection(recipe="scrap-rotary-diamond-trace")


# ---------------------------------------------------------------- fakes and helpers

def ack(cmd: str, payload: bytes = b"") -> bytes:
    """Raw RX bytes of a counted reply, e.g. ack('CM', struct.pack('>i', 1)) -> b'!CM 4;...'."""
    return f"!{cmd} {len(payload)};".encode("ascii") + payload


JF = ack("JF")
CM1 = ack("CM", struct.pack(">i", 1))
CM_PANEL = ack("CM", struct.pack(">i", -1))


def ET(n: int) -> bytes:  # noqa: N802 - mirrors the wire mnemonic
    return ack("ET", struct.pack(">I", n))


class FakeConn:
    """Stands in for gts_api.GTSConnection. Records what would be written; never touches USB.

    send_gts mirrors the driver: stamp and queue the home job, stamp and queue the job, then
    play `script` (raw RX chunks) through the driver's own parser while 'monitoring'.
    """

    def __init__(self, model_code: int = IQ, script: tuple[bytes, ...] = (JF, CM1, ET(7))) -> None:
        self.model_code = model_code
        self.dev: object | None = object()   # truthy = connected
        self.script = script
        self.sent: list[bytes] = []
        self.home_first: list[bool] = []
        self.aborted = 0
        self.connected_calls = 0
        self.disconnected = False
        self.block: threading.Event | None = None     # send_gts waits on it (abort tests)
        self.entered = threading.Event()
        self.raise_in_send: BaseException | None = None
        self._parser = gts_api.GTSConnection(verbose=False)   # parser only; no connect(), no USB

    def connect(self, timeout_s: float = 5.0, wait: bool = False) -> bool:
        self.connected_calls += 1
        return self.dev is not None

    def add_tap(self, fn: Callable[[Any], None]) -> None:
        self._parser.add_tap(fn)

    def feed(self, raw: bytes) -> None:
        self._parser._rx_buf += raw
        self._parser._parse_rx_buf()

    def _stamp(self, gts: bytes) -> bytes:
        return gts_api.GTSConnection._stamp_model_code(self, gts)   # the driver's own stamp

    def send_gts(self, gts: bytes, home_first: bool = True) -> None:
        self.home_first.append(home_first)
        if home_first:
            self.sent.append(self._stamp(gts_api.build_home_gts()))
        self.sent.append(self._stamp(gts))
        self.entered.set()
        if self.raise_in_send is not None:
            raise self.raise_in_send
        for raw in self.script:
            self.feed(raw)
        if self.block is not None:
            assert self.block.wait(5.0), "test did not release send_gts"

    def abort(self) -> None:
        self.aborted += 1
        if self.block is not None:
            self.block.set()

    def disconnect(self) -> None:
        self.disconnected = True
        self.dev = None


def gts(model_code: int = IQ, dx: int = 1000) -> bytes:
    data = gts_api.build_gts([(4500, 4500, [(dx, 0)])], speed=10, pz=50, mc=1, vz=5)
    return runmod.stamp_model_code(data, model_code)


class _Rule:
    def __init__(self, rid: str, sev: Severity, n: int = 1) -> None:
        self.id, self.severity, self.title, self.n = rid, sev, "test rule", n

    def check(self, data: bytes, job: object, inputs: object) -> list[Finding]:
        return [Finding(self.id, self.severity, f"finding {i}") for i in range(self.n)]


@pytest.fixture(scope="module")
def library() -> Any:
    return load_library(DESKTOP / "library")


@pytest.fixture(scope="module")
def inputs(library: Any) -> GateInputs:
    job = jf.load(DESKTOP / "docs" / "examples" / "square-10mm.ggj")
    return GateInputs(resolve(library, job, SEL), None, None, SEL)


@pytest.fixture(scope="module")
def machine(library: Any) -> Machine:
    m: Machine = library.get("machine", "m20-iq")
    return m


def report_for(data: bytes, inputs: GateInputs, *rules: _Rule) -> GateReport:
    return run_gate(data, inputs, rules=tuple(rules))


def home_report(passed: bool = True) -> GateReport:
    findings = () if passed else (Finding("HOME", Severity.HARD, "home job is not the fixed home job"),)
    return GateReport("0" * 64, 0, "test", IQ, (), SEL, None, findings, (), None, ("HOME",))


@pytest.fixture()
def home_ok(monkeypatch: pytest.MonkeyPatch) -> list[tuple[bytes, Machine]]:
    """Stand-in for ggdesk.gate.home (slice M1.2): records its calls, passes."""
    calls: list[tuple[bytes, Machine]] = []

    def check_home_job(data: bytes, machine: Machine) -> GateReport:
        calls.append((data, machine))
        return home_report(True)

    mod = types.ModuleType("ggdesk.gate.home")
    mod.check_home_job = check_home_job  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ggdesk.gate.home", mod)
    return calls


@pytest.fixture()
def log(tmp_path: Path) -> JobLog:
    return JobLog(tmp_path / "logs" / "jobs.jsonl")


class Clock:
    def __init__(self) -> None:
        self.n = 0

    def __call__(self) -> str:
        self.n += 1
        return f"2026-11-01T00:00:{self.n:02d}.000+00:00"


def runner(conn: FakeConn, log: JobLog, machine: Machine, clock: Callable[[], str] | None = None) -> Runner:
    return Runner(conn, log, clock or Clock(), machine=machine, settle_s=0.01)


# ---------------------------------------------------------------- success and completion

def test_success_completed(inputs: GateInputs, machine: Machine, log: JobLog,
                           home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    rep = report_for(data, inputs)
    conn = FakeConn()
    res = runner(conn, log, machine).send_gated(data, rep)
    assert res.status == "completed" and res.et == 7
    assert conn.home_first == [True]
    home, job = conn.sent
    assert job == data                               # the driver's re-stamp is a no-op: gated bytes are sent
    assert home == runmod.home_job_bytes(IQ)         # the home job checked is the home job queued
    assert home_ok == [(home, machine)]
    events = [r["event"] for r in log.records()]
    assert events == ["sent", "completed"]


def test_send_with_acknowledged_flags(inputs: GateInputs, machine: Machine, log: JobLog,
                                      home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    rep = report_for(data, inputs, _Rule("S9", Severity.SOFT, 3))
    conn = FakeConn()
    assert runner(conn, log, machine).send_gated(data, rep, "  I ACCEPT 3 FLAGS ").status == "completed"
    assert log.records()[0]["ack_given"] is True


def test_et_without_cm1_is_unconfirmed(inputs: GateInputs, machine: Machine, log: JobLog,
                                       home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    conn = FakeConn(script=(JF, CM_PANEL, ET(4)))
    res = runner(conn, log, machine).send_gated(data, report_for(data, inputs))
    assert res.status == "unconfirmed" and res.et is None
    assert log.records()[-1]["cm"] == [-1]


def test_no_et_is_unconfirmed(inputs: GateInputs, machine: Machine, log: JobLog,
                              home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    conn = FakeConn(script=(JF, CM1))
    res = runner(conn, log, machine).send_gated(data, report_for(data, inputs))
    assert res.status == "unconfirmed" and res.et is None
    assert log.records()[-1]["event"] == "unconfirmed"


def test_driver_error_logged_and_raised(inputs: GateInputs, machine: Machine, log: JobLog,
                                        home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    conn = FakeConn()
    conn.raise_in_send = RuntimeError("USB write timed out")
    r = runner(conn, log, machine)
    with pytest.raises(RuntimeError, match="timed out"):
        r.send_gated(data, report_for(data, inputs))
    last = log.records()[-1]
    assert last["event"] == "unconfirmed" and "USB write timed out" in last["error"]
    assert not r.in_flight                            # the queue is free again


# ---------------------------------------------------------------- refusals, one reason each

def _assert_refused(conn: FakeConn, log: JobLog, match: str, exc: pytest.ExceptionInfo[SendRefused]) -> None:
    assert re.search(match, str(exc.value)), str(exc.value)
    assert conn.sent == []                            # nothing reached the "machine"
    rec = log.records()[-1]
    assert rec["event"] == "refused" and rec["reason"] == str(exc.value)


def test_refuse_unbound_bytes(inputs: GateInputs, machine: Machine, log: JobLog,
                              home_ok: list[tuple[bytes, Machine]]) -> None:
    rep = report_for(gts(), inputs)
    conn = FakeConn()
    with pytest.raises(SendRefused) as e:
        runner(conn, log, machine).send_gated(gts(dx=2000), rep)
    _assert_refused(conn, log, "not bound", e)


def test_refuse_one_byte_changed(inputs: GateInputs, machine: Machine, log: JobLog,
                                 home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    rep = report_for(data, inputs)
    changed = bytearray(data)
    changed[-3] ^= 0x01
    conn = FakeConn()
    with pytest.raises(SendRefused) as e:
        runner(conn, log, machine).send_gated(bytes(changed), rep)
    _assert_refused(conn, log, "not bound", e)


def test_refuse_failed_report(inputs: GateInputs, machine: Machine, log: JobLog,
                              home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    rep = report_for(data, inputs, _Rule("H1", Severity.HARD))
    conn = FakeConn()
    with pytest.raises(SendRefused) as e:
        runner(conn, log, machine).send_gated(data, rep)
    _assert_refused(conn, log, "gate refused.*H1", e)


@pytest.mark.parametrize("typed", ["", "I ACCEPT 2 FLAGS", "i accept 3 flags", "I ACCEPT 3 FLAG"])
def test_refuse_missing_or_wrong_ack(typed: str, inputs: GateInputs, machine: Machine, log: JobLog,
                                     home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    rep = report_for(data, inputs, _Rule("S9", Severity.SOFT, 3))
    conn = FakeConn()
    with pytest.raises(SendRefused) as e:
        runner(conn, log, machine).send_gated(data, rep, typed)
    _assert_refused(conn, log, "I ACCEPT 3 FLAGS", e)
    assert log.records()[-1]["ack_given"] is bool(typed)
    assert "ack" not in log.records()[-1]             # the typed text is never logged, only ack_given


def test_refuse_connected_model_code_mismatch(inputs: GateInputs, machine: Machine, log: JobLog,
                                              home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    conn = FakeConn(model_code=0x0204)               # an Express on the cable, job gated for the IQ
    with pytest.raises(SendRefused) as e:
        runner(conn, log, machine).send_gated(data, report_for(data, inputs))
    _assert_refused(conn, log, "model code mismatch.*0x020D.*0x0204", e)


def test_refuse_header_model_code_not_library(inputs: GateInputs, machine: Machine, log: JobLog,
                                              home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts(model_code=0x0204)                    # builder default header, never stamped for the IQ
    conn = FakeConn()
    with pytest.raises(SendRefused) as e:
        runner(conn, log, machine).send_gated(data, report_for(data, inputs))
    _assert_refused(conn, log, "model code mismatch", e)


def test_refuse_report_model_code_differs(inputs: GateInputs, machine: Machine, log: JobLog,
                                          home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    rep = dataclasses.replace(report_for(data, inputs), model_code=0x0204)
    conn = FakeConn()
    with pytest.raises(SendRefused) as e:
        runner(conn, log, machine).send_gated(data, rep)
    _assert_refused(conn, log, "model code mismatch.*report 0x0204", e)


def test_refuse_not_connected(inputs: GateInputs, machine: Machine, log: JobLog,
                              home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    conn = FakeConn()
    conn.dev = None
    with pytest.raises(SendRefused) as e:
        runner(conn, log, machine).send_gated(data, report_for(data, inputs))
    _assert_refused(conn, log, "not connected", e)


def test_refuse_not_identified(inputs: GateInputs, machine: Machine, log: JobLog,
                               home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    conn = FakeConn(model_code=0)                    # connected, but no !ID reply yet
    with pytest.raises(SendRefused) as e:
        runner(conn, log, machine).send_gated(data, report_for(data, inputs))
    _assert_refused(conn, log, "not identified", e)


def test_refuse_home_check_failing(inputs: GateInputs, machine: Machine, log: JobLog,
                                   monkeypatch: pytest.MonkeyPatch) -> None:
    mod = types.ModuleType("ggdesk.gate.home")
    mod.check_home_job = lambda data, m: home_report(False)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ggdesk.gate.home", mod)
    data = gts()
    conn = FakeConn()
    with pytest.raises(SendRefused) as e:
        runner(conn, log, machine).send_gated(data, report_for(data, inputs))
    _assert_refused(conn, log, "home job failed.*HOME", e)


def test_refuse_home_check_absent(inputs: GateInputs, machine: Machine, log: JobLog,
                                  monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "ggdesk.gate.home", None)   # import raises ImportError
    data = gts()
    conn = FakeConn()
    with pytest.raises(SendRefused) as e:
        runner(conn, log, machine).send_gated(data, report_for(data, inputs))
    _assert_refused(conn, log, "home-job check .* not available", e)


def test_refuse_send_disabled_machine(inputs: GateInputs, machine: Machine, log: JobLog,
                                      home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    conn = FakeConn()
    with pytest.raises(SendRefused) as e:
        runner(conn, log, dataclasses.replace(machine, send_enabled=False)).send_gated(data, report_for(data, inputs))
    _assert_refused(conn, log, "send_enabled = false", e)


def test_refuse_without_machine_entry(inputs: GateInputs, log: JobLog,
                                      home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    conn = FakeConn()
    with pytest.raises(SendRefused) as e:
        Runner(conn, log, Clock()).send_gated(data, report_for(data, inputs))
    _assert_refused(conn, log, "no machine library entry", e)


def test_refuse_second_send_while_in_flight(inputs: GateInputs, machine: Machine, log: JobLog,
                                            home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    rep = report_for(data, inputs)
    conn = FakeConn()
    conn.block = threading.Event()
    r = runner(conn, log, machine)
    results: list[runmod.RunResult] = []
    t = threading.Thread(target=lambda: results.append(r.send_gated(data, rep)))
    t.start()
    assert conn.entered.wait(5.0)
    assert r.in_flight
    with pytest.raises(SendRefused, match="already in flight"):
        r.send_gated(data, rep)
    assert len(conn.sent) == 2                        # only the first job's home + job
    conn.block.set()
    t.join(5.0)
    assert results[0].status == "completed"
    assert [x["event"] for x in log.records()] == ["sent", "refused", "completed"]


# ---------------------------------------------------------------- abort

def test_abort_during_run(inputs: GateInputs, machine: Machine, log: JobLog,
                          home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    conn = FakeConn(script=(JF, CM1))
    conn.block = threading.Event()
    r = runner(conn, log, machine)
    results: list[runmod.RunResult] = []
    t = threading.Thread(target=lambda: results.append(r.send_gated(data, report_for(data, inputs))))
    t.start()
    assert conn.entered.wait(5.0)
    r.abort()                                         # the GUI's abort button, from another thread
    t.join(5.0)
    assert conn.aborted == 1
    assert results[0].status == "aborted"
    assert log.records()[-1]["event"] == "aborted"


def test_ctrl_c_during_run_aborts(inputs: GateInputs, machine: Machine, log: JobLog,
                                  home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    conn = FakeConn()
    conn.raise_in_send = KeyboardInterrupt()
    res = runner(conn, log, machine).send_gated(data, report_for(data, inputs))
    assert res.status == "aborted" and conn.aborted == 1
    assert log.records()[-1]["event"] == "aborted"


def test_abort_wins_over_late_et(inputs: GateInputs, machine: Machine, log: JobLog,
                                 home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    conn = FakeConn(script=(JF, CM1))
    conn.block = threading.Event()
    r = runner(conn, log, machine)
    results: list[runmod.RunResult] = []
    t = threading.Thread(target=lambda: results.append(r.send_gated(data, report_for(data, inputs))))
    t.start()
    assert conn.entered.wait(5.0)
    r.abort()
    conn.feed(ET(4))
    t.join(5.0)
    assert results[0].status == "aborted"


# ---------------------------------------------------------------- log contents and clock

def test_log_record_contents(inputs: GateInputs, machine: Machine, log: JobLog,
                             home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    rep = report_for(data, inputs, _Rule("S9", Severity.SOFT, 1))
    runner(FakeConn(), log, machine).send_gated(data, rep, "I ACCEPT 1 FLAG", operator="Zoë")
    sent, done = log.records()
    assert done["event"] == "completed" and done["et"] == 7
    assert done["sha256"] == rep.sha256 and done["size"] == len(data)
    assert done["model_code"] == IQ and done["connected_model_code"] == IQ
    assert done["ack_given"] is True and done["operator"] == "Zoë"
    assert done["cm"] == [1] and done["jf"] == 1
    summary = done["report"]
    assert summary["passed"] is True and summary["flags"] == 1 and summary["findings"] == ["S9"]
    assert summary["selection"] == SEL.to_obj()
    assert {(e["kind"], e["id"], e["version"]) for e in summary["entries"]} >= {("machine", "m20-iq", 1)}
    assert sent["event"] == "sent" and sent["ended"] is None
    assert "I ACCEPT" not in log.path.read_text(encoding="utf-8")


def test_log_lines_sorted_utf8(inputs: GateInputs, machine: Machine, log: JobLog,
                               home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    runner(FakeConn(), log, machine).send_gated(data, report_for(data, inputs), operator="Zoë")
    raw = log.path.read_bytes()
    assert "Zoë".encode() in raw
    lines = raw.decode("utf-8").splitlines()
    assert len(lines) == 2 and raw.endswith(b"\n")
    for line in lines:
        obj = json.loads(line)
        assert list(obj) == sorted(obj)


def test_injected_clock(inputs: GateInputs, machine: Machine, log: JobLog,
                        home_ok: list[tuple[bytes, Machine]]) -> None:
    data = gts()
    clock = Clock()
    res = runner(FakeConn(), log, machine, clock).send_gated(data, report_for(data, inputs))
    assert res.started == "2026-11-01T00:00:01.000+00:00"
    assert res.ended == "2026-11-01T00:00:02.000+00:00"
    done = log.records()[-1]
    assert (done["started"], done["ended"]) == (res.started, res.ended)
    with pytest.raises(SendRefused):
        runner(FakeConn(), log, machine, clock).send_gated(b"x", report_for(data, inputs))
    refused = log.records()[-1]
    assert refused["started"] == refused["ended"] == "2026-11-01T00:00:03.000+00:00"


def test_default_clock_is_utc_iso() -> None:
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}\+00:00", runmod.utc_now_iso())


def test_log_dir_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GGDESK_LOG_DIR", str(tmp_path / "x"))
    lg = JobLog()
    assert lg.path == tmp_path / "x" / "jobs.jsonl"
    lg.append({"b": 1, "a": "é"})
    assert lg.path.read_text(encoding="utf-8") == '{"a": "é", "b": 1}\n'


def test_log_default_location(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GGDESK_LOG_DIR", raising=False)
    assert joblog.default_path() == paths.user_data_dir() / "logs" / "jobs.jsonl"
    name = "gratisgraph-desktop" if sys.platform.startswith("linux") else "GratisGraph Desktop"
    assert name in str(paths.user_data_dir())


# ---------------------------------------------------------------- driver equivalence and source guard

def test_stamp_matches_driver() -> None:
    class Ident:
        model_code = IQ

    home = gts_api.build_home_gts()
    assert runmod.stamp_model_code(home, IQ) == gts_api.GTSConnection._stamp_model_code(Ident(), home)
    assert runmod.header_model_code(runmod.home_job_bytes(IQ)) == IQ
    assert runmod.header_model_code(b"not a job") is None


def test_tap_shapes_from_driver_parser() -> None:
    seen: list[Any] = []
    conn = FakeConn()
    conn.add_tap(seen.append)
    for raw in (JF, CM1, ET(7)):
        conn.feed(raw)
    jf_, cm, et = seen
    assert jf_["type"] == "ack" and jf_["cmd"] == "!JF 0;" and jf_["value"] is None
    assert cm["cmd"] == "!CM 4;" and cm["values"] == (1,)
    assert et["cmd"] == "!ET 4;" and et["value"] == 7


def _py_files() -> Iterator[Path]:
    for pkg in ("ggdesk", "ggdesk_app"):
        yield from sorted((DESKTOP / "src" / pkg).rglob("*.py"))


def test_only_run_py_calls_the_driver_send() -> None:
    """Non-negotiable 1: only the gated send path may call the driver's send."""
    pattern = re.compile(r"\.(send_gts|send_raw|send_job)\(")
    allowed = DESKTOP / "src" / "ggdesk" / "run.py"
    offenders = [str(p.relative_to(DESKTOP)) for p in _py_files()
                 if p != allowed and pattern.search(p.read_text(encoding="utf-8"))]
    assert offenders == []
    assert list(_py_files()), "source tree not found"
    assert ".send_gts(data, home_first=True)" in allowed.read_text(encoding="utf-8")
    assert ".send_raw(" not in allowed.read_text(encoding="utf-8")
