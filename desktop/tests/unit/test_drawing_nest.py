"""M2.5: parametric nest plate drawing (SVG and DXF R12) and `ggdesk drawing nest`."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

import pytest

from ggdesk.cli import main
from ggdesk.drawings import nest as nest_mod
from ggdesk.drawings.nest import NOT_FOR_CUTTING, PLACEHOLDERS, NestDrawingError, nest_plate
from ggdesk.library import Fact, Library, load_library
from ggdesk.library.model import Outline

DESKTOP = Path(__file__).resolve().parents[2]
FIXTURES = DESKTOP / "tests" / "fixtures" / "library"


@pytest.fixture(scope="module")
def lib() -> Library:
    lib = load_library(None, None, FIXTURES)
    assert not lib.errors, lib.errors
    return lib


# --- a tiny DXF reader (test only) -------------------------------------------------------------------

def read_dxf(text: str) -> tuple[dict[str, list[tuple[int, str]]], list[tuple[str, dict[int, list[str]]]]]:
    """(header variables, entities). An entity is (type, {code: [values]}); POLYLINE carries its vertices
    as code -1 entries "x,y"."""
    lines = text.split("\n")
    assert lines[-1] == ""
    pairs = [(int(lines[i].strip()), lines[i + 1]) for i in range(0, len(lines) - 1, 2)]
    header: dict[str, list[tuple[int, str]]] = {}
    entities: list[tuple[str, dict[int, list[str]]]] = []
    section = None
    var = None
    current: tuple[str, dict[int, list[str]]] | None = None
    poly: tuple[str, dict[int, list[str]]] | None = None
    for code, value in pairs:
        if code == 0 and value == "SECTION":
            section = "?"
            continue
        if code == 2 and section == "?":
            section = value
            continue
        if code == 0 and value == "ENDSEC":
            section = None
            continue
        if section == "HEADER":
            if code == 9:
                var = value
                header[var] = []
            elif var is not None:
                header[var].append((code, value))
        elif section == "ENTITIES":
            if code == 0:
                if current is not None and current[0] == "VERTEX" and poly is not None:
                    v = current[1]
                    poly[1].setdefault(-1, []).append(f"{v[10][0]},{v[20][0]}")
                if value == "VERTEX":
                    assert poly is not None
                    current = ("VERTEX", {})
                    continue
                if value == "SEQEND":
                    assert poly is not None
                    entities.append(poly)
                    poly, current = None, ("SEQEND", {})
                    continue
                current = (value, {})
                if value == "POLYLINE":
                    poly = current
                else:
                    entities.append(current)
            else:
                assert current is not None
                current[1].setdefault(code, []).append(value)
    return header, entities


def on(entities: list[tuple[str, dict[int, list[str]]]], layer: str) -> list[tuple[str, dict[int, list[str]]]]:
    return [e for e in entities if e[1][8][0] == layer]


def f(e: tuple[str, dict[int, list[str]]], code: int) -> float:
    return float(e[1][code][0])


# --- measured case: test part + test fixture ----------------------------------------------------------

def test_measured_has_no_placeholder(lib: Library) -> None:
    d = nest_plate(lib.parts["test-tag-50x28"], lib.fixtures["test-clamps"])
    assert d.unmeasured == ()
    for text in (d.svg, d.dxf, "\n".join(d.title)):
        assert "UNMEASURED" not in text
        assert NOT_FOR_CUTTING not in text
        assert "placeholder" not in text
    drawn_from = next(t for t in d.title if t.startswith("Drawn from:"))
    assert "part test-tag-50x28 v1" in drawn_from
    assert "fixture test-clamps v1" in drawn_from
    assert lib.parts["test-tag-50x28"].ref.sha256[:12] in drawn_from
    assert "Drawn from: part test-tag-50x28 v1" in d.svg and "Drawn from: part test-tag-50x28 v1" in d.dxf
    # Nest origin (50, 50) from the datum corner; pocket 50.4 x 28.4 (0.2 clearance); margin 10.
    assert d.plate_mm == pytest.approx((85.2, 74.2))


def test_dxf_pocket_and_hole_geometry(lib: Library) -> None:
    d = nest_plate(lib.parts["test-tag-50x28"], lib.fixtures["test-clamps"])
    header, ents = read_dxf(d.dxf)
    assert header["$ACADVER"] == [(1, "AC1009")]
    assert header["$INSUNITS"] == [(70, "4")]
    assert {e[1][8][0] for e in ents} == set(nest_mod.LAYERS)
    # Plate: closed 4-vertex polyline 85.2 x 74.2 from the origin.
    (plate,) = on(ents, "OUTLINE")
    assert plate[0] == "POLYLINE" and plate[1][70] == ["1"]
    assert plate[1][-1] == ["0,0", "85.2,0", "85.2,74.2", "0,74.2"]
    # Pocket: rounded rect 50.4 x 28.4, R 3.2, centred on the part origin. In the view frame (+Y up,
    # front-left corner at 0,0) the part origin is at (50, 74.2 - 50) = (50, 24.2).
    pocket = on(ents, "POCKET")
    arcs = [e for e in pocket if e[0] == "ARC"]
    lines = [e for e in pocket if e[0] == "LINE"]
    assert len(arcs) == 4 and len(lines) == 4 and len(pocket) == 8
    assert {f(a, 40) for a in arcs} == {3.2}
    xs = [f(a, 10) + s * 3.2 for a in arcs for s in (-1, 1)]
    ys = [f(a, 20) + s * 3.2 for a in arcs for s in (-1, 1)]
    assert (min(xs), max(xs)) == pytest.approx((24.8, 75.2))
    assert (min(ys), max(ys)) == pytest.approx((10.0, 38.4))
    centres = sorted((f(a, 10), f(a, 20), f(a, 50), f(a, 51)) for a in arcs)
    # Coordinates are printed to 0.0001 mm and read back exactly.
    assert centres == [(28.0, 13.2, 180.0, 270.0), (28.0, 35.2, 90.0, 180.0),
                       (72.0, 13.2, 270.0, 0.0), (72.0, 35.2, 0.0, 90.0)]
    # Lines join the arcs' tangent points.
    ends = sorted((f(e, 10), f(e, 20), f(e, 11), f(e, 21)) for e in lines)
    assert ends == [(24.8, 35.2, 24.8, 13.2), (28.0, 10.0, 72.0, 10.0),
                    (72.0, 38.4, 28.0, 38.4), (75.2, 13.2, 75.2, 35.2)]
    # Hole: 3 mm round at part (-21, 0) -> view (29, 24.2).
    (hole,) = on(ents, "HOLE")
    assert hole[0] == "CIRCLE"
    assert (f(hole, 10), f(hole, 20), f(hole, 40)) == pytest.approx((29.0, 24.2, 1.5))
    # Part origin crosshair crosses at (50, 24.2).
    datum_lines = [e for e in on(ents, "DATUM") if e[0] == "LINE"]
    h = [e for e in datum_lines if f(e, 20) == f(e, 21) == pytest.approx(24.2)]
    v = [e for e in datum_lines if f(e, 10) == f(e, 11) == pytest.approx(50.0)]
    assert h and v
    texts = [e[1][1][0] for e in on(ents, "DIMENSION") if e[0] == "TEXT"]
    for t in ("PLATE 85.20", "PLATE 74.20", "ORIGIN X 50.00", "ORIGIN Y 50.00", "POCKET 50.40", "POCKET 28.40"):
        assert t in texts


def test_svg_is_self_contained_mm_and_matches_geometry(lib: Library) -> None:
    d = nest_plate(lib.parts["test-tag-50x28"], lib.fixtures["test-clamps"])
    root = ET.fromstring(d.svg.split("\n", 1)[1])
    assert root.attrib["width"].endswith("mm") and root.attrib["height"].endswith("mm")
    vb = [float(v) for v in root.attrib["viewBox"].split()]
    assert vb[2] == pytest.approx(float(root.attrib["width"][:-2]))
    assert "href" not in d.svg and "<image" not in d.svg and "@import" not in d.svg
    assert re.findall(r"https?://[^\"]+", d.svg) == ["http://www.w3.org/2000/svg"]
    ns = "{http://www.w3.org/2000/svg}"
    groups = {g.attrib["id"]: g for g in root.iter(f"{ns}g")}
    assert set(groups) == set(nest_mod.LAYERS)
    (circle,) = groups["HOLE"].iter(f"{ns}circle")
    assert (float(circle.attrib["cx"]), float(circle.attrib["cy"]), float(circle.attrib["r"])) == \
        pytest.approx((29.0, -24.2, 1.5))
    assert len(list(groups["POCKET"].iter(f"{ns}path"))) == 4
    # Every layer colour is a module constant.
    for colour in nest_mod.SVG_COLOUR.values():
        assert colour in d.svg


def test_deterministic_text(lib: Library) -> None:
    a = nest_plate(lib.parts["test-tag-50x28"], lib.fixtures["test-clamps"])
    b = nest_plate(lib.parts["test-tag-50x28"], lib.fixtures["test-clamps"])
    assert a == b
    assert "-0," not in a.svg and "\n-0\n" not in a.dxf
    assert "\r" not in a.svg + a.dxf
    assert all(ord(ch) < 128 for ch in a.dxf)


def test_parameters_change_the_plate(lib: Library) -> None:
    d = nest_plate(lib.parts["test-tag-50x28"], lib.fixtures["test-clamps"], plate_margin_mm=5.0,
                   pocket_clearance_mm=0.5)
    # pocket 51 x 29 (R 3.5); plate = origin + half pocket + margin.
    assert d.plate_mm == pytest.approx((50 + 25.5 + 5, 50 + 14.5 + 5))
    _, ents = read_dxf(d.dxf)
    assert {f(a, 40) for a in on(ents, "POCKET") if a[0] == "ARC"} == {3.5}
    assert "pocket clearance 0.50 mm per side" in d.svg


# --- unmeasured case: the seed dog tag blank and its nest ---------------------------------------------

def test_unmeasured_dog_tag_lists_every_placeholder(lib: Library) -> None:
    d = nest_plate(lib.parts["dog-tag-blank"], lib.fixtures["dog-tag-nest"])
    assert len(d.unmeasured) == 4
    joined = "\n".join(d.unmeasured)
    for what in ("dog-tag-blank outline (G1)", "dog-tag-blank holes (G1)", "dog-tag-blank thickness_mm (G1)",
                 "dog-tag-nest nest centre origin_mm (G2)"):
        assert what in joined
    assert d.title[1] == NOT_FOR_CUTTING
    assert NOT_FOR_CUTTING in d.svg and NOT_FOR_CUTTING in d.dxf
    assert re.search(r'class="note warn"[^>]*font-size="5">NOT FOR CUTTING', d.svg)
    for label in ("UNMEASURED (G1)", "UNMEASURED (G2)", "UNMEASURED (G1, G2)"):
        assert label in d.svg and label in d.dxf
    # Every dimension text in the DXF carries the label (all derive from an unmeasured fact here).
    _, ents = read_dxf(d.dxf)
    dims = [e[1][1][0] for e in on(ents, "DIMENSION") if e[0] == "TEXT"]
    assert len(dims) == 6 and all("UNMEASURED (G" in t for t in dims)
    # Placeholder geometry: 50 x 30 R 4 blank -> pocket 50.4 x 30.4, plate 70.4 x 50.4.
    assert d.plate_mm == pytest.approx((70.4, 50.4))


def test_partly_measured_lists_only_the_unknowns(lib: Library) -> None:
    d = nest_plate(lib.parts["test-tag-50x28"], lib.fixtures["dog-tag-nest"])
    assert len(d.unmeasured) == 1 and "origin_mm (G2)" in d.unmeasured[0]
    assert "UNMEASURED (G1" not in d.svg
    assert "ORIGIN X 35.20 UNMEASURED (G2)" in d.svg
    assert "POCKET 50.40<" in d.svg       # pocket width comes from known facts: no label
    assert NOT_FOR_CUTTING in d.svg
    part = replace(lib.parts["dog-tag-blank"], thickness_mm=lib.parts["test-tag-50x28"].thickness_mm)
    d2 = nest_plate(part, lib.fixtures["test-clamps"])
    assert [u.split(" (")[0] for u in d2.unmeasured] == ["part dog-tag-blank outline", "part dog-tag-blank holes"]


def test_placeholder_table_is_documented() -> None:
    src = Path(nest_mod.__file__).read_text(encoding="utf-8")
    block = src.split("PLACEHOLDERS: dict", 1)[1].split("\n}\n", 1)[0]
    entries = re.findall(r'^    "([a-z_.]+)":', block, re.M)
    assert sorted(entries) == sorted(PLACEHOLDERS)
    assert block.count("# Drawing placeholder, not a measurement") == len(PLACEHOLDERS)
    for _, ph in PLACEHOLDERS.values():
        assert ph.gap in ("G1", "G2")


def test_polygon_outline_offsets_by_clearance(lib: Library) -> None:
    base = lib.parts["test-tag-50x28"]
    rect_poly = Outline("polygon", points=((-10.0, -5.0), (10.0, -5.0), (10.0, 5.0), (-10.0, 5.0)))
    part = replace(base, outline=Fact(rect_poly, "test", "test", "DEFINED"),
                   holes=Fact((), "test", "test", "DEFINED"))
    d = nest_plate(part, lib.fixtures["test-clamps"], pocket_clearance_mm=1.0)
    _, ents = read_dxf(d.dxf)
    (pocket,) = on(ents, "POCKET")
    assert pocket[0] == "POLYLINE" and pocket[1][70] == ["1"]
    pts = [tuple(float(v) for v in p.split(",")) for p in pocket[1][-1]]
    # Origin (50, 50); plate height 50 + 6 + 10 = 66; part origin at view (50, 16); pocket 22 x 12.
    assert d.plate_mm == pytest.approx((50 + 11 + 10, 66.0))
    assert sorted(pts) == [(39.0, 10.0), (39.0, 22.0), (61.0, 10.0), (61.0, 22.0)]
    assert on(ents, "HOLE") == []


def test_bad_parameters_are_refused(lib: Library) -> None:
    part, fx = lib.parts["test-tag-50x28"], lib.fixtures["test-clamps"]
    with pytest.raises(NestDrawingError, match="plate_margin_mm"):
        nest_plate(part, fx, plate_margin_mm=0.0)
    with pytest.raises(NestDrawingError, match="pocket_clearance_mm"):
        nest_plate(part, fx, pocket_clearance_mm=-0.1)
    # Origin (50, 50) leaves 24.8 mm left of the pocket: a 30 mm margin cannot fit.
    with pytest.raises(NestDrawingError, match="from the datum corner"):
        nest_plate(part, fx, plate_margin_mm=30.0)
    with pytest.raises(KeyError, match="no nest"):
        nest_plate(part, fx, nest_id="left")


# --- CLI ---------------------------------------------------------------------------------------------

def test_cli_unmeasured_writes_and_lists(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "nest"
    assert main(["drawing", "nest", "--part", "dog-tag-blank", "--fixture", "dog-tag-nest", "-o", str(out)]) == 0
    text = capsys.readouterr().out
    assert text.count("UNMEASURED  ") == 4
    assert NOT_FOR_CUTTING in text
    svg, dxf = tmp_path / "nest.svg", tmp_path / "nest.dxf"
    assert svg.read_bytes().decode("utf-8").startswith("<?xml")
    assert dxf.read_bytes().endswith(b"  0\nEOF\n")
    assert b"\r" not in dxf.read_bytes()


def test_cli_require_measured(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "nest"
    rc = main(["drawing", "nest", "--part", "dog-tag-blank", "--fixture", "dog-tag-nest", "-o", str(out),
               "--require-measured"])
    assert rc == 3
    assert not list(tmp_path.iterdir())
    assert "nothing written" in capsys.readouterr().err
    rc = main(["drawing", "nest", "--part", "test-tag-50x28", "--fixture", "test-clamps", "--library",
               str(FIXTURES), "-o", str(tmp_path / "t.svg"), "--require-measured"])
    assert rc == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == ["t.dxf", "t.svg"]
    assert "all dimensions from library facts" in capsys.readouterr().out


def test_cli_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["drawing", "nest", "--part", "no-such", "--fixture", "dog-tag-nest", "-o", str(tmp_path / "x")]) == 1
    assert "no part 'no-such'" in capsys.readouterr().err
    assert main(["drawing", "nest", "--part", "test-tag-50x28", "--fixture", "test-clamps", "--library",
                 str(FIXTURES), "--margin", "30", "-o", str(tmp_path / "x")]) == 1
    assert "plate_margin_mm" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())


def test_help_lists_drawing(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "drawing" in capsys.readouterr().out
