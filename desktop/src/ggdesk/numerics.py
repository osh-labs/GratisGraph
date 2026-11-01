"""The only module allowed platform-sensitive maths and rounding.

mm -> device units uses round-half-to-even, the same rule as the driver
(gts_translator: int(round(mm * 100))) and the TypeScript engine
(docs/STROKE_SCHEMA.md, "Conformance"). Ruff bans round() and math.hypot
everywhere else in the core so this cannot drift.

Trigonometry also lives here. Multiples of 45 degrees are exact (or use
the correctly rounded sqrt), so the common hatch and corner angles do not
depend on the platform's libm. Other angles go through libm and may
differ by one ulp between operating systems; a golden that depends on
such an angle must be listed in the desktop golden ties file.
"""
from __future__ import annotations

import math

UNITS_PER_MM = 100  # 1 device unit = 0.01 mm (GTS_FORMAT.md, confirmed on hardware)

_SQRT_HALF = math.sqrt(0.5)  # correctly rounded on every IEEE 754 platform


def to_units(mm: float) -> int:
    """mm -> 0.01 mm device units, round half to even."""
    return int(round(mm * UNITS_PER_MM))


def to_mm(units: int) -> float:
    """Device units -> mm."""
    return units / UNITS_PER_MM


def length(dx: float, dy: float) -> float:
    """Euclidean length. One call site so a libm difference shows up in one place."""
    return math.hypot(dx, dy)


def cos_sin_deg(deg: float) -> tuple[float, float]:
    """(cos, sin) of an angle in degrees, exact for multiples of 45 degrees."""
    d = math.fmod(deg, 360.0)
    if d < 0:
        d += 360.0
    if d % 45.0 == 0.0:
        k = int(d // 45.0) % 8
        s = _SQRT_HALF
        return ((1.0, 0.0), (s, s), (0.0, 1.0), (-s, s),
                (-1.0, 0.0), (-s, -s), (0.0, -1.0), (s, -s))[k]
    r = math.radians(d)
    return math.cos(r), math.sin(r)


def sqrt(x: float) -> float:
    """Correctly rounded square root (IEEE 754), kept here with the other maths."""
    return math.sqrt(x)


def ceil_div(a: float, b: float) -> int:
    """Smallest integer n with n * b >= a (b > 0)."""
    return math.ceil(a / b)
