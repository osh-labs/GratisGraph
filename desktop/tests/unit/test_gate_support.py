"""Shared builders for the gate tests (known-good jobs, byte edits), and checks of the builders.

Known-good bytes come from the driver's own builder (gts_api.build_gts) with
the machine model code stamped at 0x24, as ggdesk.build does; the intent is
made from the same strokes. A mutant edits those bytes (or the strokes, the
intent or a library entry, when the rule judges those) and must make exactly
the expected rule fire.
"""
from __future__ import annotations

import struct
from collections.abc import Sequence
from dataclasses import dataclass

import gts_api

from ggdesk import gts_read
from ggdesk.gate import GateConfig, GateInputs, GateReport, run_gate
from ggdesk.gts_read import Command, Segment
from ggdesk.library import Library, Selection, load_library, resolve
from ggdesk.model.job import Job
from ggdesk.model.toolpath import Intent, NarrowRegion, UStroke
from tests.conftest import DESKTOP

FIXTURES = DESKTOP / "tests" / "fixtures" / "library"
IQ = 0x020D
LIB: Library = load_library(None, None, FIXTURES)

UPts = Sequence[tuple[int, int]]


def strokes(*paths: UPts) -> tuple[UStroke, ...]:
    return tuple(UStroke(tuple(p)) for p in paths)


def stamp(data: bytes, code: int = IQ) -> bytes:
    b = bytearray(data)
    struct.pack_into(">H", b, gts_read.MODEL_CODE_OFFSET, code)
    return bytes(b)


@dataclass(frozen=True)
class Case:
    data: bytes
    inputs: GateInputs

    def gate(self) -> GateReport:
        return run_gate(self.data, self.inputs)


def make_inputs(ss: Sequence[UStroke], *, part: str = "bench-scrap-40", recipe: str = "test-confirmed-trace",
                fixture: str = "test-clamps", nest: str = "centre", lib: Library = LIB,
                char_heights: tuple[float, ...] = (), narrow: tuple[NarrowRegion, ...] = (),
                config: GateConfig | None = None, intent: bool = True,
                extra_keep_outs: tuple[tuple[tuple[float, float], ...], ...] = ()) -> GateInputs:
    sel = Selection(recipe=recipe, fixture=fixture, nest=nest, extra_keep_outs=extra_keep_outs)
    res = resolve(lib, Job(part=part, operations=()), sel)
    it = Intent(tuple(ss), char_heights, narrow) if intent else None
    return GateInputs(res, it, None, sel, config or GateConfig())


def build_bytes(ss: Sequence[UStroke], inputs: GateInputs, *, code: int = IQ) -> bytes:
    """The driver's bytes for these strokes with the recipe's setup, stamped for the machine."""
    sv = inputs.resolved.recipe.setup_values()
    data = gts_api.build_gts([s.to_driver() for s in ss], speed=sv["vs"], pz=sv["pz"], dz=sv["dz"],
                             mc=sv["mc"], vz=sv["vz"], vd=sv["vd"])
    return stamp(data, code)


def case(ss: Sequence[UStroke], **kw: object) -> Case:
    inputs = make_inputs(ss, **kw)  # type: ignore[arg-type]
    return Case(build_bytes(ss, inputs), inputs)


def fired(rep: GateReport) -> set[str]:
    return {f.rule for f in rep.findings}


# --- byte edits ---------------------------------------------------------------------------------

def cmd(op: str, arg: int = 0) -> bytes:
    return b"\xff\xfd" + op.encode("ascii") + struct.pack(">H", arg)


def seg(dx: int, dy: int, speed: int = 10) -> bytes:
    return struct.pack(">hhhhhh", 1, 1, speed, 551, dx, dy)


def records(data: bytes) -> list[Command | Segment]:
    return gts_read.read_job(data).records


def nth_command(data: bytes, op: str, n: int = 0, arg: int | None = None) -> Command:
    found = [r for r in records(data) if isinstance(r, Command) and r.op == op and (arg is None or r.arg == arg)]
    return found[n]


def end_of(r: Command | Segment) -> int:
    return r.offset + (6 if isinstance(r, Command) else 12)


def insert(data: bytes, offset: int, extra: bytes) -> bytes:
    return data[:offset] + extra + data[offset:]


def delete(data: bytes, r: Command | Segment) -> bytes:
    return data[:r.offset] + data[end_of(r):]


def replace_record(data: bytes, r: Command | Segment, new: bytes) -> bytes:
    return data[:r.offset] + new + data[end_of(r):]


def position_after(data: bytes, offset: int) -> tuple[int, int]:
    x = y = 0
    for r in records(data):
        if r.offset >= offset:
            break
        if isinstance(r, Segment):
            x += r.dx
            y += r.dy
    return x, y


# --- shapes (machine units; bench-scrap-40 at the centre nest engraves 3200..6800 on both axes) ---

SQUARE = strokes([(4500, 4500), (5500, 4500), (5500, 5500), (4500, 5500), (4500, 4500)])
F_ARROW = strokes(
    [(4000, 6000), (4000, 4000), (5000, 4000)],          # F: stem and top bar (machine +Y to the operator)
    [(4000, 5000), (4700, 5000)],                         # F: middle bar
    [(5500, 6000), (5500, 4200)],                         # arrow shaft
    [(5200, 4500), (5500, 4200), (5800, 4500)],           # arrow head
)


def test_known_good_baselines_have_no_findings() -> None:
    for ss in (SQUARE, F_ARROW):
        rep = case(ss).gate()
        assert rep.findings == (), rep.to_text()
        assert rep.passed and rep.flags == 0


def test_edit_helpers_round_trip() -> None:
    c = case(SQUARE)
    pu1 = nth_command(c.data, "PU", 0, arg=1)
    assert insert(delete(c.data, pu1), pu1.offset, cmd("PU", 1)) == c.data
    assert position_after(c.data, len(c.data)) == (0, 0)


__all__ = ["F_ARROW", "FIXTURES", "IQ", "LIB", "SQUARE", "Case", "build_bytes", "case", "cmd", "delete",
           "end_of", "fired", "insert", "make_inputs", "nth_command", "position_after", "records",
           "replace_record", "seg", "stamp", "strokes"]
