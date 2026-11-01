"""M1.0 gate contract: report binding, acknowledgement, residual lines, decode refusal."""
from __future__ import annotations

import gts_api
import pytest

from ggdesk.formats import job as jf
from ggdesk.gate import GateInputs, GateReport, Severity, ack_phrase, acknowledged, run_gate
from ggdesk.gate.types import Finding
from ggdesk.library import Selection, load_library, resolve
from tests.conftest import DESKTOP

SEL = Selection(recipe="scrap-rotary-diamond-trace")


@pytest.fixture(scope="module")
def inputs() -> GateInputs:
    lib = load_library(DESKTOP / "library")
    job = jf.load(DESKTOP / "docs" / "examples" / "square-10mm.ggj")
    return GateInputs(resolve(lib, job, SEL), None, None, SEL)


def _data() -> bytes:
    return gts_api.build_gts([(4500, 4500, [(1000, 0)])], speed=10, pz=50, mc=1, vz=5)


def test_ack_phrase() -> None:
    assert ack_phrase(0) == ""
    assert ack_phrase(1) == "I ACCEPT 1 FLAG"
    assert ack_phrase(3) == "I ACCEPT 3 FLAGS"


def test_report_binding_and_round_trip(inputs: GateInputs) -> None:
    data = _data()
    rep = run_gate(data, inputs, rules=())
    assert rep.bound_to(data)
    assert not rep.bound_to(data[:-1] + b"\x01")
    assert GateReport.from_json(rep.to_json()) == rep
    assert rep.to_json() == run_gate(data, inputs, rules=()).to_json()   # no timestamp: deterministic


def test_residual_always_present(inputs: GateInputs) -> None:
    rep = run_gate(_data(), inputs, rules=())
    assert rep.findings == ()
    assert rep.residual[0] == ("Depth is set by hand: nose fitted, knob 5 notches, pressure 2. "
                               "Software cannot verify these.")
    assert any("H11 inactive" in r for r in rep.residual)
    assert any("draft" in r for r in rep.residual)
    assert "Residual status" in rep.to_text()


def test_decode_failure_is_hard(inputs: GateInputs) -> None:
    rep = run_gate(b"not a job", inputs, rules=())
    assert not rep.passed and rep.findings[0].rule == "DECODE"


def test_acknowledgement(inputs: GateInputs) -> None:
    class TwoFlags:
        id, severity, title = "S9", Severity.SOFT, "test"

        def check(self, data: bytes, job: object, inputs: object) -> list[Finding]:
            return [Finding("S9", Severity.SOFT, "a"), Finding("S9", Severity.SOFT, "b")]

    rep = run_gate(_data(), inputs, rules=(TwoFlags(),))
    assert rep.passed and rep.flags == 2
    assert not acknowledged(rep, "")
    assert not acknowledged(rep, "I ACCEPT 3 FLAGS")
    assert not acknowledged(rep, "i accept 2 flags")
    assert acknowledged(rep, "I ACCEPT 2 FLAGS")


def test_estimate_present(inputs: GateInputs) -> None:
    rep = run_gate(_data(), inputs, rules=())
    assert rep.estimate_s is not None and rep.estimate_s > 0
