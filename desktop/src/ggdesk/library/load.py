"""TOML library loader and validators.

Layout: <dir>/<kind>s/<id>.toml, one entry per file. Directories passed later
override earlier ones by id (seed, then user, then test overlays). An invalid
entry is listed in Library.errors and left out; it is never skipped silently.
"""
from __future__ import annotations

import hashlib
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from ggdesk import paths
from ggdesk.library.model import (
    CONFIDENCE,
    KINDS,
    EntryRef,
    Fact,
    Fixture,
    Machine,
    ManualSettings,
    Material,
    Nest,
    Outline,
    Part,
    Range,
    Recipe,
    Source,
    Tool,
)
from ggdesk.model.geometry import Pt

T = TypeVar("T")
SCHEMA_VERSION = 1

# Fact fields that set a hard gate limit: a [HYPOTHESIS] value here is an error (CLAUDE.md rule 4).
HARD_LIMIT_FIELDS = {
    "machine": ("work_field_mm", "ranges", "max_job_bytes", "model_code"),
    "part": ("outline", "keep_out_margin_mm", "holes"),
    "fixture": ("datum_mm", "origin_mm", "keep_outs"),
}


class EntryError(ValueError):
    pass


@dataclass(frozen=True)
class LibraryError:
    path: Path
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


@dataclass(frozen=True)
class Library:
    machines: Mapping[str, Machine] = field(default_factory=dict)
    tools: Mapping[str, Tool] = field(default_factory=dict)
    materials: Mapping[str, Material] = field(default_factory=dict)
    parts: Mapping[str, Part] = field(default_factory=dict)
    fixtures: Mapping[str, Fixture] = field(default_factory=dict)
    recipes: Mapping[str, Recipe] = field(default_factory=dict)
    errors: tuple[LibraryError, ...] = ()
    sources: Mapping[tuple[str, str], Mapping[str, Source]] = field(default_factory=dict)
    files: Mapping[tuple[str, str], Path] = field(default_factory=dict)

    def get(self, kind: str, id: str) -> Any:
        table: Mapping[str, Any] = getattr(self, kind + "s")
        if id not in table:
            raise KeyError(f"no {kind} {id!r} in the library"
                           f" (have: {', '.join(sorted(table)) or 'none'})")
        return table[id]

    def entries(self) -> list[tuple[str, Any]]:
        out: list[tuple[str, Any]] = []
        for kind in KINDS:
            table: Mapping[str, Any] = getattr(self, kind + "s")
            out.extend((kind, table[k]) for k in sorted(table))
        return out


# --- fact parsing -----------------------------------------------------------

class _Ctx:
    def __init__(self, kind: str, sources: Mapping[str, Source]) -> None:
        self.kind = kind
        self.sources = sources

    def fact(self, doc: Mapping[str, Any], key: str, conv: Callable[[Any, str], T],
             *, required: bool = True, hard: bool = False, label: str | None = None) -> Fact[T]:
        name = label or key
        if key not in doc:
            if required:
                raise EntryError(f"missing fact {name!r}")
            return Fact(None)
        t = doc[key]
        if not isinstance(t, dict):
            raise EntryError(f"{name}: expected a fact table (value/src/ref/confidence or null/needs_measurement)")
        allowed = {"value", "src", "ref", "confidence", "null", "needs_measurement", "gap", "measure",
                   "min", "max", "note"}
        unknown = set(t) - allowed
        if unknown:
            raise EntryError(f"{name}: unknown keys {sorted(unknown)}")
        if t.get("null") is True:
            if "value" in t or "min" in t:
                raise EntryError(f"{name}: null fact also carries a value")
            nm = bool(t.get("needs_measurement", False))
            measure = t.get("measure", [])
            if nm:
                if not isinstance(t.get("gap"), str) or not t["gap"]:
                    raise EntryError(f"{name}: needs_measurement fact must name its gap (e.g. gap = \"G1\")")
                if not isinstance(measure, list) or not measure or not all(isinstance(m, str) for m in measure):
                    raise EntryError(f"{name}: needs_measurement fact needs a non-empty measure = [...] procedure")
            return Fact(None, needs_measurement=nm, gap=t.get("gap"), measure=tuple(measure))
        if t.get("needs_measurement"):
            raise EntryError(f"{name}: needs_measurement must have null = true and no value")
        src, ref, conf = t.get("src"), t.get("ref"), t.get("confidence")
        if conf not in CONFIDENCE:
            raise EntryError(f"{name}: confidence must be one of {', '.join(CONFIDENCE)}, got {conf!r}")
        if not isinstance(src, str) or src not in self.sources:
            raise EntryError(f"{name}: src {src!r} is not a key of [sources]")
        if not isinstance(ref, str) or not ref:
            raise EntryError(f"{name}: needs a ref (page, section or file)")
        if hard and conf == "HYPOTHESIS":
            raise EntryError(f"{name}: a [HYPOTHESIS] value cannot set a hard gate limit")
        raw = {"min": t["min"], "max": t["max"]} if "min" in t else t.get("value")
        if raw is None:
            raise EntryError(f"{name}: fact has neither value nor null = true")
        try:
            value = conv(raw, name)
        except (TypeError, ValueError) as e:
            raise EntryError(f"{name}: {e}") from e
        return Fact(value, src, ref, conf)


def _int(v: Any, name: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValueError(f"expected an integer, got {v!r}")
    return v


def _float(v: Any, name: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"expected a number, got {v!r}")
    return float(v)


def _pos_float(v: Any, name: str) -> float:
    f = _float(v, name)
    if f < 0:
        raise ValueError(f"must be >= 0, got {f}")
    return f


def _bool(v: Any, name: str) -> bool:
    if not isinstance(v, bool):
        raise ValueError(f"expected true or false, got {v!r}")
    return v


def _str(v: Any, name: str) -> str:
    if not isinstance(v, str):
        raise ValueError(f"expected a string, got {v!r}")
    return v


def _pt(v: Any, name: str) -> Pt:
    if not isinstance(v, list) or len(v) != 2:
        raise ValueError(f"expected [x, y], got {v!r}")
    return (_float(v[0], name), _float(v[1], name))


def _pair(v: Any, name: str) -> tuple[float, float]:
    x, y = _pt(v, name)
    if x <= 0 or y <= 0:
        raise ValueError("both dimensions must be > 0")
    return (x, y)


def _range(v: Any, name: str) -> Range:
    lo, hi = _int(v["min"], name), _int(v["max"], name)
    if lo > hi or lo < 0 or hi > 0xFFFF:
        raise ValueError(f"range {lo}..{hi} must satisfy 0 <= min <= max <= 65535")
    return Range(lo, hi)


def _polygon(v: Any, name: str) -> tuple[Pt, ...]:
    if not isinstance(v, list) or len(v) < 3:
        raise ValueError("a polygon needs at least 3 points")
    return tuple(_pt(p, name) for p in v)


def _polygons(v: Any, name: str) -> tuple[tuple[Pt, ...], ...]:
    if not isinstance(v, list):
        raise ValueError("expected a list of polygons")
    return tuple(_polygon(p, name) for p in v)


def _outline(v: Any, name: str) -> Outline:
    if not isinstance(v, dict):
        raise ValueError("an outline is a table with kind = \"rect\" or \"polygon\"")
    kind = v.get("kind")
    if kind == "rect":
        w, h = _float(v.get("width_mm"), name), _float(v.get("height_mm"), name)
        r = _float(v.get("corner_radius_mm", 0.0), name)
        if w <= 0 or h <= 0 or r < 0 or r > min(w, h) / 2:
            raise ValueError("rect needs width_mm, height_mm > 0 and 0 <= corner_radius_mm <= min/2")
        c = _pt(v.get("centre_mm", [0.0, 0.0]), name)
        return Outline("rect", w, h, r, c)
    if kind == "polygon":
        return Outline("polygon", points=_polygon(v.get("points"), name))
    raise ValueError(f"unknown outline kind {kind!r}")


def _outlines(v: Any, name: str) -> tuple[Outline, ...]:
    if not isinstance(v, list):
        raise ValueError("expected a list of outlines")
    return tuple(_outline(o, name) for o in v)


# --- entries ----------------------------------------------------------------

def _sources(doc: Mapping[str, Any]) -> dict[str, Source]:
    out: dict[str, Source] = {}
    raw = doc.get("sources", {})
    if not isinstance(raw, dict):
        raise EntryError("[sources] must be a table")
    for key, s in raw.items():
        if not isinstance(s, dict) or not isinstance(s.get("title"), str):
            raise EntryError(f"sources.{key}: needs a title")
        path, url = s.get("path"), s.get("url")
        if (path is None) == (url is None):
            raise EntryError(f"sources.{key}: give exactly one of path (repository-relative) or url")
        kind = s.get("kind")
        if kind not in ("maker", "observation", "measurement", "project_decision", "driver", "manual"):
            raise EntryError(f"sources.{key}: unknown kind {kind!r}")
        out[key] = Source(key, s["title"], path, url, kind)
    out.setdefault("override", Source("override", "bench override", None, None, "project_decision"))
    return out


def _sub(doc: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    t = doc.get(key, {})
    if not isinstance(t, dict):
        raise EntryError(f"[{key}] must be a table")
    return t


def _machine(doc: Mapping[str, Any], ref: EntryRef, c: _Ctx) -> Machine:
    ops = _sub(doc, "opcodes")
    allowed = ops.get("allowed")
    reserved = ops.get("reserved", [])
    if not isinstance(allowed, list) or not all(isinstance(o, str) and len(o) == 2 for o in allowed):
        raise EntryError("opcodes.allowed must be a list of two-character opcodes")
    if not isinstance(reserved, list) or not all(isinstance(o, str) and len(o) == 2 for o in reserved):
        raise EntryError("opcodes.reserved must be a list of two-character opcodes")
    ranges_doc = _sub(doc, "ranges")
    ranges = {k: c.fact(ranges_doc, k, _range, hard=True, label=f"ranges.{k}") for k in sorted(ranges_doc)}
    for k in ("mc", "vs", "vz", "pz", "dz", "vd"):
        if k not in ranges:
            raise EntryError(f"ranges.{k} missing")
    completion = doc.get("completion", "")
    if not isinstance(completion, str) or not completion:
        raise EntryError("completion must name the completion method")
    send_enabled = doc.get("send_enabled", False)
    if not isinstance(send_enabled, bool):
        raise EntryError("send_enabled must be true or false")
    return Machine(ref, _name(doc), c.fact(doc, "model_code", _int, hard=True), send_enabled,
                   c.fact(doc, "work_field_mm", _pair, hard=True), tuple(allowed), tuple(reserved),
                   ranges, completion, c.fact(doc, "max_job_bytes", _int, hard=True))


def _tool(doc: Mapping[str, Any], ref: EntryRef, c: _Ctx) -> Tool:
    t = doc.get("type")
    if t not in ("rotary_diamond", "drag_diamond", "carbide"):
        raise EntryError(f"type must be rotary_diamond, drag_diamond or carbide, got {t!r}")
    return Tool(ref, _name(doc), t, c.fact(doc, "needs_spindle", _bool), c.fact(doc, "needs_nose", _bool),
                c.fact(doc, "tip_width_mm", _pos_float))


def _material(doc: Mapping[str, Any], ref: EntryRef, c: _Ctx) -> Material:
    return Material(ref, _name(doc), c.fact(doc, "alloy", _str), c.fact(doc, "finish", _str),
                    c.fact(doc, "thickness_mm", _pos_float))


def _part(doc: Mapping[str, Any], ref: EntryRef, c: _Ctx) -> Part:
    mat = doc.get("material")
    if not isinstance(mat, str):
        raise EntryError("material must name a material entry")
    return Part(ref, _name(doc), mat, c.fact(doc, "outline", _outline, hard=True),
                c.fact(doc, "holes", _outlines, hard=True),
                c.fact(doc, "keep_out_margin_mm", _pos_float, hard=True),
                c.fact(doc, "thickness_mm", _pos_float))


def _fixture(doc: Mapping[str, Any], ref: EntryRef, c: _Ctx) -> Fixture:
    nests_doc = doc.get("nests", [])
    if not isinstance(nests_doc, list) or not nests_doc:
        raise EntryError("[[nests]] needs at least one nest")
    nests: list[Nest] = []
    for i, n in enumerate(nests_doc):
        if not isinstance(n, dict) or not isinstance(n.get("id"), str):
            raise EntryError(f"nests[{i}] needs an id")
        nests.append(Nest(n["id"], c.fact(n, "origin_mm", _pt, hard=True, label=f"nests[{i}].origin_mm")))
    if len({n.id for n in nests}) != len(nests):
        raise EntryError("nest ids must be unique")
    per_job = doc.get("keep_outs_per_job", False)
    if not isinstance(per_job, bool):
        raise EntryError("keep_outs_per_job must be true or false")
    return Fixture(ref, _name(doc), c.fact(doc, "datum_mm", _pt, hard=True), tuple(nests),
                   c.fact(doc, "keep_outs", _polygons, hard=True), per_job,
                   c.fact(doc, "tolerance_mm", _pos_float))


def _recipe(doc: Mapping[str, Any], ref: EntryRef, c: _Ctx) -> Recipe:
    for k in ("machine", "tool", "material"):
        if not isinstance(doc.get(k), str):
            raise EntryError(f"{k} must name a library entry")
    mode, status = doc.get("mode"), doc.get("status")
    if mode not in ("trace", "fill"):
        raise EntryError(f"mode must be trace or fill, got {mode!r}")
    if status not in ("draft", "confirmed"):
        raise EntryError(f"status must be draft or confirmed, got {status!r}")
    setup, manual, fill = _sub(doc, "setup"), _sub(doc, "manual"), _sub(doc, "fill")
    m = ManualSettings(c.fact(manual, "nose_fitted", _bool, label="manual.nose_fitted"),
                       c.fact(manual, "knob_notches", _int, label="manual.knob_notches"),
                       c.fact(manual, "pressure", _int, label="manual.pressure"))
    sf = {k: c.fact(setup, k, _int, label=f"setup.{k}") for k in ("mc", "vs", "vz", "pz", "dz")}
    vd = c.fact(setup, "vd", _int, required=False, label="setup.vd")
    need_fill = mode == "fill"
    r = Recipe(ref, _name(doc), doc["machine"], doc["tool"], doc["material"], mode, status,
               sf["mc"], sf["vs"], sf["vz"], sf["pz"], sf["dz"], vd,
               c.fact(doc, "min_char_height_mm", _pos_float), m,
               c.fact(fill, "stepover_mm", _pos_float, required=need_fill, label="fill.stepover_mm"),
               c.fact(fill, "hatch_angle_deg", _float, required=need_fill, label="fill.hatch_angle_deg"),
               c.fact(fill, "contour_pass", _bool, required=need_fill, label="fill.contour_pass"))
    if status == "confirmed":
        for k in ("mc", "vs", "vz", "pz", "dz"):
            if not getattr(r, k).known:
                raise EntryError(f"a confirmed recipe needs a known setup.{k}")
    return r


def _name(doc: Mapping[str, Any]) -> str:
    n = doc.get("name")
    if not isinstance(n, str) or not n:
        raise EntryError("needs a name")
    return n


_PARSERS: dict[str, Callable[[Mapping[str, Any], EntryRef, _Ctx], Any]] = {
    "machine": _machine, "tool": _tool, "material": _material,
    "part": _part, "fixture": _fixture, "recipe": _recipe,
}


def load_entry(path: Path, kind: str) -> tuple[Any, dict[str, Source]]:
    """Parse one TOML entry. Raises EntryError."""
    raw = path.read_bytes()
    try:
        doc = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise EntryError(f"not valid TOML: {e}") from e
    if doc.get("schema_version") != SCHEMA_VERSION:
        raise EntryError(f"schema_version must be {SCHEMA_VERSION}")
    if doc.get("kind") != kind:
        raise EntryError(f"kind must be {kind!r} for a file under {kind}s/")
    if doc.get("id") != path.stem:
        raise EntryError(f"id {doc.get('id')!r} must equal the file name {path.stem!r}")
    version = doc.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise EntryError("version must be an integer >= 1 (bump it when a value changes)")
    sources = _sources(doc)
    # Hash with LF line ends: the same entry gives the same hash on Windows (CRLF checkout) and Linux.
    ref = EntryRef(kind, path.stem, version, hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest())
    return _PARSERS[kind](doc, ref, _Ctx(kind, sources)), sources


def load_library(seed: Path | None = None, user: Path | None = None, *extra: Path,
                 check_paths: Path | None = None) -> Library:
    """Load seed, then user, then extra directories; later ones override by id.

    check_paths: repository root; when given, every source path must exist under it.
    """
    dirs = [seed if seed is not None else paths.SEED_LIBRARY]
    if user is not None:
        dirs.append(user)
    dirs.extend(extra)
    tables: dict[str, dict[str, Any]] = {k: {} for k in KINDS}
    files: dict[tuple[str, str], Path] = {}
    sources: dict[tuple[str, str], Mapping[str, Source]] = {}
    errors: list[LibraryError] = []
    for d in dirs:
        for kind in KINDS:
            sub = Path(d) / f"{kind}s"
            if not sub.is_dir():
                continue
            for p in sorted(sub.glob("*.toml")):
                try:
                    entry, srcs = load_entry(p, kind)
                except (EntryError, OSError) as e:
                    errors.append(LibraryError(p, str(e)))
                    tables[kind].pop(p.stem, None)
                    continue
                if check_paths is not None:
                    for s in srcs.values():
                        if s.path is not None and not (check_paths / s.path).exists():
                            errors.append(LibraryError(p, f"sources.{s.key}: path {s.path!r} does not resolve "
                                                          "from the repository root"))
                tables[kind][p.stem] = entry
                files[(kind, p.stem)] = p
                sources[(kind, p.stem)] = srcs
    lib = Library(tables["machine"], tables["tool"], tables["material"], tables["part"],
                  tables["fixture"], tables["recipe"], tuple(errors), sources, files)
    return _cross_check(lib)


def _cross_check(lib: Library) -> Library:
    errors = list(lib.errors)
    for rid, r in sorted(lib.recipes.items()):
        for kind, ref in (("machine", r.machine), ("tool", r.tool), ("material", r.material)):
            if ref not in getattr(lib, kind + "s"):
                errors.append(LibraryError(lib.files[("recipe", rid)], f"{kind} {ref!r} is not in the library"))
    for pid, p in sorted(lib.parts.items()):
        if p.material not in lib.materials:
            errors.append(LibraryError(lib.files[("part", pid)], f"material {p.material!r} is not in the library"))
    if len(errors) == len(lib.errors):
        return lib
    return Library(lib.machines, lib.tools, lib.materials, lib.parts, lib.fixtures, lib.recipes,
                   tuple(errors), lib.sources, lib.files)


def unmeasured(lib: Library) -> list[tuple[str, str, str, Fact[Any]]]:
    """Every needs_measurement fact: (kind, id, field path, fact). Used by measurements-needed.md."""
    out: list[tuple[str, str, str, Fact[Any]]] = []

    def walk(kind: str, eid: str, prefix: str, obj: Any) -> None:
        if isinstance(obj, Fact):
            if obj.needs_measurement:
                out.append((kind, eid, prefix, obj))
            return
        if isinstance(obj, (ManualSettings, Nest)):
            label = obj.id if isinstance(obj, Nest) else "manual"
            for f in obj.__dataclass_fields__:
                walk(kind, eid, f"{prefix}.{label}.{f}" if prefix else f"{label}.{f}", getattr(obj, f))
            return
        if isinstance(obj, Mapping):
            for k in sorted(obj):
                walk(kind, eid, f"{prefix}.{k}" if prefix else str(k), obj[k])
            return
        if isinstance(obj, tuple):
            for v in obj:
                if isinstance(v, Nest):
                    walk(kind, eid, prefix, v)

    for kind, entry in lib.entries():
        for f in entry.__dataclass_fields__:
            if f in ("ref", "overrides"):
                continue
            walk(kind, entry.ref.id, f, getattr(entry, f))
    return out
