"""Bench text: single-line Hershey (port of web/src/hershey.ts) and filled Arimo outlines.

Bench test patterns only (build plan 3.2): production text arrives as geometry from producers.
Contracts in desktop/docs/m2-plan.md section 2.2; slice M2.2 implements them.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ggdesk import paths
from ggdesk.model.geometry import Polyline, Region

FONTS = paths.ROOT.parent / "web" / "app" / "fonts"
FUTURAL = FONTS / "futural.jhf"
ARIMO = FONTS / "Arimo-Regular.ttf"


@dataclass(frozen=True)
class TextPaths:
    paths: tuple[Polyline, ...]      # part frame mm, Y up, baseline at y_mm
    width_mm: float
    cap_height_mm: float             # measured height of "H" at this size
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class TextRegions:
    regions: tuple[Region, ...]      # part frame mm, Y up, flattened within chord_mm
    width_mm: float
    cap_height_mm: float
    warnings: tuple[str, ...] = ()


def font_path(p: Path) -> Path:
    if not p.exists():
        raise FileNotFoundError(f"bench font not found: {p}")
    return p
