"""gate.home.check_home_job: the driver's home job, stamped for the IQ, passes; mutants refuse."""
from __future__ import annotations

from dataclasses import replace

import gts_api
import pytest

from ggdesk.gate.home import check_home_job
from ggdesk.gate.types import GateReport
from ggdesk.library.model import Fact
from tests.unit.test_gate_support import IQ, LIB, cmd, seg, stamp

M = LIB.machines["m20-iq"]
HOME = stamp(gts_api.build_home_gts(), IQ)
BODY = 94


def test_driver_home_job_passes() -> None:
    rep = check_home_job(HOME, M)
    assert rep.passed and rep.findings == () and rep.flags == 0
    assert rep.model_code == IQ and rep.bound_to(HOME)
    assert rep.rules_run == ("HOME",) and rep.entries == (M.ref,) and rep.selection.machine == "m20-iq"
    assert GateReport.from_json(rep.to_json()) == rep
    assert check_home_job(HOME, M, target_model_code=IQ).passed


def test_unstamped_driver_home_job_refused() -> None:
    rep = check_home_job(gts_api.build_home_gts(), M)   # 0x0204 as built
    assert not rep.passed and "0x0204" in rep.findings[0].message


def test_connected_machine_differs() -> None:
    assert not check_home_job(HOME, M, target_model_code=0x0204).passed


@pytest.mark.parametrize("data", [
    HOME + cmd("JF"),                                                    # two JF
    HOME[:BODY] + cmd("DR") + cmd("MC") + cmd("PU", 1),                  # no JF
    HOME[:BODY] + cmd("DR") + cmd("MC", 1) + cmd("PU", 1) + cmd("JF"),   # spindle on
    HOME[:BODY] + cmd("DR") + cmd("MC") + cmd("PU", 0) + cmd("JF"),      # PU 0
    HOME[:BODY] + cmd("DR") + cmd("MC") + cmd("PU", 1) + seg(100, 0) + cmd("JF"),   # motion
    HOME[:BODY] + cmd("DR") + cmd("MC") + cmd("PU", 1) + cmd("PD") + cmd("JF"),     # extra opcode
    HOME[:BODY] + cmd("DR") + cmd("MC") + cmd("JF") + cmd("PU", 1),      # JF not last
    HOME[:-2],                                                           # truncated
    b"not a job",
])
def test_home_mutants_refused(data: bytes) -> None:
    rep = check_home_job(data, M)
    assert not rep.passed
    assert all(f.rule == "HOME" for f in rep.findings)


def test_unknown_machine_model_code_refused() -> None:
    m = replace(M, model_code=Fact(None, needs_measurement=True, gap="G?", measure=("x",)))
    assert not check_home_job(HOME, m).passed
