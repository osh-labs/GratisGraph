"""F09 fill (toolpath/fill.py): offset, hatch, contour pass, narrow regions, determinism."""
from __future__ import annotations

import math
import time

import pytest

from ggdesk.formats import job as jf
from ggdesk.model.geometry import Polyline, Region
from ggdesk.model.job import FillOp
from ggdesk.model.toolpath import NarrowRegion
from ggdesk.toolpath.fill import FillParams, FillResult, fill
from tests.conftest import DESKTOP

SQUARE_HOLE = jf.load(DESKTOP / "docs" / "examples" / "fill-square-hole.ggj").operations[0]
P = FillParams(tip_width_mm=0.2, stepover_mm=0.1, hatch_angle_deg=0.0, contour_pass=True)


def _sq(c: float, x: float = 0.0, y: float = 0.0) -> tuple[tuple[float, float], ...]:
    return ((x - c, y - c), (x + c, y - c), (x + c, y + c), (x - c, y + c))


def _hatch(r: FillResult) -> list[Polyline]:
    return [p for p in r.paths if not p.closed]


def test_square_hole_contours_first() -> None:
    assert isinstance(SQUARE_HOLE, FillOp)
    r = fill(SQUARE_HOLE, 0, P)
    assert r.narrow == ()
    c = [p for p in r.paths if p.closed]
    assert r.paths[:2] == tuple(c) and len(c) == 2          # contours come before the hatch
    assert {x for p in c[:1] for x, _ in p.points} == {-3.9, 3.9}   # outer offset by 0.1
    assert {x for p in c[1:] for x, _ in p.points} == {-1.1, 1.1}   # hole grown by 0.1


def test_square_hole_hatch_lines() -> None:
    r = fill(SQUARE_HOLE, 0, P)
    h = _hatch(r)
    assert all(len(p.points) == 2 and p.points[0][1] == p.points[1][1] for p in h)   # horizontal at 0 deg
    ys = sorted({p.points[0][1] for p in h})
    # multiples of 0.1 strictly inside +-3.9 (the k = +-39 lines fall a ulp outside the offset area)
    assert len(ys) == 77 and math.isclose(ys[0], -3.8) and math.isclose(ys[-1], 3.8)
    # lines through the hole are split in two pieces
    assert sum(1 for p in h if abs(p.points[0][1]) < 1.1) == 2 * sum(1 for y in ys if abs(y) < 1.1)


def test_alternating_direction_line_by_line() -> None:
    r = fill(FillOp((Region(_sq(2.0)),)), 0, P)
    h = _hatch(r)
    dirs = [p.points[1][0] > p.points[0][0] for p in h]
    assert dirs == [i % 2 == 0 for i in range(len(h))]


def test_split_line_keeps_one_direction() -> None:
    r = fill(SQUARE_HOLE, 0, P)
    by_y: dict[float, list[Polyline]] = {}
    for p in _hatch(r):
        by_y.setdefault(p.points[0][1], []).append(p)
    for pieces in by_y.values():
        if len(pieces) == 2:
            a, b = pieces
            fwd = a.points[1][0] > a.points[0][0]
            assert (b.points[1][0] > b.points[0][0]) == fwd
            # in travel order: the second piece starts beyond the first
            assert (b.points[0][0] > a.points[1][0]) == fwd


def test_contour_pass_off() -> None:
    r = fill(SQUARE_HOLE, 0, FillParams(0.2, 0.1, 0.0, False))
    assert all(not p.closed for p in r.paths)
    assert _hatch(r) == _hatch(fill(SQUARE_HOLE, 0, P))


def test_hatch_45_exact_direction() -> None:
    r = fill(FillOp((Region(_sq(2.0)),)), 0, FillParams(0.2, 0.1, 45.0, False))
    for p in r.paths:
        (x0, y0), (x1, y1) = p.points
        assert math.isclose(x1 - x0, y1 - y0, rel_tol=1e-12, abs_tol=1e-12)


def test_hatch_positions_independent_of_region_bounds() -> None:
    """Two adjacent regions' lines are the same lines (fixed multiples of the stepover)."""
    a = fill(FillOp((Region(((0.0, 0.0), (3.0, 0.0), (3.0, 3.03), (0.0, 3.03))),)), 0, FillParams(0.2, 0.25, 0, False))
    b = fill(FillOp((Region(((3.0, 0.17), (6.0, 0.17), (6.0, 3.0), (3.0, 3.0))),)), 0, FillParams(0.2, 0.25, 0, False))
    ya = {p.points[0][1] for p in a.paths}
    yb = {p.points[0][1] for p in b.paths}
    assert ya & yb and all(math.isclose(y / 0.25, math.floor(y / 0.25 + 0.5)) for y in ya | yb)


def test_narrow_neck_and_vanishing_region() -> None:
    dumbbell = Region(((-8.0, -2.0), (-4.0, -2.0), (-4.0, -0.05), (4.0, -0.05), (4.0, -2.0), (8.0, -2.0),
                       (8.0, 2.0), (4.0, 2.0), (4.0, 0.05), (-4.0, 0.05), (-4.0, 2.0), (-8.0, 2.0)))
    bar = Region(((-6.0, 6.0), (6.0, 6.0), (6.0, 6.15), (-6.0, 6.15)))
    big = Region(_sq(1.0, 0.0, 12.0))
    r = fill(FillOp((dumbbell, bar, big)), 3, P)
    assert [(n.op_index, n.region_index) for n in r.narrow] == [(3, 0), (3, 1)]
    # width is an upper bound, rounded up to 0.01 mm: neck 0.10 mm, bar 0.15 mm
    w0, w1 = r.narrow[0].width_mm, r.narrow[1].width_mm
    assert 0.10 <= w0 <= 0.12 and 0.15 <= w1 <= 0.17
    assert all(p.points[0][1] < 3.0 or p.points[0][1] > 10.0 for p in r.paths)   # nothing for the bar


def test_tiny_region_that_vanishes_is_reported() -> None:
    r = fill(FillOp((Region(_sq(0.04)),)), 0, P)     # 0.08 mm square: area 0.0064 mm^2, below the sliver area
    assert r.paths == () and r.narrow == (NarrowRegion(0, 0, r.narrow[0].width_mm),)
    assert 0.08 <= r.narrow[0].width_mm <= 0.1


def test_corners_are_not_narrow() -> None:
    tri = Region(((0.0, 0.0), (10.0, 0.0), (5.0, 1.0)))     # sharp acute corners, wide body
    assert fill(FillOp((tri, Region(_sq(3.0, 20.0)))), 0, P).narrow == ()


def test_invalid_region_names_the_region() -> None:
    bow = Region(((0.0, 0.0), (1.0, 1.0), (1.0, 0.0), (0.0, 1.0)))
    with pytest.raises(ValueError, match=r"operations\[2\]\.regions\[1\]: not a valid area"):
        fill(FillOp((Region(_sq(1.0)), bow)), 2, P)


@pytest.mark.parametrize("bad", [FillParams(0.0, 0.1, 0, True), FillParams(0.2, 0.0, 0, True)])
def test_refuses_non_positive_params(bad: FillParams) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        fill(SQUARE_HOLE, 0, bad)


# --- determinism -------------------------------------------------------------

L_HOLE = Region(((-12.0, -12.0), (2.0, -12.0), (2.0, -4.0), (-4.0, -4.0), (-4.0, 6.0), (-12.0, 6.0)),
                (((-10.0, -10.0), (-6.0, -6.0), (-6.0, -10.0)),))


def _variants(reg: Region) -> list[Region]:
    def rot(r: tuple[tuple[float, float], ...], k: int) -> tuple[tuple[float, float], ...]:
        return r[k:] + r[:k]

    return [
        Region(tuple(reversed(reg.outer)), tuple(tuple(reversed(h)) for h in reg.holes)),
        Region(rot(reg.outer, 2), tuple(rot(h, 1) for h in reg.holes)),
        Region(rot(tuple(reversed(reg.outer)), 3), reg.holes),
    ]


@pytest.mark.parametrize("angle", [0.0, 45.0, 30.0])
def test_same_inputs_same_result(angle: float) -> None:
    p = FillParams(0.2, 0.1, angle, True)
    assert fill(FillOp((L_HOLE,)), 0, p) == fill(FillOp((L_HOLE,)), 0, p)


@pytest.mark.parametrize("angle", [0.0, 45.0, 30.0])
def test_vertex_order_and_start_do_not_matter(angle: float) -> None:
    p = FillParams(0.2, 0.1, angle, True)
    ref = fill(FillOp((L_HOLE,)), 0, p)
    for v in _variants(L_HOLE):
        assert fill(FillOp((v,)), 0, p) == ref


def test_performance_40mm_at_0_05() -> None:
    t = time.perf_counter()
    r = fill(FillOp((Region(_sq(20.0)),)), 0, FillParams(0.2, 0.05, 30.0, True))
    assert len(r.paths) > 700
    assert time.perf_counter() - t < 1.0
