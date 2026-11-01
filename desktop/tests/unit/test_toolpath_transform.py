"""F05 fixture transform: Y flip, one quantisation per coordinate, collapse handling."""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from ggdesk.model.geometry import Placement, Polyline
from ggdesk.model.toolpath import UStroke
from ggdesk.numerics import to_units
from ggdesk.toolpath import to_machine_units, to_machine_units_counted

CENTRE = Placement((50.0, 50.0))


def test_translation_and_y_flip() -> None:
    (s,) = to_machine_units([Polyline(((-14.0, 2.0), (-14.0, 14.0), (8.0, -10.0)))], CENTRE)
    assert s.points == ((3600, 4800), (3600, 3600), (5800, 6000))


def test_half_to_even_once_on_the_machine_coordinate() -> None:
    # 50 + 2.125 = 52.125 mm -> 5212.5 units -> 5212 (half to even); 50 - (-4.125) = 54.125 -> 5412
    (s,) = to_machine_units([Polyline(((2.125, -4.125), (3.0, -4.125)))], CENTRE)
    assert s.points[0] == (5212, 5412)


def test_quantisation_is_of_the_point_not_the_delta() -> None:
    # Three steps of 0.004 mm. Rounding each delta would give 0 + 0 + 0 and lose the stroke;
    # one rounding per point gives 0, 0, 1, 1 units: a 0.01 mm stroke ending where 0.012 mm rounds to.
    pts = ((0.0, 0.0), (0.004, 0.0), (0.008, 0.0), (0.012, 0.0))
    strokes, dropped = to_machine_units_counted([Polyline(pts)], Placement((0.0, 0.0)))
    assert dropped == 0
    assert strokes == (UStroke(((0, 0), (1, 0))),)


def test_zero_length_steps_dropped() -> None:
    (s,) = to_machine_units([Polyline(((0.0, 0.0), (0.001, 0.0), (1.0, 0.0), (1.0, 0.0), (1.0, 1.0)))], CENTRE)
    assert s.points == ((5000, 5000), (5100, 5000), (5100, 4900))


def test_collapsed_strokes_dropped_and_counted() -> None:
    paths = [Polyline(((0.0, 0.0), (0.004, 0.0))),        # collapses to one unit point
             Polyline(((1.0, 1.0),)),                      # a single point
             Polyline(()),                                 # nothing
             Polyline(((0.0, 0.0), (1.0, 0.0)))]
    strokes, dropped = to_machine_units_counted(paths, CENTRE)
    assert dropped == 3
    assert strokes == (UStroke(((5000, 5000), (5100, 5000))),)
    assert to_machine_units(paths, CENTRE) == strokes


coord = st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)
point = st.tuples(coord, coord)


@settings(max_examples=300, deadline=None)
@given(origin=st.tuples(st.floats(0.0, 100.0), st.floats(0.0, 100.0)),
       pts=st.lists(point, min_size=1, max_size=12))
def test_every_point_round_trips_to_to_units_of_to_machine(origin: tuple[float, float],
                                                           pts: list[tuple[float, float]]) -> None:
    pl = Placement(origin)
    pts = [p for p in pts if 0.0 <= pl.to_machine(p)[0] <= 100.0 and 0.0 <= pl.to_machine(p)[1] <= 100.0]
    expected: list[tuple[int, int]] = []
    for p in pts:
        mx, my = pl.to_machine(p)
        u = (to_units(mx), to_units(my))
        if not expected or expected[-1] != u:
            expected.append(u)
    strokes, dropped = to_machine_units_counted([Polyline(tuple(pts))], pl)
    if len(expected) < 2:
        assert strokes == () and dropped == 1
    else:
        assert dropped == 0
        assert list(strokes[0].points) == expected
