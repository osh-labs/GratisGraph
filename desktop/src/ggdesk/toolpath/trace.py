"""F04 trace: a trace operation's paths as the polylines the tool follows (part frame, mm)."""
from __future__ import annotations

from ggdesk.model.geometry import Polyline
from ggdesk.model.job import TraceOp


def trace(op: TraceOp) -> tuple[Polyline, ...]:
    """The paths to engrave, in the part frame, in job order.

    A closed path gets its closing point appended (the job format never repeats
    it), so every returned polyline is the literal point sequence to cut and is
    marked open. Nothing is simplified, merged or reordered here.
    """
    out: list[Polyline] = []
    for p in op.paths:
        pts = tuple(p.points)
        if p.closed and pts:
            pts = (*pts, pts[0])
        out.append(Polyline(pts, closed=False))
    return tuple(out)
