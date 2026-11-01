"""Resolve a job's part and the operator's selection into the entries build and gate use."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ggdesk.library.load import Library
from ggdesk.library.model import (
    EntryRef,
    Fixture,
    Machine,
    Part,
    Recipe,
    Tool,
    UnmeasuredError,
)
from ggdesk.model.geometry import Placement, Pt
from ggdesk.model.job import Job

DEFAULT_MACHINE = "m20-iq"
DEFAULT_NEST = "centre"


class SelectionError(ValueError):
    """The selection does not fit the job or the library."""


@dataclass(frozen=True)
class Selection:
    machine: str = DEFAULT_MACHINE
    recipe: str = ""
    fixture: str = "bare-bed"
    nest: str = DEFAULT_NEST
    overrides: Mapping[str, Any] = field(default_factory=dict)
    extra_keep_outs: tuple[tuple[Pt, ...], ...] = ()

    def to_obj(self) -> dict[str, Any]:
        return {"machine": self.machine, "recipe": self.recipe, "fixture": self.fixture, "nest": self.nest,
                "overrides": dict(sorted(self.overrides.items())),
                "extra_keep_outs": [[list(p) for p in poly] for poly in self.extra_keep_outs]}

    @staticmethod
    def from_obj(o: Mapping[str, Any]) -> Selection:
        return Selection(o["machine"], o["recipe"], o["fixture"], o["nest"], dict(o.get("overrides", {})),
                         tuple(tuple((float(x), float(y)) for x, y in poly) for poly in o.get("extra_keep_outs", [])))


@dataclass(frozen=True)
class Resolved:
    machine: Machine
    tool: Tool
    part: Part
    fixture: Fixture
    recipe: Recipe                      # effective: bench overrides applied
    placement: Placement | None         # None when the fixture datum or nest origin is unmeasured
    keep_outs_machine: tuple[tuple[Pt, ...], ...] | None   # None when the fixture keep-outs are unmeasured
    entries: tuple[EntryRef, ...]
    tip_width_mm: float | None          # override, else the tool's value, else None


def resolve(lib: Library, job: Job, sel: Selection) -> Resolved:
    """Look up every entry. Unmeasured geometry resolves to None; the gate refuses it (H7/H8)."""
    try:
        machine: Machine = lib.get("machine", sel.machine)
        base: Recipe = lib.get("recipe", sel.recipe)
        part: Part = lib.get("part", job.part)
        fixture: Fixture = lib.get("fixture", sel.fixture)
    except KeyError as e:
        raise SelectionError(str(e.args[0])) from e
    if base.machine != machine.ref.id:
        raise SelectionError(f"recipe {base.ref.id} is for machine {base.machine}, not {machine.ref.id}")
    try:
        tool: Tool = lib.get("tool", base.tool)
    except KeyError as e:
        raise SelectionError(str(e.args[0])) from e
    recipe = base.with_overrides(sel.overrides)
    fixture.nest(sel.nest)  # KeyError for an unknown nest
    if sel.extra_keep_outs and not fixture.keep_outs_per_job:
        raise SelectionError(f"fixture {fixture.ref.id} does not take per-job keep-outs")
    try:
        placement: Placement | None = fixture.placement(sel.nest)
    except UnmeasuredError:
        placement = None
    try:
        kos: tuple[tuple[Pt, ...], ...] | None = fixture.keep_outs_machine() + tuple(sel.extra_keep_outs)
    except UnmeasuredError:
        kos = None
    if "tip_width_mm" in recipe.overrides:
        tip: float | None = float(recipe.overrides["tip_width_mm"])
    else:
        tip = tool.tip_width_mm.value if tool.tip_width_mm.known else None
    material = lib.materials.get(base.material)
    refs = [machine.ref, tool.ref, part.ref, fixture.ref, base.ref]
    if material is not None:
        refs.append(material.ref)
    return Resolved(machine, tool, part, fixture, recipe, placement, kos, tuple(refs), tip)
