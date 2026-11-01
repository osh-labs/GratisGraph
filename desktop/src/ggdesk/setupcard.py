"""Setup card (F13 seed, shown in the bench window from M2): what the operator sets by hand.

One source for the manual-depth line: the gate's residual line, repeated verbatim,
so the card and every gate report always say the same thing.
"""
from __future__ import annotations

from dataclasses import dataclass

from ggdesk.gate.residual import manual_depth_line
from ggdesk.library.select import Resolved


@dataclass(frozen=True)
class SetupCard:
    title: str
    lines: tuple[str, ...]

    def to_text(self) -> str:
        return "\n".join([self.title, *(f"  {line}" for line in self.lines)]) + "\n"


def setup_card(resolved: Resolved) -> SetupCard:
    r, t = resolved.recipe, resolved.tool
    lines = [
        f"Tool: {t.name} ({t.type}){', spindle on (MC 1)' if r.mc.value == 1 else ''}.",
        manual_depth_line(r),
        f"Recipe: {r.ref.id} v{r.ref.version}, {r.mode}, {r.status.upper()}"
        + (" - not validated on the target part." if r.status == "draft" else "."),
        f"Fixture: {resolved.fixture.name}; part: {resolved.part.name}.",
    ]
    if r.mode == "fill":
        tip = "unknown" if resolved.tip_width_mm is None else f"{resolved.tip_width_mm:g} mm"
        step = f"{r.stepover_mm.value:g} mm" if r.stepover_mm.known else "unknown"
        lines.append(f"Fill: tip width {tip}, stepover {step}.")
    for k, v in sorted(r.overrides.items()):
        lines.append(f"Bench override: {k} = {v} (this run only).")
    if t.needs_nose.value:
        lines.append("Fit the regulating nose before the first job.")
    lines.append("Run tool-reversed first on any new job; keep the panel stop within reach.")
    return SetupCard(f"Setup card: {resolved.machine.name}", tuple(lines))
