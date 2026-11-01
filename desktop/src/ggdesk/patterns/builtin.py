"""The built-in bench patterns (F10; desktop/docs/m2-plan.md section 2.3), registered on import.

Each pattern lays out part-frame geometry (mm, +Y up) inside |x| <= 18, |y| <= 18 mm, or
|y| <= 9 mm with `compact = true` (see _layout.py). Patterns whose rows do not fit one job
split them into sets chosen by the `set` parameter. Trace patterns emit trace operations;
`char-ladder-fill` emits fill operations (its height labels are single-line Hershey digits in
trace operations with mode_hint "fill", so the whole job builds with one fill recipe).
"""
from __future__ import annotations

from typing import Any

from ggdesk import numerics
from ggdesk.model.geometry import Polyline, Pt
from ggdesk.model.job import Operation
from ggdesk.patterns import ParamSpec, PatternError, register
from ggdesk.patterns._layout import (
    BOX_X_MM,
    COMPACT,
    HERSHEY_CAP_PER_EM,
    LABEL_CAP_MM,
    LABEL_EM_MM,
    LABEL_GAP_MM,
    PART,
    SET,
    Builtin,
    Layout,
    fill_op,
    half_height,
    label_paths,
    need_positive,
    pack_rows,
    parse_floats,
    pick_set,
    rows_top_down,
    set_note,
    text_paths,
    text_width,
    trace,
)
from ggdesk.text.hershey import hershey_paths
from ggdesk.text.outline import outline_regions


def _scaled(paths: list[list[Pt]], k: float, closed: bool = False) -> tuple[Polyline, ...]:
    return tuple(Polyline(tuple((x * k, y * k) for x, y in pts), closed) for pts in paths)


# --- asymmetric (V1) ----------------------------------------------------------------------------

V1_PATHS: list[list[Pt]] = [
    [(-14.0, 2.0), (-14.0, 14.0), (-8.0, 14.0)],    # F stem and top bar (upper left)
    [(-14.0, 8.0), (-10.0, 8.0)],                    # F middle bar
    [(0.0, -3.0), (0.0, 3.0)],                       # crosshair at the part origin
    [(-3.0, 0.0), (3.0, 0.0)],
    [(-4.0, -10.0), (8.0, -10.0)],                   # +X arrow below
    [(5.0, -7.0), (8.0, -10.0), (5.0, -13.0)],
    [(12.0, -5.0), (12.0, 5.0)],                     # +Y arrow right
    [(10.0, 3.0), (12.0, 5.0), (14.0, 3.0)],
]


def _asymmetric(p: Builtin, a: dict[str, Any]) -> Layout:
    k = 0.5 if a["compact"] else 1.0
    note = "Compact: the V1 geometry at half scale" if a["compact"] else "Geometry of desktop/bench/V1"
    return Layout((trace(_scaled(V1_PATHS, k)),), note=note)


# --- pz-square (V2) -----------------------------------------------------------------------------

def _pz_square(p: Builtin, a: dict[str, Any]) -> Layout:
    s = a["size_mm"]
    need_positive(p, "size_mm", s)
    h = s / 2
    ring = ((-h, -h), (h, -h), (h, h), (-h, h))
    return Layout((trace([Polyline(ring, True)]),), note="Square centred on the part origin (V2 PZ sweep)")


# --- datum-crosshair ----------------------------------------------------------------------------

CORNER_LEG_MM = 2.0


def _datum_crosshair(p: Builtin, a: dict[str, Any]) -> Layout:
    arm, spacing, tick = a["arm_mm"], a["spacing_mm"], a["tick_mm"]
    for name in ("arm_mm", "spacing_mm", "tick_mm"):
        need_positive(p, name, a[name])
    lx, ly = BOX_X_MM, half_height(a["compact"])
    if arm > min(lx, ly):
        raise PatternError(f"{p.name}: parameter arm_mm must be <= {min(lx, ly):g} mm, got {arm!r}")
    t = tick / 2
    paths: list[Polyline] = [Polyline(((-arm, 0.0), (arm, 0.0))), Polyline(((0.0, -arm), (0.0, arm)))]
    k = 1
    while k * spacing <= lx + 1e-9:
        d = k * spacing
        if d > arm:
            paths += [Polyline(((d, -t), (d, t))), Polyline(((-d, -t), (-d, t)))]
        if d > arm and d <= ly + 1e-9:
            paths += [Polyline(((-t, d), (t, d))), Polyline(((-t, -d), (t, -d)))]
        k += 1
    c = CORNER_LEG_MM
    for sx, sy in ((-1.0, 1.0), (1.0, 1.0), (1.0, -1.0), (-1.0, -1.0)):
        x, y = sx * lx, sy * ly
        paths.append(Polyline(((x - sx * c, y), (x, y), (x, y - sy * c))))
    return Layout((trace(paths),), note=f"Ticks every {spacing!r} mm on both axes; corner marks at "
                                        f"(+/-{lx:g}, +/-{ly:g}) mm")


# --- character-height ladders -------------------------------------------------------------------

def _row_frame(heights: list[float], label_w: float, text_ws: list[float]) -> tuple[list[float], float]:
    """(baselines, x of the text column) for rows centred on the part origin."""
    width = label_w + LABEL_GAP_MM + max(text_ws)
    return rows_top_down(heights), -width / 2 + label_w + LABEL_GAP_MM


def _labels(texts: list[str], baselines: list[float], right_x: float) -> list[Polyline]:
    out: list[Polyline] = []
    for txt, y in zip(texts, baselines, strict=True):
        out += label_paths(txt, right_x - text_width(txt, LABEL_EM_MM), y)
    return out


def _char_ladder_trace(p: Builtin, a: dict[str, Any]) -> Layout:
    rows = parse_floats(p, "heights", a["heights"])
    text_paths(p, "text", a["text"], 1.0, 0.0, 0.0)          # validates the glyphs
    ems = [h / HERSHEY_CAP_PER_EM for _, h in rows]
    row_h = [max(h, LABEL_CAP_MM) for _, h in rows]
    sets = pack_rows(p, row_h, 2 * half_height(a["compact"]), "heights")
    idx = pick_set(p, sets, a["set"])
    labels = [rows[i][0] for i in idx]
    label_w = max(text_width(t, LABEL_EM_MM) for t in labels)
    baselines, x_text = _row_frame([row_h[i] for i in idx], label_w,
                                   [text_width(a["text"], ems[i]) for i in idx])
    ops: list[Operation] = []
    for i, y in zip(idx, baselines, strict=True):
        tp = hershey_paths(a["text"], ems[i], x_text, y)
        ops.append(trace(tp.paths, char_height_mm=tp.cap_height_mm))
    ops.append(trace(_labels(labels, baselines, x_text - LABEL_GAP_MM), char_height_mm=LABEL_CAP_MM))
    return Layout(tuple(ops), note=set_note(sets, a["set"]))


def _char_ladder_fill(p: Builtin, a: dict[str, Any]) -> Layout:
    rows = parse_floats(p, "heights", a["heights"])
    if not a["text"]:
        raise PatternError(f"{p.name}: parameter text must not be empty")
    unit = outline_regions(a["text"], 1.0)
    if unit.warnings:
        raise PatternError(f"{p.name}: parameter text: {'; '.join(unit.warnings)}")
    cap_per_em = unit.cap_height_mm
    ems = [h / cap_per_em for _, h in rows]
    row_h = [max(h, LABEL_CAP_MM) for _, h in rows]
    sets = pack_rows(p, row_h, 2 * half_height(a["compact"]), "heights")
    idx = pick_set(p, sets, a["set"])
    labels = [rows[i][0] for i in idx]
    label_w = max(text_width(t, LABEL_EM_MM) for t in labels)
    baselines, x_text = _row_frame([row_h[i] for i in idx], label_w, [unit.width_mm * ems[i] for i in idx])
    ops: list[Operation] = []
    for i, y in zip(idx, baselines, strict=True):
        tr = outline_regions(a["text"], ems[i], x_text, y)
        ops.append(fill_op(tr.regions, char_height_mm=tr.cap_height_mm))
    ops.append(trace(_labels(labels, baselines, x_text - LABEL_GAP_MM), mode_hint="fill",
                     char_height_mm=LABEL_CAP_MM))
    note = set_note(sets, a["set"])
    note = (note + ". " if note else "") + "Labels are single-line traces cut with the fill recipe"
    return Layout(tuple(ops), note=note)


# --- stepover ladder ----------------------------------------------------------------------------

STEP_GAP_X_UNITS = 300          # 3 mm between squares
STEP_LABEL_GAP_MM = 0.5         # square bottom to label cap top


def _stepover_ladder(p: Builtin, a: dict[str, Any]) -> Layout:
    steps = parse_floats(p, "stepovers", a["stepovers"])
    su = []
    for tok, s in steps:
        u = numerics.to_units(s)
        if u < 1 or numerics.to_mm(u) != s:
            raise PatternError(f"{p.name}: parameter stepovers: {tok!r} is not a multiple of 0.01 mm")
        su.append(u)
    size = numerics.to_units(a["size_mm"])
    if size < 2 or numerics.to_mm(size) != a["size_mm"] or size % 2:
        raise PatternError(f"{p.name}: parameter size_mm must be a positive even multiple of 0.01 mm, "
                           f"got {a['size_mm']!r}")
    cols = a["columns"]
    if cols < 1:
        raise PatternError(f"{p.name}: parameter columns must be >= 1, got {cols}")
    cols = min(cols, len(su))
    cell_h = numerics.to_mm(size) + STEP_LABEL_GAP_MM + LABEL_CAP_MM
    grid_rows = [list(range(i, min(i + cols, len(su)))) for i in range(0, len(su), cols)]
    sets = pack_rows(p, [cell_h] * len(grid_rows), 2 * half_height(a["compact"]), "size_mm")
    chosen = [grid_rows[r] for r in pick_set(p, sets, a["set"])]
    width = cols * size + (cols - 1) * STEP_GAP_X_UNITS
    tops = [y + cell_h for y in rows_top_down([cell_h] * len(chosen))]
    paths: list[Polyline] = []
    labels: list[Polyline] = []
    half = size // 2
    for row, top in zip(chosen, tops, strict=True):
        cy = numerics.to_units(top - numerics.to_mm(half))
        for c, i in enumerate(row):
            cx = -width // 2 + c * (size + STEP_GAP_X_UNITS) + half
            x0, x1, y0, y1 = cx - half, cx + half, cy - half, cy + half
            m = numerics.to_mm
            paths.append(Polyline(((m(x0), m(y0)), (m(x1), m(y0)), (m(x1), m(y1)), (m(x0), m(y1))), True))
            k = 1
            while k * su[i] < size:
                y = m(y0 + k * su[i])
                ends = ((m(x0), y), (m(x1), y))
                paths.append(Polyline(ends if k % 2 else ends[::-1]))
                k += 1
            txt = f"{numerics.to_mm(su[i]):.2f}"
            labels += label_paths(txt, m(cx) - text_width(txt, LABEL_EM_MM) / 2,
                                  m(y0) - STEP_LABEL_GAP_MM - LABEL_CAP_MM)
    return Layout((trace(paths), trace(labels, char_height_mm=LABEL_CAP_MM)), note=set_note(sets, a["set"]))


# --- corner test --------------------------------------------------------------------------------

def _corner_test(p: Builtin, a: dict[str, Any]) -> Layout:
    angles = parse_floats(p, "angles", a["angles"])
    for tok, ang in angles:
        if not 0 < ang < 180:
            raise PatternError(f"{p.name}: parameter angles: {tok!r} is not between 0 and 180 degrees")
    leg = a["leg_mm"]
    need_positive(p, "leg_mm", leg)
    teeth = a["teeth"]
    if teeth < 1:
        raise PatternError(f"{p.name}: parameter teeth must be >= 1, got {teeth}")
    cs = [numerics.cos_sin_deg(ang / 2) for _, ang in angles]   # (cos, sin) of the half angle
    tooth_h = [leg * c for c, _ in cs]
    row_h = [max(h, LABEL_CAP_MM) for h in tooth_h]
    sets = pack_rows(p, row_h, 2 * half_height(a["compact"]), "leg_mm")
    idx = pick_set(p, sets, a["set"])
    labels = [angles[i][0] for i in idx]
    label_w = max(text_width(t, LABEL_EM_MM) for t in labels)
    widths = [2 * teeth * leg * cs[i][1] for i in idx]
    baselines, x0 = _row_frame([row_h[i] for i in idx], label_w, widths)
    paths: list[Polyline] = []
    for i, y in zip(idx, baselines, strict=True):
        c, s = cs[i]
        dx, dy = leg * s, leg * c
        pts: list[Pt] = [(x0, y)]
        for n in range(2 * teeth):
            pts.append((x0 + (n + 1) * dx, y + (dy if n % 2 == 0 else 0.0)))
        paths.append(Polyline(tuple(pts)))
    lab = _labels(labels, baselines, x0 - LABEL_GAP_MM)
    return Layout((trace(paths), trace(lab, char_height_mm=LABEL_CAP_MM)),
                  note=(set_note(sets, a["set"]) + ". " if len(sets) > 1 else "")
                  + "Each zigzag has its row's included angle at every vertex; labels in degrees")


# --- job-size ladder ----------------------------------------------------------------------------

SZ_DX = 5            # device units per segment along a row (0.05 mm)
SZ_AMP = 5           # triangle-wave amplitude (0.05 mm): each segment is about 0.07 mm long
SZ_PITCH = 14        # row pitch (0.14 mm)
SZ_ROW_POINTS = 2 * numerics.to_units(BOX_X_MM) // SZ_DX + 1       # 721 points per full row
SZ_STROKE_SEGMENTS = 8 * SZ_ROW_POINTS       # the serpentine is cut into strokes of 8 rows (5768 segments)
# .m20 size of a trace job built from this pattern: FIXED + 12 bytes per segment + 42 per stroke,
# measured on the seed trace recipe (setup block without VD); the tests check the 5 % bound.
SZ_FIXED_BYTES = 154
SZ_STROKE_BYTES = 42
SZ_SEGMENT_BYTES = 12


def _strokes(n: int) -> int:
    return -(-n // SZ_STROKE_SEGMENTS)


def size_ladder_segments(target_bytes: int) -> int:
    """Segments whose estimated .m20 size is the largest not above target_bytes."""
    n = (target_bytes - SZ_FIXED_BYTES) // SZ_SEGMENT_BYTES
    for _ in range(8):
        n = (target_bytes - SZ_FIXED_BYTES - SZ_STROKE_BYTES * _strokes(n)) // SZ_SEGMENT_BYTES
    return n


def _job_size_ladder(p: Builtin, a: dict[str, Any]) -> Layout:
    kb = a["target_kb"]
    lim = numerics.to_units(half_height(a["compact"]))
    max_rows = (2 * lim - SZ_AMP) // SZ_PITCH + 1
    max_n = max_rows * SZ_ROW_POINTS - 1
    n = size_ladder_segments(kb * 1024)
    if kb < 1 or n < 1:
        raise PatternError(f"{p.name}: parameter target_kb must be >= 1, got {kb}")
    if n > max_n:
        cap = (SZ_FIXED_BYTES + SZ_STROKE_BYTES * _strokes(max_n) + SZ_SEGMENT_BYTES * max_n) // 1024
        raise PatternError(f"{p.name}: parameter target_kb {kb} does not fit the area "
                           f"(at most {cap} KB{' with compact' if a['compact'] else ''})")
    # One serpentine of n + 1 points: rows of a triangle wave, top to bottom, alternate rows right
    # to left; the step between rows is a segment too. Cut into strokes that share their end points.
    xl = -numerics.to_units(BOX_X_MM)
    pts: list[tuple[int, int]] = []
    r = 0
    while len(pts) < n + 1:
        base = lim - SZ_AMP - r * SZ_PITCH
        row = [(xl + k * SZ_DX, base + (SZ_AMP if k % 2 else 0)) for k in range(SZ_ROW_POINTS)]
        pts += [(-x, y) for x, y in row] if r % 2 else row
        r += 1
    del pts[n + 1:]
    m = numerics.to_mm
    paths = [Polyline(tuple((m(x), m(y)) for x, y in pts[i:i + SZ_STROKE_SEGMENTS + 1]))
             for i in range(0, n, SZ_STROKE_SEGMENTS)]
    return Layout((trace(paths),), note=f"{n} segments of about 0.07 mm in {r} rows and {len(paths)} strokes; "
                                        f"target {kb * 1024} bytes (1 KB = 1024 bytes); run with the tool reversed")


# --- repeat batch -------------------------------------------------------------------------------

REPEAT_ARM_MM = 3.0
REPEAT_LABEL_EM_MM = 3.2        # cap 2.1 mm, scale 0.1 mm per Hershey unit


def _repeat_batch(p: Builtin, a: dict[str, Any]) -> Layout:
    if a["quantity"] < 1:
        raise PatternError(f"{p.name}: parameter quantity must be >= 1, got {a['quantity']}")
    lx, ly = BOX_X_MM, half_height(a["compact"])
    rect = Polyline(((-lx, -ly), (lx, -ly), (lx, ly), (-lx, ly)), True)
    arm = REPEAT_ARM_MM
    cross = [Polyline(((-arm, 0.0), (arm, 0.0))), Polyline(((0.0, -arm), (0.0, arm)))]
    w = text_width(a["label"], REPEAT_LABEL_EM_MM) if a["label"] else 0.0
    lab = text_paths(p, "label", a["label"], REPEAT_LABEL_EM_MM, -w / 2, arm + 1.0)
    return Layout((trace([rect, *cross]), trace(lab, char_height_mm=REPEAT_LABEL_EM_MM * HERSHEY_CAP_PER_EM)),
                  quantity=a["quantity"],
                  note="Rectangle on the layout box (the part outline inset by its 2 mm margin), crosshair "
                       "at the part origin, label above it")


# --- registry -----------------------------------------------------------------------------------

PATTERN_LIST = (
    Builtin("asymmetric", "V1 orientation and position: F, +X and +Y arrows, crosshair", "trace",
            (PART, COMPACT), _asymmetric),
    Builtin("pz-square", "V2 PZ sweep: square at the part origin (vary --set pz=)", "trace",
            (ParamSpec("size_mm", float, 10.0, "side of the square, mm"), PART, COMPACT), _pz_square,
            ("size_mm",)),
    Builtin("datum-crosshair", "Fixture datum: crosshair at the part origin, axis ticks, corner marks", "trace",
            (ParamSpec("arm_mm", float, 3.0, "crosshair half-length, mm"),
             ParamSpec("spacing_mm", float, 5.0, "distance between axis ticks, mm"),
             ParamSpec("tick_mm", float, 1.0, "tick length, mm"), PART, COMPACT), _datum_crosshair,
            ("arm_mm", "tick_mm")),
    Builtin("char-ladder-trace", "Character-height ladder, single-line Hershey, rows labelled with cap height",
            "trace",
            (ParamSpec("heights", str, "0.8,1.0,1.2,1.5,2.0,2.5,3.0", "cap heights in mm, comma-separated"),
             ParamSpec("text", str, "AEHMRS0389", "sample text on every row"), SET, PART, COMPACT),
            _char_ladder_trace, ("heights", "text")),
    Builtin("char-ladder-fill", "Character-height ladder, filled Arimo outlines, rows labelled with cap height",
            "fill",
            (ParamSpec("heights", str, "1.5,2.0,2.5,3.0,3.5,4.0,5.0", "cap heights in mm, comma-separated"),
             ParamSpec("text", str, "AERS08", "sample text on every row"), SET, PART, COMPACT),
            _char_ladder_fill, ("heights", "text")),
    Builtin("stepover-ladder", "Stepover ladder: squares hatched with explicit trace lines, labelled in mm",
            "trace",
            (ParamSpec("stepovers", str, "0.05,0.08,0.10,0.12,0.15,0.20,0.25,0.30",
                       "hatch spacings in mm (multiples of 0.01), comma-separated"),
             ParamSpec("size_mm", float, 6.0, "side of each square, mm"),
             ParamSpec("columns", int, 4, "squares per row"), SET, PART, COMPACT),
            _stepover_ladder, ("size_mm", "columns")),
    Builtin("corner-test", "Corner test: zigzags with included angles 15 to 150 degrees, labelled", "trace",
            (ParamSpec("angles", str, "15,30,45,60,90,120,150", "included angles in degrees, comma-separated"),
             ParamSpec("leg_mm", float, 3.0, "zigzag leg length, mm"),
             ParamSpec("teeth", int, 3, "teeth per zigzag"), SET, PART, COMPACT),
            _corner_test, ("leg_mm", "teeth")),
    Builtin("job-size-ladder", "Job-size ladder: a dense serpentine of short segments sized to target_kb",
            "trace",
            (ParamSpec("target_kb", int, 16, "target .m20 size in KB of 1024 bytes (sheet: 16, 64, 256, 512, 1024)"),
             PART, COMPACT), _job_size_ladder),
    Builtin("repeat-batch", "Repeat batch: first-article layout (outline rectangle, crosshair, label) x quantity",
            "trace",
            (ParamSpec("quantity", int, 10, "job quantity"), ParamSpec("label", str, "BATCH", "label text"),
             PART, COMPACT), _repeat_batch, ("label",)),
)

for _p in PATTERN_LIST:
    register(_p)
