"""Residual status lines: printed on every report, even with zero findings (lesson 4)."""
from __future__ import annotations

from typing import Any

from ggdesk.gate.types import GateInputs
from ggdesk.library.model import Fact


def _v(f: Fact[Any], fmt: str = "{}") -> str:
    return fmt.format(f.value) if f.known else "unknown"


def residual_lines(inputs: GateInputs) -> tuple[str, ...]:
    r = inputs.resolved
    rec = r.recipe
    m = rec.manual
    nose = "unknown" if not m.nose_fitted.known else ("fitted" if m.nose_fitted.value else "not fitted")
    lines = [
        f"Depth is set by hand: nose {nose}, knob {_v(m.knob_notches)} notches, pressure {_v(m.pressure)}. "
        "Software cannot verify these.",
        f"Recipe {rec.ref.id} v{rec.ref.version} is {rec.status}"
        + (" (not yet validated on the target part)." if rec.status == "draft" else "."),
    ]
    for k, v in sorted(rec.overrides.items()):
        lines.append(f"Bench override: {k} = {v} (this run only; not a library value).")
    for label, fact in (("part outline", r.part.outline), ("part keep-out margin", r.part.keep_out_margin_mm),
                        ("fixture datum", r.fixture.datum_mm), ("fixture keep-outs", r.fixture.keep_outs),
                        ("fixture tolerance", r.fixture.tolerance_mm),
                        ("minimum character height", rec.min_char_height_mm),
                        ("tool tip width", r.tool.tip_width_mm)):
        if fact.needs_measurement:
            lines.append(f"Not measured: {label} ({fact.gap or 'gap not named'}).")
    if not r.machine.max_job_bytes.known:
        lines.append(f"Job size limit not measured ({r.machine.max_job_bytes.gap or 'G9'}): H11 inactive.")
    if r.machine.work_field_mm.known and r.machine.work_field_mm.confidence != "CONFIRMED":
        w, h = r.machine.work_field_mm.value or (0.0, 0.0)
        lines.append(f"Work field {w:g} x {h:g} mm is [{r.machine.work_field_mm.confidence}] "
                     f"({r.machine.work_field_mm.ref}), not measured on this machine.")
    lines.append("PZ units are [HYPOTHESIS] (likely 0.01 mm overtravel with the nose; G4).")
    if r.machine.model_code.known and inputs.target_model_code is None:
        lines.append(f"Model code checked against the library (0x{r.machine.model_code.value:04X}); "
                     "the connected machine is checked again at send.")
    return tuple(lines)
