"""One or more mutants per gate rule (build plan 9.1 / 9.2). Each starts from a known-good job
(zero findings) and must make exactly the expected rule fire. Inclusive boundaries are tested
on both sides (a value at the limit passes; one unit past it refuses)."""
from __future__ import annotations

from dataclasses import replace

import pytest

from ggdesk.gate import GateConfig, Severity, run_gate
from ggdesk.gts_read import Segment
from ggdesk.library.model import Fact
from ggdesk.model.toolpath import Intent, NarrowRegion
from tests.unit.test_gate_support import (
    F_ARROW,
    SQUARE,
    Case,
    build_bytes,
    case,
    cmd,
    delete,
    end_of,
    fired,
    insert,
    make_inputs,
    nth_command,
    records,
    replace_record,
    seg,
    stamp,
    strokes,
)


def _only(c: Case, rule: str) -> None:
    rep = c.gate()
    assert fired(rep) == {rule}, rep.to_text()
    sev = Severity.HARD if rule.startswith("H") else Severity.SOFT
    assert all(f.severity is sev for f in rep.findings)
    assert rep.passed is (sev is Severity.SOFT)


def _clean(c: Case) -> None:
    rep = c.gate()
    assert rep.findings == (), rep.to_text()


def _detour(c: Case, to: tuple[int, int]) -> Case:
    """Insert a rapid out to `to` and straight back, after the first stroke's PU 1."""
    pu1 = nth_command(c.data, "PU", 0, arg=1)
    x, y = 4500, 4500   # SQUARE ends where it starts
    extra = seg(to[0] - x, to[1] - y) + seg(x - to[0], y - to[1])
    return Case(insert(c.data, end_of(pu1), extra), c.inputs)


# --- H1 work field ------------------------------------------------------------------------------

def test_h1_rapid_past_field_edge() -> None:
    _only(_detour(case(SQUARE), (4500, 10001)), "H1")       # 0.01 mm past the 100 mm edge


def test_h1_rapid_past_origin() -> None:
    _only(_detour(case(SQUARE), (-1, 4500)), "H1")


def test_h1_field_edges_inclusive() -> None:
    _clean(_detour(case(SQUARE), (4500, 10000)))
    _clean(_detour(case(SQUARE), (0, 4500)))


def test_h1_offset_points_at_the_record() -> None:
    c = _detour(case(SQUARE), (4500, 10001))
    f = c.gate().findings[0]
    pu1 = nth_command(c.data, "PU", 0, arg=1)
    assert f.offset == end_of(pu1)


# --- H2 model code ------------------------------------------------------------------------------

def test_h2_express_code_for_iq() -> None:
    c = case(SQUARE)
    _only(Case(stamp(c.data, 0x0204), c.inputs), "H2")


def test_h2_connected_machine_differs() -> None:
    c = case(SQUARE)
    _only(Case(c.data, replace(c.inputs, target_model_code=0x0204)), "H2")
    _clean(Case(c.data, replace(c.inputs, target_model_code=0x020D)))


# --- H3 single final JF -------------------------------------------------------------------------

def test_h3_two_jf() -> None:
    c = case(F_ARROW)
    _only(Case(c.data + cmd("JF"), c.inputs), "H3")


def test_h3_jf_before_last_stroke() -> None:
    c = case(F_ARROW)
    za = nth_command(c.data, "ZA", 3)
    header = [r for r in records(c.data) if isinstance(r, Segment) and end_of(r) == za.offset][0]
    _only(Case(insert(c.data, header.offset, cmd("JF")), c.inputs), "H3")


def test_h3_no_jf() -> None:
    c = case(SQUARE)
    _only(Case(c.data[:-6], c.inputs), "H3")


def test_h3_header_byte_changed() -> None:
    c = case(SQUARE)
    b = bytearray(c.data)
    b[0x30] ^= 0x01
    _only(Case(bytes(b), c.inputs), "H3")


def test_h3_job_does_not_return_home() -> None:
    c = case(SQUARE)
    rec = records(c.data)
    home = [r for r in rec if isinstance(r, Segment)][-1]
    moved = seg(home.dx + 1, home.dy)
    data = replace_record(c.data, home, moved)
    _only(Case(data, c.inputs), "H3")


@pytest.mark.parametrize("field", ["pw1", "pw2", "accel"])
def test_h9_segment_field_not_observed_value(field: str) -> None:
    c = case(SQUARE)
    s0 = [r for r in records(c.data) if isinstance(r, Segment)][1]
    vals = {"pw1": s0.pw1, "pw2": s0.pw2, "accel": s0.accel}
    vals[field] = 100 if field == "accel" else 2
    import struct
    rec = struct.pack(">hhhhhh", vals["pw1"], vals["pw2"], s0.speed, vals["accel"], s0.dx, s0.dy)
    _only(Case(replace_record(c.data, s0, rec), c.inputs), "H9")


# --- H4 opcode allow-list -----------------------------------------------------------------------

@pytest.mark.parametrize("op", ["TO", "LB", "NR", "OU"])
def test_h4_opcode_not_allowed(op: str) -> None:
    c = case(F_ARROW)
    pu1 = nth_command(c.data, "PU", 0, arg=1)
    m = Case(insert(c.data, end_of(pu1), cmd(op, 0)), c.inputs)
    _only(m, "H4")
    if op in ("LB", "NR"):
        assert "reserved" in m.gate().findings[0].message


# --- H5 setup and ranges ------------------------------------------------------------------------

def test_h5_pz_changed_by_one() -> None:
    c = case(SQUARE)
    pz = nth_command(c.data, "PZ")
    _only(Case(replace_record(c.data, pz, cmd("PZ", 51)), c.inputs), "H5")


def test_h5_segment_speed_differs() -> None:
    c = case(SQUARE)
    s = [r for r in records(c.data) if isinstance(r, Segment)][2]
    _only(Case(replace_record(c.data, s, seg(s.dx, s.dy, speed=11)), c.inputs), "H5")


def test_h5_mc0_before_return_missing() -> None:
    c = case(SQUARE)
    _only(Case(delete(c.data, nth_command(c.data, "MC", 1)), c.inputs), "H5")


def test_h5_speed_change_mid_job() -> None:
    c = case(F_ARROW)
    pu1 = nth_command(c.data, "PU", 0, arg=1)
    _only(Case(insert(c.data, end_of(pu1), cmd("VS", 20)), c.inputs), "H5")


def test_h5_vd_without_recipe_vd() -> None:
    c = case(SQUARE)
    dz = nth_command(c.data, "DZ")
    _only(Case(insert(c.data, end_of(dz), cmd("VD", 15)), c.inputs), "H5")


def test_h5_recipe_vd_missing_from_bytes() -> None:
    c = case(SQUARE, recipe="test-confirmed-vd")
    _clean(c)
    _only(Case(delete(c.data, nth_command(c.data, "VD")), c.inputs), "H5")


def test_h5_value_outside_machine_range() -> None:
    base = make_inputs(SQUARE)
    rec = base.resolved.recipe
    for pz, ok in ((100, True), (101, False)):
        inputs = replace(base, resolved=replace(base.resolved, recipe=replace(rec, pz=Fact(pz, confidence="DEFINED"))))
        c = Case(build_bytes(SQUARE, inputs), inputs)
        if ok:
            _clean(c)
        else:
            _only(c, "H5")
            assert "outside the machine range 0..100" in c.gate().findings[0].message


# --- H6 spindle ---------------------------------------------------------------------------------

def test_h6_rotary_recipe_with_mc0() -> None:
    _only(case(SQUARE, recipe="test-rotary-mc0"), "H6")


def test_h6_drag_tool_with_mc1() -> None:
    _only(case(SQUARE, recipe="test-drag-mc1"), "H6")


# --- H7 part outline and margin -----------------------------------------------------------------

def test_h7_stroke_into_margin() -> None:
    ss = strokes([(3190, 4000), (4000, 4000)])   # 0.1 mm into the 2 mm margin
    _only(case(ss), "H7")


@pytest.mark.parametrize(("x", "ok"), [(3200, True), (3199, False), (6800, True), (6801, False)])
def test_h7_margin_boundary_x(x: int, ok: bool) -> None:
    c = case(strokes([(5000, 5000), (x, 5000)]))
    _clean(c) if ok else _only(c, "H7")


@pytest.mark.parametrize(("y", "ok"), [(3200, True), (3199, False), (6800, True), (6801, False)])
def test_h7_margin_boundary_y(y: int, ok: bool) -> None:
    c = case(strokes([(5000, 5000), (5000, y)]))
    _clean(c) if ok else _only(c, "H7")


def test_h7_stroke_crosses_hole() -> None:
    # test-tag-50x28: hole (3 mm round) at part (-21, 0) -> machine (29, 50); margin 1.5 mm
    _only(case(strokes([(2700, 5000), (3400, 5000)]), part="test-tag-50x28"), "H7")


@pytest.mark.parametrize(("x", "ok"), [(3200, True), (3199, False)])
def test_h7_hole_margin_boundary(x: int, ok: bool) -> None:
    c = case(strokes([(x, 5000), (4000, 5000)]), part="test-tag-50x28")
    _clean(c) if ok else _only(c, "H7")


def test_h7_rounded_corner() -> None:
    # (73.5, 37.5) is 1.5 mm from both straight edges but only ~0.88 mm from the r = 3 corner arc
    _only(case(strokes([(6000, 5000), (7350, 3750)]), part="test-tag-50x28"), "H7")


def test_h7_unmeasured_part() -> None:
    c = case(SQUARE, part="dog-tag-blank", fixture="bare-bed")
    rep = c.gate()
    hard = {f.rule for f in rep.findings if f.severity is Severity.HARD}
    assert hard == {"H7"}
    assert "unmeasured geometry (G1)" in [f for f in rep.findings if f.rule == "H7"][0].message


def test_h7_h8_unmeasured_fixture() -> None:
    inputs = make_inputs(SQUARE, fixture="dog-tag-nest")
    assert inputs.resolved.placement is None and inputs.resolved.keep_outs_machine is None
    rep = run_gate(build_bytes(SQUARE, inputs), inputs)
    hard = {f.rule for f in rep.findings if f.severity is Severity.HARD}
    assert hard == {"H7", "H8"}
    msg = {f.rule: f.message for f in rep.findings}
    assert msg["H7"].startswith("unmeasured geometry (G2)")
    assert "unmeasured geometry" in msg["H8"]


# --- H8 keep-outs -------------------------------------------------------------------------------

def test_h8_rapid_through_clamp() -> None:
    _only(_detour(case(SQUARE), (8000, 5000)), "H8")      # test-clamps keep-out x 76..86, y 40..60


@pytest.mark.parametrize(("x", "ok"), [(7599, True), (7600, False)])
def test_h8_keep_out_edge(x: int, ok: bool) -> None:
    c = _detour(case(SQUARE), (x, 5000))
    _clean(c) if ok else _only(c, "H8")


def test_h8_per_job_keep_out() -> None:
    # bare-bed takes --keep-out rectangles; the square's pen-down path crosses this one
    ko = (((54.0, 40.0), (60.0, 40.0), (60.0, 60.0), (54.0, 60.0)),)
    rep = case(SQUARE, fixture="bare-bed", extra_keep_outs=ko).gate()
    assert {f.rule for f in rep.findings if f.severity is Severity.HARD} == {"H8"}


def test_h8_home_rapid_through_jaws() -> None:
    # test-jaws spans the full width at y 20..28 mm: even the rapid from home crosses it
    rep = case(SQUARE, fixture="test-jaws").gate()
    assert fired(rep) == {"H8"}


# --- H9 pen up before rapids --------------------------------------------------------------------

def test_h9_pu1_removed_before_rapid() -> None:
    c = case(F_ARROW)
    _only(Case(delete(c.data, nth_command(c.data, "PU", 0, arg=1)), c.inputs), "H9")


def test_h9_za_removed() -> None:
    c = case(F_ARROW)
    _only(Case(delete(c.data, nth_command(c.data, "ZA", 1)), c.inputs), "H9")


def test_h9_pu1_replaced_by_pu0() -> None:
    c = case(F_ARROW)
    pu1 = nth_command(c.data, "PU", 1, arg=1)
    _only(Case(replace_record(c.data, pu1, cmd("PU", 0)), c.inputs), "H9")


# --- H10 intent ---------------------------------------------------------------------------------

def test_h10_one_delta_altered() -> None:
    c = case(SQUARE)
    segs = [r for r in records(c.data) if isinstance(r, Segment)]
    s, t = segs[2], segs[3]     # second and third pen-down segments
    # +1 unit on one delta, -1 on the next: the shape changes, the end point (and return home) does not.
    data = replace_record(c.data, t, seg(t.dx - 1, t.dy))
    data = replace_record(data, s, seg(s.dx + 1, s.dy))
    _only(Case(data, c.inputs), "H10")
    # Uncompensated, the job also stops short of home: H3 refuses it too.
    rep = Case(replace_record(c.data, s, seg(s.dx + 1, s.dy)), c.inputs).gate()
    assert fired(rep) == {"H3", "H10"}


def test_h10_no_intent() -> None:
    c = case(SQUARE)
    rep = Case(c.data, replace(c.inputs, intent=None)).gate()
    assert fired(rep) == {"H10"}
    assert rep.findings[0].message == "no intent: bytes cannot be checked against a job"


def test_h10_stroke_missing_and_extra() -> None:
    c = case(F_ARROW)
    fewer = replace(c.inputs, intent=Intent(F_ARROW[:-1]))
    rep = Case(c.data, fewer).gate()
    assert fired(rep) == {"H10"} and "not in the job's toolpath" in rep.findings[0].message
    more = replace(c.inputs, intent=Intent(F_ARROW + F_ARROW[:1]))
    rep = Case(c.data, more).gate()
    assert fired(rep) == {"H10"} and "missing from the bytes" in rep.findings[0].message


def test_h10_reversed_stroke_accepted() -> None:
    inputs = make_inputs(F_ARROW)
    flipped = tuple(s.reversed() if i % 2 else s for i, s in enumerate(F_ARROW))
    _clean(Case(build_bytes(flipped, inputs), inputs))


# --- H11 job size -------------------------------------------------------------------------------

def test_h11_inactive_while_unmeasured() -> None:
    c = case(SQUARE)
    assert not c.inputs.resolved.machine.max_job_bytes.known
    _clean(c)


def test_h11_oversized() -> None:
    c = case(SQUARE)
    m = c.inputs.resolved.machine
    for limit, ok in ((len(c.data), True), (len(c.data) - 1, False)):
        machine = replace(m, max_job_bytes=Fact(limit, confidence="DEFINED"))
        inputs = replace(c.inputs, resolved=replace(c.inputs.resolved, machine=machine))
        _clean(Case(c.data, inputs)) if ok else _only(Case(c.data, inputs), "H11")


# --- soft rules ---------------------------------------------------------------------------------

def test_s1_draft_recipe() -> None:
    _only(case(SQUARE, recipe="scrap-rotary-diamond-trace"), "S1")


@pytest.mark.parametrize(("h", "ok"), [(2.0, True), (1.9, False)])
def test_s2_char_height(h: float, ok: bool) -> None:
    c = case(SQUARE, char_heights=(5.0, h))
    _clean(c) if ok else _only(c, "S2")


def test_s2_unknown_minimum_is_residual_only() -> None:
    c = case(SQUARE, recipe="scrap-rotary-diamond-trace", char_heights=(0.1,))
    rep = c.gate()
    assert fired(rep) == {"S1"}
    assert any("minimum character height" in r for r in rep.residual)


def test_s3_one_flag_per_narrow_region() -> None:
    c = case(SQUARE, narrow=(NarrowRegion(0, 1, 0.1), NarrowRegion(0, 3, 0.05)))
    rep = c.gate()
    assert fired(rep) == {"S3"} and rep.flags == 2 and rep.ack_phrase == "I ACCEPT 2 FLAGS"


def test_s4_fixture_tolerance_unknown() -> None:
    _only(case(SQUARE, fixture="bare-bed"), "S4")


def test_s5_long_fill() -> None:
    # hatch at 0.05 mm over 32 x 32 mm: about 640 lines, well over the 1800 s default
    lines = [[(3300, y), (6700, y)] if i % 2 == 0 else [(6700, y), (3300, y)]
             for i, y in enumerate(range(3300, 6701, 5))]
    c = case(strokes(*lines))
    _only(c, "S5")
    assert c.gate().estimate_s is not None and c.gate().estimate_s > 1800


def test_s5_limit_boundary() -> None:
    c = case(SQUARE)
    est = c.gate().estimate_s
    assert est is not None
    _clean(Case(c.data, replace(c.inputs, config=GateConfig(max_run_time_s=est))))
    _only(Case(c.data, replace(c.inputs, config=GateConfig(max_run_time_s=est - 0.001))), "S5")
