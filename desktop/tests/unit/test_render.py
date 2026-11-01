"""render.draw_list / render.to_svg / ggdesk preview: preview from DECODED bytes only."""
from __future__ import annotations

import re
import struct
from pathlib import Path

import gts_api
import pytest

from ggdesk.cli import main
from ggdesk.formats import job as jf
from ggdesk.gts_read import MODEL_CODE_OFFSET, GtsFormatError, read_job
from ggdesk.library import Resolved, Selection, load_library, resolve
from ggdesk.render import KINDS, OPERATOR_LABEL, DrawList, draw_list, to_svg
from ggdesk.render.svg import fmt_mm
from tests.conftest import DESKTOP

SEED = DESKTOP / "library"
TESTLIB = DESKTOP / "tests" / "fixtures" / "library"
SQUARE = DESKTOP / "docs" / "examples" / "square-10mm.ggj"
RECIPE = "scrap-rotary-diamond-trace"

# Two strokes in machine units: a 10 mm square at (45..55, 45..55) and a 5 mm line.
STROKES = [(4500, 4500, [(1000, 0), (0, 1000), (-1000, 0), (0, -1000)]),
           (6000, 4800, [(500, 0)])]


def job_bytes(strokes: list[tuple[int, int, list[tuple[int, int]]]] = STROKES, model: int = 0x020D) -> bytes:
    data = bytearray(gts_api.build_gts(strokes, speed=10, pz=50, dz=500, mc=1, vz=5, vd=15))
    struct.pack_into(">H", data, MODEL_CODE_OFFSET, model)
    return bytes(data)


def _resolved(sel: Selection | None = None) -> Resolved:
    lib = load_library(SEED, None, TESTLIB)
    return resolve(lib, jf.load(SQUARE), sel or Selection(recipe=RECIPE))


def test_cut_items_are_the_decoded_strokes_in_mm() -> None:
    dl = draw_list(job_bytes())
    cuts = dl.of_kind("cut")
    assert [c.points for c in cuts] == [
        ((45.0, 45.0), (55.0, 45.0), (55.0, 55.0), (45.0, 55.0), (45.0, 45.0)),
        ((60.0, 48.0), (65.0, 48.0)),
    ]
    decoded = read_job(job_bytes()).strokes()
    assert [tuple((x / 100, y / 100) for x, y in s.points) for s in decoded] == [c.points for c in cuts]


def test_rapids_are_pen_up_moves_including_return_home() -> None:
    dl = draw_list(job_bytes())
    assert [r.points for r in dl.of_kind("rapid")] == [
        ((0.0, 0.0), (45.0, 45.0)),
        ((45.0, 45.0), (60.0, 48.0)),
        ((65.0, 48.0), (0.0, 0.0)),
    ]
    assert [s.points for s in dl.of_kind("start")] == [((45.0, 45.0),)]


def test_draw_list_follows_the_bytes_not_any_build_state() -> None:
    data = bytearray(job_bytes())
    seg = next(r for r in read_job(bytes(data)).records
               if hasattr(r, "dx") and r.dx == 1000 and r.dy == 0)
    struct.pack_into(">h", data, seg.offset + 8, 1001)     # dx of the first cut segment, +0.01 mm
    dl = draw_list(bytes(data))
    assert dl.of_kind("cut")[0].points[1] == (55.01, 45.0)


def test_without_resolved_there_is_no_field_part_or_keep_out() -> None:
    dl = draw_list(job_bytes())
    assert {i.kind for i in dl.items} == {"cut", "rapid", "start"}
    assert dl.extent_mm == (65.0, 55.0)


def test_resolved_adds_field_part_and_keep_outs() -> None:
    ko = ((10.0, 10.0), (20.0, 10.0), (20.0, 20.0), (10.0, 20.0))
    dl = draw_list(job_bytes(), _resolved(Selection(recipe=RECIPE, extra_keep_outs=(ko,))))
    assert [i.kind for i in dl.items][:3] == ["field", "part", "keep_out"]
    assert dl.of_kind("field")[0].points == ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0), (0.0, 0.0))
    part = dl.of_kind("part")[0].points
    assert part[0] == part[-1]
    assert {p for p in part} == {(30.0, 30.0), (70.0, 30.0), (70.0, 70.0), (30.0, 70.0)}
    assert dl.of_kind("keep_out")[0].points == ko + (ko[0],)
    assert dl.extent_mm == (100.0, 100.0)


def test_paint_order_is_fixed() -> None:
    dl = draw_list(job_bytes(), _resolved())
    order = [KINDS.index(i.kind) for i in dl.items]
    assert order == sorted(order)


def test_undecodable_bytes_raise() -> None:
    with pytest.raises(GtsFormatError):
        draw_list(b"not a job")


def _svg_items(svg: str) -> list[tuple[str, tuple[tuple[float, float], ...]]]:
    out: list[tuple[str, tuple[tuple[float, float], ...]]] = []
    for m in re.finditer(r'<(polyline|circle) class="[^"]*" data-kind="([a-z_]+)" ([^/]*)/>', svg):
        attrs = dict(re.findall(r'([a-z]+)="([^"]*)"', m.group(3)))
        if m.group(1) == "circle":
            out.append((m.group(2), ((float(attrs["cx"]), float(attrs["cy"])),)))
        else:
            pts = tuple((float(a), float(b)) for a, b in (p.split(",") for p in attrs["points"].split()))
            out.append((m.group(2), pts))
    return out


def svg_matches(dl: DrawList, svg: str) -> bool:
    items = _svg_items(svg)
    if len(items) != len(dl.items):
        return False
    for (kind, pts), it in zip(items, dl.items, strict=True):
        if kind != it.kind or len(pts) != len(it.points):
            return False
        if any(abs(a - b) > 5e-5 for p, q in zip(pts, it.points, strict=True) for a, b in zip(p, q, strict=True)):
            return False
    return True


def test_svg_has_exactly_the_draw_list_items() -> None:
    dl = draw_list(job_bytes(), _resolved())
    svg = to_svg(dl)
    assert svg_matches(dl, svg)
    assert f">{OPERATOR_LABEL}</text>" in svg


def test_svg_is_deterministic_text() -> None:
    a = to_svg(draw_list(job_bytes(), _resolved()))
    b = to_svg(draw_list(job_bytes(), _resolved()))
    assert a == b
    assert a.endswith("</svg>\n") and "\r" not in a


def test_operator_label_is_at_the_front_edge() -> None:
    svg = to_svg(draw_list(job_bytes(), _resolved()))
    m = re.search(r'<text class="label" x="([-\d.]+)" y="([-\d.]+)"', svg)
    assert m and float(m.group(2)) > 100.0        # below the field's front edge (+Y toward the operator)


@pytest.mark.parametrize("v,s", [(0.0, "0"), (-0.0, "0"), (12.5, "12.5"), (1 / 3, "0.3333"), (-0.00001, "0")])
def test_fmt_mm(v: float, s: str) -> None:
    assert fmt_mm(v) == s


def test_cli_preview_writes_svg(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    m20 = tmp_path / "j.m20"
    m20.write_bytes(job_bytes())
    out = tmp_path / "j.svg"
    assert main(["preview", str(m20), "-o", str(out)]) == 0
    assert out.read_bytes().decode("utf-8") == to_svg(draw_list(job_bytes()))
    assert "2 cut paths" in capsys.readouterr().out


def test_cli_preview_with_job_draws_field_and_part(tmp_path: Path) -> None:
    m20 = tmp_path / "j.m20"
    m20.write_bytes(job_bytes())
    out = tmp_path / "j.svg"
    rc = main(["preview", str(m20), "-o", str(out), "--job", str(SQUARE), "--recipe", RECIPE,
               "--keep-out", "10,10,20,20"])
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert 'data-kind="field"' in text and 'data-kind="part"' in text and 'data-kind="keep_out"' in text


def test_cli_preview_job_needs_recipe(tmp_path: Path) -> None:
    m20 = tmp_path / "j.m20"
    m20.write_bytes(job_bytes())
    assert main(["preview", str(m20), "-o", str(tmp_path / "x.svg"), "--job", str(SQUARE)]) == 2


def test_cli_preview_refuses_bad_bytes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.m20"
    bad.write_bytes(b"garbage")
    out = tmp_path / "bad.svg"
    assert main(["preview", str(bad), "-o", str(out)]) == 1
    assert not out.exists()
    assert "bad.m20" in capsys.readouterr().err
