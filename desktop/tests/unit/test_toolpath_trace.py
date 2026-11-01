"""F04 trace: part-frame polylines; closed paths get their closing point."""
from __future__ import annotations

from ggdesk.model.geometry import Polyline
from ggdesk.model.job import TraceOp
from ggdesk.toolpath import trace


def test_open_path_unchanged() -> None:
    op = TraceOp((Polyline(((0.0, 0.0), (1.0, 2.0), (3.0, 4.0))),))
    assert trace(op) == (Polyline(((0.0, 0.0), (1.0, 2.0), (3.0, 4.0))),)


def test_closed_path_gets_closing_point() -> None:
    sq = ((-5.0, -5.0), (5.0, -5.0), (5.0, 5.0), (-5.0, 5.0))
    (out,) = trace(TraceOp((Polyline(sq, closed=True),)))
    assert out.points == (*sq, (-5.0, -5.0))
    assert out.closed is False   # the returned point list is literal: nothing more to add


def test_order_and_count_preserved() -> None:
    paths = (Polyline(((0.0, 0.0), (1.0, 0.0))), Polyline(((2.0, 0.0), (3.0, 0.0), (3.0, 1.0)), closed=True),
             Polyline(((9.0, 9.0), (8.0, 8.0))))
    out = trace(TraceOp(paths))
    assert [p.points[0] for p in out] == [(0.0, 0.0), (2.0, 0.0), (9.0, 9.0)]
    assert len(out[1].points) == 4


def test_empty_closed_path_stays_empty() -> None:
    assert trace(TraceOp((Polyline((), closed=True),))) == (Polyline(()),)
