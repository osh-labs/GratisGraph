"""Typed library entries with provenance (build plan section 6.1).

Every physical value is a Fact: a value with its source, reference and
confidence, or null with needs_measurement, the gap it belongs to and a
measurement procedure. Nothing here invents a value.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from ggdesk import numerics
from ggdesk.model.geometry import Placement, Pt

CONFIDENCE = ("CONFIRMED", "STRONG", "HYPOTHESIS", "DEFINED")
KINDS = ("machine", "tool", "material", "part", "fixture", "recipe")


class UnmeasuredError(ValueError):
    """A value the operation needs is needs_measurement."""


class OverrideError(ValueError):
    """A bench override was refused."""


@dataclass(frozen=True)
class Fact[T]:
    value: T | None
    src: str | None = None
    ref: str | None = None
    confidence: str | None = None
    needs_measurement: bool = False
    gap: str | None = None
    measure: tuple[str, ...] = ()

    @property
    def known(self) -> bool:
        return self.value is not None and not self.needs_measurement

    def require(self, what: str) -> T:
        """The value, or UnmeasuredError naming `what` and the gap."""
        if self.value is None or self.needs_measurement:
            gap = f" ({self.gap})" if self.gap else ""
            raise UnmeasuredError(f"{what} is needs_measurement{gap}")
        return self.value

    def describe(self) -> str:
        if not self.known:
            return f"unknown (needs_measurement{', ' + self.gap if self.gap else ''})"
        return f"{self.value} [{self.confidence}]"


def defined[T](value: T, ref: str = "") -> Fact[T]:
    """A value set by a bench override or a definition, not read from a source."""
    return Fact(value, src="override", ref=ref, confidence="DEFINED")


@dataclass(frozen=True)
class EntryRef:
    kind: str
    id: str
    version: int
    sha256: str


@dataclass(frozen=True)
class Source:
    key: str
    title: str
    path: str | None
    url: str | None
    kind: str


@dataclass(frozen=True)
class Range:
    min: int
    max: int

    def contains(self, v: int) -> bool:
        return self.min <= v <= self.max


@dataclass(frozen=True)
class Outline:
    """A closed outline in the part frame (mm). `rect` is centred on the origin."""
    kind: Literal["rect", "polygon"]
    width_mm: float = 0.0
    height_mm: float = 0.0
    corner_radius_mm: float = 0.0
    centre_mm: Pt = (0.0, 0.0)
    points: tuple[Pt, ...] = ()

    def polygon(self, chord_mm: float = 0.01) -> tuple[Pt, ...]:
        """Vertices, counter-clockwise in the part frame. Rounded corners flattened within chord_mm."""
        if self.kind == "polygon":
            return self.points
        hw, hh = self.width_mm / 2, self.height_mm / 2
        cx, cy = self.centre_mm
        r = min(self.corner_radius_mm, hw, hh)
        if r <= 0:
            return ((cx - hw, cy - hh), (cx + hw, cy - hh), (cx + hw, cy + hh), (cx - hw, cy + hh))
        # segments per quarter so that the sagitta r(1 - cos(a/2)) <= chord_mm
        n = 1
        while True:
            c, _ = numerics.cos_sin_deg(45.0 / n)
            if r * (1 - c) <= chord_mm or n >= 256:
                break
            n += 1
        pts: list[Pt] = []
        corners = ((cx + hw - r, cy - hh + r, 270.0), (cx + hw - r, cy + hh - r, 0.0),
                   (cx - hw + r, cy + hh - r, 90.0), (cx - hw + r, cy - hh + r, 180.0))
        for ccx, ccy, a0 in corners:
            for i in range(n + 1):
                c, s = numerics.cos_sin_deg(a0 + 90.0 * i / n)
                pts.append((ccx + r * c, ccy + r * s))
        return tuple(pts)


@dataclass(frozen=True)
class Machine:
    ref: EntryRef
    name: str
    model_code: Fact[int]
    send_enabled: bool
    work_field_mm: Fact[tuple[float, float]]
    opcodes_allowed: tuple[str, ...]
    opcodes_reserved: tuple[str, ...]
    ranges: Mapping[str, Fact[Range]]
    completion: str
    max_job_bytes: Fact[int]


@dataclass(frozen=True)
class Tool:
    ref: EntryRef
    name: str
    type: str
    needs_spindle: Fact[bool]
    needs_nose: Fact[bool]
    tip_width_mm: Fact[float]


@dataclass(frozen=True)
class Material:
    ref: EntryRef
    name: str
    alloy: Fact[str]
    finish: Fact[str]
    thickness_mm: Fact[float]


@dataclass(frozen=True)
class Part:
    ref: EntryRef
    name: str
    material: str
    outline: Fact[Outline]
    holes: Fact[tuple[Outline, ...]]
    keep_out_margin_mm: Fact[float]
    thickness_mm: Fact[float]


@dataclass(frozen=True)
class Nest:
    id: str
    origin_mm: Fact[Pt]


@dataclass(frozen=True)
class Fixture:
    ref: EntryRef
    name: str
    datum_mm: Fact[Pt]
    nests: tuple[Nest, ...]
    keep_outs: Fact[tuple[tuple[Pt, ...], ...]]
    keep_outs_per_job: bool
    tolerance_mm: Fact[float]

    def nest(self, nest_id: str) -> Nest:
        for n in self.nests:
            if n.id == nest_id:
                return n
        raise KeyError(f"fixture {self.ref.id} has no nest {nest_id!r} "
                       f"(nests: {', '.join(n.id for n in self.nests) or 'none'})")

    def placement(self, nest_id: str) -> Placement:
        """Machine position of the part origin: datum + nest origin. Raises UnmeasuredError."""
        dx, dy = self.datum_mm.require(f"fixture {self.ref.id} datum")
        n = self.nest(nest_id)
        ox, oy = n.origin_mm.require(f"fixture {self.ref.id} nest {nest_id} origin")
        return Placement((dx + ox, dy + oy))

    def keep_outs_machine(self) -> tuple[tuple[Pt, ...], ...]:
        """Keep-out polygons in the machine frame (stored relative to the datum, machine axes)."""
        dx, dy = self.datum_mm.require(f"fixture {self.ref.id} datum")
        polys = self.keep_outs.require(f"fixture {self.ref.id} keep-outs")
        return tuple(tuple((dx + x, dy + y) for x, y in poly) for poly in polys)


@dataclass(frozen=True)
class ManualSettings:
    nose_fitted: Fact[bool]
    knob_notches: Fact[int]
    pressure: Fact[int]


OVERRIDABLE = ("vs", "vz", "vd", "pz", "dz", "stepover_mm", "hatch_angle_deg", "contour_pass",
               "min_char_height_mm", "tip_width_mm")
_INT_KEYS = ("vs", "vz", "vd", "pz", "dz")
_FLOAT_KEYS = ("stepover_mm", "hatch_angle_deg", "min_char_height_mm", "tip_width_mm")


@dataclass(frozen=True)
class Recipe:
    ref: EntryRef
    name: str
    machine: str
    tool: str
    material: str
    mode: Literal["trace", "fill"]
    status: Literal["draft", "confirmed"]
    mc: Fact[int]
    vs: Fact[int]
    vz: Fact[int]
    pz: Fact[int]
    dz: Fact[int]
    vd: Fact[int]
    min_char_height_mm: Fact[float]
    manual: ManualSettings
    stepover_mm: Fact[float]
    hatch_angle_deg: Fact[float]
    contour_pass: Fact[bool]
    tip_width_mm: Fact[float] = field(default_factory=lambda: Fact(None))  # set only by override
    overrides: Mapping[str, Any] = field(default_factory=dict)

    def with_overrides(self, values: Mapping[str, Any]) -> Recipe:
        """A bench variant: draft recipes only, OVERRIDABLE keys only. The result records each override."""
        if not values:
            return self
        if self.status != "draft":
            raise OverrideError(f"recipe {self.ref.id} is {self.status}; bench overrides need a draft recipe")
        changes: dict[str, Any] = {}
        merged = dict(self.overrides)
        for k, v in sorted(values.items()):
            if k not in OVERRIDABLE:
                raise OverrideError(f"{k!r} cannot be overridden (allowed: {', '.join(OVERRIDABLE)})")
            if k in _INT_KEYS:
                if isinstance(v, bool) or not isinstance(v, int):
                    raise OverrideError(f"{k} must be an integer, got {v!r}")
            elif k in _FLOAT_KEYS:
                if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0 and k != "hatch_angle_deg":
                    raise OverrideError(f"{k} must be a positive number, got {v!r}")
                v = float(v)
            elif not isinstance(v, bool):
                raise OverrideError(f"{k} must be true or false, got {v!r}")
            changes[k] = defined(v, f"bench override {k}={v}")
            merged[k] = v
        return replace(self, **changes, overrides=merged)

    def setup_values(self) -> dict[str, int | None]:
        """mc, vs, vz, pz, dz, vd as build_gts takes them. Raises UnmeasuredError on an unknown value."""
        out: dict[str, int | None] = {}
        for k in ("mc", "vs", "vz", "pz", "dz"):
            out[k] = getattr(self, k).require(f"recipe {self.ref.id} {k}")
        if self.vd.needs_measurement:
            self.vd.require(f"recipe {self.ref.id} vd")
        out["vd"] = self.vd.value
        return out
