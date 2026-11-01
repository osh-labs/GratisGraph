"""Job + library + selection -> final .m20 bytes (desktop/docs/m1-plan.md section 2.5).

The build refuses what it cannot build (unplaced part, a recipe/mode mismatch,
a fill without a fill recipe, tip width or stepover, an unknown setup value,
nothing to cut). It does not
judge geometry against the part, the keep-outs or the work field: that is the
output gate's job, on the final bytes, and a check here would hide a gate
finding.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

import gts_api
import gts_optimise

from ggdesk.formats import job as job_format
from ggdesk.gate.types import GateConfig, GateInputs
from ggdesk.library.load import Library
from ggdesk.library.model import OverrideError, UnmeasuredError
from ggdesk.library.select import Resolved, Selection, SelectionError, resolve
from ggdesk.model.geometry import Polyline
from ggdesk.model.job import FillOp, Job, TraceOp
from ggdesk.model.toolpath import Intent, NarrowRegion, UStroke
from ggdesk.toolpath import order, to_machine_units_counted, trace
from ggdesk.toolpath.fill import FillParams, fill

MODEL_CODE_OFFSET = 0x24   # header uint16 BE: the driver stamps the connected machine's code here


class BuildError(ValueError):
    """The job cannot be built with this selection (the message says why)."""


@dataclass(frozen=True)
class BuildResult:
    data: bytes                    # final bytes, machine model code at header 0x24
    intent: Intent
    ordered: tuple[UStroke, ...]
    resolved: Resolved
    job_sha256: str | None         # always set by build(); Optional kept from the M1.0 contract
    estimate_s: float
    dropped_points: int            # paths dropped because they collapsed to one point after quantisation


def job_sha256(job: Job, job_text: str | None = None) -> str:
    """SHA-256 of the job file text (UTF-8) when given, else of its canonical dumps()."""
    text = job_text if job_text is not None else job_format.dumps(job)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stamp_model_code(data: bytes, model_code: int) -> bytes:
    """Write model_code (uint16 BE) at header 0x24, as the driver does at send time."""
    if not 0 <= model_code <= 0xFFFF:
        raise BuildError(f"machine model code {model_code} does not fit the header (uint16)")
    b = bytearray(data)
    struct.pack_into(">H", b, MODEL_CODE_OFFSET, model_code)
    return bytes(b)


def _resolve(lib: Library, job: Job, sel: Selection) -> Resolved:
    try:
        return resolve(lib, job, sel)
    except (SelectionError, OverrideError) as e:
        raise BuildError(str(e)) from e
    except KeyError as e:   # unknown nest
        raise BuildError(str(e.args[0]) if e.args else "unknown library entry") from e


def build(job: Job, lib: Library, sel: Selection, *, job_text: str | None = None) -> BuildResult:
    res = _resolve(lib, job, sel)
    recipe = res.recipe

    if res.placement is None:
        try:
            res.fixture.placement(sel.nest)
            gap = "unmeasured fixture geometry"
        except UnmeasuredError as e:
            gap = str(e)
        raise BuildError(f"cannot place the part on fixture {res.fixture.ref.id} nest {sel.nest}: {gap}")

    for i, op in enumerate(job.operations):
        if isinstance(op, FillOp) and recipe.mode != "fill":
            raise BuildError(f"operations[{i}]: a fill operation needs a fill recipe; recipe "
                             f"{recipe.ref.id} mode is {recipe.mode!r}")
    for i, op in enumerate(job.operations):
        if op.mode_hint != recipe.mode:
            raise BuildError(f"operations[{i}]: mode_hint {op.mode_hint!r} does not match recipe "
                             f"{recipe.ref.id} mode {recipe.mode!r}")
    fill_params = _fill_params(res) if any(isinstance(op, FillOp) for op in job.operations) else None

    try:
        setup = recipe.setup_values()
    except UnmeasuredError as e:
        raise BuildError(f"recipe setup value unknown: {e}") from e
    if not res.machine.model_code.known:
        raise BuildError(f"machine {res.machine.ref.id} model code is unknown "
                         f"({res.machine.model_code.describe()})")
    model_code = int(res.machine.model_code.require("machine model code"))

    strokes: list[UStroke] = []
    dropped = 0
    heights: list[float] = []
    narrow: list[NarrowRegion] = []
    for i, op in enumerate(job.operations):
        if isinstance(op, FillOp):
            assert fill_params is not None
            try:
                fr = fill(op, i, fill_params)
            except ValueError as e:
                raise BuildError(f"fill: {e}") from e
            narrow.extend(fr.narrow)
            # closed contour paths get their closing point exactly as trace() gives a closed path
            paths: tuple[Polyline, ...] = trace(TraceOp(fr.paths))
        else:
            paths = trace(op)
        s, d = to_machine_units_counted(paths, res.placement)
        strokes.extend(s)
        dropped += d
        if op.char_height_mm is not None:
            heights.append(op.char_height_mm)
    if not strokes:
        raise BuildError(f"the job has no strokes to cut after quantisation to 0.01 mm "
                         f"({dropped} path(s) collapsed to a single point)")

    intent = Intent(tuple(strokes), tuple(heights), tuple(narrow))
    ordered = tuple(order(strokes))
    drv = [s.to_driver() for s in ordered]
    vs = setup["vs"]
    assert vs is not None
    try:
        raw = gts_api.build_gts(drv, speed=vs, pz=setup["pz"], dz=setup["dz"], mc=setup["mc"],
                                vz=setup["vz"], vd=setup["vd"])
    except (ValueError, struct.error) as e:
        raise BuildError(f"the driver cannot encode this job: {e}") from e
    data = stamp_model_code(bytes(raw), model_code)

    est = gts_optimise.estimate_duration(drv, speed=vs)
    if est is None:
        raise BuildError("run-time estimate unavailable (the driver's velocity constant is unset)")
    return BuildResult(data=data, intent=intent, ordered=ordered, resolved=res,
                       job_sha256=job_sha256(job, job_text), estimate_s=float(est), dropped_points=dropped)


def _fill_params(res: Resolved) -> FillParams:
    """Fill parameters from the effective recipe and the resolved tip width; BuildError names a gap."""
    recipe = res.recipe
    if res.tip_width_mm is None:
        f = res.tool.tip_width_mm
        gap = f" ({f.gap})" if f.gap else ""
        raise BuildError(f"fill needs the tip width: tool {res.tool.ref.id} tip_width_mm is "
                         f"needs_measurement{gap}; measure it or set a bench override tip_width_mm")
    try:
        stepover = float(recipe.stepover_mm.require(f"recipe {recipe.ref.id} stepover_mm"))
        angle = float(recipe.hatch_angle_deg.require(f"recipe {recipe.ref.id} hatch_angle_deg"))
        contour = bool(recipe.contour_pass.require(f"recipe {recipe.ref.id} contour_pass"))
    except UnmeasuredError as e:
        raise BuildError(f"fill parameter unknown: {e}") from e
    return FillParams(tip_width_mm=float(res.tip_width_mm), stepover_mm=stepover, hatch_angle_deg=angle,
                      contour_pass=contour)


def gate_inputs(result: BuildResult, sel: Selection, config: GateConfig | None = None) -> GateInputs:
    return GateInputs(result.resolved, result.intent, result.job_sha256, sel, config or GateConfig())
