"""Job + library + selection -> final .m20 bytes (M1.1 implements; this is the M1.0 contract).

See desktop/docs/m1-plan.md section 2.5.
"""
from __future__ import annotations

from dataclasses import dataclass

from ggdesk.gate.types import GateConfig, GateInputs
from ggdesk.library.load import Library
from ggdesk.library.select import Resolved, Selection
from ggdesk.model.job import Job
from ggdesk.model.toolpath import Intent, UStroke


class BuildError(ValueError):
    """The job cannot be built with this selection (the message says why)."""


@dataclass(frozen=True)
class BuildResult:
    data: bytes                    # final bytes, machine model code at header 0x24
    intent: Intent
    ordered: tuple[UStroke, ...]
    resolved: Resolved
    job_sha256: str | None
    estimate_s: float
    dropped_points: int


def build(job: Job, lib: Library, sel: Selection, *, job_text: str | None = None) -> BuildResult:
    raise BuildError("build: not implemented in this build (slice M1.1)")


def gate_inputs(result: BuildResult, sel: Selection, config: GateConfig | None = None) -> GateInputs:
    return GateInputs(result.resolved, result.intent, result.job_sha256, sel, config or GateConfig())
