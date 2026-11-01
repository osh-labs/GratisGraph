"""Fill operation (F09): hatch, optional contour pass, inward offset of half the tip width.

Contract: desktop/docs/m2-plan.md section 2.1. Everything is in the part frame, in mm.

Geometry (Shapely 2.x / GEOS):

- Each region (outer ring minus its holes) is normalised first (`shapely.normalize`: canonical ring
  orientation and start vertex), so the result does not depend on the vertex order or the start vertex
  of the job's rings.
- Offset area: the region buffered inward by `tip_width_mm / 2` with mitre joins. It is where the tool
  centre may go. A mitre corner excludes at least what a round one would, so the offset area lies
  inside the exact one. Mitre joins need no trigonometry; GEOS uses libm only when a corner exceeds the
  mitre limit and is bevelled instead. MITRE_LIMIT = 100 keeps every corner wider than about 1.15
  degrees on the trig-free path; a golden that contains a sharper corner must be listed in the ties file.
- Hatch: lines at `hatch_angle_deg` (direction from `numerics.cos_sin_deg`, exact at multiples of 45
  degrees), at the offsets k * stepover_mm (k an integer) from the part-frame origin along the line
  normal, so the pattern never depends on a region's bounds and adjacent regions line up. Each line is
  clipped to the offset area; collinear touching pieces are merged and each piece becomes one two-point
  path. Within a region, successive lines alternate direction.
- Contour pass: the offset area's rings as closed paths (exterior, then holes, per component), emitted
  before the hatch of the same region.
- Narrow regions: the part of a region the tool cannot reach is the region minus the offset area
  buffered back out by `tip_width_mm / 2` (mitre). Pieces of at most NARROW_MIN_AREA_MM2 are numeric
  slivers and ignored. A region with any piece left, or whose offset area is empty (it vanishes under
  the offset, whatever its size), is reported once as NarrowRegion(op_index, region_index, width_mm).
  width_mm is an upper bound on the width of the unreached parts: twice (the largest maximum-inscribed-
  circle radius over the pieces + the search tolerance), rounded up to 0.01 mm. Corners are not
  reported: a mitre buffer gives a corner back exactly, although a round tool does not reach into it.

Order: regions in job order; within a region contours (components by their normalised coordinates),
then hatch lines by k. Nothing is ordered by object identity or set iteration.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import shapely
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from ggdesk import numerics
from ggdesk.model.geometry import Polyline, Pt, Region
from ggdesk.model.job import FillOp
from ggdesk.model.toolpath import NarrowRegion

MITRE_LIMIT = 100.0          # GEOS bevels (with libm trig) only corners sharper than 2*asin(1/100) ~ 1.15 deg
NARROW_MIN_AREA_MM2 = 0.01   # unreached pieces at or below this area are numeric slivers (plan 2.1)
INSCRIBED_TOL_MM = 0.001     # maximum_inscribed_circle search tolerance (added to the radius: upper bound)


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


def region_polygon(region: Region) -> Polygon:
    """The region as a normalised Shapely polygon. ValueError if it is not a valid area."""
    try:
        poly = Polygon(region.outer, list(region.holes))
    except (ValueError, TypeError, shapely.errors.GEOSException) as e:
        raise ValueError(f"not a polygon: {e}") from e
    if poly.is_empty or not poly.is_valid:
        raise ValueError(f"not a valid area ({shapely.is_valid_reason(poly)})")
    return shapely.normalize(poly)


def offset_area(poly: Polygon, distance_mm: float) -> list[Polygon]:
    """Components of `poly` buffered inward by distance_mm (mitre joins), in a stable order."""
    area = shapely.normalize(poly.buffer(-distance_mm, join_style="mitre", mitre_limit=MITRE_LIMIT))
    return _polygons(area)


def _polygons(g: BaseGeometry) -> list[Polygon]:
    parts = [p for p in shapely.get_parts(g) if isinstance(p, Polygon) and not p.is_empty]
    return sorted(parts, key=lambda p: tuple(p.exterior.coords))


def _ring(coords: object) -> Polyline:
    pts = tuple((float(x), float(y)) for x, y in list(coords)[:-1])  # type: ignore[call-overload]
    return Polyline(pts, closed=True)


def _contours(components: list[Polygon]) -> list[Polyline]:
    out: list[Polyline] = []
    for c in components:
        out.append(_ring(c.exterior.coords))
        out.extend(_ring(h.coords) for h in c.interiors)
    return out


def _hatch(area: MultiPolygon, params: FillParams) -> list[Polyline]:
    """Clipped hatch lines, line by line in k order, alternating direction."""
    s = params.stepover_mm
    ux, uy = numerics.cos_sin_deg(params.hatch_angle_deg)   # along the line
    nx, ny = -uy, ux                                         # line normal
    coords = shapely.get_coordinates(area)
    pn = [x * nx + y * ny for x, y in coords]
    pu = [x * ux + y * uy for x, y in coords]
    k0 = math.ceil(min(pn) / s)
    k1 = math.floor(max(pn) / s)
    t0, t1 = min(pu) - 1.0, max(pu) + 1.0
    lines = []
    for k in range(k0, k1 + 1):
        c = k * s
        bx, by = c * nx, c * ny
        lines.append(LineString(((bx + t0 * ux, by + t0 * uy), (bx + t1 * ux, by + t1 * uy))))
    if not lines:
        return []
    shapely.prepare(area)
    clipped = shapely.intersection(lines, area)
    out: list[Polyline] = []
    n_lines = 0
    for g in clipped:
        pieces: list[tuple[Pt, Pt]] = []
        for p in shapely.get_parts(g):
            if not isinstance(p, LineString) or p.is_empty or p.length == 0.0:
                continue
            cs = list(p.coords)
            a: Pt = (float(cs[0][0]), float(cs[0][1]))
            b: Pt = (float(cs[-1][0]), float(cs[-1][1]))
            if a[0] * ux + a[1] * uy > b[0] * ux + b[1] * uy:
                a, b = b, a
            pieces.append((a, b))
        if not pieces:
            continue
        pieces.sort(key=lambda ab: (ab[0][0] * ux + ab[0][1] * uy, ab[0], ab[1]))
        merged: list[tuple[Pt, Pt]] = [pieces[0]]
        for a, b in pieces[1:]:
            if merged[-1][1] == a:
                merged[-1] = (merged[-1][0], b)
            else:
                merged.append((a, b))
        if n_lines % 2 == 1:
            merged = [(b, a) for a, b in reversed(merged)]
        out.extend(Polyline((a, b)) for a, b in merged)
        n_lines += 1
    return out


def _narrow_width(poly: Polygon, components: list[Polygon], half: float) -> float | None:
    """Upper bound on the width of the unreached parts of `poly` (mm, rounded up to 0.01), or None."""
    if components:
        reach = shapely.union_all(components).buffer(half, join_style="mitre", mitre_limit=MITRE_LIMIT)
        rest = _polygons(shapely.normalize(poly.difference(reach)))
        rest = [p for p in rest if p.area > NARROW_MIN_AREA_MM2]
        if not rest:
            return None
    else:
        rest = [poly]
    r = max(shapely.maximum_inscribed_circle(p, INSCRIBED_TOL_MM).length for p in rest)
    w = 2.0 * (r + INSCRIBED_TOL_MM)
    return numerics.to_mm(numerics.ceil_div(w * numerics.UNITS_PER_MM, 1.0))


def fill(op: FillOp, op_index: int, params: FillParams) -> FillResult:
    """Paths that clear every region of `op` (part frame, mm) and the regions left (partly) unreached."""
    if not params.tip_width_mm > 0:
        raise ValueError(f"tip width must be positive, got {params.tip_width_mm!r}")
    if not params.stepover_mm > 0:
        raise ValueError(f"stepover must be positive, got {params.stepover_mm!r}")
    half = params.tip_width_mm / 2
    paths: list[Polyline] = []
    narrow: list[NarrowRegion] = []
    for ri, region in enumerate(op.regions):
        try:
            poly = region_polygon(region)
        except ValueError as e:
            raise ValueError(f"operations[{op_index}].regions[{ri}]: {e}") from e
        comps = offset_area(poly, half)
        w = _narrow_width(poly, comps, half)
        if w is not None:
            narrow.append(NarrowRegion(op_index, ri, w))
        if not comps:
            continue
        if params.contour_pass:
            paths.extend(_contours(comps))
        paths.extend(_hatch(MultiPolygon(comps), params))
    return FillResult(tuple(paths), tuple(narrow))
