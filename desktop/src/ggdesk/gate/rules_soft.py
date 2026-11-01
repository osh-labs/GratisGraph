"""Soft gate rules S1 to S5 (build plan 9.2) and S6 (values not yet run on the machine).

Each finding is a flag the operator must acknowledge by typing the count (`I ACCEPT 3 FLAGS`).
Rules never modify anything."""
from __future__ import annotations

from ggdesk import gts_read
from ggdesk.gate.types import Finding, GateInputs, Severity


class S1DraftRecipe:
    id = "S1"
    severity = Severity.SOFT
    title = "Recipe status is draft"

    def check(self, data: bytes, job: gts_read.Job, inputs: GateInputs) -> list[Finding]:
        rec = inputs.resolved.recipe
        if rec.status == "draft":
            return [Finding(self.id, self.severity,
                            f"recipe {rec.ref.id} v{rec.ref.version} is draft (not yet validated on the target part)")]
        return []


class S2CharHeight:
    id = "S2"
    severity = Severity.SOFT
    title = "Character height below the recipe's validated minimum"

    def check(self, data: bytes, job: gts_read.Job, inputs: GateInputs) -> list[Finding]:
        rec = inputs.resolved.recipe
        if inputs.intent is None or not rec.min_char_height_mm.known or rec.min_char_height_mm.value is None:
            return []   # unknown minimum: the residual line covers it
        lo = rec.min_char_height_mm.value
        below = [h for h in inputs.intent.char_heights_mm if h < lo]
        if not below:
            return []
        return [Finding(self.id, self.severity,
                        f"{len(below)} operation(s) with character height below the recipe minimum {lo:g} mm "
                        f"(smallest {min(below):g} mm)")]


class S3NarrowRegions:
    id = "S3"
    severity = Severity.SOFT
    title = "Regions narrower than the tip width (left unengraved)"

    def check(self, data: bytes, job: gts_read.Job, inputs: GateInputs) -> list[Finding]:
        if inputs.intent is None:
            return []
        return [Finding(self.id, self.severity,
                        f"operation {n.op_index} region {n.region_index} is {n.width_mm:g} mm wide, narrower than "
                        "the tip: left unengraved")
                for n in inputs.intent.narrow_regions]


class S4FixtureTolerance:
    id = "S4"
    severity = Severity.SOFT
    title = "Fixture datum tolerance not yet measured"

    def check(self, data: bytes, job: gts_read.Job, inputs: GateInputs) -> list[Finding]:
        fx = inputs.resolved.fixture
        if fx.tolerance_mm.known:
            return []
        return [Finding(self.id, self.severity,
                        f"fixture {fx.ref.id} tolerance not measured ({fx.tolerance_mm.gap or 'gap not named'}): "
                        "placement error unknown")]


def estimate_s(job: gts_read.Job) -> float | None:
    """The driver's run-time model (gts_optimise.estimate_duration) on the decoded strokes and VS."""
    import gts_optimise

    strokes = job.strokes()
    vs = next((arg for op, arg in job.setup() if op == "VS"), None)
    if vs is None or not strokes:
        return None
    est = gts_optimise.estimate_duration([s.to_driver() for s in strokes], speed=vs)
    return None if est is None else float(est)


class S5RunTime:
    id = "S5"
    severity = Severity.SOFT
    title = "Estimated run time over the configured limit"

    def check(self, data: bytes, job: gts_read.Job, inputs: GateInputs) -> list[Finding]:
        if not job.strokes():
            return []
        est = estimate_s(job)
        lim = inputs.config.max_run_time_s
        if est is None:
            return [Finding(self.id, self.severity, "run time could not be estimated")]
        if est > lim:
            return [Finding(self.id, self.severity, f"estimated run time about {est:.0f} s is over the {lim:g} s "
                                                    "limit")]
        return []


class S6Unobserved:
    id = "S6"
    severity = Severity.SOFT
    title = "Setup value never observed on this machine"

    def check(self, data: bytes, job: gts_read.Job, inputs: GateInputs) -> list[Finding]:
        """H5 holds the value inside the machine range; this flags values outside what was tried on the IQ."""
        obs = inputs.resolved.machine.observed
        out: list[Finding] = []
        for r in job.records:
            if isinstance(r, gts_read.Segment):
                break
            f = obs.get(r.op.lower())
            if f is not None and f.known and f.value is not None and not f.value.contains(r.arg):
                out.append(Finding(self.id, self.severity,
                                   f"{r.op} {r.arg} has not been run on {inputs.resolved.machine.ref.id} "
                                   f"(observed {f.value.min}..{f.value.max}: {f.ref})", r.offset))
        return out


SOFT_RULES = (S1DraftRecipe(), S2CharHeight(), S3NarrowRegions(), S4FixtureTolerance(), S5RunTime(), S6Unobserved())
