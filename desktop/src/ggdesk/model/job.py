"""The gratisgraph-job v1 document (docs/job-format.md).

Geometry is in the part frame, in mm. The job states intent only: no machine
parameters. The app chooses the recipe, fixture and nest at build time.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ggdesk.model.geometry import Polyline, Region


def _empty() -> Mapping[str, Any]:
    return {}


@dataclass(frozen=True)
class TraceOp:
    """Engrave on the path (single-line lettering, outlines)."""
    paths: tuple[Polyline, ...]
    mode_hint: str = "trace"
    char_height_mm: float | None = None
    extra: Mapping[str, Any] = field(default_factory=_empty)


@dataclass(frozen=True)
class FillOp:
    """Clear the inside of closed regions (filled lettering). Built in M2."""
    regions: tuple[Region, ...]
    mode_hint: str = "fill"
    char_height_mm: float | None = None
    extra: Mapping[str, Any] = field(default_factory=_empty)


Operation = TraceOp | FillOp


@dataclass(frozen=True)
class JobSource:
    name: str
    version: str = ""


@dataclass(frozen=True)
class Job:
    part: str
    operations: tuple[Operation, ...]
    quantity: int = 1
    reference: str = ""
    source: JobSource | None = None
    chord_tolerance_mm: float = 0.01
    extra: Mapping[str, Any] = field(default_factory=_empty)
