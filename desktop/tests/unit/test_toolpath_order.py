"""Ordering only reorders and reverses: the multiset of strokes (forward or reversed) is unchanged."""
from __future__ import annotations

from collections import Counter

from hypothesis import given, settings
from hypothesis import strategies as st

from ggdesk.model.toolpath import UStroke
from ggdesk.toolpath import order


def _canon(s: UStroke) -> tuple[tuple[int, int], ...]:
    """A stroke and its reverse compare equal."""
    return min(s.points, tuple(reversed(s.points)))


def _multiset(strokes: list[UStroke] | tuple[UStroke, ...]) -> Counter[tuple[tuple[int, int], ...]]:
    return Counter(_canon(s) for s in strokes)


def test_empty() -> None:
    assert order([]) == []


def test_reorders_and_reverses_only() -> None:
    strokes = [UStroke(((9000, 9000), (9500, 9000))),
               UStroke(((1000, 1000), (1000, 2000), (2000, 2000))),
               UStroke(((5000, 5000), (6000, 5000), (6000, 6000), (5000, 5000))),   # closed
               UStroke(((1100, 1000), (1100, 2000))),
               UStroke(((1100, 2100), (1100, 1050)))]
    out = order(strokes)
    assert len(out) == len(strokes)
    assert _multiset(out) == _multiset(strokes)
    assert out[0].points[0] == (1000, 1000)          # nearest to home first
    assert out != strokes                            # it did reorder


def test_no_merging_of_touching_strokes() -> None:
    # End of one stroke equals the start of the next: merge=True would join them; merge=False must not.
    a = UStroke(((1000, 1000), (2000, 1000)))
    b = UStroke(((2000, 1000), (3000, 1000)))
    out = order([a, b])
    assert len(out) == 2
    assert _multiset(out) == _multiset([a, b])


unit = st.integers(min_value=0, max_value=10000)


@st.composite
def strokes(draw: st.DrawFn) -> UStroke:
    pts = draw(st.lists(st.tuples(unit, unit), min_size=2, max_size=6))
    dedup = [pts[0]]
    for p in pts[1:]:
        if p != dedup[-1]:
            dedup.append(p)
    if len(dedup) < 2:
        dedup.append((dedup[0][0] + 1, dedup[0][1]))
    return UStroke(tuple(dedup))


@settings(max_examples=150, deadline=None)
@given(st.lists(strokes(), min_size=0, max_size=25))
def test_multiset_invariant(ss: list[UStroke]) -> None:
    out = order(ss)
    assert _multiset(out) == _multiset(ss)
