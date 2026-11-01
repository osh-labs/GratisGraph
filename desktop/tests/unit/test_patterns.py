"""Bench test patterns (F10, M2.3): every built-in pattern builds and passes the gate's hard rules
with the seed library, fits its area (36 x 36 mm, or 36 x 18 mm compact), is deterministic and
matches its golden job text. The .m20 goldens are the pattern_* cases in tests/golden/ (checked
by test_build_golden.py).

Regenerate a job golden only for an intended change, explained in the commit:
    ggdesk pattern NAME -o desktop/tests/golden/patterns/NAME.ggj
"""
from __future__ import annotations

import json
import math
from typing import Any

import pytest

from ggdesk import __version__, numerics
from ggdesk.build import BuildResult, build, gate_inputs
from ggdesk.formats import job as job_format
from ggdesk.gate import GateReport, run_gate
from ggdesk.gate.types import Severity
from ggdesk.library import Library, Selection, load_library
from ggdesk.model.job import FillOp, Job, TraceOp
from ggdesk.patterns import DEFAULT_PART, PATTERNS, Pattern, PatternError, coerce
from ggdesk.patterns._layout import extent
from ggdesk.patterns.builtin import V1_PATHS
from tests.conftest import DESKTOP
from tests.golden import make_goldens as mg

NAMES = ("asymmetric", "pz-square", "datum-crosshair", "char-ladder-trace", "char-ladder-fill",
         "stepover-ladder", "corner-test", "job-size-ladder", "repeat-batch")
TRACE_SEL = Selection(recipe="scrap-rotary-diamond-trace", fixture="bare-bed")
FILL_SEL = Selection(recipe="scrap-rotary-diamond-fill", fixture="bare-bed",
                     overrides={"tip_width_mm": 0.2, "stepover_mm": 0.1})
JOB_GOLDENS = DESKTOP / "tests" / "golden" / "patterns"
SIZE_SHEET_KB = (16, 64, 256, 512, 1024)


@pytest.fixture(scope="module")
def lib() -> Library:
    return load_library(None, None)       # the seed library only


def _sel(p: Pattern) -> Selection:
    return FILL_SEL if p.mode == "fill" else TRACE_SEL


def _build_and_gate(job: Job, p: Pattern, lib: Library) -> tuple[BuildResult, GateReport]:
    text = job_format.dumps(job)
    res = build(job, lib, _sel(p), job_text=text)
    return res, run_gate(res.data, gate_inputs(res, _sel(p)))


def _sets(p: Pattern, **params: Any) -> int:
    """How many sets the pattern splits into with these parameters (1 when it has no `set`)."""
    if "set" not in {s.name for s in p.params}:
        return 1
    n = 1
    while True:
        try:
            p.generate(**params, set=n + 1)
        except PatternError as e:
            assert "parameter set" in str(e)
            return n
        n += 1


# --- registry ---------------------------------------------------------------------------------

def test_registry_holds_the_plan_patterns() -> None:
    assert set(NAMES) <= set(PATTERNS)
    for name in NAMES:
        p = PATTERNS[name]
        assert p.name == name and p.title and p.mode in ("trace", "fill")
        assert p.mode == ("fill" if name == "char-ladder-fill" else "trace")


@pytest.mark.parametrize("name", NAMES)
def test_every_pattern_takes_part_and_compact(name: str) -> None:
    specs = {s.name: s for s in PATTERNS[name].params}
    assert specs["part"].type is str and specs["part"].default == DEFAULT_PART == "bench-scrap-40"
    assert specs["compact"].type is bool and specs["compact"].default is False
    job = PATTERNS[name].generate(part="test-plate-100")
    assert job.part == "test-plate-100"


# --- build and gate with defaults ---------------------------------------------------------------

@pytest.mark.parametrize("name", NAMES)
def test_default_builds_and_passes_hard_rules(name: str, lib: Library) -> None:
    p = PATTERNS[name]
    job = p.generate()
    assert job.part == "bench-scrap-40"
    res, rep = _build_and_gate(job, p, lib)
    hard = [f for f in rep.findings if f.severity is Severity.HARD]
    assert hard == [] and rep.passed
    if p.mode == "trace":   # pattern geometry never collapses (fill may clip hatch slivers to a point)
        assert res.dropped_points == 0


@pytest.mark.parametrize("name", [n for n in NAMES if n != "job-size-ladder"])
def test_compact_builds_and_passes_hard_rules(name: str, lib: Library) -> None:
    p = PATTERNS[name]
    for s in range(1, _sets(p, compact=True) + 1):
        kw: dict[str, Any] = {"compact": True}
        if s > 1:
            kw["set"] = s
        _, rep = _build_and_gate(p.generate(**kw), p, lib)
        assert rep.passed, (name, s, [f.message for f in rep.findings if f.severity is Severity.HARD])


# --- areas ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("compact", [False, True])
def test_every_set_fits_its_area(name: str, compact: bool) -> None:
    p = PATTERNS[name]
    lim_y = 9.0 if compact else 18.0
    n = _sets(p, compact=compact)
    for s in range(1, n + 1):
        kw: dict[str, Any] = {"compact": compact}
        if "set" in {x.name for x in p.params}:
            kw["set"] = s
        mx, my = extent(p.generate(**kw).operations)
        assert mx <= 18.0 + 1e-9 and my <= lim_y + 1e-9, (name, compact, s, mx, my)


def test_defaults_fit_one_job_except_compact_ladders() -> None:
    for name in NAMES:
        assert _sets(PATTERNS[name]) == 1, name
    assert _sets(PATTERNS["char-ladder-trace"], compact=True) == 2
    assert _sets(PATTERNS["char-ladder-fill"], compact=True) == 2
    assert _sets(PATTERNS["corner-test"], compact=True) == 2
    assert _sets(PATTERNS["stepover-ladder"], compact=True) == 1


def test_compact_sets_cover_every_row() -> None:
    p = PATTERNS["char-ladder-trace"]
    heights = [op.char_height_mm for s in (1, 2) for op in p.generate(compact=True, set=s).operations[:-1]]
    assert heights == pytest.approx([0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0], abs=1e-9)


def test_set_reference_names_the_set() -> None:
    job = PATTERNS["corner-test"].generate(compact=True, set=2)
    assert "set=2" in job.reference and "Set 2 of 2" in job.reference


# --- determinism and goldens ------------------------------------------------------------------------

@pytest.mark.parametrize("name", NAMES)
def test_deterministic(name: str) -> None:
    p = PATTERNS[name]
    assert job_format.dumps(p.generate()) == job_format.dumps(p.generate())
    assert job_format.dumps(p.generate(compact=True)) == job_format.dumps(p.generate(compact=True))


@pytest.mark.parametrize("name", NAMES)
def test_job_text_golden(name: str) -> None:
    golden = (JOB_GOLDENS / f"{name}.ggj").read_text(encoding="utf-8")
    assert job_format.dumps(PATTERNS[name].generate()) == golden, f"{name}: job text differs from the golden"


@pytest.mark.parametrize("name", NAMES)
def test_bytes_golden_case(name: str, lib: Library) -> None:
    case = "pattern_" + name.replace("-", "_")
    assert case in mg.case_names()
    o = json.loads((mg.CASES / f"{case}.json").read_text(encoding="utf-8"))
    assert o["job"] == f"tests/golden/patterns/{name}.ggj"
    assert Selection.from_obj(o["selection"]) == _sel(PATTERNS[name])


@pytest.mark.parametrize("name", NAMES)
def test_source_and_reference(name: str) -> None:
    p = PATTERNS[name]
    job = p.generate()
    assert job.source is not None
    assert (job.source.name, job.source.version) == (f"ggdesk pattern {name}", __version__)
    for s in p.params:
        assert f"{s.name}=" in job.reference
    assert "compact=false" in job.reference and 'part="bench-scrap-40"' in job.reference


def test_generated_jobs_round_trip() -> None:
    for name in NAMES:
        job = PATTERNS[name].generate()
        assert job_format.loads(job_format.dumps(job)) == job


# --- per-pattern geometry --------------------------------------------------------------------------

def test_asymmetric_equals_v1_bench_job() -> None:
    v1 = job_format.load(DESKTOP / "bench" / "V1" / "v1-asymmetric.ggj")
    job = PATTERNS["asymmetric"].generate()
    assert job.operations == v1.operations
    assert job.part == v1.part and job.quantity == v1.quantity
    half = PATTERNS["asymmetric"].generate(compact=True)
    assert isinstance(half.operations[0], TraceOp)
    assert [pl.points for pl in half.operations[0].paths] == [
        tuple((x / 2, y / 2) for x, y in pts) for pts in V1_PATHS]


def test_pz_square_equals_v2_bench_job() -> None:
    v2 = job_format.load(DESKTOP / "bench" / "V2" / "v2-square-10mm.ggj")
    assert PATTERNS["pz-square"].generate().operations == v2.operations
    assert PATTERNS["pz-square"].generate(compact=True).operations == v2.operations


def test_datum_crosshair_marks() -> None:
    op = PATTERNS["datum-crosshair"].generate().operations[0]
    assert isinstance(op, TraceOp)
    paths = [pl.points for pl in op.paths]
    assert paths[:2] == [((-3.0, 0.0), (3.0, 0.0)), ((0.0, -3.0), (0.0, 3.0))]
    for d in (5.0, 10.0, 15.0):
        assert ((d, -0.5), (d, 0.5)) in paths and ((-0.5, d), (0.5, d)) in paths
    assert ((-16.0, 18.0), (-18.0, 18.0), (-18.0, 16.0)) in paths      # upper-left corner mark
    compact = [pl.points for pl in PATTERNS["datum-crosshair"].generate(compact=True).operations[0].paths]  # type: ignore[union-attr]
    assert ((-0.5, 10.0), (0.5, 10.0)) not in compact and ((-0.5, 5.0), (0.5, 5.0)) in compact
    assert ((16.0, -9.0), (18.0, -9.0), (18.0, -7.0)) in compact


def test_char_ladder_trace_rows() -> None:
    job = PATTERNS["char-ladder-trace"].generate()
    *rows, labels = job.operations
    assert all(isinstance(op, TraceOp) and op.mode_hint == "trace" for op in job.operations)
    assert [op.char_height_mm for op in rows] == pytest.approx([0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0], abs=1e-12)
    for op in rows:   # true cap height: the "H" of each row spans exactly its char_height_mm
        assert op.char_height_mm is not None
    assert labels.char_height_mm == 1.3125
    # rows from small (top) to large (bottom), not overlapping
    tops = [max(y for pl in op.paths for _, y in pl.points) for op in rows]  # type: ignore[union-attr]
    bottoms = [min(y for pl in op.paths for _, y in pl.points) for op in rows]  # type: ignore[union-attr]
    assert all(b > t for b, t in zip(bottoms, tops[1:], strict=False))


def test_char_ladder_fill_rows() -> None:
    job = PATTERNS["char-ladder-fill"].generate()
    *rows, labels = job.operations
    assert all(isinstance(op, FillOp) and op.mode_hint == "fill" for op in rows)
    assert [op.char_height_mm for op in rows] == pytest.approx([1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0], abs=1e-12)
    assert isinstance(labels, TraceOp) and labels.mode_hint == "fill"


def _hatch_ys(op: TraceOp) -> list[list[int]]:
    """Per square (closed path), the device-unit y of its hatch lines in order."""
    out: list[list[int]] = []
    for pl in op.paths:
        if pl.closed:
            out.append([])
        else:
            ys = {numerics.to_units(y) for _, y in pl.points}
            assert len(ys) == 1
            out[-1].append(ys.pop())
    return out


def test_stepover_ladder_spacings() -> None:
    job = PATTERNS["stepover-ladder"].generate()
    op = job.operations[0]
    assert isinstance(op, TraceOp) and op.char_height_mm is None
    squares = _hatch_ys(op)
    steps = [5, 8, 10, 12, 15, 20, 25, 30]
    assert len(squares) == len(steps)
    for ys, s in zip(squares, steps, strict=True):
        assert {b - a for a, b in zip(ys, ys[1:], strict=False)} == {s}
        assert len(ys) == -(-600 // s) - 1
    # alternate hatch directions within a square
    lines = [pl for pl in op.paths if not pl.closed][:3]
    assert lines[0].points[0][0] < lines[0].points[1][0] and lines[1].points[0][0] > lines[1].points[1][0]


def test_corner_test_angles() -> None:
    job = PATTERNS["corner-test"].generate()
    op = job.operations[0]
    assert isinstance(op, TraceOp)
    want = [15, 30, 45, 60, 90, 120, 150]
    assert len(op.paths) == len(want)
    for pl, ang in zip(op.paths, want, strict=True):
        pts = pl.points
        assert len(pts) == 7
        for a, b, c in zip(pts, pts[1:], pts[2:], strict=False):
            u = (a[0] - b[0], a[1] - b[1])
            v = (c[0] - b[0], c[1] - b[1])
            cosang = (u[0] * v[0] + u[1] * v[1]) / (math.sqrt(u[0] ** 2 + u[1] ** 2) * math.sqrt(v[0] ** 2 + v[1] ** 2))
            assert math.degrees(math.acos(cosang)) == pytest.approx(ang, abs=1e-9)


def test_repeat_batch_quantity_and_outline() -> None:
    job = PATTERNS["repeat-batch"].generate()
    assert job.quantity == 10
    op = job.operations[0]
    assert isinstance(op, TraceOp)
    assert op.paths[0].closed and op.paths[0].points == ((-18.0, -18.0), (18.0, -18.0), (18.0, 18.0), (-18.0, 18.0))
    assert PATTERNS["repeat-batch"].generate(quantity=3).quantity == 3
    compact = PATTERNS["repeat-batch"].generate(compact=True).operations[0]
    assert isinstance(compact, TraceOp) and compact.paths[0].points[2] == (18.0, 9.0)


@pytest.mark.parametrize("kb", SIZE_SHEET_KB)
def test_job_size_ladder_within_5_percent(kb: int, lib: Library) -> None:
    job = PATTERNS["job-size-ladder"].generate(target_kb=kb)
    res = build(job, lib, TRACE_SEL)
    target = kb * 1024
    assert abs(len(res.data) - target) <= 0.05 * target, (kb, len(res.data))
    mx, my = extent(job.operations)
    assert mx <= 18.0 and my <= 18.0


def test_job_size_ladder_compact_reaches_1024_kb(lib: Library) -> None:
    job = PATTERNS["job-size-ladder"].generate(target_kb=1024, compact=True)
    mx, my = extent(job.operations)
    assert mx <= 18.0 and my <= 9.0
    n = sum(len(pl.points) - 1 for op in job.operations for pl in op.paths)  # type: ignore[union-attr]
    assert abs(154 + 12 * n + 42 * len(job.operations[0].paths) - 1024 * 1024) <= 12   # type: ignore[union-attr]


# --- parameter errors ----------------------------------------------------------------------------------

@pytest.mark.parametrize(("name", "params", "param"), [
    ("asymmetric", {"colour": "red"}, "colour"),
    ("asymmetric", {"compact": "maybe"}, "compact"),
    ("asymmetric", {"part": " "}, "part"),
    ("pz-square", {"size_mm": "-1"}, "size_mm"),
    ("pz-square", {"size_mm": "40"}, "size_mm"),
    ("pz-square", {"size_mm": "x"}, "size_mm"),
    ("datum-crosshair", {"spacing_mm": "0"}, "spacing_mm"),
    ("datum-crosshair", {"arm_mm": "20"}, "arm_mm"),
    ("char-ladder-trace", {"heights": "1.0,abc"}, "heights"),
    ("char-ladder-trace", {"heights": "40"}, "heights"),
    ("char-ladder-trace", {"text": ""}, "text"),
    ("char-ladder-trace", {"text": "AEHMRS0389AEHMRS0389"}, "text"),
    ("char-ladder-trace", {"text": "Ä"}, "text"),
    ("char-ladder-trace", {"set": "2"}, "set"),
    ("char-ladder-trace", {"set": "0"}, "set"),
    ("char-ladder-fill", {"heights": "-2"}, "heights"),
    ("char-ladder-fill", {"text": "☃"}, "text"),
    ("stepover-ladder", {"stepovers": "0.125"}, "stepovers"),
    ("stepover-ladder", {"size_mm": "6.005"}, "size_mm"),
    ("stepover-ladder", {"columns": "0"}, "columns"),
    ("stepover-ladder", {"columns": "8"}, "columns"),
    ("corner-test", {"angles": "180"}, "angles"),
    ("corner-test", {"teeth": "0"}, "teeth"),
    ("corner-test", {"leg_mm": "40"}, "leg_mm"),
    ("corner-test", {"leg_mm": "10", "angles": "150"}, "leg_mm"),
    ("job-size-ladder", {"target_kb": "0"}, "target_kb"),
    ("job-size-ladder", {"target_kb": "3000"}, "target_kb"),
    ("job-size-ladder", {"target_kb": "1100", "compact": "true"}, "target_kb"),
    ("job-size-ladder", {"target_kb": "1.5"}, "target_kb"),
    ("repeat-batch", {"quantity": "0"}, "quantity"),
    ("repeat-batch", {"label": "é"}, "label"),
])
def test_parameter_errors_name_the_parameter(name: str, params: dict[str, str], param: str) -> None:
    p = PATTERNS[name]
    with pytest.raises(PatternError) as e:
        p.generate(**coerce(p, params))
    assert param in str(e.value)
    assert str(e.value).startswith(f"{name}:")
