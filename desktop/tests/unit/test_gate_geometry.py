"""gate/geometry.py: closed polygons, boundaries tested on both sides, concave shapes and holes."""
from __future__ import annotations

import pytest

from ggdesk.gate import geometry as g

SQ = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
# a U shape: the notch x 40..60, y 40..100 is outside
U = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (60.0, 100.0), (60.0, 40.0), (40.0, 40.0), (40.0, 100.0),
     (0.0, 100.0)]


@pytest.mark.parametrize(("p", "inside"), [
    ((50.0, 50.0), True), ((0.0, 50.0), True), ((100.0, 100.0), True), ((100.0, 50.0), True),
    ((100.01, 50.0), False), ((-0.01, 50.0), False), ((50.0, 100.01), False)])
def test_point_in_polygon_closed(p: tuple[float, float], inside: bool) -> None:
    assert g.point_in_polygon(p, SQ) is inside


def test_point_strictly_inside_excludes_boundary() -> None:
    assert not g.point_strictly_inside((0.0, 50.0), SQ)
    assert g.point_strictly_inside((1.0, 50.0), SQ)


def test_concave() -> None:
    assert not g.point_in_polygon((50.0, 70.0), U)
    assert g.point_in_polygon((50.0, 20.0), U)
    assert not g.segment_inside((20.0, 70.0), (80.0, 70.0), U)     # endpoints inside, crosses the notch
    assert g.segment_inside((20.0, 20.0), (80.0, 20.0), U)
    assert g.segment_inside((40.0, 40.0), (60.0, 40.0), U)         # along the notch floor: on the boundary


def test_point_segment_distance() -> None:
    assert g.point_segment_dist2((5.0, 3.0), (0.0, 0.0), (10.0, 0.0)) == 9.0
    assert g.point_segment_dist2((-3.0, 4.0), (0.0, 0.0), (10.0, 0.0)) == 25.0
    assert g.point_segment_dist2((13.0, 4.0), (0.0, 0.0), (10.0, 0.0)) == 25.0
    assert g.point_segment_dist2((1.0, 1.0), (0.0, 0.0), (0.0, 0.0)) == 2.0


def test_segments_intersect_and_distance() -> None:
    assert g.segments_intersect((0, 0), (10, 10), (0, 10), (10, 0))
    assert g.segments_intersect((0, 0), (10, 0), (10, 0), (10, 5))          # touching at an end
    assert g.segments_intersect((0, 0), (10, 0), (5, 0), (20, 0))           # collinear overlap
    assert not g.segments_intersect((0, 0), (10, 0), (0, 1), (10, 1))
    assert not g.segments_intersect((0, 0), (10, 0), (11, 0), (20, 0))
    assert g.segment_segment_dist2((0, 0), (10, 10), (0, 10), (10, 0)) == 0.0
    assert g.segment_segment_dist2((0, 0), (10, 0), (0, 3), (10, 3)) == 9.0


@pytest.mark.parametrize(("d", "ok"), [(200.0, True), (199.0, False), (200.0 - 1e-7, True), (250.0, True)])
def test_clearance_boundary(d: float, ok: bool) -> None:
    assert g.clearance_ok(d * d, 200.0) is ok


def test_clearance_zero_margin() -> None:
    assert g.clearance_ok(0.0, 0.0)


def test_representation_error_at_the_margin() -> None:
    # an edge at -2.3 mm lands at -229.99999999999997 units: the origin is exactly 2.3 mm (230 units) from it
    edge = -2.3 * 100
    assert edge != -230.0
    poly = [(edge, -1000.0), (1000.0, -1000.0), (1000.0, 1000.0), (edge, 1000.0)]
    assert g.boundary_dist2((0.0, 0.0), poly) < 230.0 * 230.0          # the raw float says "too close"
    assert g.clearance_ok(g.boundary_dist2((0.0, 0.0), poly), 230.0)   # EPS judges it on the margin
    assert not g.clearance_ok(g.boundary_dist2((-1.0, 0.0), poly), 230.0)


def test_segment_meets_polygon() -> None:
    box = [(40.0, 40.0), (60.0, 40.0), (60.0, 60.0), (40.0, 60.0)]
    assert g.segment_meets_polygon((0, 50), (100, 50), box)        # through
    assert g.segment_meets_polygon((50, 50), (51, 51), box)        # wholly inside
    assert g.segment_meets_polygon((0, 40), (100, 40), box)        # along an edge
    assert g.segment_meets_polygon((0, 50), (40, 50), box)         # ends on the edge
    assert not g.segment_meets_polygon((0, 50), (39.99, 50), box)
    assert not g.segment_meets_polygon((0, 0), (100, 30), box)


def test_segment_enters_interior() -> None:
    hole = [(40.0, 40.0), (60.0, 40.0), (60.0, 60.0), (40.0, 60.0)]
    assert g.segment_enters_interior((0, 50), (100, 50), hole)
    assert not g.segment_enters_interior((0, 40), (100, 40), hole)  # grazes the edge
    assert not g.segment_enters_interior((0, 0), (10, 10), hole)
