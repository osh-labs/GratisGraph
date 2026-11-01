"""Hard gate rules H1 to H11 (build plan 9.1; decisions in desktop/docs/m1-plan.md 2.4).

Each rule judges only the decoded bytes (ggdesk.gts_read) and the GateInputs
(library entries, effective recipe, placement, keep-outs, intent). Rules
return findings; they never modify anything. A hard finding blocks the send.

A rule reports at most MAX_FINDINGS findings, then one finding counting the
rest, so a badly broken job still gives a readable report.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from ggdesk import gts_read
from ggdesk.gate import geometry as geo
from ggdesk.gate.types import Finding, GateInputs, Severity
from ggdesk.gts_read import Command, Segment
from ggdesk.library.model import Fact, UnmeasuredError
from ggdesk.numerics import UNITS_PER_MM, to_mm

MAX_FINDINGS = 20
SETUP_OPS = ("DR", "MC", "VS", "VZ", "PZ", "DZ", "VD")

UPt = tuple[int, int]


def _mm(p: UPt) -> str:
    return f"({to_mm(p[0]):.2f}, {to_mm(p[1]):.2f}) mm"


def _cap(rule: str, found: list[Finding]) -> list[Finding]:
    if len(found) <= MAX_FINDINGS:
        return found
    extra = len(found) - MAX_FINDINGS
    return found[:MAX_FINDINGS] + [Finding(rule, Severity.HARD, f"... and {extra} more finding(s) of this rule")]


def _gap(what: str, fact: Fact[Any]) -> str:
    return f"{what} ({fact.gap or 'gap not named'})"


def _pd_points(job: gts_read.Job) -> list[tuple[int, UPt]]:
    """(offset, position) of every PD command: the pen-down start point of each stroke."""
    x = y = 0
    out: list[tuple[int, UPt]] = []
    for r in job.records:
        if isinstance(r, Segment):
            x += r.dx
            y += r.dy
        elif r.op == "PD":
            out.append((r.offset, (x, y)))
    return out


class H1WorkField:
    id = "H1"
    severity = Severity.HARD
    title = "Every position inside the machine work field"

    def check(self, data: bytes, job: gts_read.Job, inputs: GateInputs) -> list[Finding]:
        field = inputs.resolved.machine.work_field_mm
        if not field.known or field.value is None:
            return [Finding(self.id, self.severity, "work field unknown: " + _gap("machine work_field_mm", field))]
        w, h = field.value
        wu, hu = w * UNITS_PER_MM, h * UNITS_PER_MM
        out: list[Finding] = []
        for m in job.moves():
            x, y = m.end
            if not (0 <= x <= wu and 0 <= y <= hu):
                kind = "pen-down" if m.down else "rapid"
                out.append(Finding(self.id, self.severity,
                                   f"{kind} position {_mm(m.end)} outside the work field "
                                   f"[0, {w:g}] x [0, {h:g}] mm", m.offset))
        return _cap(self.id, out)


class H2ModelCode:
    id = "H2"
    severity = Severity.HARD
    title = "Header model code equals the target machine"

    def check(self, data: bytes, job: gts_read.Job, inputs: GateInputs) -> list[Finding]:
        mc = inputs.resolved.machine.model_code
        off = gts_read.MODEL_CODE_OFFSET
        if not mc.known or mc.value is None:
            return [Finding(self.id, self.severity, "machine model code unknown: " + _gap("model_code", mc), off)]
        out: list[Finding] = []
        if job.model_code != mc.value:
            out.append(Finding(self.id, self.severity,
                               f"header model code 0x{job.model_code:04X} is not the machine's 0x{mc.value:04X} "
                               f"({inputs.resolved.machine.ref.id})", off))
        t = inputs.target_model_code
        if t is not None and job.model_code != t:
            out.append(Finding(self.id, self.severity,
                               f"header model code 0x{job.model_code:04X} is not the connected machine's 0x{t:04X}",
                               off))
        return out


def _spec_header() -> bytes:
    """The 94-byte header from docs/GTS_FORMAT.md 5.2 (written from the spec, not the builder).

    The model code at 0x24 is left zero here: H2 judges it.
    """
    h = bytearray(94)
    h[0:6] = b"!MM88;"
    meta = "ot : 1\0".encode("utf-16-le")
    h[0x0A:0x0A + len(meta)] = meta
    h[0x30:0x32] = (0x0DE4).to_bytes(2, "big")
    h[0x34:0x36] = (0x0DE4).to_bytes(2, "big")
    h[0x3D] = 0x02
    h[0x5D] = 0x04
    return bytes(h)


SPEC_HEADER = _spec_header()


class H3SingleFinalJF:
    id = "H3"
    severity = Severity.HARD
    title = "Job framing: spec header, return home, exactly one JF as the final record"

    def check(self, data: bytes, job: gts_read.Job, inputs: GateInputs) -> list[Finding]:
        jfs = [c for c in job.commands if c.op == "JF"]
        last = job.records[-1] if job.records else None
        out: list[Finding] = []
        hdr = bytearray(data[:94])
        hdr[gts_read.MODEL_CODE_OFFSET:gts_read.MODEL_CODE_OFFSET + 2] = b"\0\0"
        if bytes(hdr) != SPEC_HEADER:
            first = next(i for i, (a, b) in enumerate(zip(hdr, SPEC_HEADER, strict=True)) if a != b)
            out.append(Finding(self.id, self.severity,
                               f"header differs from GTS_FORMAT 5.2 at byte 0x{first:02X}", first))
        pos = job.positions()
        if pos and pos[-1] != (0, 0):
            out.append(Finding(self.id, self.severity, f"the job ends at {_mm(pos[-1])}, not at home (0, 0)"))
        if not jfs:
            out.append(Finding(self.id, self.severity, "no JF: the job never ends"))
        elif len(jfs) > 1:
            for c in jfs[:-1] if jfs[-1] is last else jfs:
                out.append(Finding(self.id, self.severity, f"extra JF ({len(jfs)} in the job; exactly one allowed)",
                                   c.offset))
        if jfs and not (isinstance(last, Command) and last.op == "JF"):
            out.append(Finding(self.id, self.severity, "the final record is not JF",
                               None if last is None else last.offset))
        return _cap(self.id, out)


class H4Opcodes:
    id = "H4"
    severity = Severity.HARD
    title = "Only opcodes on the machine's allow-list"

    def check(self, data: bytes, job: gts_read.Job, inputs: GateInputs) -> list[Finding]:
        m = inputs.resolved.machine
        allowed = set(m.opcodes_allowed)
        out: list[Finding] = []
        for c in job.commands:
            if c.op not in allowed:
                why = " (reserved: not emitted in M1/M2)" if c.op in m.opcodes_reserved else ""
                out.append(Finding(self.id, self.severity,
                                   f"opcode {c.op} {c.arg} is not on the {m.ref.id} allow-list{why}", c.offset))
        return _cap(self.id, out)


class H5Setup:
    id = "H5"
    severity = Severity.HARD
    title = "Setup equals the recipe; values inside the machine's ranges"

    def check(self, data: bytes, job: gts_read.Job, inputs: GateInputs) -> list[Finding]:
        rec = inputs.resolved.recipe
        machine = inputs.resolved.machine
        out: list[Finding] = []
        try:
            sv = rec.setup_values()
        except UnmeasuredError as e:
            return [Finding(self.id, self.severity, f"recipe value unmeasured: {e}")]
        expected: list[tuple[str, int]] = [("DR", 0), ("MC", sv["mc"] or 0), ("VS", sv["vs"] or 0),
                                           ("VZ", sv["vz"] or 0), ("PZ", sv["pz"] or 0), ("DZ", sv["dz"] or 0)]
        if sv["vd"] is not None:
            expected.append(("VD", sv["vd"]))
        setup_cmds: list[Command] = []
        for r in job.records:
            if isinstance(r, Segment):
                break
            setup_cmds.append(r)
        got = [(c.op, c.arg) for c in setup_cmds]
        if got != expected:
            exp_s = " ".join(f"{o} {a}" for o, a in expected)
            got_s = " ".join(f"{o} {a}" for o, a in got) or "nothing"
            first = next((i for i, (g, e) in enumerate(zip(got, expected, strict=False)) if g != e),
                         min(len(got), len(expected)))
            off = setup_cmds[first].offset if first < len(setup_cmds) else None
            out.append(Finding(self.id, self.severity,
                               f"setup is [{got_s}]; recipe {rec.ref.id} needs [{exp_s}]", off))
        # every setup value inside the machine's ranges
        for c in setup_cmds:
            key = c.op.lower()
            if c.op == "DR":
                continue
            rng = machine.ranges.get(key)
            if rng is None:
                out.append(Finding(self.id, self.severity, f"{c.op} has no range in machine {machine.ref.id}",
                                   c.offset))
            elif not rng.known or rng.value is None:
                out.append(Finding(self.id, self.severity, f"{c.op} {c.arg}: range unknown ("
                                   f"{rng.gap or 'gap not named'})", c.offset))
            elif not rng.value.contains(c.arg):
                out.append(Finding(self.id, self.severity,
                                   f"{c.op} {c.arg} outside the machine range {rng.value.min}..{rng.value.max}",
                                   c.offset))
        # setup opcodes after the setup block: only MC 0 right before the return home, when MC 1
        mc_on = ("MC", 1) in got
        segs = [i for i, r in enumerate(job.records) if isinstance(r, Segment)]
        ret = segs[-1] if segs else None
        mc0_index = ret - 1 if (mc_on and ret is not None) else None
        for i, r in enumerate(job.records[len(setup_cmds):], start=len(setup_cmds)):
            if isinstance(r, Command) and r.op in SETUP_OPS:
                if i == mc0_index and r.op == "MC" and r.arg == 0:
                    continue
                out.append(Finding(self.id, self.severity, f"{r.op} {r.arg} outside the setup block", r.offset))
        if mc_on and ret is not None:
            prev = job.records[ret - 1] if ret >= 1 else None
            if not (isinstance(prev, Command) and prev.op == "MC" and prev.arg == 0):
                out.append(Finding(self.id, self.severity,
                                   "MC 1 job without MC 0 immediately before the return home",
                                   job.records[ret].offset))
        # segment speed field equals VS
        vs = sv["vs"]
        for m in job.moves():
            if m.segment.speed != vs:
                out.append(Finding(self.id, self.severity,
                                   f"segment speed {m.segment.speed} is not VS {vs}", m.offset))
        return _cap(self.id, out)


class H6Spindle:
    id = "H6"
    severity = Severity.HARD
    title = "MC 1 if and only if the tool needs the spindle"

    def check(self, data: bytes, job: gts_read.Job, inputs: GateInputs) -> list[Finding]:
        tool = inputs.resolved.tool
        need = tool.needs_spindle
        if not need.known or need.value is None:
            return [Finding(self.id, self.severity,
                            f"tool {tool.ref.id}: " + _gap("needs_spindle unknown", need))]
        mc1 = [c for c in job.commands if c.op == "MC" and c.arg == 1]
        setup_mc = next((arg for op, arg in job.setup() if op == "MC"), None)
        if need.value and setup_mc != 1:
            return [Finding(self.id, self.severity,
                            f"tool {tool.ref.id} needs the spindle but the setup has "
                            f"{'no MC' if setup_mc is None else f'MC {setup_mc}'}")]
        if not need.value and mc1:
            return [Finding(self.id, self.severity, f"tool {tool.ref.id} must not spin but the job sends MC 1",
                            mc1[0].offset)]
        return []


class H7PartOutline:
    id = "H7"
    severity = Severity.HARD
    title = "Every pen-down point inside the part outline minus its keep-out margin"

    def check(self, data: bytes, job: gts_read.Job, inputs: GateInputs) -> list[Finding]:
        r = inputs.resolved
        part, fixture = r.part, r.fixture
        missing: list[str] = []
        gaps: set[str] = set()

        def need(what: str, fact: Fact[Any]) -> None:
            if not fact.known:
                missing.append(_gap(what, fact))
                if fact.gap:
                    gaps.add(fact.gap)

        need("part outline", part.outline)
        need("part holes", part.holes)
        need("part keep-out margin", part.keep_out_margin_mm)
        if r.placement is None:
            need("fixture datum", fixture.datum_mm)
            try:
                nest = fixture.nest(inputs.selection.nest)
                need(f"nest {nest.id} origin", nest.origin_mm)
            except KeyError:
                missing.append(f"nest {inputs.selection.nest} not in fixture {fixture.ref.id}")
            if not missing:
                missing.append("placement unknown")
        if missing:
            return [Finding(self.id, self.severity,
                            f"unmeasured geometry ({', '.join(sorted(gaps)) or 'gap not named'}): "
                            + "; ".join(missing))]
        assert part.outline.value is not None and part.holes.value is not None
        assert part.keep_out_margin_mm.value is not None and r.placement is not None
        place = r.placement

        def units(poly: tuple[tuple[float, float], ...]) -> list[geo.FPt]:
            return [(x * UNITS_PER_MM, y * UNITS_PER_MM) for x, y in (place.to_machine(p) for p in poly)]

        outline = units(part.outline.value.polygon())
        holes = [units(h.polygon()) for h in part.holes.value]
        margin = part.keep_out_margin_mm.value * UNITS_PER_MM
        mm = part.keep_out_margin_mm.value
        out: list[Finding] = []

        def point_problem(p: geo.FPt) -> str | None:
            if not geo.point_in_polygon(p, outline):
                return "outside the part outline"
            if not geo.clearance_ok(geo.boundary_dist2(p, outline), margin):
                return f"closer than {mm:g} mm to the part edge"
            for h in holes:
                if geo.point_strictly_inside(p, h):
                    return "inside a hole"
                if not geo.clearance_ok(geo.boundary_dist2(p, h), margin):
                    return f"closer than {mm:g} mm to a hole"
            return None

        for off, p in _pd_points(job):
            why = point_problem((float(p[0]), float(p[1])))
            if why:
                out.append(Finding(self.id, self.severity, f"pen-down point {_mm(p)} {why}", off))
        for m in job.moves():
            if not m.down:
                continue
            a = (float(m.start[0]), float(m.start[1]))
            b = (float(m.end[0]), float(m.end[1]))
            why = point_problem(b)
            if why is None:
                if not geo.segment_inside(a, b, outline):
                    why = "leaves the part outline"
                elif not geo.clearance_ok(geo.segment_boundary_dist2(a, b, outline), margin):
                    why = f"passes closer than {mm:g} mm to the part edge"
                else:
                    for h in holes:
                        if geo.segment_enters_interior(a, b, h):
                            why = "crosses a hole"
                        elif not geo.clearance_ok(geo.segment_boundary_dist2(a, b, h), margin):
                            why = f"passes closer than {mm:g} mm to a hole"
                        if why:
                            break
            if why:
                out.append(Finding(self.id, self.severity,
                                   f"pen-down segment {_mm(m.start)} -> {_mm(m.end)} {why}", m.offset))
        return _cap(self.id, out)


class H8KeepOuts:
    id = "H8"
    severity = Severity.HARD
    title = "No position or move inside or through a fixture keep-out"

    def check(self, data: bytes, job: gts_read.Job, inputs: GateInputs) -> list[Finding]:
        r = inputs.resolved
        if r.keep_outs_machine is None:
            fx = r.fixture
            gaps = [_gap("fixture keep-outs", fx.keep_outs)] if not fx.keep_outs.known else []
            if not fx.datum_mm.known:
                gaps.append(_gap("fixture datum", fx.datum_mm))
            return [Finding(self.id, self.severity,
                            f"unmeasured geometry: fixture {fx.ref.id} " + "; ".join(gaps or ["keep-outs unknown"]))]
        polys = [[(x * UNITS_PER_MM, y * UNITS_PER_MM) for x, y in poly] for poly in r.keep_outs_machine]
        if not polys:
            return []
        out: list[Finding] = []
        for m in job.moves():
            a = (float(m.start[0]), float(m.start[1]))
            b = (float(m.end[0]), float(m.end[1]))
            for k, poly in enumerate(polys):
                if geo.segment_meets_polygon(a, b, poly):
                    kind = "pen-down move" if m.down else "rapid"
                    out.append(Finding(self.id, self.severity,
                                       f"{kind} {_mm(m.start)} -> {_mm(m.end)} enters keep-out {k + 1}", m.offset))
                    break
        return _cap(self.id, out)


class H9PenUpBeforeRapid:
    id = "H9"
    severity = Severity.HARD
    title = "Every rapid preceded by PU 1; stroke blocks well formed"

    def check(self, data: bytes, job: gts_read.Job, inputs: GateInputs) -> list[Finding]:
        recs = job.records
        out: list[Finding] = []
        seen_pd = False
        pu1 = True
        down = False
        for i, r in enumerate(recs):
            if isinstance(r, Segment):
                if (r.pw1, r.pw2, r.accel) != (1, 1, 551):
                    out.append(Finding(self.id, self.severity,
                                       f"segment fields pw1 {r.pw1}, pw2 {r.pw2}, accel {r.accel}: only 1, 1, 551 "
                                       "are observed on the wire (GTS_FORMAT 5.4)", r.offset))
                if not down and seen_pd and not pu1:
                    out.append(Finding(self.id, self.severity, "rapid without PU 1 since the last PD", r.offset))
                continue
            if r.op == "PD":
                prev1 = recs[i - 1] if i >= 1 else None
                prev2 = recs[i - 2] if i >= 2 else None
                if r.arg != 0:
                    out.append(Finding(self.id, self.severity, f"PD {r.arg} (stroke blocks use PD 0)", r.offset))
                if not (isinstance(prev1, Command) and prev1.op == "ZA" and prev1.arg == 1
                        and isinstance(prev2, Segment)):
                    out.append(Finding(self.id, self.severity,
                                       "PD not preceded by a stroke header segment and ZA 1", r.offset))
                j = i + 1
                while j < len(recs) and isinstance(recs[j], Segment):
                    j += 1
                tail = [(c.op, c.arg) if isinstance(c, Command) else None for c in recs[j:j + 3]]
                if tail != [("PU", 0), ("PU", 0), ("PU", 1)]:
                    off = recs[j].offset if j < len(recs) else r.offset
                    out.append(Finding(self.id, self.severity,
                                       "stroke not closed by PU 0, PU 0, PU 1", off))
                seen_pd, down, pu1 = True, True, False
            elif r.op == "PU":
                down = False
                if r.arg == 1:
                    pu1 = True
            elif r.op == "ZA":
                nxt = recs[i + 1] if i + 1 < len(recs) else None
                if not (isinstance(nxt, Command) and nxt.op == "PD"):
                    out.append(Finding(self.id, self.severity, "ZA not immediately followed by PD", r.offset))
        return _cap(self.id, out)


def _key(points: tuple[UPt, ...]) -> tuple[UPt, ...]:
    rev = tuple(reversed(points))
    return min(points, rev)


class H10Intent:
    id = "H10"
    severity = Severity.HARD
    title = "Decoded strokes equal the intended toolpath"

    def check(self, data: bytes, job: gts_read.Job, inputs: GateInputs) -> list[Finding]:
        if inputs.intent is None:
            return [Finding(self.id, self.severity, "no intent: bytes cannot be checked against a job")]
        decoded = job.strokes()
        want = Counter(_key(s.points) for s in inputs.intent.strokes)
        have = Counter(_key(s.points) for s in decoded)
        out: list[Finding] = []
        extra = have - want
        for s in decoded:
            k = _key(s.points)
            if extra[k] > 0:
                extra[k] -= 1
                out.append(Finding(self.id, self.severity,
                                   f"stroke from {_mm(s.points[0])} ({len(s.points)} points) is not in the job's "
                                   "toolpath", s.offset))
        missing = want - have
        for k, n in sorted(missing.items()):
            for _ in range(n):
                out.append(Finding(self.id, self.severity,
                                   f"intended stroke from {_mm(k[0])} ({len(k)} points) is missing from the bytes"))
        return _cap(self.id, out)


class H11JobSize:
    id = "H11"
    severity = Severity.HARD
    title = "Job size within the measured machine limit"

    def check(self, data: bytes, job: gts_read.Job, inputs: GateInputs) -> list[Finding]:
        lim = inputs.resolved.machine.max_job_bytes
        if not lim.known or lim.value is None:
            return []   # inactive until G9 is measured; a residual line says so
        if len(data) > lim.value:
            return [Finding(self.id, self.severity,
                            f"job is {len(data)} bytes; the machine limit is {lim.value} bytes")]
        return []


HARD_RULES = (H1WorkField(), H2ModelCode(), H3SingleFinalJF(), H4Opcodes(), H5Setup(), H6Spindle(),
              H7PartOutline(), H8KeepOuts(), H9PenUpBeforeRapid(), H10Intent(), H11JobSize())
