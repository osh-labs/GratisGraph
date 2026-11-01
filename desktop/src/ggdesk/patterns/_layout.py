"""Shared layout helpers for the built-in bench patterns (desktop/docs/m2-plan.md section 2.3).

Every pattern lays out its geometry in the part frame inside a fixed box: |x| <= 18 mm and
|y| <= 18 mm (the 40 x 40 mm `bench-scrap-40` area minus its 2 mm margin), or |y| <= 9 mm with
`compact = true` (a tag-sized area). The box is a property of the pattern, not of the `part`
parameter: `part` only names the library entry written to the job, and the output gate judges
the geometry against that part (H7).

All maths here is +, -, * and / on floats, plus ggdesk.numerics for anything else, so the same
parameters give the same job text on every platform.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from ggdesk import __version__, numerics
from ggdesk.model.geometry import Polyline, Pt
from ggdesk.model.job import FillOp, Job, JobSource, Operation, TraceOp
from ggdesk.patterns import DEFAULT_PART, ParamSpec, PatternError, coerce
from ggdesk.text.hershey import hershey_paths

BOX_X_MM = 18.0               # half-width of the layout box
BOX_Y_MM = 18.0               # half-height of the layout box
COMPACT_Y_MM = 9.0            # half-height with compact = true
FIT_EPS_MM = 1e-9

LABEL_EM_MM = 2.0             # Hershey em size of the small labels (scale 1/16: exact binary coordinates)
LABEL_CAP_MM = LABEL_EM_MM * 21 / 32      # 1.3125 mm: futural "H" is 21 of 32 em units
HERSHEY_CAP_PER_EM = 21 / 32
ROW_GAP_MM = 1.5              # vertical gap between ladder rows
LABEL_GAP_MM = 1.0            # gap between a row label and the row

PART = ParamSpec("part", str, DEFAULT_PART, "part library id written to the job (default bench-scrap-40)")
COMPACT = ParamSpec("compact", bool, False, "fit |x| <= 18, |y| <= 9 mm (tag-sized area) instead of 36 x 36 mm")
SET = ParamSpec("set", int, 1, "which set of rows when the rows do not fit one job (1 = first)")


def half_height(compact: bool) -> float:
    return COMPACT_Y_MM if compact else BOX_Y_MM


@dataclass
class Builtin:
    """A registered pattern: metadata plus a layout function taking the coerced parameters.

    Not frozen: the Pattern protocol declares plain (settable) attributes."""
    name: str
    title: str
    mode: Literal["trace", "fill"]
    params: tuple[ParamSpec, ...]
    layout: Callable[[Builtin, dict[str, Any]], Layout]
    size_params: tuple[str, ...] = ()       # named when the layout does not fit the box

    def generate(self, **params: Any) -> Job:
        p = coerce(self, params)
        part = p.get("part", DEFAULT_PART)
        if not isinstance(part, str) or not part.strip():
            raise PatternError(f"{self.name}: parameter part must name a part library entry")
        lay = self.layout(self, p)
        check_fit(self, lay.operations, bool(p.get("compact", False)))
        return Job(part=part.strip(), operations=lay.operations, quantity=lay.quantity,
                   reference=reference(self, p, lay.note),
                   source=JobSource(f"ggdesk pattern {self.name}", __version__))


@dataclass(frozen=True)
class Layout:
    operations: tuple[Operation, ...]
    quantity: int = 1
    note: str = ""


def fmt_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    return repr(v)


def reference(p: Builtin, params: dict[str, Any], note: str) -> str:
    args = ", ".join(f"{s.name}={fmt_value(params[s.name])}" for s in p.params)
    return f"{p.title}. Parameters: {args}" + (f". {note}" if note else "")


def points_of(ops: Iterable[Operation]) -> Iterable[Pt]:
    for op in ops:
        if isinstance(op, TraceOp):
            for pl in op.paths:
                yield from pl.points
        else:
            for r in op.regions:
                yield from r.outer
                for h in r.holes:
                    yield from h


def extent(ops: Iterable[Operation]) -> tuple[float, float]:
    """(max |x|, max |y|) over every point of every operation."""
    mx = my = 0.0
    for x, y in points_of(ops):
        mx = max(mx, abs(x))
        my = max(my, abs(y))
    return mx, my


def check_fit(p: Builtin, ops: Sequence[Operation], compact: bool) -> None:
    lim_y = half_height(compact)
    mx, my = extent(ops)
    if mx > BOX_X_MM + FIT_EPS_MM or my > lim_y + FIT_EPS_MM:
        hint = f"; reduce parameter(s) {', '.join(p.size_params)}" if p.size_params else ""
        raise PatternError(f"{p.name}: the layout reaches |x| {mx:.3f} mm, |y| {my:.3f} mm, outside the "
                           f"|x| <= {BOX_X_MM:g}, |y| <= {lim_y:g} mm area{' (compact)' if compact else ''}{hint}")


def parse_floats(p: Builtin, param: str, text: str) -> tuple[tuple[str, float], ...]:
    """'0.8, 1.0' -> (('0.8', 0.8), ('1.0', 1.0)): each value > 0 and finite, with its text for labels."""
    out: list[tuple[str, float]] = []
    for tok in (t.strip() for t in text.split(",")):
        try:
            v = float(tok)
        except ValueError as e:
            raise PatternError(f"{p.name}: parameter {param} expects comma-separated numbers, got {text!r}") from e
        if not 0 < v < 1e6:
            raise PatternError(f"{p.name}: parameter {param} values must be > 0, got {tok!r}")
        out.append((tok, v))
    if not out:
        raise PatternError(f"{p.name}: parameter {param} needs at least one value")
    return tuple(out)


def need_positive(p: Builtin, param: str, v: float) -> None:
    if not 0 < v < 1e6:
        raise PatternError(f"{p.name}: parameter {param} must be > 0, got {v!r}")


def text_paths(p: Builtin, param: str, text: str, em_mm: float, x: float, y: float) -> tuple[Polyline, ...]:
    """Hershey single-line text (baseline at y, left edge at x); a missing glyph is a parameter error."""
    if not text:
        raise PatternError(f"{p.name}: parameter {param} must not be empty")
    tp = hershey_paths(text, em_mm, x, y)
    if tp.warnings:
        raise PatternError(f"{p.name}: parameter {param}: {'; '.join(tp.warnings)}")
    return tp.paths


def text_width(text: str, em_mm: float) -> float:
    return hershey_paths(text, em_mm).width_mm


def label_paths(text: str, x: float, y: float) -> tuple[Polyline, ...]:
    """A small Hershey label (pattern-made text, always printable ASCII)."""
    return hershey_paths(text, LABEL_EM_MM, x, y).paths


def pack_rows(p: Builtin, heights: Sequence[float], limit: float, param: str) -> list[list[int]]:
    """Greedy split of rows (top to bottom) into sets whose height with gaps fits `limit`."""
    sets: list[list[int]] = []
    cur: list[int] = []
    used = 0.0
    for i, h in enumerate(heights):
        if h > limit + FIT_EPS_MM:
            raise PatternError(f"{p.name}: parameter {param}: a row {h:.3f} mm tall does not fit the "
                               f"{limit:g} mm area")
        need = h if not cur else used + ROW_GAP_MM + h
        if cur and need > limit + FIT_EPS_MM:
            sets.append(cur)
            cur, used = [i], h
        else:
            cur.append(i)
            used = need
    if cur:
        sets.append(cur)
    return sets


def pick_set(p: Builtin, sets: list[list[int]], set_no: int) -> list[int]:
    if not 1 <= set_no <= len(sets):
        raise PatternError(f"{p.name}: parameter set must be 1 to {len(sets)} with these parameters, got {set_no}")
    return sets[set_no - 1]


def set_note(sets: list[list[int]], set_no: int) -> str:
    return f"Set {set_no} of {len(sets)}" if len(sets) > 1 else ""


def rows_top_down(heights: Sequence[float]) -> list[float]:
    """Baselines of rows stacked top to bottom with ROW_GAP_MM, the block centred on y = 0."""
    total = sum(heights) + ROW_GAP_MM * (len(heights) - 1)
    y = total / 2
    out: list[float] = []
    for h in heights:
        out.append(y - h)
        y -= h + ROW_GAP_MM
    return out


def mm(units: int) -> float:
    return numerics.to_mm(units)


def trace(paths: Iterable[Polyline], mode_hint: str = "trace", char_height_mm: float | None = None) -> TraceOp:
    return TraceOp(tuple(paths), mode_hint, char_height_mm)


def fill_op(regions: Iterable[Any], char_height_mm: float | None = None) -> FillOp:
    return FillOp(tuple(regions), "fill", char_height_mm)
