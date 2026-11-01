"""The output gate: an independent check of the final .m20 bytes (build plan section 9).

It decodes with ggdesk.gts_read (never the builder's state), runs every rule,
and returns a report bound to the bytes' SHA-256. It refuses; it never repairs.
"""
from __future__ import annotations

import hashlib

from ggdesk import __version__, gts_read
from ggdesk.gate.residual import residual_lines
from ggdesk.gate.types import (
    Finding,
    GateConfig,
    GateInputs,
    GateReport,
    Rule,
    Severity,
    ack_phrase,
    acknowledged,
)

# M1.2 fills this tuple, in rule-id order. Nothing else in the gate changes when a rule is added.
RULES: tuple[Rule, ...] = ()


def run_gate(data: bytes, inputs: GateInputs, rules: tuple[Rule, ...] | None = None) -> GateReport:
    data = bytes(data)
    active = RULES if rules is None else rules
    findings: list[Finding] = []
    model_code: int | None = None
    estimate: float | None = None
    try:
        job = gts_read.read_job(data)
    except gts_read.GtsFormatError as e:
        findings.append(Finding("DECODE", Severity.HARD, f"bytes do not decode as a GTS job: {e}"))
        job = None
    if job is not None:
        model_code = job.model_code
        for rule in active:
            findings.extend(rule.check(data, job, inputs))
        estimate = _estimate(job, inputs)
    return GateReport(
        sha256=hashlib.sha256(data).hexdigest(), size=len(data), app_version=__version__,
        model_code=model_code, entries=inputs.resolved.entries, selection=inputs.selection,
        job_sha256=inputs.job_sha256, findings=tuple(findings),
        residual=residual_lines(inputs), estimate_s=estimate, rules_run=tuple(r.id for r in active))


def _estimate(job: gts_read.Job, inputs: GateInputs) -> float | None:
    """Run-time estimate (F20) from the decoded strokes, with the driver's motion model."""
    import gts_optimise

    strokes = job.strokes()
    vs = next((arg for op, arg in job.setup() if op == "VS"), None)
    if vs is None or not strokes:
        return None
    est = gts_optimise.estimate_duration([s.to_driver() for s in strokes], speed=vs)
    return None if est is None else float(est)


__all__ = ["RULES", "Finding", "GateConfig", "GateInputs", "GateReport", "Rule", "Severity", "ack_phrase",
           "acknowledged", "run_gate"]
