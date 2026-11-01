from __future__ import annotations

import re

from ggdesk.numerics import length, to_mm, to_units
from tests.conftest import DESKTOP


def test_half_to_even_matches_stroke_schema() -> None:
    # docs/STROKE_SCHEMA.md: 0.125 mm -> 12, 0.135 mm -> 14
    assert to_units(0.125) == 12
    assert to_units(0.135) == 14
    assert to_units(-0.125) == -12
    assert to_mm(1234) == 12.34


def test_length() -> None:
    assert length(3.0, 4.0) == 5.0


def test_round_only_in_numerics() -> None:
    """Rounding policy: round( appears in the core only in numerics.py."""
    hits = []
    for p in (DESKTOP / "src" / "ggdesk").rglob("*.py"):
        if p.name == "numerics.py":
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"(?<![\w.])round\(", line):
                hits.append(f"{p.name}:{i}")
    assert not hits, hits
