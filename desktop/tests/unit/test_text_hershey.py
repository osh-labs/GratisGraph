"""Hershey port: exact conformance with web/src/hershey.ts and the mm geometry for patterns."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ggdesk.numerics import to_units
from ggdesk.text import FUTURAL
from ggdesk.text.hershey import (
    _parse_int,
    hershey_paths,
    hershey_strokes,
    load_jhf,
    parse_jhf,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "hershey" / "hershey_conformance.json"
CASES: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
SIZES = (0.8, 1.0, 1.27, 2.5, 3.333, 5.0)


@pytest.mark.parametrize("case", CASES, ids=[f"{i}:{c['sizeMm']}@{c['xMm']},{c['yMm']}" for i, c in enumerate(CASES)])
def test_conformance_with_typescript(case: dict[str, Any]) -> None:
    r = hershey_strokes(case["text"], case["sizeMm"], case["xMm"], case["yMm"])
    got = [{"start": list(s.start), "deltas": [list(d) for d in s.deltas]} for s in r.strokes]
    assert got == case["strokes"]
    assert r.width_mm == case["widthMm"]  # exact float equality: same operations in the same order
    assert list(r.warnings) == case["warnings"]


def test_fixture_covers_the_brief() -> None:
    texts = {c["text"] for c in CASES}
    assert "".join(map(chr, range(32, 127))) in texts
    assert {"0123456789", "Hello, World!"} <= texts
    assert set(SIZES) <= {c["sizeMm"] for c in CASES}
    assert any(c["warnings"] for c in CASES)


def test_fixture_exercises_exact_ties() -> None:
    """At least some vertices land exactly on a 0.005 mm tie, where half-to-even matters."""
    glyphs = load_jhf()
    ties = 0
    for c in CASES:
        scale = c["sizeMm"] / 32
        pen = c["xMm"]
        for ch in c["text"]:
            idx = ord(ch) - 32
            if not 0 <= idx < len(glyphs):
                pen += 16 * scale
                continue
            g = glyphs[idx]
            for path in g.paths:
                for hx, hy in path:
                    for v in (pen + (hx - g.left) * scale, c["yMm"] + (9 - hy) * scale):
                        u = v * 100
                        ties += (u - int(u // 1)) == 0.5
            pen += (g.right - g.left) * scale
    assert ties > 100


def test_parse_int_matches_javascript() -> None:
    assert _parse_int("  9") == 9
    assert _parse_int("12a") == 12
    assert _parse_int(" -3") == -3
    assert _parse_int("   ") is None
    assert _parse_int("x1") is None


def test_parse_jhf_wraps_records_and_skips_bad_ones() -> None:
    text = "12345  3MW\r\nRFRT\nbad\n\n12345  2LTRF\n12345  4LT\n"   # last record is truncated
    gs = parse_jhf(text)
    assert len(gs) == 2
    assert gs[0].left == -5 and gs[0].right == 5
    assert gs[0].paths == (((0, -12), (0, 2)),)
    assert gs[1].paths == ()


def test_font_covers_ascii_32_to_127() -> None:
    assert len(load_jhf(FUTURAL)) == 96  # 96 records in file order: ASCII 32 .. 127 (the TS maps the same)


def test_paths_are_the_stroke_geometry() -> None:
    for size, x, y in ((2.5, 0.0, 0.0), (1.27, 3.1, -4.2)):
        p = hershey_paths("Hello, World!", size, x, y)
        s = hershey_strokes("Hello, World!", size, x, y)
        assert p.width_mm == s.width_mm
        assert len(p.paths) == len(s.strokes)
        for poly, st in zip(p.paths, s.strokes, strict=True):
            assert not poly.closed
            assert (to_units(poly.points[0][0]), to_units(poly.points[0][1])) == st.start
            end = (st.start[0] + sum(d[0] for d in st.deltas), st.start[1] + sum(d[1] for d in st.deltas))
            assert (to_units(poly.points[-1][0]), to_units(poly.points[-1][1])) == end


def test_paths_y_up_baseline_at_y() -> None:
    p = hershey_paths("H", 10.0, 0.0, 2.0)
    ys = [pt[1] for poly in p.paths for pt in poly.points]
    assert min(ys) == 2.0
    assert max(ys) == pytest.approx(2.0 + p.cap_height_mm)


def test_cap_height_is_measured_h() -> None:
    g = load_jhf()[ord("H") - 32]
    ys = [hy for path in g.paths for _, hy in path]
    assert hershey_paths("x", 3.2).cap_height_mm == (max(ys) - min(ys)) * 3.2 / 32


def test_cap_height_monotonic_in_size() -> None:
    caps = [hershey_paths("A", s).cap_height_mm for s in (0.5, *SIZES, 10.0)]
    assert caps == sorted(caps) and len(set(caps)) == len(caps)


def test_missing_glyph_warns_and_advances() -> None:
    p = hershey_paths("AéA", 3.2)
    a = hershey_paths("A", 3.2)
    assert p.warnings == ('No Hershey glyph for "é" — skipped',)
    assert p.width_mm == pytest.approx(2 * a.width_mm + 16 * 0.1)


def test_deterministic() -> None:
    assert hershey_paths("Hello, World!", 2.5, 1, 1) == hershey_paths("Hello, World!", 2.5, 1, 1)
    assert hershey_strokes("Hello, World!", 2.5, 1, 1) == hershey_strokes("Hello, World!", 2.5, 1, 1)
