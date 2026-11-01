"""Fill operation (F09): hatch, optional contour pass, inward offset of half the tip width.

Contract (desktop/docs/m2-plan.md section 2.1). M2.0 ships the types and a stub;
slice M2.1 implements it with Shapely (mitre joins only, so offsets need no trig).
Regions narrower than the tool are reported as NarrowRegion, never dropped silently.
"""
from __future__ import annotations

from dataclasses import dataclass

from ggdesk.model.geometry import Polyline
from ggdesk.model.job import FillOp
from ggdesk.model.toolpath import NarrowRegion


@dataclass(frozen=True)
class FillParams:
    tip_width_mm: float        # the tool centre stays tip_width_mm / 2 inside each region
    stepover_mm: float         # hatch line spacing
    hatch_angle_deg: float     # hatch direction, part frame, counter-clockwise from +X
    contour_pass: bool         # also trace the offset boundary (before the hatch)


@dataclass(frozen=True)
class FillResult:
    paths: tuple[Polyline, ...]          # part frame mm; contour paths closed, hatch paths open
    narrow: tuple[NarrowRegion, ...]     # S3 input


def fill(op: FillOp, op_index: int, params: FillParams) -> FillResult:
    raise NotImplementedError("fill: not implemented in this build (slice M2.1)")
