"""The only module allowed platform-sensitive maths and rounding.

mm -> device units uses round-half-to-even, the same rule as the driver
(gts_translator: int(round(mm * 100))) and the TypeScript engine
(docs/STROKE_SCHEMA.md, "Conformance"). Ruff bans round() and math.hypot
everywhere else in the core so this cannot drift.
"""
from __future__ import annotations

import math

UNITS_PER_MM = 100  # 1 device unit = 0.01 mm (GTS_FORMAT.md, confirmed on hardware)


def to_units(mm: float) -> int:
    """mm -> 0.01 mm device units, round half to even."""
    return int(round(mm * UNITS_PER_MM))


def to_mm(units: int) -> float:
    """Device units -> mm."""
    return units / UNITS_PER_MM


def length(dx: float, dy: float) -> float:
    """Euclidean length. One call site so a libm difference shows up in one place."""
    return math.hypot(dx, dy)
