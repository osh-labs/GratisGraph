"""M1 end to end with the real build, the real gate rules, the real home-job check and a FakeConn.

job (.ggj) -> ggdesk build -> .m20 + gate report -> ggdesk check -> ggdesk send (fake USB).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ggdesk import gate
from ggdesk import run as runmod
from ggdesk.cli import main
from ggdesk.gate import GateReport
from ggdesk.joblog import JobLog
from tests.conftest import DESKTOP
from tests.unit.test_run import CM1, ET, JF, FakeConn

JOB = DESKTOP / "docs" / "examples" / "asymmetric-f-arrow.ggj"
SEL = ["--recipe", "scrap-rotary-diamond-trace", "--fixture", "bare-bed"]


@pytest.fixture()
def built(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, list[FakeConn]]:
    monkeypatch.setenv("GGDESK_LOG_DIR", str(tmp_path / "logs"))
    out = tmp_path / "v1.m20"
    assert main(["build", str(JOB), "-o", str(out), *SEL]) == 0
    conns: list[FakeConn] = []

    def fake_open() -> FakeConn:
        # !MZ 4; telemetry as the IQ sends it, then the run's !CM 1 and !ET.
        mz = b"!MZ 4;" + (2366).to_bytes(4, "big")
        c = FakeConn(script=(JF, mz, CM1, ET(24)))
        conns.append(c)
        return c

    monkeypatch.setattr(runmod, "open_connection", fake_open)
    return out, out.with_suffix(".gate.json"), conns


def test_rules_are_live() -> None:
    ids = [r.id for r in gate.RULES]
    assert ids == [f"H{i}" for i in range(1, 12)] + [f"S{i}" for i in range(1, 6)]


def test_build_check_send(built: tuple[Path, Path, list[FakeConn]], tmp_path: Path) -> None:
    m20, rep_path, conns = built
    rep = GateReport.from_json(rep_path.read_text(encoding="utf-8"))
    assert rep.passed and {f.rule for f in rep.findings} == {"S1", "S4"}   # draft recipe; bare-bed tolerance
    assert rep.ack_phrase == "I ACCEPT 2 FLAGS"
    assert main(["check", str(JOB), str(m20), *SEL]) == 0
    # Without the acknowledgement the send is refused before any byte is written.
    assert main(["send", str(m20), "--report", str(rep_path), "--job", str(JOB)]) == 3
    assert conns == [] or conns[-1].sent == []
    cap = tmp_path / "capture.jsonl"
    assert main(["send", str(m20), "--report", str(rep_path), "--job", str(JOB), "--ack", "I ACCEPT 2 FLAGS",
                 "--capture", str(cap)]) == 0
    conn = conns[-1]
    assert conn.sent[1] == m20.read_bytes()            # the gated bytes, byte for byte
    lines = [json.loads(x) for x in cap.read_text(encoding="utf-8").splitlines()]
    assert any(str(rec["item"].get("cmd", "")).startswith("!MZ") or rec["item"].get("axis") == "Z"
               for rec in lines if isinstance(rec["item"], dict))
    events = [r["event"] for r in JobLog().records()]
    assert events[-2:] == ["sent", "completed"]


def test_edited_bytes_refused(built: tuple[Path, Path, list[FakeConn]]) -> None:
    m20, rep_path, conns = built
    b = bytearray(m20.read_bytes())
    b[-20] ^= 1
    m20.write_bytes(bytes(b))
    assert main(["send", str(m20), "--report", str(rep_path), "--job", str(JOB), "--ack", "I ACCEPT 2 FLAGS"]) == 3
    assert all(c.sent == [] for c in conns)


def test_gui_session_sends_through_the_real_runner(built: tuple[Path, Path, list[FakeConn]],
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    """The bench session's default runner factory passes the machine entry (home-job check needs it)."""
    from ggdesk.library import Selection
    from ggdesk_app.session import BenchSession

    m20, _rep, conns = built
    s = BenchSession()
    s.open_job(JOB)
    s.select(Selection(recipe="scrap-rotary-diamond-trace"))
    s.build_and_gate()
    assert s.state.data == m20.read_bytes()
    res: Any = s.send("I ACCEPT 2 FLAGS", operator="bench")
    assert res.status == "completed" and res.et == 24
    assert conns[-1].sent[1] == m20.read_bytes()
    assert JobLog().records()[-1]["operator"] == "bench"
