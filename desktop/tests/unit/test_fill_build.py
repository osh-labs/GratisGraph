"""F09 fill through build: recipe and parameter checks, intent, gate (H7, H10, S3), goldens, determinism."""
from __future__ import annotations

from dataclasses import replace

import pytest

from ggdesk import gts_read
from ggdesk.build import BuildError, build, gate_inputs
from ggdesk.formats import job as jf
from ggdesk.gate import run_gate
from ggdesk.library import Library, Selection
from ggdesk.model.geometry import Region
from ggdesk.model.job import FillOp, Job
from ggdesk.model.toolpath import NarrowRegion
from tests.conftest import DESKTOP
from tests.golden import make_goldens as mg

EXAMPLE = DESKTOP / "docs" / "examples" / "fill-square-hole.ggj"
NARROW = DESKTOP / "tests" / "fixtures" / "jobs" / "fill-narrow.ggj"
SEL = Selection(recipe="test-confirmed-fill", fixture="bare-bed")


@pytest.fixture(scope="module")
def lib() -> Library:
    return mg.snapshot_library()


def test_fill_goldens_present() -> None:
    assert {"fill_square_hole", "fill_hatch45", "fill_narrow"} <= set(mg.case_names())


def test_builds_and_passes_gate_without_h7(lib: Library) -> None:
    job = jf.load(EXAMPLE)
    r = build(job, lib, SEL)
    rep = run_gate(r.data, gate_inputs(r, SEL))
    assert rep.passed
    assert not [f for f in rep.findings if f.rule.startswith("H")]   # no H7 (outline/margin), H10 (intent) etc.
    assert {f.rule for f in rep.findings} == {"S4"}                   # bare-bed tolerance only


def test_contours_closed_in_the_bytes(lib: Library) -> None:
    r = build(jf.load(EXAMPLE), lib, SEL)
    closed = [s for s in gts_read.read_job(r.data).strokes() if s.points[0] == s.points[-1]]
    assert len(closed) == 2
    # outer contour: part (+-3.9) -> machine (50 +- 3.9) mm
    assert {(4610, 4610), (5390, 5390)} <= set(closed[0].points) | set(closed[1].points)


def test_narrow_regions_reach_intent_and_s3(lib: Library) -> None:
    sel = SEL
    r = build(jf.load(NARROW), lib, sel)
    assert [(n.op_index, n.region_index) for n in r.intent.narrow_regions] == [(0, 0), (0, 1)]
    assert all(isinstance(n, NarrowRegion) and n.width_mm < 0.2 for n in r.intent.narrow_regions)
    rep = run_gate(r.data, gate_inputs(r, sel))
    s3 = [f for f in rep.findings if f.rule == "S3"]
    assert len(s3) == 2 and rep.passed and not [f for f in rep.findings if f.rule.startswith("H")]


def test_bench_overrides_supply_tip_and_stepover(lib: Library) -> None:
    sel = Selection(recipe="scrap-rotary-diamond-fill", overrides={"tip_width_mm": 0.2, "stepover_mm": 0.2})
    a = build(jf.load(EXAMPLE), lib, sel).data
    b = build(jf.load(EXAMPLE), lib, SEL).data
    assert [s.points for s in gts_read.read_job(a).strokes()] == [s.points for s in gts_read.read_job(b).strokes()]


def test_refuses_unknown_tip_width(lib: Library) -> None:
    sel = Selection(recipe="scrap-rotary-diamond-fill", overrides={"stepover_mm": 0.1})
    with pytest.raises(BuildError, match=r"tip width.*rotary-diamond.*needs_measurement \(G3\)"):
        build(jf.load(EXAMPLE), lib, sel)


def test_refuses_unknown_stepover(lib: Library) -> None:
    sel = Selection(recipe="scrap-rotary-diamond-fill", overrides={"tip_width_mm": 0.2})
    with pytest.raises(BuildError, match=r"fill parameter unknown: .*stepover_mm is needs_measurement \(G6\)"):
        build(jf.load(EXAMPLE), lib, sel)


def test_refuses_fill_with_a_trace_recipe(lib: Library) -> None:
    job = replace(jf.load(EXAMPLE))
    with pytest.raises(BuildError, match=r"operations\[0\]: a fill operation needs a fill recipe.*'trace'"):
        build(job, lib, Selection(recipe="test-confirmed-trace"))
    op = job.operations[0]
    assert isinstance(op, FillOp)
    hinted = replace(job, operations=(replace(op, mode_hint="trace"),))
    with pytest.raises(BuildError, match=r"mode_hint 'trace' does not match recipe test-confirmed-fill"):
        build(hinted, lib, SEL)


def test_refuses_invalid_region(lib: Library) -> None:
    bow = Region(((0.0, 0.0), (1.0, 1.0), (1.0, 0.0), (0.0, 1.0)))
    with pytest.raises(BuildError, match=r"fill: operations\[0\]\.regions\[0\]: not a valid area"):
        build(Job("bench-scrap-40", (FillOp((bow,)),)), lib, SEL)


def test_same_bytes_twice_and_vertex_order(lib: Library) -> None:
    job = jf.load(EXAMPLE)
    a = build(job, lib, SEL).data
    assert build(job, lib, SEL).data == a
    op = job.operations[0]
    assert isinstance(op, FillOp)
    rev = tuple(Region(tuple(reversed(r.outer)), tuple(tuple(reversed(h)) for h in r.holes)) for r in op.regions)
    rot = tuple(Region(r.outer[2:] + r.outer[:2], tuple(h[1:] + h[:1] for h in r.holes)) for r in op.regions)
    for regions in (rev, rot):
        assert build(replace(job, operations=(replace(op, regions=regions),)), lib, SEL).data == a


def test_hatch45_golden_lines_are_diagonal(lib: Library) -> None:
    data = (mg.OUTPUTS / "fill_hatch45.m20").read_bytes()
    for s in gts_read.read_job(data).strokes():
        if len(s.points) == 2:
            (x0, y0), (x1, y1) = s.points
            # part +45 deg -> machine (dx, -dy); quantisation may move each end by half a unit
            assert abs(abs(x1 - x0) - abs(y1 - y0)) <= 1 and (x1 - x0) * (y1 - y0) <= 0
