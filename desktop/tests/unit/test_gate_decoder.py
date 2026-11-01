"""The gate's extended decoder (gts_read.Job.moves) agrees with the driver's preview parser
(gts_preview.parse_gts) on random valid jobs and on the root golden corpus."""
from __future__ import annotations

import json

import gts_api
import gts_preview
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ggdesk.gts_read import GtsFormatError, Job, read_job
from tests.conftest import GOLDEN

MANIFEST = json.loads((GOLDEN / "manifest.json").read_text(encoding="utf-8"))

coord = st.integers(min_value=0, max_value=10000)
delta = st.integers(min_value=-2000, max_value=2000).filter(lambda d: d != 0)
stroke = st.tuples(coord, coord, st.lists(st.tuples(delta, delta), min_size=1, max_size=8))
job_args = st.fixed_dictionaries({
    "strokes": st.lists(stroke, min_size=1, max_size=12),
    "speed": st.integers(min_value=1, max_value=40),
    "pz": st.integers(min_value=0, max_value=100),
    "dz": st.integers(min_value=100, max_value=500),
    "mc": st.sampled_from([0, 1]),
    "vd": st.one_of(st.none(), st.just(15)),
})


def _mm(p: tuple[int, int]) -> tuple[float, float]:
    return (p[0] / 100.0, p[1] / 100.0)


def _agree(data: bytes) -> None:
    job = read_job(data)
    strokes, rapids, _bounds = gts_preview.parse_gts(data)
    decoded = job.strokes()
    assert len(decoded) == len(strokes)
    for mine, theirs in zip(decoded, strokes, strict=True):
        assert len(mine.points) == len(theirs["points"])
        for a, b in zip(mine.points, theirs["points"], strict=True):
            assert _mm(a) == pytest.approx(b, abs=1e-6)
    # rapids between strokes: the driver records the move from each stroke's end to the next start
    moves = job.moves()
    rapid_ends = [m.end for m in moves if not m.down]
    assert len(rapid_ends) == len(strokes) + 1                 # one header per stroke + the return home
    assert rapid_ends[-1] == (0, 0)
    inter = [(m.start, m.end) for m in moves if not m.down][1:-1]
    expected = rapids[-len(inter):] if inter else []
    assert len(expected) == len(inter)
    for (s, e), (rs, re) in zip(inter, expected, strict=True):
        assert _mm(s) == pytest.approx(rs, abs=1e-6) and _mm(e) == pytest.approx(re, abs=1e-6)
    _self_consistent(job)


def _self_consistent(job: Job) -> None:
    moves = job.moves()
    assert [m.end for m in moves] == job.positions()
    for a, b in zip(moves, moves[1:], strict=False):
        assert a.end == b.start
    assert [m.end for m in moves if m.down] == [p for s in job.strokes() for p in s.points[1:]]


@settings(max_examples=150, deadline=None)
@given(job_args)
def test_decoder_agrees_with_preview_on_random_jobs(kw: dict) -> None:  # type: ignore[type-arg]
    data = gts_api.build_gts(kw["strokes"], speed=kw["speed"], pz=kw["pz"], dz=kw["dz"], mc=kw["mc"], vd=kw["vd"])
    _agree(data)


@pytest.mark.parametrize("name", sorted(MANIFEST["cases"]))
def test_decoder_agrees_with_preview_on_goldens(name: str) -> None:
    _agree((GOLDEN / MANIFEST["cases"][name]["output"]).read_bytes())


def test_moves_mark_pen_state() -> None:
    data = gts_api.build_gts([(100, 200, [(50, 0), (0, 50)])], speed=10)
    moves = read_job(data).moves()
    assert [(m.start, m.end, m.down) for m in moves] == [
        ((0, 0), (100, 200), False), ((100, 200), (150, 200), True), ((150, 200), (150, 250), True),
        ((150, 250), (0, 0), False)]
    assert all(m.offset == m.segment.offset for m in moves)


@pytest.mark.parametrize("tail", [b"\xff", b"\xff\xfd\x00\x01\x00\x00", b"\x00" * 7])
def test_still_refuses_unexplained_bytes(tail: bytes) -> None:
    data = gts_api.build_gts([(100, 200, [(50, 0)])], speed=10)
    with pytest.raises(GtsFormatError):
        read_job(data + tail)
