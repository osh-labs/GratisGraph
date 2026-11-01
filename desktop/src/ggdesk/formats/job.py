"""gratisgraph-job v1 reader and writer (desktop/docs/job-format.md).

The reader validates by hand (no runtime dependency) and names the JSON path
of the first problem. formats/job.schema.json states the same rules for
producers; tests/unit/test_job_format.py checks the examples against both.
Unknown keys at the top level and in each operation are kept in `extra` and
written back after the known keys, so a round trip loses nothing.
"""
from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ggdesk.model.geometry import Polyline, Pt, Region
from ggdesk.model.job import FillOp, Job, JobSource, Operation, TraceOp

FORMAT = "gratisgraph-job"
VERSION = 1
MAX_CHORD_TOLERANCE_MM = 0.01
SCHEMA_PATH = Path(__file__).with_name("job.schema.json")

_TOP_KEYS = ("format", "version", "units", "part", "quantity", "reference", "source",
             "chord_tolerance_mm", "operations")
_OP_KEYS = {"trace": ("op", "mode_hint", "char_height_mm", "paths"),
            "fill": ("op", "mode_hint", "char_height_mm", "regions")}


class JobFormatError(ValueError):
    """The document is not a valid gratisgraph-job v1 file."""


def _err(path: str, msg: str) -> JobFormatError:
    return JobFormatError(f"{path}: {msg}")


def _num(v: Any, path: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise _err(path, f"expected a finite number, got {v!r}")
    return float(v)


def _str(v: Any, path: str) -> str:
    if not isinstance(v, str):
        raise _err(path, f"expected a string, got {v!r}")
    return v


def _obj(v: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(v, dict):
        raise _err(path, "expected an object")
    return v


def _list(v: Any, path: str) -> list[Any]:
    if not isinstance(v, list):
        raise _err(path, "expected an array")
    return v


def _point(v: Any, path: str) -> Pt:
    lst = _list(v, path)
    if len(lst) != 2:
        raise _err(path, "a point is [x, y]")
    return (_num(lst[0], f"{path}[0]"), _num(lst[1], f"{path}[1]"))


def _ring(v: Any, path: str, minimum: int) -> tuple[Pt, ...]:
    pts = tuple(_point(p, f"{path}[{i}]") for i, p in enumerate(_list(v, path)))
    if len(pts) < minimum:
        raise _err(path, f"needs at least {minimum} points, got {len(pts)}")
    return pts


def _polyline(v: Any, path: str) -> Polyline:
    o = _obj(v, path)
    unknown = set(o) - {"points", "closed"}
    if unknown:
        raise _err(path, f"unknown keys {sorted(unknown)}")
    closed = o.get("closed", False)
    if not isinstance(closed, bool):
        raise _err(f"{path}.closed", "expected true or false")
    pts = _ring(o.get("points"), f"{path}.points", 3 if closed else 2)
    if closed and pts[0] == pts[-1]:
        raise _err(f"{path}.points", "a closed path must not repeat its first point")
    return Polyline(pts, closed)


def _region(v: Any, path: str) -> Region:
    o = _obj(v, path)
    unknown = set(o) - {"outer", "holes"}
    if unknown:
        raise _err(path, f"unknown keys {sorted(unknown)}")
    outer = _ring(o.get("outer"), f"{path}.outer", 3)
    holes = tuple(_ring(h, f"{path}.holes[{i}]", 3)
                  for i, h in enumerate(_list(o.get("holes", []), f"{path}.holes")))
    for name, ring in [("outer", outer)] + [(f"holes[{i}]", h) for i, h in enumerate(holes)]:
        if ring[0] == ring[-1]:
            raise _err(f"{path}.{name}", "a ring must not repeat its first point")
    return Region(outer, holes)


def _extra(o: Mapping[str, Any], known: tuple[str, ...]) -> dict[str, Any]:
    return {k: v for k, v in o.items() if k not in known}


def _operation(v: Any, path: str) -> Operation:
    o = _obj(v, path)
    kind = o.get("op")
    if kind not in _OP_KEYS:
        raise _err(f"{path}.op", f"expected 'trace' or 'fill', got {kind!r}")
    mode = _str(o.get("mode_hint", kind), f"{path}.mode_hint")
    ch = o.get("char_height_mm")
    char_h = None if ch is None else _num(ch, f"{path}.char_height_mm")
    if char_h is not None and char_h <= 0:
        raise _err(f"{path}.char_height_mm", "must be > 0")
    extra = _extra(o, _OP_KEYS[kind])
    if kind == "trace":
        paths = tuple(_polyline(p, f"{path}.paths[{i}]")
                      for i, p in enumerate(_list(o.get("paths"), f"{path}.paths")))
        if not paths:
            raise _err(f"{path}.paths", "needs at least one path")
        return TraceOp(paths, mode, char_h, extra)
    regions = tuple(_region(r, f"{path}.regions[{i}]")
                    for i, r in enumerate(_list(o.get("regions"), f"{path}.regions")))
    if not regions:
        raise _err(f"{path}.regions", "needs at least one region")
    return FillOp(regions, mode, char_h, extra)


def from_obj(doc: Any) -> Job:
    o = _obj(doc, "$")
    if o.get("format") != FORMAT:
        raise _err("$.format", f"expected {FORMAT!r}, got {o.get('format')!r}")
    if o.get("version") != VERSION or isinstance(o.get("version"), bool):
        raise _err("$.version", f"unsupported version {o.get('version')!r} (this build reads {VERSION})")
    if o.get("units") != "mm":
        raise _err("$.units", f"expected 'mm', got {o.get('units')!r}")
    part = _str(o.get("part"), "$.part")
    if not part:
        raise _err("$.part", "must name a part library entry")
    qty = o.get("quantity", 1)
    if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
        raise _err("$.quantity", f"expected an integer >= 1, got {qty!r}")
    ref = _str(o.get("reference", ""), "$.reference")
    src = None
    if "source" in o:
        so = _obj(o["source"], "$.source")
        if set(so) - {"name", "version"}:
            raise _err("$.source", f"unknown keys {sorted(set(so) - {'name', 'version'})}")
        src = JobSource(_str(so.get("name"), "$.source.name"), _str(so.get("version", ""), "$.source.version"))
    tol = _num(o.get("chord_tolerance_mm", MAX_CHORD_TOLERANCE_MM), "$.chord_tolerance_mm")
    if not 0 < tol <= MAX_CHORD_TOLERANCE_MM:
        raise _err("$.chord_tolerance_mm", f"must be > 0 and <= {MAX_CHORD_TOLERANCE_MM} mm, got {tol}")
    ops = tuple(_operation(op, f"$.operations[{i}]")
                for i, op in enumerate(_list(o.get("operations"), "$.operations")))
    if not ops:
        raise _err("$.operations", "needs at least one operation")
    return Job(part, ops, qty, ref, src, tol, _extra(o, _TOP_KEYS))


def loads(text: str) -> Job:
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        raise JobFormatError(f"not JSON: {e}") from e
    return from_obj(doc)


def load(path: Path) -> Job:
    return loads(Path(path).read_text(encoding="utf-8"))


def _pts(pts: tuple[Pt, ...]) -> list[list[float]]:
    return [[x, y] for x, y in pts]


def to_obj(job: Job) -> dict[str, Any]:
    out: dict[str, Any] = {"format": FORMAT, "version": VERSION, "units": "mm", "part": job.part,
                           "quantity": job.quantity}
    if job.reference:
        out["reference"] = job.reference
    if job.source is not None:
        out["source"] = {"name": job.source.name, "version": job.source.version}
    out["chord_tolerance_mm"] = job.chord_tolerance_mm
    ops: list[dict[str, Any]] = []
    for op in job.operations:
        d: dict[str, Any]
        if isinstance(op, TraceOp):
            d = {"op": "trace", "mode_hint": op.mode_hint}
            if op.char_height_mm is not None:
                d["char_height_mm"] = op.char_height_mm
            d["paths"] = [{"points": _pts(p.points), "closed": p.closed} for p in op.paths]
        else:
            d = {"op": "fill", "mode_hint": op.mode_hint}
            if op.char_height_mm is not None:
                d["char_height_mm"] = op.char_height_mm
            d["regions"] = [{"outer": _pts(r.outer), "holes": [_pts(h) for h in r.holes]}
                            for r in op.regions]
        d.update(op.extra)
        ops.append(d)
    out["operations"] = ops
    out.update(job.extra)
    return out


def dumps(job: Job) -> str:
    """Deterministic text: fixed key order, extras after the known keys, 2-space indent, final newline."""
    return json.dumps(to_obj(job), indent=2, ensure_ascii=False) + "\n"


def dump(job: Job, path: Path) -> None:
    Path(path).write_text(dumps(job), encoding="utf-8", newline="\n")
