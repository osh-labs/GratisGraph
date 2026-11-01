"""Parametric nest plate for one blank: SVG and DXF R12 (m2-plan section 2.6).

The plate is drawn in top view with the machine's axes: the plate datum corner is the back-left
corner (nearest machine home), +X right, the operator at the bottom of the sheet. The fixture's
nest origin (relative to its datum, machine axes) places the part-frame origin on the plate; the
part frame has +Y away from the operator, so the blank appears as the operator reads it.

Drawing coordinates ("view frame", both outputs): mm, origin at the plate's front-left corner, +Y up
(the usual CAD convention, so the DXF lands in the first quadrant). The plate datum corner is
therefore at (0, plate height). The SVG prints the same entities with Y negated (viewBox in mm).

Every dimension that comes from a `needs_measurement` fact uses a value from PLACEHOLDERS, carries
`UNMEASURED (Gn)` next to it, and is listed in `NestDrawing.unmeasured`; the title block then says
the plate is not for cutting. Placeholders are drawing placeholders only: nothing here is a
measurement, and no placeholder ever reaches the library, a job or the gate.

Rounding and trigonometry go through ggdesk.numerics; numbers are printed with fixed-point string
formatting (correctly rounded on every platform), so the text is identical on Linux and Windows.
"""
from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Any, Literal

from ggdesk import numerics
from ggdesk.library.model import Fact, Fixture, Outline, Part
from ggdesk.model.geometry import Pt

# --- placeholders ------------------------------------------------------------------------------
# DRAWING PLACEHOLDERS, NOT MEASUREMENTS. They only let the drawing show its layout while the
# library fact is needs_measurement; every dimension drawn from one is labelled UNMEASURED with its
# gap and the title block says "NOT FOR CUTTING". Replace the library fact (G1/G2), never these.


@dataclass(frozen=True)
class Placeholder:
    gap: str
    note: str


PLACEHOLDERS: dict[str, tuple[object, Placeholder]] = {
    # Drawing placeholder, not a measurement: blank outline (rounded rectangle centred on the part origin).
    "part.outline": (Outline("rect", width_mm=50.0, height_mm=30.0, corner_radius_mm=4.0),
                     Placeholder("G1", "rect 50 x 30 mm, corner R 4")),
    # Drawing placeholder, not a measurement: one round hole left of centre.
    "part.holes": ((Outline("rect", width_mm=4.0, height_mm=4.0, corner_radius_mm=2.0, centre_mm=(-19.0, 0.0)),),
                   Placeholder("G1", "one hole DIA 4 at (-19, 0) from the part origin")),
    # Drawing placeholder, not a measurement: blank thickness (sets the pocket depth).
    "part.thickness_mm": (1.0, Placeholder("G1", "1.0 mm")),
    # Drawing placeholder, not a measurement: the nest origin is put where the pocket sits exactly
    # plate_margin_mm from the datum corner on both axes (a layout rule, not a value).
    "fixture.nest.origin_mm": (None, Placeholder("G2", "pocket placed plate_margin_mm from the datum corner")),
}

# --- drawing constants (design choices, not measurements) -----------------------------------------
DEFAULT_PLATE_MARGIN_MM = 10.0       # plate material around the pocket (m2-plan 2.6 default)
DEFAULT_POCKET_CLEARANCE_MM = 0.2    # per side, blank outline to pocket wall
CROSSHAIR_ARM_MM = 4.0
TEXT_MM = 2.5
TITLE_MM = 3.5
WARN_MM = 5.0
DIM_GAP_MM = 2.0                     # gap between the geometry and an extension line
DIM_TIER_MM = 7.0                    # spacing of dimension tiers
ARROW_MM = 1.5
SHEET_MARGIN_MM = 6.0

LAYERS = ("OUTLINE", "POCKET", "HOLE", "DATUM", "DIMENSION", "NOTE")
# DXF colour numbers (ACI) and SVG print colours per layer. The core has no theme; these are the
# drawing's own palette (a document, like render/svg.py's print palette).
DXF_COLOUR = {"OUTLINE": 7, "POCKET": 5, "HOLE": 3, "DATUM": 1, "DIMENSION": 8, "NOTE": 7}
SVG_COLOUR = {"OUTLINE": "#111827", "POCKET": "#1d4ed8", "HOLE": "#047857", "DATUM": "#b91c1c",
              "DIMENSION": "#4b5563", "NOTE": "#111827"}
SVG_WARN_COLOUR = "#b91c1c"
SVG_STROKE_MM = 0.25

NOT_FOR_CUTTING = "NOT FOR CUTTING: unmeasured dimensions"


class NestDrawingError(ValueError):
    """The parameters or library values cannot make a plate (e.g. the pocket overlaps the datum corner)."""


@dataclass(frozen=True)
class NestDrawing:
    svg: str
    dxf: str
    unmeasured: tuple[str, ...]
    plate_mm: tuple[float, float] = (0.0, 0.0)   # overall width, height
    title: tuple[str, ...] = ()


# --- entities --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class _Line:
    layer: str
    a: Pt
    b: Pt


@dataclass(frozen=True)
class _Arc:
    """Counter-clockwise (view frame, +Y up) from start_deg to end_deg."""
    layer: str
    c: Pt
    r: float
    start_deg: float
    end_deg: float


@dataclass(frozen=True)
class _Circle:
    layer: str
    c: Pt
    r: float


@dataclass(frozen=True)
class _Poly:
    layer: str
    pts: tuple[Pt, ...]
    closed: bool = True


@dataclass(frozen=True)
class _Text:
    layer: str
    p: Pt
    height: float
    text: str
    anchor: Literal["start", "middle"] = "start"
    vertical: bool = False
    warn: bool = False


_Entity = _Line | _Arc | _Circle | _Poly | _Text


@dataclass
class _Sheet:
    items: list[_Entity] = field(default_factory=list)

    def add(self, e: _Entity) -> None:
        self.items.append(e)


def fmt(v: float) -> str:
    """Deterministic number text: fixed 4 decimals, trailing zeros removed, no negative zero."""
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def fmt_dim(v: float) -> str:
    """Dimension text: 2 decimals (0.01 mm, the machine's resolution)."""
    s = f"{v:.2f}"
    return "0.00" if s == "-0.00" else s


# --- geometry helpers ------------------------------------------------------------------------------

def _is_circle(o: Outline) -> bool:
    return (o.kind == "rect" and o.width_mm == o.height_mm
            and o.corner_radius_mm == o.width_mm / 2)


def _rect_entities(sheet: _Sheet, layer: str, cx: float, cy: float, w: float, h: float, r: float) -> None:
    """A rounded rectangle centred at (cx, cy) in the view frame: LINEs and ARCs (exact)."""
    hw, hh = w / 2, h / 2
    r = min(r, hw, hh)
    if hw == r and hh == r:
        sheet.add(_Circle(layer, (cx, cy), r))
        return
    x0, x1, y0, y1 = cx - hw, cx + hw, cy - hh, cy + hh
    if r > 0:
        if x1 - r > x0 + r:
            sheet.add(_Line(layer, (x0 + r, y0), (x1 - r, y0)))
            sheet.add(_Line(layer, (x1 - r, y1), (x0 + r, y1)))
        if y1 - r > y0 + r:
            sheet.add(_Line(layer, (x1, y0 + r), (x1, y1 - r)))
            sheet.add(_Line(layer, (x0, y1 - r), (x0, y0 + r)))
        sheet.add(_Arc(layer, (x1 - r, y0 + r), r, 270.0, 360.0))
        sheet.add(_Arc(layer, (x1 - r, y1 - r), r, 0.0, 90.0))
        sheet.add(_Arc(layer, (x0 + r, y1 - r), r, 90.0, 180.0))
        sheet.add(_Arc(layer, (x0 + r, y0 + r), r, 180.0, 270.0))
    else:
        sheet.add(_Poly(layer, ((x0, y0), (x1, y0), (x1, y1), (x0, y1))))


def _offset_polygon(points: tuple[Pt, ...], d: float) -> tuple[Pt, ...]:
    """Outward offset of a polygon by d (mitre joins only, as the fill code: no trigonometry)."""
    if d == 0:
        return points
    from shapely.geometry import Polygon
    from shapely.geometry.polygon import orient

    poly = orient(Polygon(points).buffer(d, join_style="mitre", mitre_limit=10.0), 1.0)
    coords = list(poly.exterior.coords)[:-1]
    return tuple((float(x), float(y)) for x, y in coords)


def _bbox(o: Outline, clearance: float) -> tuple[float, float, float, float]:
    """Part-frame bounding box of the outline grown by `clearance`."""
    if o.kind == "rect":
        cx, cy = o.centre_mm
        hw, hh = o.width_mm / 2 + clearance, o.height_mm / 2 + clearance
        return (cx - hw, cy - hh, cx + hw, cy + hh)
    pts = _offset_polygon(o.points, clearance)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


# --- dimensions ------------------------------------------------------------------------------------

def _label(value: float, gaps: tuple[str, ...], prefix: str = "") -> str:
    t = f"{prefix}{fmt_dim(value)}"
    if gaps:
        t += f" UNMEASURED ({', '.join(gaps)})"
    return t


def _hdim(sheet: _Sheet, xa: float, xb: float, y_from: float, y_dim: float, text: str, warn: bool) -> None:
    """Horizontal dimension between x = xa and x = xb, measured at y_dim, extension lines from y_from."""
    up = 1.0 if y_dim > y_from else -1.0
    for x in (xa, xb):
        sheet.add(_Line("DIMENSION", (x, y_from + up * DIM_GAP_MM / 2), (x, y_dim + up * 1.0)))
    sheet.add(_Line("DIMENSION", (xa, y_dim), (xb, y_dim)))
    a, s = ARROW_MM, ARROW_MM / 3
    sheet.add(_Poly("DIMENSION", ((xa + a, y_dim + s), (xa, y_dim), (xa + a, y_dim - s)), closed=False))
    sheet.add(_Poly("DIMENSION", ((xb - a, y_dim + s), (xb, y_dim), (xb - a, y_dim - s)), closed=False))
    sheet.add(_Text("DIMENSION", ((xa + xb) / 2, y_dim + 0.8), TEXT_MM, text, "middle", warn=warn))


def _vdim(sheet: _Sheet, ya: float, yb: float, x_from: float, x_dim: float, text: str, warn: bool) -> None:
    """Vertical dimension between y = ya and y = yb, measured at x_dim, extension lines from x_from."""
    right = 1.0 if x_dim > x_from else -1.0
    for y in (ya, yb):
        sheet.add(_Line("DIMENSION", (x_from + right * DIM_GAP_MM / 2, y), (x_dim + right * 1.0, y)))
    lo, hi = min(ya, yb), max(ya, yb)
    sheet.add(_Line("DIMENSION", (x_dim, lo), (x_dim, hi)))
    a, s = ARROW_MM, ARROW_MM / 3
    sheet.add(_Poly("DIMENSION", ((x_dim - s, lo + a), (x_dim, lo), (x_dim + s, lo + a)), closed=False))
    sheet.add(_Poly("DIMENSION", ((x_dim - s, hi - a), (x_dim, hi), (x_dim + s, hi - a)), closed=False))
    sheet.add(_Text("DIMENSION", (x_dim - 0.8, (lo + hi) / 2), TEXT_MM, text, "middle", vertical=True, warn=warn))


# --- the drawing -----------------------------------------------------------------------------------

def _fact_or_placeholder(fact: Fact[Any], key: str, what: str,
                         unmeasured: list[str]) -> tuple[Any, tuple[str, ...]]:
    """(value, gaps): the fact's value when known, else the placeholder and its gap (recorded)."""
    if fact.known:
        return fact.value, ()
    value, ph = PLACEHOLDERS[key]
    gap = fact.gap or ph.gap
    unmeasured.append(f"{what} ({gap}): drawn from placeholder {ph.note}")
    return value, (gap,)


def _gaps(*groups: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({g for grp in groups for g in grp}))


def nest_plate(part: Part, fixture: Fixture, *, nest_id: str = "centre",
               plate_margin_mm: float = DEFAULT_PLATE_MARGIN_MM,
               pocket_clearance_mm: float = DEFAULT_POCKET_CLEARANCE_MM) -> NestDrawing:
    """A nest plate for one blank of `part` in nest `nest_id` of `fixture`.

    plate_margin_mm: plate material around the pocket (design choice). pocket_clearance_mm: per side,
    blank outline to pocket wall (design choice). The pocket depth is the blank thickness (blank flush).
    Raises NestDrawingError on parameters that cannot make a plate, KeyError on an unknown nest.
    """
    if not plate_margin_mm > 0:
        raise NestDrawingError(f"plate_margin_mm must be > 0, got {plate_margin_mm}")
    if not pocket_clearance_mm >= 0:
        raise NestDrawingError(f"pocket_clearance_mm must be >= 0, got {pocket_clearance_mm}")
    nest = fixture.nest(nest_id)
    pid, fid = part.ref.id, fixture.ref.id
    unmeasured: list[str] = []
    outline, g_out = _fact_or_placeholder(part.outline, "part.outline", f"part {pid} outline", unmeasured)
    holes, g_hole = _fact_or_placeholder(part.holes, "part.holes", f"part {pid} holes", unmeasured)
    thick, g_thick = _fact_or_placeholder(part.thickness_mm, "part.thickness_mm", f"part {pid} thickness_mm",
                                          unmeasured)
    assert isinstance(outline, Outline) and holes is not None and thick is not None
    c, m = pocket_clearance_mm, plate_margin_mm
    bx0, by0, bx1, by1 = _bbox(outline, c)         # pocket box, part frame

    # Nest origin relative to the datum corner, machine axes (+Y toward the operator).
    if nest.origin_mm.known:
        assert nest.origin_mm.value is not None
        ox, oy = nest.origin_mm.value
        g_org: tuple[str, ...] = ()
    else:
        _, ph = PLACEHOLDERS["fixture.nest.origin_mm"]
        gap = nest.origin_mm.gap or ph.gap
        unmeasured.append(f"fixture {fid} nest {nest_id} origin_mm ({gap}): drawn from placeholder {ph.note}")
        ox, oy = m - bx0, m + by1
        g_org = (gap,)
    # Pocket extent from the datum corner (machine axes): x right, y toward the operator.
    left, back = ox + bx0, oy - by1
    if left < m - 1e-9 or back < m - 1e-9:
        raise NestDrawingError(
            f"the pocket edge is {fmt_dim(left)} mm (X) / {fmt_dim(back)} mm (Y) from the datum corner, "
            f"less than plate_margin_mm {fmt_dim(m)}: reduce the margin or move the nest origin")
    width = ox + bx1 + m
    height = oy - by0 + m

    def view(p: Pt) -> Pt:     # part frame -> view frame
        return (ox + p[0], height - oy + p[1])

    sheet = _Sheet()
    # Plate outline and datum corner.
    sheet.add(_Poly("OUTLINE", ((0.0, 0.0), (width, 0.0), (width, height), (0.0, height))))
    d = 3.0
    sheet.add(_Poly("DATUM", ((0.0, height - d), (0.0, height), (d, height)), closed=False))
    sheet.add(_Line("DATUM", (0.0, height), (d * 0.7, height - d * 0.7)))
    sheet.add(_Text("DATUM", (1.0, height - d - TEXT_MM), TEXT_MM * 0.8, "DATUM CORNER (back-left)"))

    # Pocket.
    if outline.kind == "rect":
        pcx, pcy = view(outline.centre_mm)
        _rect_entities(sheet, "POCKET", pcx, pcy, outline.width_mm + 2 * c, outline.height_mm + 2 * c,
                       outline.corner_radius_mm + c if outline.corner_radius_mm > 0 else 0.0)
    else:
        sheet.add(_Poly("POCKET", tuple(view(p) for p in _offset_polygon(outline.points, c))))
    # Blank holes (reference positions, through the blank).
    hole_notes: list[str] = []
    for i, h in enumerate(holes):
        if h.kind == "rect":
            hcx, hcy = view(h.centre_mm)
            _rect_entities(sheet, "HOLE", hcx, hcy, h.width_mm, h.height_mm, h.corner_radius_mm)
            hx, hy = ox + h.centre_mm[0], oy - h.centre_mm[1]
            hsize = (f"DIA {fmt_dim(h.width_mm)}" if _is_circle(h)
                    else f"{fmt_dim(h.width_mm)} x {fmt_dim(h.height_mm)} R {fmt_dim(h.corner_radius_mm)}")
        else:
            sheet.add(_Poly("HOLE", tuple(view(p) for p in h.points)))
            xs = [ox + p[0] for p in h.points]
            ys = [oy - p[1] for p in h.points]
            hx, hy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            hsize = f"polygon, {len(h.points)} vertices"
        gh = _gaps(g_hole, g_org)
        hole_notes.append(f"Blank hole {i + 1}: {hsize}, centre X {fmt_dim(hx)} Y {fmt_dim(hy)} from the datum corner"
                          + (f" UNMEASURED ({', '.join(gh)})" if gh else ""))

    # Part-frame origin crosshair (the datum crosshair is engraved here).
    px, py = view((0.0, 0.0))
    a = CROSSHAIR_ARM_MM
    sheet.add(_Line("DATUM", (px - a, py), (px + a, py)))
    sheet.add(_Line("DATUM", (px, py - a), (px, py + a)))
    sheet.add(_Circle("DATUM", (px, py), a / 4))
    sheet.add(_Text("DATUM", (px + a + 0.6, py + 0.6), TEXT_MM * 0.8, "PART ORIGIN"))

    # Dimensions.
    g_plate = _gaps(g_out, g_org)
    pw, ph_ = bx1 - bx0, by1 - by0
    pl, pr = ox + bx0, ox + bx1
    pt_, pb = height - oy + by1, height - oy + by0     # pocket top / bottom (view)
    _hdim(sheet, 0.0, width, 0.0, -DIM_TIER_MM, _label(width, g_plate, "PLATE "), bool(g_plate))
    _vdim(sheet, 0.0, height, 0.0, -DIM_TIER_MM * 2, _label(height, g_plate, "PLATE "), bool(g_plate))
    _hdim(sheet, 0.0, ox, height, height + DIM_TIER_MM, _label(ox, g_org, "ORIGIN X "), bool(g_org))
    _vdim(sheet, height, height - oy, 0.0, -DIM_TIER_MM, _label(oy, g_org, "ORIGIN Y "), bool(g_org))
    _hdim(sheet, pl, pr, pt_, height + DIM_TIER_MM * 2, _label(pw, g_out, "POCKET "), bool(g_out))
    _vdim(sheet, pb, pt_, width, width + DIM_TIER_MM, _label(ph_, g_out, "POCKET "), bool(g_out))

    # Title block and notes, below the plate.
    lines: list[tuple[str, float, bool]] = []
    title = f"NEST PLATE: {part.name} ({pid}) in {fixture.name} ({fid}), nest {nest_id}"
    lines.append((title, TITLE_MM, False))
    if unmeasured:
        lines.append((NOT_FOR_CUTTING, WARN_MM, True))
        lines.extend((f"UNMEASURED: {u}", TEXT_MM, True) for u in unmeasured)
    lines.append((f"Drawn from: part {pid} v{part.ref.version} (sha256 {part.ref.sha256[:12]}), "
                  f"fixture {fid} v{fixture.ref.version} (sha256 {fixture.ref.sha256[:12]}), nest {nest_id}",
                  TEXT_MM, False))
    lines.append((f"Parameters (design choices, not measurements): plate margin {fmt_dim(m)} mm, "
                  f"pocket clearance {fmt_dim(c)} mm per side", TEXT_MM, False))
    if outline.kind == "rect" and outline.corner_radius_mm > 0:
        lines.append((_label(outline.corner_radius_mm + c, g_out, "Pocket corner R "), TEXT_MM, bool(g_out)))
    lines.append((_label(thick, g_thick, "Pocket depth (= blank thickness, blank flush) "), TEXT_MM,
                  bool(g_thick)))
    lines.extend((t, TEXT_MM, "UNMEASURED" in t) for t in hole_notes)
    lines.append(("Units mm. Top view in machine axes: datum corner back-left (nearest home), +X right, "
                  "operator at the bottom.", TEXT_MM, False))
    lines.append(("Fixture datum, keep-outs and tolerance are measured on the machine after mounting (V4); "
                  "they do not set plate dimensions.", TEXT_MM, False))
    y = -DIM_TIER_MM * 2 - TITLE_MM
    for text, size, warn in lines:
        y -= size * 1.6
        sheet.add(_Text("NOTE", (0.0, y), size, text, warn=warn))

    title_text = tuple(t for t, _, _ in lines)
    return NestDrawing(_to_svg(sheet), _to_dxf(sheet), tuple(unmeasured), (width, height), title_text)


# --- bounds ----------------------------------------------------------------------------------------

def _bounds(sheet: _Sheet) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for e in sheet.items:
        if isinstance(e, _Line):
            xs += [e.a[0], e.b[0]]
            ys += [e.a[1], e.b[1]]
        elif isinstance(e, (_Arc, _Circle)):
            xs += [e.c[0] - e.r, e.c[0] + e.r]
            ys += [e.c[1] - e.r, e.c[1] + e.r]
        elif isinstance(e, _Poly):
            xs += [p[0] for p in e.pts]
            ys += [p[1] for p in e.pts]
        else:
            # Text: estimate its extent (0.6 em per character) so the sheet holds it.
            w = len(e.text) * e.height * 0.6
            if e.vertical:
                xs += [e.p[0] - e.height, e.p[0]]
                ys += [e.p[1] - w / 2, e.p[1] + w / 2]
            else:
                x0 = e.p[0] - (w / 2 if e.anchor == "middle" else 0.0)
                xs += [x0, x0 + w]
                ys += [e.p[1], e.p[1] + e.height]
    return (min(xs), min(ys), max(xs), max(ys))


# --- SVG -------------------------------------------------------------------------------------------

def _to_svg(sheet: _Sheet) -> str:
    x0, y0, x1, y1 = _bounds(sheet)
    x0, y0, x1, y1 = x0 - SHEET_MARGIN_MM, y0 - SHEET_MARGIN_MM, x1 + SHEET_MARGIN_MM, y1 + SHEET_MARGIN_MM
    w, h = x1 - x0, y1 - y0

    def P(p: Pt) -> str:          # view frame -> SVG user units (Y down)
        return f"{fmt(p[0])},{fmt(-p[1])}"

    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{fmt(w)}mm" height="{fmt(h)}mm" '
        f'viewBox="{fmt(x0)} {fmt(-y1)} {fmt(w)} {fmt(h)}">',
        "<!-- GratisGraph Desktop nest plate drawing. Units mm. Top view, machine axes: "
        "datum corner back-left, operator at the bottom. -->",
        "<style>",
        *(f".{k.lower()} {{fill:none;stroke:{v};stroke-width:{fmt(SVG_STROKE_MM)}}}"
          for k, v in SVG_COLOUR.items()),
        *(f"text.{k.lower()} {{fill:{v};stroke:none;font-family:sans-serif}}" for k, v in SVG_COLOUR.items()),
        f"text.warn {{fill:{SVG_WARN_COLOUR};font-weight:bold}}",
        "</style>",
    ]
    for layer in LAYERS:
        out.append(f'<g id="{layer}">')
        for e in sheet.items:
            if e.layer != layer:
                continue
            cls = layer.lower()
            if isinstance(e, _Line):
                out.append(f'<line class="{cls}" x1="{fmt(e.a[0])}" y1="{fmt(-e.a[1])}" '
                           f'x2="{fmt(e.b[0])}" y2="{fmt(-e.b[1])}"/>')
            elif isinstance(e, _Circle):
                out.append(f'<circle class="{cls}" cx="{fmt(e.c[0])}" cy="{fmt(-e.c[1])}" r="{fmt(e.r)}"/>')
            elif isinstance(e, _Arc):
                cs, ss = numerics.cos_sin_deg(e.start_deg)
                ce, se = numerics.cos_sin_deg(e.end_deg)
                a = (e.c[0] + e.r * cs, e.c[1] + e.r * ss)
                b = (e.c[0] + e.r * ce, e.c[1] + e.r * se)
                large = 1 if (e.end_deg - e.start_deg) % 360.0 > 180.0 else 0
                # CCW with +Y up is sweep-flag 0 once Y is flipped.
                out.append(f'<path class="{cls}" d="M {P(a)} A {fmt(e.r)} {fmt(e.r)} 0 {large} 0 {P(b)}"/>')
            elif isinstance(e, _Poly):
                tag = "polygon" if e.closed else "polyline"
                out.append(f'<{tag} class="{cls}" points="{" ".join(P(p) for p in e.pts)}"/>')
            else:
                tcls = f"{cls} warn" if e.warn else cls
                anchor = ' text-anchor="middle"' if e.anchor == "middle" else ""
                rot = f' transform="rotate(-90 {fmt(e.p[0])} {fmt(-e.p[1])})"' if e.vertical else ""
                out.append(f'<text class="{tcls}" x="{fmt(e.p[0])}" y="{fmt(-e.p[1])}" '
                           f'font-size="{fmt(e.height)}"{anchor}{rot}>{html.escape(e.text, quote=False)}</text>')
        out.append("</g>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


# --- DXF R12 ---------------------------------------------------------------------------------------

def _ascii(text: str) -> str:
    return "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in text)


def _to_dxf(sheet: _Sheet) -> str:
    """AutoCAD R12 ASCII DXF (AC1009): LINE, ARC, CIRCLE, POLYLINE/VERTEX/SEQEND, TEXT. mm."""
    x0, y0, x1, y1 = _bounds(sheet)
    o: list[str] = []

    def g(code: int, value: str | int) -> None:
        o.append(f"{code:>3}")
        o.append(str(value))

    def pt(p: Pt, base: int = 10) -> None:
        g(base, fmt(p[0]))
        g(base + 10, fmt(p[1]))
        g(base + 20, "0")

    g(0, "SECTION")
    g(2, "HEADER")
    g(9, "$ACADVER")
    g(1, "AC1009")
    g(9, "$INSUNITS")
    g(70, 4)
    g(9, "$MEASUREMENT")
    g(70, 1)
    g(9, "$EXTMIN")
    pt((x0, y0))
    g(9, "$EXTMAX")
    pt((x1, y1))
    g(0, "ENDSEC")
    g(0, "SECTION")
    g(2, "TABLES")
    g(0, "TABLE")
    g(2, "LTYPE")
    g(70, 1)
    g(0, "LTYPE")
    g(2, "CONTINUOUS")
    g(70, 0)
    g(3, "Solid line")
    g(72, 65)
    g(73, 0)
    g(40, "0")
    g(0, "ENDTAB")
    g(0, "TABLE")
    g(2, "LAYER")
    g(70, len(LAYERS))
    for layer in LAYERS:
        g(0, "LAYER")
        g(2, layer)
        g(70, 0)
        g(62, DXF_COLOUR[layer])
        g(6, "CONTINUOUS")
    g(0, "ENDTAB")
    g(0, "ENDSEC")
    g(0, "SECTION")
    g(2, "ENTITIES")
    for layer in LAYERS:
        for e in sheet.items:
            if e.layer != layer:
                continue
            if isinstance(e, _Line):
                g(0, "LINE")
                g(8, layer)
                pt(e.a)
                pt(e.b, 11)
            elif isinstance(e, _Circle):
                g(0, "CIRCLE")
                g(8, layer)
                pt(e.c)
                g(40, fmt(e.r))
            elif isinstance(e, _Arc):
                g(0, "ARC")
                g(8, layer)
                pt(e.c)
                g(40, fmt(e.r))
                g(50, fmt(e.start_deg))
                g(51, fmt(e.end_deg % 360.0 if e.end_deg >= 360.0 else e.end_deg))
            elif isinstance(e, _Poly):
                g(0, "POLYLINE")
                g(8, layer)
                g(66, 1)
                pt((0.0, 0.0))
                g(70, 1 if e.closed else 0)
                for p in e.pts:
                    g(0, "VERTEX")
                    g(8, layer)
                    pt(p)
                g(0, "SEQEND")
                g(8, layer)
            else:
                g(0, "TEXT")
                g(8, layer)
                pt(e.p)
                g(40, fmt(e.height))
                g(1, _ascii(e.text))
                if e.vertical:
                    g(50, "90")
                if e.anchor == "middle":
                    g(72, 1)
                    pt(e.p, 11)
    g(0, "ENDSEC")
    g(0, "EOF")
    return "\n".join(o) + "\n"
