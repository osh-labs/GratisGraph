"""Hershey single-stroke text: an exact port of web/src/hershey.ts.

Reads web/app/fonts/futural.jhf (Hershey "futural" in the 1986 JHF encoding). The Hershey data
carry the use notice in web/app/fonts/HERSHEY-NOTICE.txt; no font file is copied into desktop/.

`hershey_strokes` is the conformance surface: it returns exactly what the TypeScript
`hersheyTextToStrokes(jhf, text, sizeMm, xMm, yMm)` returns (strokes in 0.01 mm device units, the
width in mm and the same warning strings). The float operations follow the TypeScript in the same
order (`scale = size / 32`, `penX + (hx - left) * scale`, `yMm + (9 - hy) * scale`) and mm -> units
goes through `ggdesk.numerics.to_units` (half to even, the same as TS `mmToUnits`).
desktop/tests/fixtures/hershey/ holds the fixture generated from the TypeScript; the unit test
compares every case exactly.

`hershey_paths` gives the same geometry as unquantised mm polylines (part frame, Y up, baseline
at y_mm) for bench patterns, plus the measured height of "H" at that size.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from ggdesk.model.geometry import Polyline, Pt
from ggdesk.numerics import to_units
from ggdesk.text import FUTURAL, TextPaths, font_path

HPt = tuple[int, int]
UStart = tuple[int, int]


@dataclass(frozen=True)
class HGlyph:
    """One JHF glyph: left and right bearings and pen-down paths (Hershey units, Y down)."""
    left: int
    right: int
    paths: tuple[tuple[HPt, ...], ...]


@dataclass(frozen=True)
class HStroke:
    """A TS `Stroke`: absolute start in device units, then relative moves (never (0, 0))."""
    start: UStart
    deltas: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class HersheyStrokes:
    """What `hersheyTextToStrokes` returns: `{ strokes, widthMm, warnings }`."""
    strokes: tuple[HStroke, ...]
    width_mm: float
    warnings: tuple[str, ...] = ()


_PARSE_INT = re.compile(r"\s*([+-]?\d+)")


def _parse_int(s: str) -> int | None:
    """JavaScript parseInt(s, 10): leading whitespace, optional sign, leading digits; None for NaN."""
    m = _PARSE_INT.match(s)
    return int(m.group(1)) if m else None


def _cv(c: str) -> int:
    return ord(c) - 82  # 'R'


def parse_jhf(text: str) -> tuple[HGlyph, ...]:
    """Port of parseJhf: records may wrap across lines (total chars = 8 + 2 * nverts)."""
    lines = [ln for ln in re.split(r"\r?\n", text) if len(ln) > 0]
    glyphs: list[HGlyph] = []
    i = 0
    while i < len(lines):
        rec = lines[i]
        i += 1
        nv = _parse_int(rec[5:8])
        if nv is None:  # TS: need is NaN, so no wrapping, then `continue`
            continue
        need = 8 + nv * 2
        while len(rec) < need and i < len(lines):
            rec += lines[i]
            i += 1
        if len(rec) < need:
            continue
        left, right = _cv(rec[8]), _cv(rec[9])
        paths: list[tuple[HPt, ...]] = []
        cur: list[HPt] = []
        for k in range(1, nv):
            a, b = rec[8 + k * 2], rec[9 + k * 2]
            if a == " " and b == "R":
                if len(cur) >= 2:
                    paths.append(tuple(cur))
                cur = []
            else:
                cur.append((_cv(a), _cv(b)))
        if len(cur) >= 2:
            paths.append(tuple(cur))
        glyphs.append(HGlyph(left, right, tuple(paths)))
    return tuple(glyphs)


@cache
def _load(path: Path) -> tuple[HGlyph, ...]:
    # newline="" keeps the bytes as the TS reads them (readFileSync 'utf8', no newline translation)
    with font_path(path).open(encoding="utf-8", newline="") as f:
        return parse_jhf(f.read())


def load_jhf(path: Path = FUTURAL) -> tuple[HGlyph, ...]:
    """The glyphs of a .jhf file, mapped to ASCII 32.. in file order."""
    return _load(path)


def _to_stroke(points_mm: list[Pt]) -> HStroke | None:
    """Port of toStroke: quantise each point once, drop zero moves, None if nothing moves."""
    if len(points_mm) < 2:
        return None
    sx, sy = to_units(points_mm[0][0]), to_units(points_mm[0][1])
    deltas: list[tuple[int, int]] = []
    px, py = sx, sy
    for p in points_mm[1:]:
        qx, qy = to_units(p[0]), to_units(p[1])
        if qx != px or qy != py:
            deltas.append((qx - px, qy - py))
        px, py = qx, qy
    return HStroke((sx, sy), tuple(deltas)) if deltas else None


def _layout(text: str, size_mm: float, x_mm: float, y_mm: float,
            glyphs: tuple[HGlyph, ...]) -> tuple[list[list[Pt]], float, list[str]]:
    """The mm polylines (one per glyph path, file order), the width and the warnings."""
    scale = size_mm / 32
    warnings: list[str] = []
    polys: list[list[Pt]] = []
    pen_x = x_mm
    for ch in text:  # code points, as the TS `for (const ch of text)`
        idx = ord(ch) - 32
        if idx < 0 or idx >= len(glyphs):
            warnings.append(f'No Hershey glyph for "{ch}" — skipped')
            pen_x += 16 * scale
            continue
        g = glyphs[idx]
        for path in g.paths:
            polys.append([(pen_x + (hx - g.left) * scale, y_mm + (9 - hy) * scale) for hx, hy in path])
        pen_x += (g.right - g.left) * scale
    return polys, pen_x - x_mm, warnings


def hershey_strokes(text: str, size_mm: float, x_mm: float = 0, y_mm: float = 0) -> HersheyStrokes:
    """Exactly `hersheyTextToStrokes(futural, text, sizeMm, xMm, yMm)` (size = 32 Hershey units)."""
    polys, width, warnings = _layout(text, size_mm, x_mm, y_mm, load_jhf())
    strokes = [s for s in (_to_stroke(p) for p in polys) if s is not None]
    return HersheyStrokes(tuple(strokes), width, tuple(warnings))


def _cap_height_units(glyphs: tuple[HGlyph, ...]) -> int:
    """Height of "H" in Hershey units, measured from its paths."""
    ys = [hy for path in glyphs[ord("H") - 32].paths for _, hy in path]
    return max(ys) - min(ys)


def hershey_paths(text: str, size_mm: float, x_mm: float = 0.0, y_mm: float = 0.0) -> TextPaths:
    """The same geometry as `hershey_strokes`, as open mm polylines (part frame, Y up, baseline y_mm)."""
    glyphs = load_jhf()
    polys, width, warnings = _layout(text, size_mm, x_mm, y_mm, glyphs)
    paths = tuple(Polyline(tuple(p)) for p in polys)
    cap = _cap_height_units(glyphs) * (size_mm / 32)
    return TextPaths(paths, width, cap, tuple(warnings))
