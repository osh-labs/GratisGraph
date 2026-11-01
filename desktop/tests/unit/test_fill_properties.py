"""F09 fill properties (hypothesis): random convex and concave polygons with holes, random parameters.

- every output point lies inside the region offset inward by tip/2 (distance to the region boundary
  >= tip/2 - 1e-6 mm, and inside the region);
- the tool footprint (every path buffered by tip/2) never leaves the region;
- hatch lines sit at multiples of the stepover, and in a convex region without holes every multiple between the first
  and last line is present (spacing equals the stepover);
- the result does not depend on vertex order or start vertex.
"""
from __future__ import annotations

import math

import shapely
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from shapely.geometry import LinearRing, LineString, Point, Polygon

from ggdesk import numerics
from ggdesk.model.geometry import Pt, Region
from ggdesk.model.job import FillOp
from ggdesk.toolpath.fill import FillParams, fill

TOL = 1e-6


def _star(cx: float, cy: float, radii: list[float], phase: float) -> tuple[Pt, ...]:
    n = len(radii)
    return tuple((cx + r * math.cos(phase + 2 * math.pi * i / n), cy + r * math.sin(phase + 2 * math.pi * i / n))
                 for i, r in enumerate(radii))


@st.composite
def regions(draw: st.DrawFn, convex: bool | None = None, hole: bool | None = None) -> Region:
    n = draw(st.integers(3, 12))
    is_convex = draw(st.booleans()) if convex is None else convex
    r_max = draw(st.floats(1.0, 15.0))
    if is_convex:
        radii = [r_max] * n
    else:
        radii = [draw(st.floats(0.35 * r_max, r_max)) for _ in range(n)]
    phase = draw(st.floats(0.0, 6.28))
    outer = _star(0.0, 0.0, radii, phase)
    holes: list[tuple[Pt, ...]] = []
    if draw(st.booleans()) if hole is None else hole:
        # a hole inside the core disc every star contains (radius 0.35 r_max * cos(pi/3) on 3 vertices)
        hr = draw(st.floats(0.02, 0.15)) * r_max
        holes.append(tuple(reversed(_star(0.0, 0.0, [hr] * draw(st.integers(3, 6)), draw(st.floats(0, 6.28))))))
    reg = Region(outer, tuple(holes))
    poly = Polygon(reg.outer, [list(h) for h in reg.holes])
    assume(poly.is_valid and poly.area > 0.0)
    return reg


params = st.builds(FillParams, tip_width_mm=st.floats(0.05, 1.0), stepover_mm=st.floats(0.05, 1.0),
                   hatch_angle_deg=st.one_of(st.sampled_from([0.0, 45.0, 90.0, 135.0, -45.0]), st.floats(-180, 180)),
                   contour_pass=st.booleans())


def _poly(reg: Region) -> Polygon:
    return Polygon(reg.outer, [list(h) for h in reg.holes])


@settings(max_examples=150, deadline=None)
@given(regions(), params)
def test_points_inside_offset_region(reg: Region, p: FillParams) -> None:
    poly = _poly(reg)
    boundary = poly.boundary
    for path in fill(FillOp((reg,)), 0, p).paths:
        for x, y in path.points:
            pt = Point(x, y)
            assert poly.covers(pt)
            assert boundary.distance(pt) >= p.tip_width_mm / 2 - TOL


@settings(max_examples=150, deadline=None)
@given(regions(), params)
def test_footprint_stays_in_region(reg: Region, p: FillParams) -> None:
    poly = _poly(reg)
    r = fill(FillOp((reg,)), 0, p)
    lines = [LinearRing(q.points) if q.closed else LineString(q.points) for q in r.paths]
    if not lines:
        return
    foot = shapely.union_all([g.buffer(p.tip_width_mm / 2, quad_segs=16) for g in lines])
    assert foot.difference(poly).area <= 1e-6


@settings(max_examples=150, deadline=None)
@given(regions(convex=True, hole=False), params)
def test_hatch_spacing_equals_stepover(reg: Region, p: FillParams) -> None:
    ux, uy = numerics.cos_sin_deg(p.hatch_angle_deg)
    nx, ny = -uy, ux
    ks: list[int] = []
    for q in fill(FillOp((reg,)), 0, p).paths:
        if q.closed:
            continue
        assert len(q.points) == 2
        cs = [(x * nx + y * ny) / p.stepover_mm for x, y in q.points]
        k = math.floor(cs[0] + 0.5)
        assert all(abs(c - k) <= 1e-6 for c in cs)      # on the line k * stepover from the origin
        ks.append(k)
    distinct = sorted(set(ks))
    assert ks == list(dict.fromkeys(ks))                # one piece per line in a convex region, in k order
    assert distinct == list(range(distinct[0], distinct[-1] + 1)) if distinct else True


@settings(max_examples=60, deadline=None)
@given(regions(), params, st.integers(0, 11), st.booleans())
def test_vertex_order_invariance(reg: Region, p: FillParams, shift: int, flip: bool) -> None:
    k = shift % len(reg.outer)
    outer = reg.outer[k:] + reg.outer[:k]
    holes = reg.holes
    if flip:
        outer = tuple(reversed(outer))
        holes = tuple(tuple(reversed(h)) for h in holes)
    assert fill(FillOp((Region(outer, holes),)), 0, p) == fill(FillOp((reg,)), 0, p)
