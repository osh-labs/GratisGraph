"""A backend-neutral draw list built from DECODED job bytes (m1-plan 2.7).

Cut and rapid items come only from `ggdesk.gts_read` decoding the bytes, never
from the builder's in-memory strokes, so the preview shows what the machine
will receive. The work field, the part outline (and holes) at its placement
and the keep-outs come from the resolved library entries when known.

Coordinates: machine frame, mm. Home (0, 0) is back-left, +X right, +Y toward
the operator. Renderers draw +Y DOWN on screen (no flip), so the screen looks
like the bed seen from the operator's side: the back of the bed (home) at the
top, the front edge where the operator stands at the bottom. Renderers put a
small "operator" label at the front edge.

Closed shapes (field, part, keep_out) repeat their first point at the end, so
every item's points are the exact polyline to draw. A `start` item has one
point: where the tool first goes down.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ggdesk import gts_read
from ggdesk.gts_read import Segment
from ggdesk.library.select import Resolved
from ggdesk.model.geometry import Pt
from ggdesk.numerics import to_mm

Kind = Literal["field", "part", "keep_out", "cut", "rapid", "start"]
KINDS: tuple[Kind, ...] = ("field", "part", "keep_out", "rapid", "cut", "start")   # paint order
OPERATOR_LABEL = "operator"


@dataclass(frozen=True)
class DrawItem:
    kind: Kind
    points: tuple[Pt, ...]


@dataclass(frozen=True)
class DrawList:
    items: tuple[DrawItem, ...]
    extent_mm: tuple[float, float]       # (width, height) of the area to show, from (0, 0)

    def of_kind(self, kind: Kind) -> tuple[DrawItem, ...]:
        return tuple(i for i in self.items if i.kind == kind)

    def bounds(self) -> tuple[float, float, float, float]:
        """(min x, min y, max x, max y) over (0, 0), the extent and every point."""
        xs = [0.0, self.extent_mm[0]] + [p[0] for i in self.items for p in i.points]
        ys = [0.0, self.extent_mm[1]] + [p[1] for i in self.items for p in i.points]
        return (min(xs), min(ys), max(xs), max(ys))


def _closed(poly: tuple[Pt, ...]) -> tuple[Pt, ...]:
    pts = tuple((float(x), float(y)) for x, y in poly)
    if pts and pts[0] != pts[-1]:
        pts = pts + (pts[0],)
    return pts


def _mm(p: tuple[int, int]) -> Pt:
    return (to_mm(p[0]), to_mm(p[1]))


def _decoded_items(job: gts_read.Job) -> tuple[list[DrawItem], list[DrawItem], DrawItem | None]:
    """Rapids (pen-up segments, one item each) and cuts (pen-down paths) by walking the records."""
    rapids: list[DrawItem] = []
    x = y = 0
    down = False
    for r in job.records:
        if isinstance(r, Segment):
            nx, ny = x + r.dx, y + r.dy
            if not down and (r.dx or r.dy):
                rapids.append(DrawItem("rapid", (_mm((x, y)), _mm((nx, ny)))))
            x, y = nx, ny
        elif r.op == "PD":
            down = True
        elif r.op == "PU":
            down = False
    cuts = [DrawItem("cut", tuple(_mm(p) for p in s.points)) for s in job.strokes()]
    start = DrawItem("start", (cuts[0].points[0],)) if cuts else None
    return rapids, cuts, start


def _resolved_items(resolved: Resolved) -> tuple[list[DrawItem], list[DrawItem], list[DrawItem]]:
    field: list[DrawItem] = []
    part: list[DrawItem] = []
    keep: list[DrawItem] = []
    wf = resolved.machine.work_field_mm
    if wf.known and wf.value is not None:
        w, h = float(wf.value[0]), float(wf.value[1])
        field.append(DrawItem("field", _closed(((0.0, 0.0), (w, 0.0), (w, h), (0.0, h)))))
    pl = resolved.placement
    if pl is not None:
        p = resolved.part
        if p.outline.known and p.outline.value is not None:
            part.append(DrawItem("part", _closed(tuple(pl.to_machine(q) for q in p.outline.value.polygon()))))
        if p.holes.known and p.holes.value is not None:
            for hole in p.holes.value:
                part.append(DrawItem("part", _closed(tuple(pl.to_machine(q) for q in hole.polygon()))))
    if resolved.keep_outs_machine is not None:
        keep.extend(DrawItem("keep_out", _closed(poly)) for poly in resolved.keep_outs_machine if poly)
    return field, part, keep


def draw_list(data: bytes, resolved: Resolved | None = None) -> DrawList:
    """Decode `data` (raises gts_read.GtsFormatError) and list what to draw, in paint order."""
    job = gts_read.read_job(bytes(data))
    rapids, cuts, start = _decoded_items(job)
    field: list[DrawItem] = []
    part: list[DrawItem] = []
    keep: list[DrawItem] = []
    if resolved is not None:
        field, part, keep = _resolved_items(resolved)
    items = (*field, *part, *keep, *rapids, *cuts, *((start,) if start else ()))
    if field:
        extent = (field[0].points[2][0], field[0].points[2][1])
    else:
        pts = [p for i in items for p in i.points]
        extent = (max((p[0] for p in pts), default=0.0), max((p[1] for p in pts), default=0.0))
    return DrawList(tuple(items), (float(extent[0]), float(extent[1])))
