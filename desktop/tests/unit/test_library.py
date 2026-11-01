from __future__ import annotations

from pathlib import Path

import pytest

from ggdesk.formats import job as jf
from ggdesk.library import (
    OverrideError,
    Selection,
    SelectionError,
    UnmeasuredError,
    load_library,
    resolve,
    unmeasured,
)
from ggdesk.library.load import EntryError, load_entry
from tests.conftest import DESKTOP, REPO

SEED = DESKTOP / "library"
TESTLIB = DESKTOP / "tests" / "fixtures" / "library"
ASYM = jf.load(DESKTOP / "docs" / "examples" / "asymmetric-f-arrow.ggj")


def test_seed_library_is_valid() -> None:
    lib = load_library(SEED, check_paths=REPO)
    assert lib.errors == ()
    assert set(lib.machines) == {"m20-iq"}
    assert {"bare-bed", "dog-tag-nest"} <= set(lib.fixtures)
    assert {"dog-tag-blank", "bench-scrap-40"} <= set(lib.parts)


def test_test_overlay_is_valid() -> None:
    lib = load_library(SEED, None, TESTLIB, check_paths=REPO)
    assert lib.errors == ()


def test_seed_machine_values() -> None:
    m = load_library(SEED).machines["m20-iq"]
    assert m.model_code.value == 0x020D and m.model_code.confidence == "CONFIRMED"
    assert m.opcodes_allowed == ("DR", "MC", "VS", "VZ", "PZ", "DZ", "VD", "ZA", "PD", "PU", "JF")
    assert m.opcodes_reserved == ("LB", "NR")
    assert not m.max_job_bytes.known and m.max_job_bytes.gap == "G9"
    assert m.ranges["pz"].value is not None and m.ranges["pz"].value.max == 100


def test_run3_recipe() -> None:
    r = load_library(SEED).recipes["scrap-rotary-diamond-trace"]
    assert r.status == "draft"
    assert r.setup_values() == {"mc": 1, "vs": 10, "vz": 5, "pz": 50, "dz": 500, "vd": None}
    assert r.manual.knob_notches.value == 5 and r.manual.pressure.value == 2


def test_every_unmeasured_fact_names_gap_and_procedure() -> None:
    facts = unmeasured(load_library(SEED))
    assert facts
    for kind, eid, field, fact in facts:
        assert fact.gap and fact.gap.startswith("G"), (kind, eid, field)
        assert fact.measure, (kind, eid, field)


def test_resolve_bare_bed() -> None:
    lib = load_library(SEED)
    res = resolve(lib, ASYM, Selection(recipe="scrap-rotary-diamond-trace"))
    assert res.placement is not None and res.placement.origin_mm == (50.0, 50.0)
    assert res.placement.to_machine((-14.0, 14.0)) == (36.0, 36.0)   # F top: left and away from operator
    assert res.keep_outs_machine == ()
    assert res.tip_width_mm is None
    assert [e.id for e in res.entries][:5] == ["m20-iq", "rotary-diamond", "bench-scrap-40", "bare-bed",
                                               "scrap-rotary-diamond-trace"]


def test_resolve_unmeasured_nest_gives_no_placement() -> None:
    lib = load_library(SEED)
    res = resolve(lib, ASYM, Selection(recipe="scrap-rotary-diamond-trace", fixture="dog-tag-nest"))
    assert res.placement is None and res.keep_outs_machine is None
    with pytest.raises(UnmeasuredError, match="G2"):
        res.fixture.placement("centre")


def test_overrides() -> None:
    lib = load_library(SEED)
    sel = Selection(recipe="scrap-rotary-diamond-trace", overrides={"pz": 80, "tip_width_mm": 0.2})
    res = resolve(lib, ASYM, sel)
    assert res.recipe.pz.value == 80 and res.recipe.pz.confidence == "DEFINED"
    assert res.tip_width_mm == 0.2
    assert dict(res.recipe.overrides) == {"pz": 80, "tip_width_mm": 0.2}
    with pytest.raises(OverrideError):
        resolve(lib, ASYM, Selection(recipe="scrap-rotary-diamond-trace", overrides={"mc": 0}))
    with pytest.raises(OverrideError):
        resolve(lib, ASYM, Selection(recipe="scrap-rotary-diamond-trace", overrides={"pz": 1.5}))


def test_confirmed_recipe_refuses_overrides() -> None:
    lib = load_library(SEED, None, TESTLIB)
    with pytest.raises(OverrideError, match="confirmed"):
        resolve(lib, ASYM, Selection(recipe="test-confirmed-trace", overrides={"pz": 40}))


def test_per_job_keep_outs_only_where_allowed() -> None:
    lib = load_library(SEED, None, TESTLIB)
    ko = (((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)),)
    res = resolve(lib, ASYM, Selection(recipe="scrap-rotary-diamond-trace", extra_keep_outs=ko))
    assert res.keep_outs_machine == ko
    with pytest.raises(SelectionError):
        resolve(lib, ASYM, Selection(recipe="scrap-rotary-diamond-trace", fixture="test-jaws",
                                     extra_keep_outs=ko))


def test_unknown_ids() -> None:
    lib = load_library(SEED)
    with pytest.raises(SelectionError, match="recipe"):
        resolve(lib, ASYM, Selection(recipe="nope"))


def _entry(tmp_path: Path, kind: str, body: str, name: str = "x") -> Path:
    d = tmp_path / f"{kind}s"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.toml"
    p.write_text(f'schema_version = 1\nkind = "{kind}"\nid = "{name}"\nversion = 1\nname = "X"\n' + body,
                 encoding="utf-8")
    return p


SRC = '[sources.s]\ntitle = "t"\nurl = "https://example.invalid/doc"\nkind = "maker"\n'


@pytest.mark.parametrize(("body", "msg"), [
    ('type = "rotary_diamond"\n' + SRC + '[needs_spindle]\nvalue = true\nsrc = "s"\nref = "r"\nconfidence = "SURE"\n'
     '[needs_nose]\nnull = true\n[tip_width_mm]\nnull = true\n', "confidence"),
    ('type = "rotary_diamond"\n' + SRC + '[needs_spindle]\nvalue = true\nsrc = "nope"\nref = "r"\n'
     'confidence = "STRONG"\n'
     '[needs_nose]\nnull = true\n[tip_width_mm]\nnull = true\n', "src"),
    ('type = "rotary_diamond"\n[needs_spindle]\nnull = true\n[needs_nose]\nnull = true\n'
     '[tip_width_mm]\nnull = true\nneeds_measurement = true\n', "gap"),
    ('type = "rotary_diamond"\n[needs_spindle]\nnull = true\n[needs_nose]\nnull = true\n'
     '[tip_width_mm]\nnull = true\nneeds_measurement = true\ngap = "G3"\nmeasure = []\n', "measure"),
    ('type = "laser"\n[needs_spindle]\nnull = true\n[needs_nose]\nnull = true\n[tip_width_mm]\nnull = true\n', "type"),
])
def test_invalid_tool_entries(tmp_path: Path, body: str, msg: str) -> None:
    p = _entry(tmp_path, "tool", body)
    with pytest.raises(EntryError, match=msg):
        load_entry(p, "tool")


def test_hypothesis_cannot_set_hard_limit(tmp_path: Path) -> None:
    p = _entry(tmp_path, "part", 'material = "scrap-aluminum"\n' + SRC +
               '[outline]\nvalue = { kind = "rect", width_mm = 10.0, height_mm = 10.0 }\nsrc = "s"\nref = "r"\n'
               'confidence = "HYPOTHESIS"\n[holes]\nnull = true\n[keep_out_margin_mm]\nnull = true\n'
               '[thickness_mm]\nnull = true\n')
    with pytest.raises(EntryError, match="HYPOTHESIS"):
        load_entry(p, "part")


def test_id_must_match_file(tmp_path: Path) -> None:
    p = _entry(tmp_path, "material", "", name="y")
    p.write_text(p.read_text().replace('id = "y"', 'id = "z"'))
    with pytest.raises(EntryError, match="file name"):
        load_entry(p, "material")


def test_invalid_entry_is_listed_not_skipped(tmp_path: Path) -> None:
    _entry(tmp_path, "tool", 'type = "laser"\n')
    lib = load_library(SEED, tmp_path)
    assert len(lib.errors) == 1 and "x.toml" in str(lib.errors[0])
    assert "x" not in lib.tools


def test_user_library_overrides_by_id(tmp_path: Path) -> None:
    (tmp_path / "recipes").mkdir()
    src = (SEED / "recipes" / "scrap-rotary-diamond-trace.toml").read_text()
    (tmp_path / "recipes" / "scrap-rotary-diamond-trace.toml").write_text(
        src.replace("\nversion = 1", "\nversion = 2", 1))
    lib = load_library(SEED, tmp_path)
    assert lib.recipes["scrap-rotary-diamond-trace"].ref.version == 2


def test_rounded_outline_is_flattened_within_chord() -> None:
    from ggdesk import numerics
    from ggdesk.library.model import Outline
    o = Outline("rect", 50.0, 28.0, 3.0)
    poly = o.polygon(0.01)
    assert len(poly) > 8
    for x, y in poly:
        assert abs(x) <= 25.0 + 1e-9 and abs(y) <= 14.0 + 1e-9
    # every vertex on a corner arc lies on the radius
    cx, cy = 25.0 - 3.0, 14.0 - 3.0
    for x, y in poly:
        if x > cx and y > cy:
            assert abs(numerics.length(x - cx, y - cy) - 3.0) < 1e-9


def test_entry_hash_ignores_line_endings(tmp_path: Path) -> None:
    src = SEED / "tools" / "rotary-diamond.toml"
    crlf = tmp_path / "tools"
    crlf.mkdir()
    (crlf / "rotary-diamond.toml").write_bytes(src.read_bytes().replace(b"\n", b"\r\n"))
    a, _ = load_entry(src, "tool")
    b, _ = load_entry(crlf / "rotary-diamond.toml", "tool")
    assert a.ref.sha256 == b.ref.sha256
