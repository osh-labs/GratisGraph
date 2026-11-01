"""F05 fixture transform: part-frame polylines (mm) -> machine strokes (device units).

Each point goes through Placement.to_machine in mm, then exactly one
numerics.to_units per coordinate. Quantising once keeps the intent the gate
compares with (H10) identical to the bytes: a point or a delta is never
quantised a second time.
"""
from __future__ import annotations

from collections.abc import Iterable

from ggdesk import numerics
from ggdesk.model.geometry import Placement, Polyline, UPt
from ggdesk.model.toolpath import UStroke


def to_machine_units_counted(paths: Iterable[Polyline], placement: Placement) -> tuple[tuple[UStroke, ...], int]:
    """(strokes, dropped).

    Consecutive points that quantise to the same unit position are merged (a
    zero-length step is never emitted). A path left with fewer than two
    distinct points is dropped and counted.
    """
    strokes: list[UStroke] = []
    dropped = 0
    for poly in paths:
        pts: list[UPt] = []
        for p in poly.points:
            u = numerics.to_units_pt(placement.to_machine(p))
            if not pts or pts[-1] != u:
                pts.append(u)
        if len(pts) < 2:
            dropped += 1
            continue
        strokes.append(UStroke(tuple(pts)))
    return tuple(strokes), dropped


def to_machine_units(paths: Iterable[Polyline], placement: Placement) -> tuple[UStroke, ...]:
    """Machine strokes in device units (to_machine_units_counted also returns the drop count)."""
    return to_machine_units_counted(paths, placement)[0]
