"""Stroke ordering for less pen-up travel: the driver's optimiser, without merging.

gts_optimise.optimise_strokes(merge=True) joins strokes whose ends are close by
bridging the gap with the tool down, which would engrave a line the job does
not contain. With merge=False it only reorders strokes and reverses open ones,
so the gate's H10 multiset comparison (each stroke forward or reversed) holds.

The driver's TSP pass (nearest neighbour + 2-opt) grows roughly with the cube of
the stroke count: about 6 s for 100 strokes and 37 s for 337 on the dev
container, so a bench fill of several hundred hatch lines would not build in
reasonable time. Up to TSP_STROKE_LIMIT strokes the full optimiser runs (every
golden up to M2 is below it, so their bytes are unchanged); above it the
toolpath's own order is kept (fill emits its hatch lines in boustrophedon order,
patterns in reading order) and only the driver's linear per-stroke reversal runs.

The driver's bidirectional pass is off: after the greedy reversal has already
snaked a run of parallel lines, it reverses every other line again, so every
hatch line ran the same way with a full-width rapid back between lines (rapid
travel about equal to the cut length in the first fill goldens). No trace golden
depends on it (they are byte-identical with it off).
"""
from __future__ import annotations

from collections.abc import Sequence

import gts_optimise

from ggdesk.model.toolpath import UStroke

TSP_STROKE_LIMIT = 128


def order(strokes: Sequence[UStroke]) -> list[UStroke]:
    """Strokes in cutting order, some reversed. Same multiset of strokes as the input."""
    if not strokes:
        return []
    out = gts_optimise.optimise_strokes([s.to_driver() for s in strokes], merge=False,
                                        reorder=len(strokes) <= TSP_STROKE_LIMIT, bidirectional=False)
    return [UStroke.from_driver((int(sx), int(sy), [(int(dx), int(dy)) for dx, dy in d])) for sx, sy, d in out]
