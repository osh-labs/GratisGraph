"""Known-good corpus: every job is accepted with zero hard findings (100 %), and the gate is
read-only (run_gate leaves its input unchanged). The root golden Express jobs are refused for
the IQ by H2 alone, which is correct: they carry the Express model code 0x0204."""
from __future__ import annotations

import json

import pytest

from ggdesk.gate import RULES, GateReport, Severity, run_gate
from ggdesk.gate.types import Finding
from ggdesk.model.toolpath import UStroke
from tests.conftest import GOLDEN
from tests.unit.test_gate_support import F_ARROW, SQUARE, Case, build_bytes, case, fired, make_inputs, strokes


def _circle() -> tuple[UStroke, ...]:
    # 72-gon of radius 15 mm at the centre, integer vertices from exact 45-degree multiples and a table
    from ggdesk.numerics import cos_sin_deg, to_units
    pts = []
    for i in range(72):
        c, s = cos_sin_deg(5.0 * i)
        pts.append((5000 + to_units(15.0 * c), 5000 + to_units(15.0 * s)))
    pts.append(pts[0])
    return strokes(pts)


def _rapid_heavy() -> tuple[UStroke, ...]:
    # 49 short dashes scattered over the area: many rapids, little cutting
    out = []
    for i in range(7):
        for j in range(7):
            x, y = 3300 + ((i * 3 + j * 5) % 7) * 500, 3300 + j * 500
            out.append([(x, y), (x + 50, y + 20)])
    return strokes(*out)


def _field_plate_edges() -> tuple[UStroke, ...]:
    # a 100 x 100 mm test plate with no margin, on bare-bed: pen-down along the work-field edges exactly
    return strokes([(0, 0), (10000, 0), (10000, 10000), (0, 10000), (0, 0)])


def _margin_exact() -> tuple[UStroke, ...]:
    # bench-scrap-40: engrave area 3200..6800 on both axes; a square exactly on the margin line
    return strokes([(3200, 3200), (6800, 3200), (6800, 6800), (3200, 6800), (3200, 3200)])


def _tag_hole_and_edges() -> tuple[UStroke, ...]:
    # test-tag-50x28 (rounded, with a hole at machine (29, 50)): touching the hole margin and the top edge margin
    return strokes([(3200, 5000), (7000, 5000)], [(3300, 3750), (7000, 3750)], [(4000, 6250), (6000, 6250)])


CORPUS: dict[str, Case] = {}


def _corpus() -> dict[str, Case]:
    if not CORPUS:
        CORPUS.update({
            "square": case(SQUARE),
            "f_arrow": case(F_ARROW),
            "circle_72": case(_circle()),
            "rapid_heavy": case(_rapid_heavy()),
            "margin_exact": case(_margin_exact()),
            "field_edges": case(_field_plate_edges(), part="test-plate-100", fixture="bare-bed"),
            "tag_hole": case(_tag_hole_and_edges(), part="test-tag-50x28"),
            "vd_recipe": case(F_ARROW, recipe="test-confirmed-vd"),
            "seed_draft_rotary": case(SQUARE, recipe="scrap-rotary-diamond-trace", fixture="bare-bed"),
        })
    return CORPUS


@pytest.mark.parametrize("name", ["square", "f_arrow", "circle_72", "rapid_heavy", "margin_exact", "field_edges",
                                  "tag_hole", "vd_recipe", "seed_draft_rotary"])
def test_known_good_accepted(name: str) -> None:
    rep = _corpus()[name].gate()
    assert rep.passed, rep.to_text()
    assert [f for f in rep.findings if f.severity is Severity.HARD] == []
    assert rep.rules_run == tuple(r.id for r in RULES)


def test_corpus_soft_flags_are_the_expected_ones() -> None:
    c = _corpus()
    assert fired(c["seed_draft_rotary"].gate()) == {"S1", "S4"}
    assert fired(c["field_edges"].gate()) == {"S4"}
    for name in ("square", "f_arrow", "circle_72", "rapid_heavy", "margin_exact", "tag_hole", "vd_recipe"):
        assert c[name].gate().findings == (), name


def test_vd_job_has_vd_in_setup() -> None:
    from ggdesk.gts_read import read_job
    assert ("VD", 15) in read_job(_corpus()["vd_recipe"].data).setup()


def test_rules_in_id_order() -> None:
    ids = [r.id for r in RULES]
    assert ids == [f"H{i}" for i in range(1, 12)] + [f"S{i}" for i in range(1, 7)]
    assert all(r.severity is (Severity.HARD if r.id[0] == "H" else Severity.SOFT) for r in RULES)
    assert all(r.title for r in RULES)


def test_run_gate_leaves_input_unchanged() -> None:
    c = _corpus()["f_arrow"]
    buf = bytearray(c.data)
    before = bytes(buf)
    seen: list[type] = []

    class Spy:
        id, severity, title = "S9", Severity.SOFT, "spy"

        def check(self, data: bytes, job: object, inputs: object) -> list[Finding]:
            seen.append(type(data))
            return []

    rep = run_gate(buf, c.inputs, rules=(*RULES, Spy()))   # type: ignore[arg-type]
    assert bytes(buf) == before
    assert seen == [bytes]                     # rules receive immutable bytes
    assert rep.bound_to(before)
    assert run_gate(before, c.inputs).to_json() == run_gate(before, c.inputs).to_json()


def test_report_round_trips_with_findings() -> None:
    c = _corpus()["seed_draft_rotary"]
    rep = c.gate()
    assert GateReport.from_json(rep.to_json()) == rep
    assert "To send, type: I ACCEPT 2 FLAGS" in rep.to_text()


MANIFEST = json.loads((GOLDEN / "manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(MANIFEST["cases"]))
def test_root_golden_express_jobs_refused_for_iq(name: str) -> None:
    data = (GOLDEN / MANIFEST["cases"][name]["output"]).read_bytes()
    inputs = make_inputs(SQUARE, recipe="scrap-rotary-diamond-trace", fixture="bare-bed")
    rep = run_gate(data, inputs)
    assert not rep.passed
    h2 = [f for f in rep.findings if f.rule == "H2"]
    assert h2 and "0x0204" in h2[0].message and "0x020D" in h2[0].message


def test_build_bytes_are_driver_bytes_with_iq_stamp() -> None:
    import gts_api
    inputs = make_inputs(SQUARE)
    data = build_bytes(SQUARE, inputs)
    ref = gts_api.build_gts([s.to_driver() for s in SQUARE], speed=10, pz=50, dz=500, mc=1, vz=5)
    assert data[:0x24] == ref[:0x24] and data[0x26:] == ref[0x26:] and data[0x24:0x26] == b"\x02\x0d"
