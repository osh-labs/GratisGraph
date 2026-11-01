"""build(): refusals, intent, model code stamping, job hash, estimate, determinism."""
from __future__ import annotations

import hashlib
import struct
from collections import Counter
from dataclasses import replace

import gts_optimise
import pytest

from ggdesk import gts_read
from ggdesk.build import BuildError, build, gate_inputs, job_sha256
from ggdesk.formats import job as jf
from ggdesk.gate import run_gate
from ggdesk.library import Fact, Library, Selection, load_library
from ggdesk.model.geometry import Polyline, Region
from ggdesk.model.job import FillOp, Job, TraceOp
from ggdesk.model.toolpath import UStroke
from tests.conftest import DESKTOP

RECIPE = "scrap-rotary-diamond-trace"
SEL = Selection(recipe=RECIPE)
EXAMPLES = DESKTOP / "docs" / "examples"


@pytest.fixture(scope="module")
def lib() -> Library:
    return load_library(DESKTOP / "library", None, DESKTOP / "tests" / "fixtures" / "library")


def _job(*ops: TraceOp | FillOp) -> Job:
    return Job("bench-scrap-40", tuple(ops))


def _canon(s: UStroke | gts_read.Stroke) -> tuple[tuple[int, int], ...]:
    return min(tuple(s.points), tuple(reversed(s.points)))


def test_square_bytes_decode_to_the_intent(lib: Library) -> None:
    text = (EXAMPLES / "square-10mm.ggj").read_text(encoding="utf-8")
    r = build(jf.loads(text), lib, SEL, job_text=text)
    dec = gts_read.read_job(r.data)
    assert dec.model_code == 0x020D == struct.unpack_from(">H", r.data, 0x24)[0]
    assert dec.setup() == [("DR", 0), ("MC", 1), ("VS", 10), ("VZ", 5), ("PZ", 50), ("DZ", 500)]
    (stroke,) = dec.strokes()
    assert set(stroke.points) == {(4500, 4500), (5500, 4500), (5500, 5500), (4500, 5500)}
    assert stroke.points[0] == stroke.points[-1]          # closed: closing point appended
    assert r.intent.strokes == (UStroke(((4500, 5500), (5500, 5500), (5500, 4500), (4500, 4500), (4500, 5500))),)
    assert r.dropped_points == 0
    assert r.job_sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_bytes_match_driver_build_plus_stamp(lib: Library) -> None:
    import gts_api

    r = build(jf.load(EXAMPLES / "asymmetric-f-arrow.ggj"), lib, SEL)
    raw = gts_api.build_gts([s.to_driver() for s in r.ordered], speed=10, pz=50, dz=500, mc=1, vz=5, vd=None)
    assert r.data[:0x24] == raw[:0x24] and r.data[0x26:] == raw[0x26:]
    assert r.data[0x24:0x26] == b"\x02\x0d"


def test_decoded_strokes_equal_intent_as_multiset(lib: Library) -> None:
    for name in ("asymmetric-f-arrow.ggj", "square-10mm.ggj"):
        r = build(jf.load(EXAMPLES / name), lib, SEL)
        dec = gts_read.read_job(r.data).strokes()
        assert Counter(map(_canon, dec)) == Counter(map(_canon, r.intent.strokes))
        assert [s.points for s in dec] == [s.points for s in r.ordered]


def test_job_sha256_defaults_to_canonical_dump(lib: Library) -> None:
    job = jf.load(EXAMPLES / "square-10mm.ggj")
    r = build(job, lib, SEL)
    assert r.job_sha256 == hashlib.sha256(jf.dumps(job).encode("utf-8")).hexdigest() == job_sha256(job)


def test_estimate_uses_ordered_strokes_and_vs(lib: Library) -> None:
    r = build(jf.load(EXAMPLES / "asymmetric-f-arrow.ggj"), lib, SEL)
    assert r.estimate_s == gts_optimise.estimate_duration([s.to_driver() for s in r.ordered], speed=10)
    assert r.estimate_s > 0


def test_char_heights_in_intent(lib: Library) -> None:
    job = _job(TraceOp((Polyline(((0.0, 0.0), (1.0, 0.0))),), char_height_mm=3.5),
               TraceOp((Polyline(((0.0, 1.0), (1.0, 1.0))),)),
               TraceOp((Polyline(((0.0, 2.0), (1.0, 2.0))),), char_height_mm=2.0))
    assert build(job, lib, SEL).intent.char_heights_mm == (3.5, 2.0)


def test_dropped_points_counted(lib: Library) -> None:
    job = _job(TraceOp((Polyline(((0.0, 0.0), (0.003, 0.002))), Polyline(((0.0, 0.0), (5.0, 0.0))))))
    r = build(job, lib, SEL)
    assert r.dropped_points == 1 and len(r.intent.strokes) == 1


def test_overrides_reach_the_bytes(lib: Library) -> None:
    job = jf.load(EXAMPLES / "square-10mm.ggj")
    r = build(job, lib, Selection(recipe=RECIPE, overrides={"pz": 80, "vs": 25}))
    setup = dict(gts_read.read_job(r.data).setup())
    assert setup["PZ"] == 80 and setup["VS"] == 25 and setup["VZ"] == 5


def test_deterministic(lib: Library) -> None:
    job = jf.load(DESKTOP / "tests" / "fixtures" / "jobs" / "multi-stroke.ggj")
    a = build(job, lib, SEL)
    b = build(job, load_library(DESKTOP / "library", None, DESKTOP / "tests" / "fixtures" / "library"), SEL)
    assert a.data == b.data and a.intent == b.intent and a.estimate_s == b.estimate_s


def test_gate_inputs_carry_intent_and_hash(lib: Library) -> None:
    r = build(jf.load(EXAMPLES / "square-10mm.ggj"), lib, SEL)
    gi = gate_inputs(r, SEL)
    assert gi.intent is r.intent and gi.job_sha256 == r.job_sha256 and gi.selection == SEL
    rep = run_gate(r.data, gi)
    assert rep.bound_to(r.data) and rep.model_code == 0x020D


def test_build_does_not_judge_geometry(lib: Library) -> None:
    # Far outside the part and the work field: build emits it; the gate refuses it (H1/H7), not build.
    job = _job(TraceOp((Polyline(((-45.0, 0.0), (60.0, 0.0))),)))
    r = build(job, lib, SEL)
    assert gts_read.read_job(r.data).strokes()[0].points in (((500, 5000), (11000, 5000)),
                                                              ((11000, 5000), (500, 5000)))


# --- refusals ---------------------------------------------------------------

def test_refuses_unmeasured_placement(lib: Library) -> None:
    job = Job("dog-tag-blank", (TraceOp((Polyline(((0.0, 0.0), (1.0, 0.0))),)),))
    with pytest.raises(BuildError, match=r"cannot place the part.*dog-tag-nest.*needs_measurement"):
        build(job, lib, Selection(recipe=RECIPE, fixture="dog-tag-nest"))


def test_refuses_fill(lib: Library) -> None:
    job = jf.load(EXAMPLES / "fill-square-hole.ggj")
    with pytest.raises(BuildError, match=r"fill operations are not implemented in this build \(M2\)"):
        build(job, lib, SEL)
    mixed = _job(TraceOp((Polyline(((0.0, 0.0), (1.0, 0.0))),)),
                 FillOp((Region(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0))),)))
    with pytest.raises(BuildError, match=r"operations\[1\]: fill"):
        build(mixed, lib, SEL)


def test_refuses_mode_mismatch(lib: Library) -> None:
    job = _job(TraceOp((Polyline(((0.0, 0.0), (1.0, 0.0))),), mode_hint="fill"))
    with pytest.raises(BuildError, match=r"mode_hint 'fill' does not match recipe .* mode 'trace'"):
        build(job, lib, SEL)


def test_refuses_unknown_setup_value(lib: Library) -> None:
    rec = lib.recipes[RECIPE]
    unknown = Fact[int](None, needs_measurement=True, gap="GX", measure=("test",))
    broken = replace(lib, recipes={**lib.recipes, RECIPE: replace(rec, vs=unknown)})
    with pytest.raises(BuildError, match=r"setup value unknown.*vs.*GX"):
        build(_job(TraceOp((Polyline(((0.0, 0.0), (1.0, 0.0))),))), broken, SEL)


def test_refuses_unknown_model_code(lib: Library) -> None:
    m = lib.machines["m20-iq"]
    broken = replace(lib, machines={"m20-iq": replace(m, model_code=Fact[int](None, needs_measurement=True,
                                                                               gap="GX", measure=("t",)))})
    with pytest.raises(BuildError, match="model code is unknown"):
        build(_job(TraceOp((Polyline(((0.0, 0.0), (1.0, 0.0))),))), broken, SEL)


def test_refuses_empty_job(lib: Library) -> None:
    job = _job(TraceOp((Polyline(((0.0, 0.0), (0.001, 0.0))),)))
    with pytest.raises(BuildError, match="no strokes"):
        build(job, lib, SEL)
    with pytest.raises(BuildError, match="no strokes"):
        build(_job(), lib, SEL)


def test_refuses_bad_selection(lib: Library) -> None:
    job = jf.load(EXAMPLES / "square-10mm.ggj")
    with pytest.raises(BuildError, match="no recipe 'nope'"):
        build(job, lib, Selection(recipe="nope"))
    with pytest.raises(BuildError, match="no nest 'corner'"):
        build(job, lib, Selection(recipe=RECIPE, nest="corner"))
    with pytest.raises(BuildError, match="bench overrides need a draft recipe"):
        build(job, lib, Selection(recipe="test-confirmed-trace", overrides={"pz": 80}))
