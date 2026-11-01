"""Stroke ordering for less pen-up travel: the driver's optimiser, without merging.

gts_optimise.optimise_strokes(merge=True) joins strokes whose ends are close by
bridging the gap with the tool down, which would engrave a line the job does
not contain. With merge=False it only reorders strokes and reverses open ones,
so the gate's H10 multiset comparison (each stroke forward or reversed) holds.
"""
from __future__ import annotations

from collections.abc import Sequence

import gts_optimise

from ggdesk.model.toolpath import UStroke


def order(strokes: Sequence[UStroke]) -> list[UStroke]:
    """Strokes in cutting order, some reversed. Same multiset of strokes as the input."""
    if not strokes:
        return []
    out = gts_optimise.optimise_strokes([s.to_driver() for s in strokes], merge=False)
    return [UStroke.from_driver((int(sx), int(sy), [(int(dx), int(dy)) for dx, dy in d])) for sx, sy, d in out]
