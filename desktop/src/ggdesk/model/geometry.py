"""Plain geometry in mm (part or machine frame) and device units.

Part frame: origin at the centre of the part's engrave area, +X right, +Y up
as the operator reads the finished part. Machine frame (GTS_FORMAT.md 1):
home (0, 0) back-left, +X right, +Y toward the operator. The fixture map
from part to machine is therefore a translation plus a Y flip.
"""
from __future__ import annotations

from dataclasses import dataclass

Pt = tuple[float, float]
UPt = tuple[int, int]


@dataclass(frozen=True)
class Polyline:
    """An open or closed path. A closed path does not repeat its first point."""
    points: tuple[Pt, ...]
    closed: bool = False


@dataclass(frozen=True)
class Region:
    """A closed area to clear: one outer ring and any number of holes (no repeated closing points)."""
    outer: tuple[Pt, ...]
    holes: tuple[tuple[Pt, ...], ...] = ()


@dataclass(frozen=True)
class Placement:
    """Where the part-frame origin sits on the machine (mm, machine frame)."""
    origin_mm: Pt

    def to_machine(self, p: Pt) -> Pt:
        """Part frame -> machine frame: translate, flip Y. No rotation or scale in v1."""
        return (self.origin_mm[0] + p[0], self.origin_mm[1] - p[1])

    def to_part(self, p: Pt) -> Pt:
        """Machine frame -> part frame (inverse of to_machine)."""
        return (p[0] - self.origin_mm[0], self.origin_mm[1] - p[1])
