# M1 plan: bench app (job format, trace, gate, CLI, bench window)

Status: software complete 2026-11-01 (PRs #8 to #12 and the M1.Z integration PR); hardware stages V1 and
V2 not yet run. Owner questions answered by the coding agent under delegated authority; owner to confirm.

## Bottom line

M1 delivers the thin bench app of build plan section 7: the `gratisgraph-job` v1 format (F03), the trace
operation (F04), the part-to-machine fixture transform (F05), the output gate with rules H1 to H11 and
S1 to S5 bound to the job's SHA-256 (F06), a CLI for every core operation (F07), the bench window (F08),
the library schema with seed entries (F11, schema part) and the run-time estimate (F20). One contracts PR
(M1.0, serial), four parallel slices (M1.1 build, M1.2 gate, M1.3 run, M1.4 bench window), one
integration PR (M1.Z) that writes the acceptance document, the exit table, and the V1 and V2 operator
sheets. Hardware exit items (G4, G10, G15) stay open for the owner with ready sheets.

## 1. Principles carried into M1

| Non-negotiable | How M1 keeps it |
|---|---|
| Output gate on final bytes | `ggdesk.gate.run_gate(data, inputs)` decodes with `ggdesk.gts_read` (never the builder's state). `ggdesk.run.send_gated` is the only caller of a connection's `send_gts`; a test greps the source tree for other callers. No override control exists in the CLI or GUI. |
| Hard vs soft | Hard findings make `report.passed` false. Soft findings need `ack == ack_phrase(n)` (`I ACCEPT 3 FLAGS`; `I ACCEPT 1 FLAG`). Nothing else unlocks a send. |
| Refuses, never repairs | Rules return findings only; they receive the bytes as `bytes` (immutable). |
| Determinism | All mm-to-unit rounding through `ggdesk.numerics`; no clock in build or gate; the report carries no timestamp. The job log takes an injectable clock. |
| Goldens are the test | Desktop goldens (job + library snapshot -> `.m20`) in `desktop/tests/golden/`, recomputed on Linux and Windows CI; regenerated only by `make_goldens.py --write` in a commit that explains why. |
| Never invent physical values | Seed library values only from build plan section 1 with evidence tags; unknowns `needs_measurement` with a `measure` procedure and gap ID. Definitions (e.g. the bench part's declared area) are tagged `DEFINED`, never `CONFIRMED`. A [HYPOTHESIS] fact cannot set a hard gate limit (the loader refuses one in a hard-limit field). |
| Qt-free core | Unchanged checks (ruff TID251, import probe). The GUI calls the core only through `ggdesk_app/session.py`. |
| Driver modules untouched | M1 wraps `gts_api.build_gts`, `gts_optimise.optimise_strokes` and `estimate_duration`, `GTSConnection.send_gts` / `add_tap` / `abort`. No root module changes are planned. |
| No producer names | Seed and test data are generic (`dog-tag-blank`, `bench-scrap-40`). |
| No USB in this repository's tests | Every send-path test uses a `FakeConn`. |

## 2. Components and contracts

All paths are under `desktop/src/ggdesk/` unless stated. Types are frozen dataclasses unless stated.
Coordinates: `MM = float`; `Pt = tuple[float, float]` (mm); `UPt = tuple[int, int]` (device units,
0.01 mm). Frames: part frame (origin at the centre of the part's engrave area, +X right, +Y up as the
operator reads the finished part) and machine frame (home back-left, +X right, +Y toward the operator).

### 2.1 `model/` (M1.0)

```python
# model/geometry.py
class Polyline:      points: tuple[Pt, ...]; closed: bool = False
class Region:        outer: tuple[Pt, ...]; holes: tuple[tuple[Pt, ...], ...] = ()
class Placement:     origin_mm: Pt            # machine position of the part-frame origin
    def to_machine(self, p: Pt) -> Pt: ...    # (ox + x, oy - y): Y flip, no rotation or scale

# model/job.py
class TraceOp:   paths: tuple[Polyline, ...]; mode_hint: str = "trace";
                 char_height_mm: float | None = None; extra: Mapping[str, Any] = {}
class FillOp:    regions: tuple[Region, ...]; mode_hint: str = "fill";
                 char_height_mm: float | None = None; extra: ...           # built in M2
Operation = TraceOp | FillOp
class JobSource: name: str; version: str
class Job:       part: str; operations: tuple[Operation, ...]; quantity: int = 1;
                 reference: str = ""; source: JobSource | None = None;
                 chord_tolerance_mm: float = 0.01; extra: Mapping[str, Any] = {}

# model/toolpath.py
class UStroke:   points: tuple[UPt, ...]        # absolute machine units, >= 2 points, no repeats
    def to_driver(self) -> tuple[int, int, list[tuple[int, int]]]: ...   # (sx, sy, deltas)
class NarrowRegion: op_index: int; region_index: int; width_mm: float      # S3 input (M2)
class Intent:    strokes: tuple[UStroke, ...]    # toolpath after quantisation, before ordering
                 char_heights_mm: tuple[float, ...] = ()
                 narrow_regions: tuple[NarrowRegion, ...] = ()
```

### 2.2 `formats/job.py` (M1.0)

```python
FORMAT = "gratisgraph-job"; VERSION = 1
class JobFormatError(ValueError)                   # message names the JSON path, e.g. operations[2].paths[0]
def loads(text: str) -> Job
def load(path: Path) -> Job
def dumps(job: Job) -> str                          # deterministic: fixed key order, extras after, 2-space indent, trailing \n
def dump(job: Job, path: Path) -> None
```

Schema: `formats/job.schema.json` (JSON Schema draft 2020-12). Spec: `desktop/docs/job-format.md`.
Examples: `desktop/docs/examples/*.ggj`. Unknown keys at the top level and in each operation are
preserved in `extra` and written back after the known keys. `chord_tolerance_mm` must be `> 0` and
`<= 0.01`. `units` must be `"mm"`. A closed polyline repeats no closing point (the trace op adds it).

### 2.3 `library/` (M1.0)

One TOML file per entry under `desktop/library/<kind>s/<id>.toml` (`machines`, `tools`, `materials`,
`parts`, `fixtures`, `recipes`). Every physical value is a fact table:

```toml
[work_field_mm]
value = [100.0, 100.0]
src = "driver"                # key into [sources]
ref = "gts_api.py M20_PROFILE"
confidence = "STRONG"         # CONFIRMED | STRONG | HYPOTHESIS | DEFINED

[tip_width_mm]
null = true
needs_measurement = true
gap = "G3"
measure = ["V3 step 2: trace a 10 mm line, measure the groove width at 3 points under a loupe"]
```

```python
# library/model.py
class Fact(Generic[T]): value: T | None; src: str | None; ref: str | None; confidence: str | None;
                        needs_measurement: bool; gap: str | None; measure: tuple[str, ...]
    @property known -> bool
class EntryRef:  kind: str; id: str; version: int; sha256: str     # sha256 of the TOML file bytes
class Range:     min: int; max: int
class Machine:   ref; name; model_code: Fact[int]; send_enabled: bool; work_field_mm: Fact[tuple[float, float]];
                 opcodes_allowed: tuple[str, ...]; opcodes_reserved: tuple[str, ...];
                 ranges: Mapping[str, Fact[Range]];   # keys mc vs vz pz dz vd
                 completion: str; max_job_bytes: Fact[int]
class Tool:      ref; name; type: str; needs_spindle: Fact[bool]; needs_nose: Fact[bool]; tip_width_mm: Fact[float]
class Material:  ref; name; alloy: Fact[str]; finish: Fact[str]; thickness_mm: Fact[float]
class Outline:   kind: "rect" | "polygon"; width_mm; height_mm; corner_radius_mm; points: tuple[Pt, ...]
    def polygon(self) -> tuple[Pt, ...]       # part frame, rounded corners flattened at <= 0.01 mm chord
class Part:      ref; name; material: str; outline: Fact[Outline]; holes: Fact[tuple[Outline, ...]];
                 keep_out_margin_mm: Fact[float]; thickness_mm: Fact[float]
class Nest:      id: str; origin_mm: Fact[Pt]            # offset from the datum, machine frame
class Fixture:   ref; name; datum_mm: Fact[Pt]; nests: tuple[Nest, ...]; keep_outs: Fact[tuple[tuple[Pt, ...], ...]];
                 keep_outs_per_job: bool; tolerance_mm: Fact[float]
    def placement(self, nest_id: str) -> Placement       # raises UnmeasuredError if datum or nest unknown
class ManualSettings: nose_fitted: Fact[bool]; knob_notches: Fact[int]; pressure: Fact[int]
class Recipe:    ref; name; machine: str; tool: str; material: str; mode: "trace" | "fill"; status: "draft" | "confirmed";
                 mc: Fact[int]; vs: Fact[int]; vz: Fact[int]; pz: Fact[int]; dz: Fact[int]; vd: Fact[int | None];
                 min_char_height_mm: Fact[float]; manual: ManualSettings;
                 stepover_mm: Fact[float]; hatch_angle_deg: Fact[float]; contour_pass: Fact[bool];   # fill, M2
                 overrides: Mapping[str, Any] = {}
    def with_overrides(self, values: Mapping[str, Any]) -> Recipe   # draft recipes only; else OverrideError
OVERRIDABLE = ("vs", "vz", "vd", "pz", "dz", "stepover_mm", "hatch_angle_deg", "contour_pass",
               "min_char_height_mm", "tip_width_mm")

# library/load.py
class LibraryError: path: Path; message: str
class Library:   machines, tools, materials, parts, fixtures, recipes: Mapping[str, <type>]; errors: tuple[LibraryError, ...]
    def get(self, kind: str, id: str) -> Any       # KeyError names kind and id
def load_library(seed: Path = paths.SEED_LIBRARY, user: Path | None = None, *extra: Path) -> Library
    # later directories override earlier ones by id; invalid entries are listed in .errors, never skipped silently
```

Validators (in `load.py`): schema_version 1; `id` equals the file stem; fact tables well formed;
`needs_measurement` facts carry `gap` and a non-empty `measure`; `src` keys resolve in `[sources]`; source
`path`s resolve from a fresh clone (relative to the repository root) unless the source is a URL; a
[HYPOTHESIS] fact in a hard-limit field (machine `work_field_mm`, `ranges`, `max_job_bytes`; part
`outline`, `keep_out_margin_mm`; fixture `datum_mm`, nest `origin_mm`, `keep_outs`) is an error; recipe
references resolve.

Selection used by build and gate:

```python
# library/select.py
class Selection: machine: str; recipe: str; fixture: str; nest: str;
                 overrides: Mapping[str, Any] = {}; extra_keep_outs: tuple[tuple[Pt, ...], ...] = ()
class Resolved:  machine; tool; part; fixture; recipe (effective, overrides applied); placement: Placement | None;
                 keep_outs_machine: tuple[tuple[Pt, ...], ...]; entries: tuple[EntryRef, ...]; tip_width_mm: float | None
def resolve(lib: Library, job: Job, sel: Selection) -> Resolved
    # extra_keep_outs only when fixture.keep_outs_per_job; tip width = override, else tool value
```

### 2.4 `gate/` (M1.0 types; M1.2 rules)

```python
# gate/types.py
class Severity(StrEnum): HARD = "hard"; SOFT = "soft"
class Finding:   rule: str; severity: Severity; message: str; offset: int | None = None
class GateConfig: max_run_time_s: float = 1800.0       # S5 limit, a project setting, not a machine fact
class GateInputs: resolved: Resolved; intent: Intent | None; job_sha256: str | None; selection: Selection;
                  config: GateConfig = GateConfig(); target_model_code: int | None = None   # connected !ID at send
class Rule(Protocol): id: str; severity: Severity; title: str
    def check(self, data: bytes, job: gts_read.Job, inputs: GateInputs) -> list[Finding]
class GateReport: sha256: str; size: int; app_version: str; model_code: int; entries: tuple[EntryRef, ...];
                  selection: Selection; job_sha256: str | None; findings: tuple[Finding, ...];
                  residual: tuple[str, ...]; estimate_s: float | None; rules_run: tuple[str, ...]
    passed -> bool (no hard findings); flags -> int (soft count); ack_phrase -> str
    def bound_to(self, data: bytes) -> bool
    def to_json(self) -> str   # sorted keys, no timestamp; from_json(text) round-trips
    def to_text(self) -> str
def ack_phrase(n: int) -> str                         # "I ACCEPT 3 FLAGS" / "I ACCEPT 1 FLAG" / "" for 0
def acknowledged(report: GateReport, typed: str) -> bool  # exact match after strip; True when flags == 0

# gate/__init__.py
RULES: tuple[Rule, ...]                                # empty in M1.0; M1.2 fills it
def run_gate(data: bytes, inputs: GateInputs) -> GateReport
    # decode failure -> one HARD finding "DECODE"; then every rule in RULES; residual lines always
```

Rules (M1.2): H1 to H11 and S1 to S5 exactly as build plan section 9, with these decisions:
H1 bounds are inclusive `[0, W] x [0, H]` in units; H5 compares the whole setup block (`DR 0`, `MC`, `VS`,
`VZ`, `PZ`, `DZ`, then `VD` only when the recipe has one), the `MC 0` before the return home when
`MC 1`, the segment `speed` field (= `VS`), and each value against the machine's ranges; H7 refuses when
the part outline, margin, fixture datum or nest origin is `needs_measurement` ("unmeasured geometry");
H8 refuses when the fixture's keep-outs are `needs_measurement`; H9 also checks the stroke block shape
(`ZA 1`, `PD 0` before pen-down segments; `PU 0, PU 0, PU 1` after); H10 compares decoded pen-down
strokes with `intent.strokes` as a multiset, each stroke equal forward or reversed (the optimiser may
reverse open strokes); no intent is a HARD finding; H11 is present and returns nothing while
`max_job_bytes` is null (a residual line says so). S2 needs both `char_height_mm` and a known
`min_char_height_mm`; otherwise a residual line. S4 flags a fixture whose `tolerance_mm` is unknown. S5
uses `gts_optimise.estimate_duration` on the decoded strokes.

Residual lines (always, in this order): the manual-depth line (`Depth is set by hand: nose <fitted>,
knob <n> notches, pressure <p>. Software cannot verify these.`, with `unknown` for null facts); recipe
status; each bench override (`Bench override: pz = 80 (library 50)`); unmeasured facts the job relies on
(gap IDs); `Job size limit not measured (G9): H11 inactive.`; `PZ units are [HYPOTHESIS] (G4).`

The home job the driver queues before each job (`home_first=True`) is gated by
`gate.home.check_home_job(data, machine) -> GateReport` (M1.2): decode, single final `JF`, no segments,
only `DR 0, MC 0, PU 1, JF`, model code. `run` refuses to send if it fails.

### 2.5 `toolpath/` and `build.py` (M1.1)

```python
# toolpath/trace.py
def trace(op: TraceOp) -> tuple[Polyline, ...]            # part frame; closed paths get their closing point
# toolpath/transform.py
def to_machine_units(paths: Iterable[Polyline], placement: Placement) -> tuple[UStroke, ...]
    # placement in mm, then ONE quantisation per point via numerics.to_units; zero deltas dropped;
    # strokes that collapse to one point are dropped and counted
# toolpath/order.py
def order(strokes: Sequence[UStroke]) -> list[UStroke]    # gts_optimise.optimise_strokes(merge=False)
# build.py
class BuildError(ValueError)
class BuildResult: data: bytes; intent: Intent; ordered: tuple[UStroke, ...]; resolved: Resolved;
                   job_sha256: str; estimate_s: float; dropped_points: int
def build(job: Job, lib: Library, sel: Selection, *, job_text: str | None = None) -> BuildResult
    # build_gts(strokes, speed=vs, pz=pz, dz=dz, mc=mc, vz=vz, vd=vd), then the machine's model_code
    # written at header 0x24 so the gated bytes are the bytes sent
def gate_inputs(result: BuildResult, sel: Selection, config: GateConfig = GateConfig()) -> GateInputs
```

Ordering uses `merge=False`: merging bridges gaps with the tool down, which would engrave lines the job
does not contain.

### 2.6 `run.py`, `joblog.py` (M1.3)

```python
class Connection(Protocol):
    model_code: int; dev: object | None
    def connect(self, timeout_s: float = 5.0, wait: bool = False) -> bool
    def add_tap(self, fn: Callable[[Any], None]) -> None
    def send_gts(self, gts: bytes, home_first: bool = True) -> None   # blocks in the driver's monitor
    def abort(self) -> None
    def disconnect(self) -> None
class SendRefused(RuntimeError)
class RunResult: status: "completed" | "unconfirmed" | "aborted"; et: int | None; started: str; ended: str
class Runner:
    def __init__(self, conn: Connection, log: JobLog, clock: Callable[[], str] = utc_now_iso)
    def send_gated(self, data: bytes, report: GateReport, ack: str = "") -> RunResult
        # refuses (SendRefused, logged) unless: report.bound_to(data); report.passed; acknowledged(report, ack);
        # connection model code == header model code == report.model_code; home job passes check_home_job;
        # queue empty (one item in M1). Then conn.send_gts(data, home_first=True).
    def abort(self) -> None                                   # conn.abort(): `!1B 0;`
# joblog.py
class JobLog: def __init__(self, path: Path | None = None)   # default: user data dir / logs / jobs.jsonl
    def append(self, record: Mapping[str, Any]) -> None       # one JSON object per line, sorted keys
def open_connection() -> Connection                           # real GTSConnection; never used by tests
```

Completion comes from the driver's IQ monitor; `Runner` registers a tap and records `!CM` and `!ET`:
`completed` when an `!ET` follows `!CM 4;` = 1, `aborted` after `abort()`, else `unconfirmed`.

### 2.7 `render/` and the bench window (M1.4)

```python
# render/drawlist.py
class DrawItem: kind: "field" | "part" | "keep_out" | "cut" | "rapid" | "start"; points: tuple[Pt, ...]  # machine mm
class DrawList: items: tuple[DrawItem, ...]; extent_mm: tuple[float, float]
def draw_list(data: bytes, resolved: Resolved | None = None) -> DrawList   # from DECODED bytes only
# render/svg.py
def to_svg(dl: DrawList, px_per_mm: float = 5.0) -> str
```

GUI (`ggdesk_app/`): `session.py` `BenchSession` (the only object that calls the core: open job, select,
build, gate, send, abort) and `extensions.py` `INSTALLERS` (M1.0); `panels/preview.py` (QGraphicsView
painting the same `DrawList`), `panels/gate_report.py` (findings, residual lines, ack field), send and
abort buttons, status line (M1.4). `theme.py` holds every colour. The window never builds or gates; the
send button is enabled only when the session says the report passed and the ack matches.

### 2.8 CLI (`cli.py` M1.0; `commands/*.py` per slice)

`ggdesk check | build | preview | send | pattern | library validate | inspect | version`. `cli.py` only
parses arguments and calls `ggdesk.commands.<name>.run(args) -> int`. M1.0 ships each command module as
a stub printing `ggdesk <name>: not implemented in this build` to stderr and returning 2.

| Command | Slice | Behaviour |
|---|---|---|
| `build JOB.ggj -o OUT.m20 --recipe R --fixture F [--nest N] [--machine M] [--set k=v]... [--keep-out x0,y0,x1,y1]...` | M1.1 | Writes `OUT.m20`, then gates it and writes `OUT.gate.json` and `OUT.gate.txt`; exit 0 pass, 3 refused |
| `check JOB.ggj FILE.m20 [selection flags]` | M1.2 | Gates existing bytes against the job; prints the text report; exit 0 / 3 |
| `send FILE.m20 --report FILE.gate.json [--job JOB.ggj] [--ack "I ACCEPT n FLAGS"]` | M1.3 | Refuses without a passing report bound to the file's SHA-256; re-runs the gate from the report's recorded selection and job, and refuses if the result differs; Ctrl-C sends `!1B 0;` |
| `preview FILE.m20 -o OUT.svg [selection flags + --job]` | M1.4 | SVG from the decoded bytes |
| `library validate [--user DIR]` | M1.0 | Lists errors; exit 1 if any |
| `pattern` | M2 | stub in M1 |

## 3. Threading and performance

The bench window runs build and gate on one background worker (single thread, latest wins). USB send
runs on its own thread because `send_gts` blocks in the driver's monitor; abort is callable from the
UI thread. Build plus gate for a bench job (under 1000 segments) must finish in under 1 s.

## 4. CI changes

- `desktop.yml` core job also runs `library validate` and the desktop golden check.
- `fastjsonschema` (BSD-3, pure Python) joins the `dev` extra to test the examples against the schema.
- Root `.gitignore` gains exceptions for `desktop/tests/golden/**/*.m20` and `desktop/bench/**` so the
  desktop goldens and bench files are committed; `.gitattributes` already marks `*.m20` binary.

## 5. Parallel slices

| Slice | Wave | Owns (files) | May add to shared files | Depends on | Estimate |
|---|---|---|---|---|---|
| M1.0 contracts | 1 | `model/`, `formats/`, `library/`, `gate/types.py`, `gate/__init__.py`, `cli.py`, `commands/*` (stubs), `commands/library.py`, `numerics.py`, `desktop/library/**`, `ggdesk_app/session.py`, `ggdesk_app/extensions.py`, `docs/job-format.md`, `docs/examples/`, tests for these | - | plan | 1 PR |
| M1.1 build | 2 | `toolpath/`, `build.py`, `commands/build.py`, `tests/unit/test_toolpath_*.py`, `tests/unit/test_build*.py`, `tests/golden/` (desktop) | `numerics.py`: new helpers only | M1.0 | 1 PR |
| M1.2 gate | 2 | `gts_read.py` (extend, additive), `gate/rules_*.py`, `gate/geometry.py`, `gate/home.py`, `gate/__init__.py` (`RULES` tuple only), `commands/check.py`, `tests/unit/test_gate_*.py`, `tests/fixtures/library/**` | - | M1.0 | 1 PR |
| M1.3 run | 2 | `run.py`, `joblog.py`, `commands/send.py`, `tests/unit/test_run*.py` | - | M1.0 | 1 PR |
| M1.4 bench window | 2 | `render/`, `commands/preview.py`, `ggdesk_app/panels/**`, `ggdesk_app/bench.py`, `ggdesk_app/theme.py`, `ggdesk_app/workers.py`, `tests/gui/**`, `tests/unit/test_render*.py` | one line in `extensions.py`; `app.py` window wiring | M1.0 | 1 PR |
| M1.Z integration | last | status lines, `m1-acceptance.md`, build-plan exit table, `docs/validation/V1-*.md`, `V2-*.md`, `bench/`, `docs/reviews/m1-review.md`, cross-slice tests | | all | 1 to 2 PRs |

Merge order: M1.0; then M1.1, M1.2, M1.3, M1.4 as each turns green (any order); then M1.Z.
Slices never edit status lines, exit tables or acceptance docs. `decisions.md` is append-only.

## 6. Owner questions (answered under delegated authority; owner to confirm)

| # | Question | Answer (coding agent, owner to confirm) |
|---|---|---|
| 1 | Job file extension and envelope | `.ggj`, JSON, `"format": "gratisgraph-job"`, `"version": 1`, units mm; draft until M4 freezes it |
| 2 | Part frame | Origin at the centre of the part's engrave area; +X right, +Y up as the operator reads the part. Machine +Y points to the operator, so the fixture map includes a Y flip. An asymmetric golden ("F" and an arrow) locks the orientation |
| 3 | Bench fixture | Built-in `bare-bed`: datum = machine home, one nest `centre` at the work-field centre (50, 50) mm (DEFINED), identity map apart from the Y flip, keep-outs entered per job (`--keep-out`), tolerance unmeasured (S4 flags) |
| 4 | Bench part | `bench-scrap-40`: a declared 40 x 40 mm engrave area with a 2 mm margin (DEFINED: the operator clamps stock that covers it). Bench patterns target it until the tag blank is measured |
| 5 | Unmeasured geometry | Refused (hard, H7/H8). Unmeasured tolerance only flags (S4) |
| 6 | Machine parameter ranges | Hard ranges are the observed envelope, so the gate refuses untested values rather than assuming a machine limit: VS 10..40, VZ 5..40 [CONFIRMED], PZ 0..100 [STRONG], DZ 100..500 [STRONG], VD 15..15 [CONFIRMED, one value], MC 0..1 |
| 7 | Opcode allow-list (H4) | `DR MC VS VZ PZ DZ VD ZA PD PU JF` (+ `LB NR` reserved, not emitted in M1/M2) |
| 8 | Bench overrides | `--set k=v` on a draft recipe only (`vs vz vd pz dz stepover_mm hatch_angle_deg contour_pass min_char_height_mm tip_width_mm`); each listed in the report's residual lines; confirmed recipes refuse overrides. This is how V2 runs the `PZ` sweep |
| 9 | Home job | The driver's fixed home job (queued by `send_gts(home_first=True)`) is gated by `check_home_job` before each send |
| 10 | Report timestamp | None in the report (determinism); times go in the job log |
| 11 | Send path | `ggdesk.run.Runner` wraps `GTSConnection`; one queue item in M1; completion from the driver's IQ monitor via a tap; job log JSON lines in the user data directory |
| 12 | Ordering | `gts_optimise.optimise_strokes(merge=False)`, wrapped; no new optimiser |
| 13 | S5 run-time limit | 1800 s default, a project setting in `GateConfig` |
