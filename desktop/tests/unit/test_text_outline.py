"""Arimo filled outlines: region grouping, ring validity, flattening bound, cap height, determinism."""
from __future__ import annotations

import pytest
from shapely.geometry import LinearRing, Point, Polygon

from ggdesk.text import ARIMO
from ggdesk.text.outline import _load, outline_regions

PRINTABLE = "".join(map(chr, range(33, 127)))


def _poly(r: object) -> Polygon:
    return Polygon(r.outer, r.holes)  # type: ignore[attr-defined]


def test_o_one_region_one_hole() -> None:
    r = outline_regions("O", 5.0)
    assert [len(g.holes) for g in r.regions] == [1]


def test_b_two_holes() -> None:
    r = outline_regions("B", 5.0)
    assert [len(g.holes) for g in r.regions] == [2]


def test_i_two_regions() -> None:
    r = outline_regions("i", 5.0)
    assert [len(g.holes) for g in r.regions] == [0, 0]


@pytest.mark.parametrize("size", [0.8, 2.5, 20.0])
def test_rings_closed_free_valid_and_oriented(size: float) -> None:
    r = outline_regions(PRINTABLE, size, 1.5, -2.0)
    assert r.warnings == ()
    for g in r.regions:
        for ring in (g.outer, *g.holes):
            assert len(ring) >= 3
            assert ring[0] != ring[-1]
            assert all(ring[i] != ring[i + 1] for i in range(len(ring) - 1))
        assert LinearRing(g.outer).is_ccw
        assert all(not LinearRing(h).is_ccw for h in g.holes)
        assert _poly(g).is_valid


def test_regions_do_not_overlap_within_a_glyph() -> None:
    for ch in PRINTABLE:
        ps = [_poly(g) for g in outline_regions(ch, 5.0).regions]
        for i in range(len(ps)):
            for j in range(i + 1, len(ps)):
                assert ps[i].intersection(ps[j]).area == pytest.approx(0.0, abs=1e-12), ch


@pytest.mark.parametrize("chord", [0.002, 0.01, 0.05])
@pytest.mark.parametrize("size", [0.8, 5.0])
def test_flattening_within_chord(size: float, chord: float) -> None:
    """Every point of the true quadratic curves lies within chord_mm of the flattened boundary."""
    f = _load(ARIMO)
    scale = size / f.units_per_em
    for ch in "OSe@3g":
        r = outline_regions(ch, size, chord_mm=chord)
        boundary = Polygon()
        for g in r.regions:
            boundary = boundary.union(_poly(g).boundary) if not boundary.is_empty else _poly(g).boundary
        worst = 0.0
        for contour in f.contours[f.cmap[ord(ch)]]:
            for seg in contour:
                if len(seg) != 3:
                    continue
                p0, c, p2 = seg
                for k in range(65):
                    t = k / 64
                    u = 1 - t
                    x = (u * u * p0[0] + 2 * u * t * c[0] + t * t * p2[0]) * scale
                    y = (u * u * p0[1] + 2 * u * t * c[1] + t * t * p2[1]) * scale
                    worst = max(worst, boundary.distance(Point(x, y)))
        assert worst <= chord * (1 + 1e-9), (ch, worst)


def test_finer_chord_gives_more_vertices() -> None:
    n = [sum(len(g.outer) for g in outline_regions("O", 5.0, chord_mm=c).regions) for c in (0.05, 0.01, 0.002)]
    assert n[0] < n[1] < n[2]


def test_cap_height_from_os2_and_monotonic() -> None:
    f = _load(ARIMO)
    assert outline_regions("H", 2.048).cap_height_mm == pytest.approx(f.cap_height / 1000)
    caps = [outline_regions("H", s).cap_height_mm for s in (0.8, 1.0, 1.27, 2.5, 3.333, 5.0)]
    assert caps == sorted(caps) and len(set(caps)) == len(caps)
    h = _poly(outline_regions("H", 10.0).regions[0])
    assert h.bounds[3] - h.bounds[1] == pytest.approx(outline_regions("H", 10.0).cap_height_mm, rel=1e-3)


def test_y_up_baseline_and_offset() -> None:
    a = outline_regions("H", 10.0)
    b = outline_regions("H", 10.0, 3.0, 4.0)
    ay = [p[1] for p in a.regions[0].outer]
    assert min(ay) == pytest.approx(0.0, abs=1e-9) and max(ay) > 5.0
    assert b.regions[0].outer[0] == pytest.approx((a.regions[0].outer[0][0] + 3.0, a.regions[0].outer[0][1] + 4.0))


def test_width_is_sum_of_advances() -> None:
    f = _load(ARIMO)
    r = outline_regions("AV A", 2.048)
    want = sum(f.advances[f.cmap[ord(c)]] for c in "AV A") / 1000
    assert r.width_mm == pytest.approx(want)


def test_missing_glyph_warns_and_advances_a_third_em() -> None:
    r = outline_regions("A一A", 3.0)
    a = outline_regions("A", 3.0)
    assert r.warnings == ('No glyph for "一" — skipped',)
    assert r.width_mm == pytest.approx(2 * a.width_mm + 1.0)
    assert len(r.regions) == 2 * len(a.regions)


def test_space_has_no_regions_but_advances() -> None:
    r = outline_regions(" ", 5.0)
    assert r.regions == () and r.width_mm > 0 and r.warnings == ()


def test_rejects_non_positive_size_or_chord() -> None:
    with pytest.raises(ValueError):
        outline_regions("A", 0.0)
    with pytest.raises(ValueError):
        outline_regions("A", 1.0, chord_mm=0.0)


def test_deterministic() -> None:
    assert outline_regions("Hello, World!", 3.333, 1, 2) == outline_regions("Hello, World!", 3.333, 1, 2)
