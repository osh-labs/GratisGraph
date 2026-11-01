"""M2.0 contracts: setup card, pattern registry helpers, fill recipe, stubs present."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from ggdesk.formats import job as jf
from ggdesk.gate import GateInputs
from ggdesk.gate.residual import manual_depth_line, residual_lines
from ggdesk.library import Selection, load_library, resolve
from ggdesk.model.job import Job
from ggdesk.patterns import ParamSpec, PatternError, coerce
from ggdesk.setupcard import setup_card
from ggdesk.toolpath.fill import FillParams
from tests.conftest import DESKTOP

LIB = load_library(DESKTOP / "library")
SQUARE = jf.load(DESKTOP / "docs" / "examples" / "square-10mm.ggj")


def test_setup_card_repeats_the_gate_line() -> None:
    sel = Selection(recipe="scrap-rotary-diamond-trace", overrides={"pz": 80})
    res = resolve(LIB, SQUARE, sel)
    card = setup_card(res)
    gate_lines = residual_lines(GateInputs(res, None, None, sel))
    assert card.lines[1] == gate_lines[0] == manual_depth_line(res.recipe)
    assert "Depth is set by hand: nose fitted, knob 5 notches, pressure 2." in card.to_text()
    assert any("Bench override: pz = 80" in line for line in card.lines)
    assert "DRAFT" in card.to_text()


def test_fill_recipe() -> None:
    r = LIB.recipes["scrap-rotary-diamond-fill"]
    assert r.mode == "fill" and r.status == "draft"
    assert not r.stepover_mm.known and r.stepover_mm.gap == "G6"
    assert r.hatch_angle_deg.value == 0.0 and r.contour_pass.value is True
    assert r.vs.confidence == "HYPOTHESIS"
    res = resolve(LIB, SQUARE, Selection(recipe="scrap-rotary-diamond-fill",
                                         overrides={"stepover_mm": 0.1, "tip_width_mm": 0.2}))
    card = setup_card(res)
    assert "Fill: tip width 0.2 mm, stepover 0.1 mm." in card.lines


@dataclass(frozen=True)
class _P:
    name: str = "demo"
    title: str = "Demo"
    mode: str = "trace"
    params: tuple[ParamSpec, ...] = (ParamSpec("size", float, 2.0, "mm"), ParamSpec("n", int, 3, "count"),
                                     ParamSpec("fill", bool, False, "flag"))

    def generate(self, **params: Any) -> Job:
        raise NotImplementedError


def test_coerce() -> None:
    p: Any = _P()
    assert coerce(p, {}) == {"size": 2.0, "n": 3, "fill": False}
    assert coerce(p, {"size": "1.5", "n": "4", "fill": "true"}) == {"size": 1.5, "n": 4, "fill": True}
    with pytest.raises(PatternError, match="unknown"):
        coerce(p, {"colour": 1})
    with pytest.raises(PatternError, match="expects int"):
        coerce(p, {"n": "x"})
    with pytest.raises(PatternError):
        coerce(p, {"fill": "maybe"})


def test_fill_params_type() -> None:
    fp = FillParams(0.2, 0.1, 0.0, True)
    assert fp.tip_width_mm == 0.2
