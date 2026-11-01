"""Gate for the driver's fixed home job (queued by send_gts(home_first=True)).

check_home_job returns an ordinary GateReport so the send path handles both
reports alike. Its `selection` is Selection(machine=<machine id>) with every
other field at its default (no recipe, fixture or job applies), `entries` is
the machine entry alone, `residual` and `estimate_s` are empty, and
`rules_run` is ("HOME",). Every finding is HARD with rule id "HOME".

The home job must be exactly the records DR 0, MC 0, PU 1, JF 0 (the driver's
build_home_gts) with no segments, and its header model code must equal the
machine's (and the connected machine's, when given).
"""
from __future__ import annotations

import hashlib

from ggdesk import __version__, gts_read
from ggdesk.gate.types import Finding, GateReport, Severity
from ggdesk.gts_read import Command
from ggdesk.library.model import Machine
from ggdesk.library.select import Selection

RULE = "HOME"
HOME_RECORDS = (("DR", 0), ("MC", 0), ("PU", 1), ("JF", 0))


def check_home_job(data: bytes, machine: Machine, *, target_model_code: int | None = None) -> GateReport:
    data = bytes(data)
    findings: list[Finding] = []
    model: int | None = None
    try:
        job = gts_read.read_job(data)
    except gts_read.GtsFormatError as e:
        findings.append(Finding(RULE, Severity.HARD, f"home job does not decode: {e}"))
        job = None
    if job is not None:
        model = job.model_code
        segs = [r for r in job.records if not isinstance(r, Command)]
        if segs:
            findings.append(Finding(RULE, Severity.HARD, f"home job has {len(segs)} segment(s); it must have none",
                                    segs[0].offset))
        got = tuple((r.op, r.arg) for r in job.records if isinstance(r, Command))
        if got != HOME_RECORDS:
            findings.append(Finding(RULE, Severity.HARD,
                                    "home job records are [" + " ".join(f"{o} {a}" for o, a in got)
                                    + "]; expected [DR 0 MC 0 PU 1 JF 0]"))
        mc = machine.model_code
        if not mc.known or mc.value is None:
            findings.append(Finding(RULE, Severity.HARD, "machine model code unknown",
                                    gts_read.MODEL_CODE_OFFSET))
        elif job.model_code != mc.value:
            findings.append(Finding(RULE, Severity.HARD,
                                    f"home job model code 0x{job.model_code:04X} is not the machine's "
                                    f"0x{mc.value:04X}", gts_read.MODEL_CODE_OFFSET))
        if target_model_code is not None and job.model_code != target_model_code:
            findings.append(Finding(RULE, Severity.HARD,
                                    f"home job model code 0x{job.model_code:04X} is not the connected machine's "
                                    f"0x{target_model_code:04X}", gts_read.MODEL_CODE_OFFSET))
    return GateReport(
        sha256=hashlib.sha256(data).hexdigest(), size=len(data), app_version=__version__, model_code=model,
        entries=(machine.ref,), selection=Selection(machine=machine.ref.id), job_sha256=None,
        findings=tuple(findings), residual=(), estimate_s=None, rules_run=(RULE,))
