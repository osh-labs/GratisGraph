"""Filled bench text from the Arimo glyph outlines (web/app/fonts/Arimo-Regular.ttf) via fontTools.

Arimo is licensed under the SIL Open Font License 1.1 (web/app/fonts/OFL-Arimo.txt); the font is
read in place and no font file is copied into desktop/. The variable font's default instance is
used (the glyf outlines), as in web/src/ttf.ts.

Layout follows web/src/ttf.ts: size is the em height (mm per `unitsPerEm`), glyphs advance by the
font's advance widths (no kerning, no hinting), a character without a glyph warns
`No glyph for "c" — skipped` and advances one third of an em. The TrueType quadratic contours are
flattened so that the chord error is at most `chord_mm`: a quadratic with control points P0, P1, P2
split into n equal parameter steps deviates from each chord by at most |P0 - 2 P1 + P2| / (4 n^2),
so n = ceil(sqrt(|P0 - 2 P1 + P2| / (4 chord))). Only `ggdesk.numerics` is used for the square
root, length and ceiling.

Contours become regions by orientation and containment: TrueType outer contours run clockwise
(Y up) and holes anticlockwise; each hole joins the smallest outer contour of the same glyph that
contains it. Output rings are in the part frame (mm, Y up, baseline at y_mm), outer rings
anticlockwise and holes clockwise, with no repeated closing point. Order is deterministic: text
order, then the outer contour's order in the glyph; holes in contour order.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from ggdesk.model.geometry import Pt, Region
from ggdesk.numerics import ceil_div, length, sqrt
from ggdesk.text import ARIMO, TextRegions, font_path

# A contour segment in font units: a line (p0, p1) or a quadratic (p0, ctrl, p2).
Seg = tuple[Pt, ...]


@dataclass(frozen=True)
class _Font:
    units_per_em: int
    cap_height: float                       # font units
    cmap: dict[int, str]
    advances: dict[str, int]
    contours: dict[str, tuple[tuple[Seg, ...], ...]]   # glyph name -> contour segments


def _segments(pts: list[tuple[float, float]], on: list[bool]) -> tuple[Seg, ...]:
    """TrueType contour -> closed list of line and quadratic segments (implied on-curve midpoints)."""
    n = len(pts)
    if n == 0:
        return ()
    # start at an on-curve point; if there is none, at the implied midpoint of the first two points
    start = next((i for i in range(n) if on[i]), None)
    if start is None:
        p0, p1 = pts[0], pts[1 % n]
        first: Pt = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
        seq = [(pts[(1 + k) % n], False) for k in range(n)]
    else:
        first = pts[start]
        seq = [(pts[(start + k) % n], on[(start + k) % n]) for k in range(1, n)]
    seq.append((first, True))
    segs: list[Seg] = []
    cur = first
    ctrl: Pt | None = None
    for p, is_on in seq:
        if is_on:
            segs.append((cur, p) if ctrl is None else (cur, ctrl, p))
            cur, ctrl = p, None
        elif ctrl is None:
            ctrl = p
        else:
            mid = ((ctrl[0] + p[0]) / 2, (ctrl[1] + p[1]) / 2)
            segs.append((cur, ctrl, mid))
            cur, ctrl = mid, p
    return tuple(segs)


@cache
def _load(path: Path) -> _Font:
    from fontTools.ttLib import TTFont  # imported here: only bench text needs it

    tt: Any = TTFont(str(font_path(path)))
    glyf = tt["glyf"]
    hmtx = tt["hmtx"]
    upem = int(tt["head"].unitsPerEm)
    cmap = {int(k): str(v) for k, v in tt.getBestCmap().items()}
    names = sorted(set(cmap.values()))
    contours: dict[str, tuple[tuple[Seg, ...], ...]] = {}
    for name in names:
        coords, ends, flags = glyf[name].getCoordinates(glyf)
        out: list[tuple[Seg, ...]] = []
        s = 0
        for e in ends:
            pts = [(float(x), float(y)) for x, y in coords[s:e + 1]]
            on = [bool(f & 1) for f in flags[s:e + 1]]
            out.append(_segments(pts, on))
            s = e + 1
        contours[name] = tuple(out)
    os2 = tt["OS/2"] if "OS/2" in tt else None
    cap = getattr(os2, "sCapHeight", 0) if os2 is not None else 0
    if not cap:  # measured "H": its outline's vertical extent
        ys = [p[1] for seg in contours[cmap[ord("H")]] for s2 in seg for p in s2]
        cap = max(ys) - min(ys)
    return _Font(upem, float(cap), cmap, {n: int(hmtx[n][0]) for n in names}, contours)


def _steps(p0: Pt, c: Pt, p2: Pt, tol_units: float) -> int:
    """Equal parameter steps so a quadratic stays within tol_units of its chords."""
    d = length(p0[0] - 2 * c[0] + p2[0], p0[1] - 2 * c[1] + p2[1])
    if d == 0.0:
        return 1
    return max(1, ceil_div(sqrt(d / (4 * tol_units)), 1.0))


def _flatten(segs: tuple[Seg, ...], tol_units: float) -> list[Pt]:
    """Closed contour -> its vertices in font units (no repeated closing point)."""
    pts: list[Pt] = []
    for seg in segs:
        if len(seg) == 2:
            pts.append(seg[0])
            continue
        p0, c, p2 = seg
        n = _steps(p0, c, p2, tol_units)
        for i in range(n):
            t = i / n
            u = 1 - t
            a, b, cc = u * u, 2 * u * t, t * t
            pts.append((a * p0[0] + b * c[0] + cc * p2[0], a * p0[1] + b * c[1] + cc * p2[1]))
    return pts


def _clean(ring: list[Pt]) -> list[Pt]:
    """Drop consecutive duplicates and a repeated closing point."""
    out: list[Pt] = []
    for p in ring:
        if not out or p != out[-1]:
            out.append(p)
    while len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def _area2(ring: list[Pt]) -> float:
    """Twice the signed area (positive = anticlockwise, Y up)."""
    s = 0.0
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return s


def _inside(p: Pt, ring: list[Pt]) -> bool:
    """Even-odd point in polygon."""
    x, y = p
    hit = False
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def _glyph_regions(rings: list[list[Pt]], warnings: list[str], ch: str) -> list[tuple[list[Pt], list[list[Pt]]]]:
    """Group one glyph's rings (font units, Y up) into (outer, holes) by orientation and containment."""
    outers = [i for i, r in enumerate(rings) if _area2(r) < 0]   # TrueType outer: clockwise
    holes = [i for i, r in enumerate(rings) if _area2(r) > 0]
    owned: dict[int, list[int]] = {i: [] for i in outers}
    for h in holes:
        hosts = [o for o in outers if _inside(rings[h][0], rings[o])]
        if not hosts:
            warnings.append(f'Glyph "{ch}": a hole contour lies in no outer contour; filled as an outer')
            owned[h] = []
            continue
        owned[min(hosts, key=lambda o: (-_area2(rings[o]), o))].append(h)
    out: list[tuple[list[Pt], list[list[Pt]]]] = []
    for i in sorted(owned):
        outer = rings[i] if _area2(rings[i]) > 0 else rings[i][::-1]
        hs = [rings[h] if _area2(rings[h]) < 0 else rings[h][::-1] for h in owned[i]]
        out.append((outer, hs))
    return out


def outline_regions(text: str, size_mm: float, x_mm: float = 0.0, y_mm: float = 0.0,
                    chord_mm: float = 0.01) -> TextRegions:
    """Filled glyph regions for `text` at em height `size_mm`, flattened within `chord_mm`."""
    if size_mm <= 0 or chord_mm <= 0:
        raise ValueError("outline_regions: size_mm and chord_mm must be positive")
    f = _load(ARIMO)
    scale = size_mm / f.units_per_em          # mm per font unit
    tol = chord_mm / scale                    # chord tolerance in font units
    warnings: list[str] = []
    regions: list[Region] = []
    pen_x = x_mm
    for ch in text:
        name = f.cmap.get(ord(ch))
        if name is None or name == ".notdef":
            warnings.append(f'No glyph for "{ch}" — skipped')
            pen_x += (f.units_per_em / 3) * scale
            continue
        rings = [r for r in (_clean(_flatten(c, tol)) for c in f.contours[name]) if len(r) >= 3]
        for outer, holes in _glyph_regions(rings, warnings, ch):
            def mm(r: list[Pt], px: float = pen_x) -> tuple[Pt, ...]:
                return tuple(_clean([(px + gx * scale, y_mm + gy * scale) for gx, gy in r]))
            regions.append(Region(mm(outer), tuple(mm(h) for h in holes)))
        pen_x += f.advances[name] * scale
    return TextRegions(tuple(regions), pen_x - x_mm, f.cap_height * scale, tuple(warnings))
