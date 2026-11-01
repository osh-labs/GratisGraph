"""Toolpaths in device units, and the intent the gate compares the bytes with."""
from __future__ import annotations

from dataclasses import dataclass

from ggdesk.model.geometry import UPt


@dataclass(frozen=True)
class UStroke:
    """One pen-down path: absolute machine units, at least two points, no repeated neighbours."""
    points: tuple[UPt, ...]

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError("a stroke needs at least two points")
        for a, b in zip(self.points, self.points[1:], strict=False):
            if a == b:
                raise ValueError(f"repeated point {a} in stroke")

    def to_driver(self) -> tuple[int, int, list[tuple[int, int]]]:
        """(sx, sy, [(dx, dy), ...]): the tuple form build_gts and optimise_strokes take."""
        (sx, sy) = self.points[0]
        deltas = [(b[0] - a[0], b[1] - a[1]) for a, b in zip(self.points, self.points[1:], strict=False)]
        return (sx, sy, deltas)

    @staticmethod
    def from_driver(t: tuple[int, int, list[tuple[int, int]]]) -> UStroke:
        sx, sy, deltas = t
        pts = [(sx, sy)]
        for dx, dy in deltas:
            pts.append((pts[-1][0] + dx, pts[-1][1] + dy))
        return UStroke(tuple(pts))

    def reversed(self) -> UStroke:
        return UStroke(tuple(reversed(self.points)))


@dataclass(frozen=True)
class NarrowRegion:
    """A fill region (or part of one) narrower than the tool: left unengraved, reported (S3)."""
    op_index: int
    region_index: int
    width_mm: float


@dataclass(frozen=True)
class Intent:
    """What the job should engrave, after quantisation and before ordering.

    The gate (H10) compares the decoded pen-down strokes with these, each
    stroke equal forward or reversed, as a multiset.
    """
    strokes: tuple[UStroke, ...]
    char_heights_mm: tuple[float, ...] = ()
    narrow_regions: tuple[NarrowRegion, ...] = ()
