# GratisGraph Desktop build plan

Status: draft, 2026-11-01. Owner: Chris Lee. No milestone started.

## Bottom line

GratisGraph Desktop is a Linux-first desktop application (Kubuntu first, Windows 10 LTSC 1809 and newer
second) for running Gravograph M20-family rotary engravers. It takes 2D geometry from a documented job
format, turns it into toolpaths for a chosen tool, material and fixture, checks the final machine bytes with
an independent output gate, previews exactly what will be sent, queues jobs and runs the machine. The
existing GratisGraph Python modules (USB driver, GTS builder, optimiser, GTS parser) become the driver
layer. The desktop app adds a Qt-free core (job format, tooling operations, data libraries, gate) and a
PySide6 interface over it.

The first reference article is an engraved aluminum dog tag, in two lettering modes: single-line (traced)
and filled. The main risk is not software. Depth is set by hand on the regulating nose, the tag blank,
fixture and tooling are not yet specified, and the rotary data so far rests on three cuts of 10 mm squares
on scrap. The plan therefore ships a thin bench app early (M1) and uses it to close the tooling gaps (M2)
before the operator workflow (M3) and the external job interface (M4) are frozen.

First milestone: M0, which merges the M20 IQ fixes, makes the existing test suite enforceable in CI, adds
rotary parameters to the GTS builder, and scaffolds `desktop/`.

## 1. Sources

| Source | What it proves | Evidence tag |
|---|---|---|
| `docs/GTS_FORMAT.md` (normative wire format) | Framing, header, opcodes, segment records, execution model | [CONFIRMED] on M20 Express; rows marked "(IQ)" [CONFIRMED] on M20 IQ+ |
| `docs/PROTOCOL_FINDINGS.md`, "M20 IQ on Linux" (2026-10-28) | Header model code at 0x24 is enforced; wrong code gives `!JF` then silent discard | [CONFIRMED] |
| Same, "M20 IQ Hardware Probes" (2026-10-29) | Job completion on `!ET` after `!CM 4;` = 1; `NR`/`LB`; Point&Shoot; `!DL` pointer offset (2170, 0) | [CONFIRMED] |
| Same, spindle probes | Spindle turns only with `MC 1` and tool down; `VR` ignored (fixed speed) | [CONFIRMED] (audio and visual, two runs) |
| Same, "Rotary diamond cut" | Clean cut with nose + knob 5 notches + pressure 2, `PZ 50`, `VS 10`, `VZ 5`; no-nose cuts chatter | [CONFIRMED], three cuts, 10 mm squares, unidentified scrap |
| Same | `PZ` with nose is overtravel past the auto-ZRef touch, units 0.01 mm | [HYPOTHESIS], one sample |
| Same, citing the M20 operator manual (EN_C) | Knob 0.025 mm per notch; vise flatness 0.1 mm; 0.5 to 1 mm overtravel guidance | [STRONG] as transcription from the manual |
| `gts_api.py` `M20_PROFILE` | Work field 100 x 100 mm | [STRONG] (driver profile; not measured on the IQ) |
| Gravostyle 7 static analysis (findings doc) | Opcode vocabulary; vendor-only opcodes not seen on the wire | [STRONG] for meaning; not a basis for emitting them |
| `tests/golden/`, `tests/regression/` | Python and TypeScript builders byte-identical; output matches Gravostyle captures | [CONFIRMED] when goldens are present (currently git-ignored, see G13) |
| `gts_probe.py` | Probe method and baseline job | [CONFIRMED] as a bench tool |

## 2. Gap register

A closed gap is annotated in place with its evidence, never deleted.

| ID | Gap | Impact | How to close | Needed by |
|---|---|---|---|---|
| G1 | Dog tag blank: supplier, outline, thickness, alloy, finish (bare or anodized), edge (flat or rolled), hole position | Fixture design, recipe, part keep-out | Choose a supplier; measure 5 blanks with calipers; record in `library/parts/` | M2 |
| G2 | Fixture for the tag: how a thin blank is held flat and registered; datum offset from machine home | Placement error, chatter on thin stock | Build a nest; measure the datum by engraving a crosshair on 5 blanks and measuring the offset | M2 |
| G3 | Tooling for aluminum: tool for single-line mode (rotary diamond, diamond drag, or carbide), tool and tip width for fill mode | Recipe content, fill stepover | Bench matrix in M2 with the candidate tools on the chosen blank | M2 |
| G4 | `PZ` units and effect with the nose fitted (one sample) | Recipe limits used by the gate | `PZ` sweep 20, 50, 80, 100 with `!MZ` capture; repeat 3 times | M1 |
| G5 | Minimum readable character height, per lettering mode, on the tag | Product limits handed to SEM | Character-height ladder test pattern, M2 | M2 |
| G6 | Fill stepover vs tip width, and fill pattern (hatch angle, contour pass) | Fill appearance and run time | Stepover ladder test pattern, M2 | M2 |
| G7 | Segment `accel` field (vendor label `DANG`) effect at corners | Corner quality in text | Corner test pattern at `accel` 551 vs alternatives; ⚠ only if corners show defects | M2 |
| G8 | Where `MC 1` belongs in a builder-produced job (setup vs per stroke) | Spindle state during rapids and plunges | M0 hardware run of a builder-produced rotary job; compare to probe run 3 | M0 |
| G9 | Largest job the machine accepts, and behaviour of very long jobs (the unexplained ~500 KB `PZ 100` capture) | Fill jobs may be large | Send fills of increasing size, record acceptance and `!ET` | M2 |
| G10 | Physical stop behaviour: what the panel stop does mid-job, and what `/abort` (`!1B 0;`) does mid-job on the IQ | Operator safety procedure, app abort semantics | Bench test with tool reversed, record telemetry | M1 |
| G11 | Repeatability: depth and position over consecutive parts | Batch quality | 10 consecutive tags, measure position and inspect depth | M2 |
| G12 | Windows 10 LTSC: WinUSB driver install for the IQ, PySide6 and Python floor on 1809 | Second platform | VM and real station test | M5 |
| G13 | Golden `.m20` outputs are git-ignored (`*.m20`), so 15 golden tests fail on a fresh clone and the Python/TypeScript byte-identity guard is not enforced | All builder changes in M0 are unguarded | Un-ignore `tests/golden/outputs/`, commit goldens, add CI | M0 |
| G14 | Express behaviour after shared driver changes (Chris has only the IQ) | Upstream acceptance | Upstream maintainer runs the Express goldens and a hardware check | M0 |
| G15 | Machine bed coordinate frame vs fixture frame on the IQ, including Y direction | Mirrored or offset parts | First M1 hardware test uses an asymmetric pattern (lesson 5) | M1 |
| G16 | Exact Python and PySide6 versions that support both Kubuntu 24.04 and Windows 10 1809 | Stack pin | Check current Qt LTS and PySide6 wheel floors at M0 | M0 |

## 3. Scope

### 3.1 Goals

1. Run M20 IQ+ engraving jobs from Kubuntu with no vendor software, through a desktop interface usable by
   shop staff.
2. Turn 2D geometry into toolpaths for two lettering modes: single-line (trace) and filled (pocket fill), with
   tool-width awareness and per-material recipes.
3. Never send a job that has not passed an independent check of its final bytes.
4. Serve as the bench platform for tooling, fixture and recipe development (M2).
5. Accept jobs from external systems through a documented, generic job format (M4), so any product
   configurator can drive it without linking to GPL code.
6. Keep driver-layer changes small and suitable for upstream GratisGraph.

### 3.2 Non-goals

- A design or layout editor. Product layout, text fitting and proofs belong to the system that produces the
  job (for SEM, SEM-Configurator). The app arranges jobs on fixtures, nothing more.
- Fonts for production text. Text arrives as geometry. The app's only text rendering is for bench test
  patterns (the bundled Hershey `futural.jhf`).
- Laser machines, raster/photo engraving, rotary (cylinder) accessories, tool changers, braille.
- Opcodes not confirmed on the wire (`TO`, `OP`, `3D`, `V2`, `ME`, `BD`, raster set).
- Replacing the upstream web app or tray. They stay; the desktop app is a separate route.
- macOS for v1 (upstream already covers macOS through the tray and web app).
- SEM product rules, SEM endpoints or credentials in this repository.

### 3.3 Feature inventory

| ID | Feature | MoSCoW | Milestone |
|---|---|---|---|
| F01 | Machine connect, identify (`!ID`), model-code stamping | Must | M0 (exists) |
| F02 | Rotary parameters in the builder: `MC`, `VD`, separate `VZ`, `PZ` by recipe | Must | M0 |
| F03 | Job format reader/writer (`gratisgraph-job` v1) | Must | M1 |
| F04 | Trace operation (single-line paths) | Must | M1 |
| F05 | Fixture transform: part frame to machine frame | Must | M1 |
| F06 | Output gate with hash-bound report | Must | M1 |
| F07 | CLI for every core operation (`check`, `build`, `preview`, `send`) | Must | M1 |
| F08 | Bench window: open job, parsed-back preview, gate report, send, completion status | Must | M1 |
| F09 | Fill operation: hatch with tool-width stepover, optional contour pass, inward tool offset | Must | M2 |
| F10 | Test-pattern generator: character-height ladder, stepover ladder, corner test, crosshair datum | Must | M2 |
| F11 | Data libraries with provenance: machines, tools, materials, parts, fixtures, recipes | Must | M1 (schema), M2 (values) |
| F12 | Job queue: several jobs per green press, ordering, re-run last | Must | M3 |
| F13 | Setup card: manual settings per recipe (nose, knob notches, pressure, tool) shown before send | Must | M3 |
| F14 | Job log: bytes hash, gate report, recipe, operator, start and end, `!ET` | Must | M3 |
| F15 | Bench and operator modes (operator: confirmed recipes only, jobs from a job source) | Must | M3 |
| F16 | Job source: watched folder | Must | M3 |
| F17 | Job source: HTTP pull by job id from a configured endpoint | Should | M4 |
| F18 | Multi-part nests (several tags per fixture load) | Should | M4 |
| F19 | First-article check prompt per batch | Should | M3 |
| F20 | Estimated run time from the optimiser | Should | M1 |
| F21 | Packaged builds: Linux one-folder + udev installer; Windows one-folder + driver guide | Must | M5 |
| F22 | Packaged self-test (headless) | Must | M5 |
| F23 | Point&Shoot placement (host-side offset from `!PS`) | Could | M6 |
| F24 | M20 Express and other family models | Could | M6 |
| F25 | Tool life log per tool | Could | M6 |

## 4. Architecture

### 4.1 Rules (non-negotiables)

1. **Output gate.** No job reaches the machine without passing the gate on the final `.m20` bytes. Hard rules
   block; soft rules need typed acknowledgement (`I ACCEPT 3 FLAGS`). No override in the GUI. The gate
   refuses; it never repairs. Only the gated send path can write to USB.
2. **Determinism.** Same job file, library version and recipe give byte-identical `.m20` output on Linux and
   Windows. Clock and nonces are injectable. Platform-sensitive maths and mm-to-device rounding (half-to-even,
   per `docs/STROKE_SCHEMA.md`) go through one numerics module.
3. **Golden files are the test.** Any change to `.m20` output for a reference case is intentional, explained
   in the commit, and updates the golden.
4. **Evidence tagging.** Hardware claims are tagged [CONFIRMED], [STRONG] or [HYPOTHESIS]. A
   [HYPOTHESIS] value never sets a hard gate limit.
5. **Data is configuration with provenance.** Machine, tool, material, part, fixture and recipe values live
   in TOML with source, reference and confidence. Unknown is `null` + `needs_measurement`.
6. **Qt-free core.** All computation is in `ggdesk/`; `ggdesk_app/` is a thin PySide6 shell. Enforced by
   ruff banned-api and an import-probe test.
7. **Decisions are logged** in `desktop/docs/decisions.md`.
8. **Upstream-clean driver changes.** Changes to the root GratisGraph modules are small, keep Express output
   byte-identical by default, and go upstream as separate PRs. `desktop/` never needs to be upstreamed.
9. **Interchange boundary.** External systems talk to the app only through the job format and job sources.
   No external system imports this code.

No user extension SDK is planned (blueprint rule 7 dropped; reason logged).

### 4.2 Layers and modules

```
(repo root, upstream)   gts_api.py, gts_translator.py, gts_optimise.py, gts_preview.py, gts_prepare.py
                        driver layer: USB, !ID, build_gts, optimise, GTS parser. Packaged by a root
                        pyproject.toml added in M0 (upstreamable).
desktop/
  src/ggdesk/           Qt-free core, typed, deterministic
    model/              Job, Operation (trace, fill), Part, Fixture, Recipe, QueueItem
    numerics.py         rounding, trig, hypot; the only place for them
    formats/job.py      gratisgraph-job v1 reader/writer and schema validation
    library/            TOML loaders and validators (machines, tools, materials, parts, fixtures, recipes)
    toolpath/           trace, fill (hatch, contour, inward offset), fixture transform, ordering
    patterns/           bench test patterns (ladders, corner test, datum crosshair)
    build.py            toolpaths + recipe -> strokes -> driver build_gts -> bytes
    gate/               independent decode (own parser), rules, report bound to SHA-256
    run.py              gated send, queue, completion via driver monitor, job log
    render/             draw list from decoded bytes -> screen and SVG
    cli.py              ggdesk check | build | preview | send | pattern | library validate
  src/ggdesk_app/       PySide6 shell
    session.py          the only object that calls the core
    workers.py          single-thread, debounced, latest-wins background work; USB on its own worker
    panels/             preview, gate report, setup card, queue, log, machine status
    theme.py, selftest.py
  library/              seed TOML (read-only in the bundle); user library overrides by id
  tests/                unit, golden, gate mutants, property, gui (offscreen)
  docs/                 build-plan.md, decisions.md, job-format.md, mN-plan.md, validation/
```

Rules carried from the blueprint: the app never builds, gates or writes bytes itself; it asks the core. OS-
specific code lives only in the driver's USB path and packaging. The preview draws the decoded final bytes,
not the in-memory model.

The gate's decoder must be independent of `build_gts`. `gts_preview.py` already parses `.m20` separately
from the builder and is byte-verified against Gravostyle captures; the gate uses its own decoder in
`ggdesk/gate/` and a property test asserts it agrees with `gts_preview.py` on the golden corpus.

### 4.3 Stack and OS floors

| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3.12 (`>=3.12,<3.14`), verify at M0 (G16) | Blueprint default; the driver is Python. Upstream's tray build uses 3.14; the desktop app has its own environment |
| GUI | PySide6 pinned to one Qt LTS minor | Blueprint default; QGraphicsView for the bed preview; native on KDE |
| USB | pyusb + libusb (existing driver) | Already proven on Linux (udev, unprivileged) and Windows (WinUSB) |
| Geometry | Shapely for fill offsets and hatch clipping (verify licence and wheel availability at M0) | Mature; avoids hand-written polygon offsetting |
| Config | TOML (`tomllib`, `tomli-w`) | Blueprint default |
| Tests | pytest, hypothesis, pytest-qt (offscreen) | Blueprint default |
| Lint and types | ruff, mypy strict on `ggdesk` and `ggdesk_app` | Blueprint default |
| Packaging | PyInstaller one-folder, pinned | Blueprint default. Named `GratisGraphDesktop` so it cannot collide with the tray's `GratisGraph.exe` |
| Licence | GPL-3.0 | Required: the app imports the GPL driver |

OS floors: Kubuntu 24.04 (build on the oldest glibc supported). Windows 10 LTSC 2019 (1809) and newer; this
caps the Qt minor (Qt 6.8 to 6.12 list 1809; verify at M0).

## 5. Extensions / SDK

None in v1. External systems integrate through the job format (section 6.3), not through code.

## 6. Data libraries and job format

### 6.1 Library kinds

One TOML file per entry under `desktop/library/<kind>/`, with the blueprint provenance block. Seed values
are `needs_measurement` unless listed in section 1.

| Kind | Holds | Gate reads |
|---|---|---|
| `machines/` | Model code, work field, wire-confirmed opcode allow-list, `PZ`/`VS`/`VZ`/`VD` ranges, completion method | Field (hard), opcode allow-list (hard), parameter ranges (hard) |
| `tools/` | Type (rotary diamond, drag diamond, carbide), tip width, needs spindle, needs nose | Spindle state matches tool (hard) |
| `materials/` | Alloy, finish, thickness | Recipe link only |
| `parts/` | Blank outline, holes, engraving keep-out margin | Engrave area (hard) |
| `fixtures/` | Datum offset from machine home, nest positions, keep-outs (jaws), measured placement tolerance | Keep-outs (hard), tolerance status (residual) |
| `recipes/` | Material x tool x mode: `VS`, `VZ`, `VD`, `PZ`, stepover, passes; manual settings (nose, knob notches, pressure); validated minimum character height; status (draft, confirmed) | Setup opcodes equal recipe (hard); draft status (soft); minimum height (soft) |

Seed entries at M1: `machines/m20-iq.toml` with values from section 1; one recipe
`recipes/scrap-rotary-diamond-trace.toml` from probe run 3, status draft, tagged [CONFIRMED] for the three
observed cuts only.

### 6.2 Target definitions

One machine definition in v1 (M20 IQ+, model code 0x020D). New definitions start send-disabled. Express
and other family models are M6.

### 6.3 Job format (`gratisgraph-job` v1)

Specified in full in `desktop/docs/job-format.md` (M1), frozen at M4. Outline:

- UTF-8 JSON, `"format": "gratisgraph-job"`, `"version": 1`, units mm.
- `part`: library id of the blank (e.g. a dog tag entry). Geometry is in the part frame (origin and axes
  defined by the part entry), never the machine frame. The app applies the fixture transform.
- `operations`: ordered list. `trace` carries open or closed polylines engraved on the path. `fill` carries
  closed regions (outer rings with holes) to be cleared. Each has a `mode_hint` the recipe lookup uses.
- Curves arrive flattened to polylines with a stated chord tolerance (at most 0.01 mm, one device unit).
- `quantity`, `reference` (an opaque string, such as an order or design code), `source` (producer name and
  version). Unknown keys preserved and ignored, as in `.ggs`.
- No machine parameters. The producer states intent; the app chooses the recipe.

This keeps fonts, layout rules and product logic with the producer, and tool knowledge with the app.

## 7. Milestones

Each milestone ends when its exit criteria are met and CI is green on Linux and Windows. Exit tables are
filled in by the milestone's integration PR.

### M0 Foundation and upstream fixes

- Merge `fix/m20-iq-model-code` into the fork's `main`. Open upstream PRs: model-code stamping, IQ
  completion detection, payload decoding, `gts_probe.py`, docs.
- Un-ignore and commit golden outputs; add CI (`pytest` + `npm test`) on Linux and Windows (G13).
- Root `pyproject.toml` that packages the flat driver modules unchanged (upstreamable).
- Builder: recipe parameters (`MC`, `VD`, separate `VZ`), defaults byte-identical to today's Express
  output. Fix the depth/lift naming in `gts_prepare.py` so it matches `docs/GTS_FORMAT.md` (`PZ` is the
  depth-related value). Separate upstream PR; maintainer verifies on the Express (G14).
- Scaffold `desktop/`: pyproject, Qt-free core, import probe, ruff, mypy, CI job, `CLAUDE.md`,
  `tools/check.sh`, `decisions.md`.
- Hardware: reproduce probe run 3 with a builder-produced job (G8).

Exit criteria:

| Exit item | State | Evidence |
|---|---|---|
| All existing goldens committed and byte-identical on Linux and Windows CI | open | |
| Express default output unchanged (golden diff empty) | open | |
| Builder-produced rotary job cuts like probe run 3 on the IQ (photo + capture) | open | |
| `desktop/` CI green: lint, types, import probe | open | |
| Upstream PRs opened (IQ fixes; builder parameters) | open | |
| G8, G13, G16 closed | open | |

### M1 Bench app: job format, trace, gate, CLI, bench window

- `gratisgraph-job` v1 spec and reader; trace operation; fixture transform; library schema and validators.
- Output gate with every rule in section 9 and a mutant per rule.
- CLI for every operation; gated send with the driver's IQ completion monitor.
- Bench window: open a job or pattern, parsed-back preview on the bed with fixture and part outlines, gate
  report with flag acknowledgement, send, live status, re-run.
- `PZ` sweep (G4) and stop behaviour (G10) on the bench.
- First real-world test: an asymmetric pattern (letter "F", an arrow and a datum crosshair) on scrap
  aluminum through the app (G15).

Exit criteria:

| Exit item | State | Evidence |
|---|---|---|
| 100 % of gate mutants rejected; 100 % of known-good corpus accepted | open | |
| Asymmetric test engraved in the previewed orientation and position (photo, measured offset) | open | |
| G4, G10, G15 closed | open | |
| Bench window runs offscreen in CI; packaged self-test stub passes | open | |

### M2 Tooling program and first dog tag

- Fill operation: hatch at recipe stepover and angle, optional contour pass, inward offset of half the tip
  width; regions too narrow for the tool are reported, never silently dropped.
- Test patterns: character-height ladder (both modes), stepover ladder, corner test, datum crosshair.
- Tag blank chosen and measured (G1); nest fixture built and its datum measured (G2).
- Tooling matrix on the blank (G3, G6, G7); job size limit (G9); repeatability over 10 tags (G11).
- Recipes for the tag in both modes promoted to confirmed, with minimum character height recorded (G5).
- First article: one dog tag in each mode, engraved from a hand-written job file through the bench window.

Exit criteria:

| Exit item | State | Evidence |
|---|---|---|
| Two confirmed recipes (trace, fill) for the chosen blank, with manual settings and minimum character height | open | |
| Fixture datum measured over 5 blanks with a stated tolerance | open | |
| 10-tag repeatability run logged (position and depth inspection) | open | |
| First-article tags (both modes) photographed and logged with gate reports | open | |
| G1, G2, G3, G5, G6, G9, G11 closed; G7 closed or deferred with reason | open | |

### M3 Operator app

- Shell first, then slices: queue (several jobs per green press, re-run last), setup card shown and confirmed
  before each load, job log, first-article prompt, watched-folder job source.
- Bench and operator modes. Operator mode: confirmed recipes only, jobs only from a job source, no ad hoc
  parameters. Both modes run the full gate; modes differ in which inputs are allowed, not in checking. Mode
  selection is a local setting, not access control (stated honestly in the UI and docs).

Exit criteria:

| Exit item | State | Evidence |
|---|---|---|
| Acceptance doc: every Must ID up to M3 traced to a test | open | |
| A staff member runs a 5-tag batch from a folder job using only the setup card and the app | open | |

### M4 External job interface

- Freeze `gratisgraph-job` v1; publish `desktop/docs/job-format.md` with example files and a validator
  command.
- Generic HTTP job source: pull by job id from a configured endpoint, station key in local config only.
- Multi-part nests (several tags per fixture load).
- Conformance fixtures any producer can test against.

Exit criteria:

| Exit item | State | Evidence |
|---|---|---|
| Format frozen; validator and conformance fixtures published | open | |
| An external producer's job runs end to end through the HTTP source (for SEM: see SEM-Configurator `docs/plan-engraving.md`) | open | |

### M5 Release hardening

- PyInstaller one-folder bundles for Kubuntu and Windows; Linux installer script that installs the udev rule
  (one sudo step); Windows guide reusing upstream `docs/WINDOWS_SETUP.md` for WinUSB.
- Packaged self-test; first-run setup (library location, machine check).
- Windows 10 LTSC acceptance on a real station (G12).

Exit criteria:

| Exit item | State | Evidence |
|---|---|---|
| Packaged app passes self-test on Kubuntu 24.04 and Windows 10 1809 | open | |
| 30 production days on Kubuntu with no gate escape or unexplained part | open | |

### M6 Post-v1

Point&Shoot placement (F23), Express and other family models (F24), tool life log (F25), batch tags from a
CSV, upstream offer of the job format.

## 8. Test strategy

- **Goldens.** Driver goldens (existing corpus) plus desktop goldens: job file + library snapshot to
  expected `.m20` bytes, recomputed on Linux and Windows in CI. Fixtures marked binary in `.gitattributes`.
- **Gate mutants.** One or more broken inputs per rule; known-good corpus accepted 100 %.
- **Property tests.** Gate decoder agrees with `gts_preview.py`; fill output stays inside the region
  offset by half the tip width; trace output equals input polylines after quantisation.
- **GUI.** pytest-qt offscreen; the preview and the SVG export draw the same list (test compares them).
- **Hardware.** Not in CI. Staged validation (section 10), each run logged with capture, photos and gate
  report.

## 9. Output gate

The gate decodes the final bytes with its own parser and judges them against the active machine, tool,
part, fixture and recipe entries. It never edits the job.

### 9.1 Hard rules (block)

| ID | Rule | Source | Mutant |
|---|---|---|---|
| H1 | Every position (pen down and rapid, integrated from deltas, including the return home) inside the machine work field | `machines/`, GTS_FORMAT §5.6 | One rapid 0.01 mm past the field edge |
| H2 | Header model code equals the target machine (at send: the connected machine's `!ID`) | GTS_FORMAT §5.2 | Job stamped 0x0204 for an IQ |
| H3 | Exactly one `JF`, and it is the final record | GTS_FORMAT §5.5 | Two `JF`; `JF` before the last stroke |
| H4 | Only opcodes on the machine's wire-confirmed allow-list | `machines/` | Job containing `TO` |
| H5 | Setup opcodes (`MC`, `VS`, `VZ`, `VD`, `PZ`) equal the selected recipe and lie within machine ranges | `recipes/`, `machines/` | `PZ` changed by 1 |
| H6 | `MC 1` present when the tool needs the spindle; absent when it must not spin | `tools/`, findings (spindle) | Rotary recipe with `MC 0` |
| H7 | Every pen-down point inside the part outline minus its keep-out margin, at the fixture position | `parts/`, `fixtures/` | One stroke 0.1 mm into the margin |
| H8 | No position inside a fixture keep-out (jaws) | `fixtures/` | Rapid through a jaw zone |
| H9 | Every stroke header (rapid) is preceded by `PU 1` or is the first stroke | GTS_FORMAT §5.4 to §5.6 | `PU 1` removed before a rapid |
| H10 | Decoded strokes equal the intended toolpath after quantisation | `build.py` intent vs decode | One delta altered by 1 unit |
| H11 | Job size under the measured machine limit (null until G9 closes; then hard) | G9 | Oversized fill |

### 9.2 Soft rules (flag)

| ID | Rule | Source | Mutant |
|---|---|---|---|
| S1 | Recipe status is draft | `recipes/` | Draft recipe |
| S2 | Character or feature height below the recipe's validated minimum | `recipes/`, G5 | Text 0.1 mm under minimum |
| S3 | Fill regions or features narrower than the tip width (left unengraved) | toolpath report | Hairline region |
| S4 | Fixture datum tolerance not yet measured | `fixtures/` | Fixture with null tolerance |
| S5 | Estimated run time over a configured limit | optimiser estimate | Long fill |

### 9.3 Report and binding

JSON and text report bound to the `.m20` SHA-256, the library entry ids and versions, and the app version.
The send path accepts only bytes with a passing report bound to those exact bytes. The report always prints
the residual state, even with zero flags, including: "Depth is set by hand: nose <fitted>, knob <n>
notches, pressure <p>. Software cannot verify these." The setup card repeats the same lines.

## 10. Real-world validation stages

Stages run in order; any error is a finding to take back to the desk, never something to retry in the
field. Logs and photos go in `desktop/docs/validation/`.

| Stage | Content | Milestone |
|---|---|---|
| V0 | Builder-produced rotary square vs probe run 3, tool reversed first, then real cut | M0 |
| V1 | Asymmetric orientation and position test on scrap aluminum | M1 |
| V2 | `PZ` sweep, stop behaviour | M1 |
| V3 | Tooling matrix and ladders on the tag blank | M2 |
| V4 | First-article tags, both modes; 10-tag repeatability | M2 |
| V5 | Staff-run batch from a folder job | M3 |
| V6 | External producer job end to end | M4 |
| V7 | 30 production days | M5 |

## 11. Risk register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Thin tag flexes or vibrates in the vise; chatter and uneven depth | High | High | Dedicated nest with full support under the tag (G2); nose-regulated depth |
| R2 | Manual depth settings differ between operators | Medium | High | Setup card per recipe; first-article check per batch; recipe records knob and pressure |
| R3 | Upstream declines or delays the driver changes | Medium | Medium | Keep changes small and default-preserving; fork carries them meanwhile; rebase each upstream release |
| R4 | GPL obligations reach a producer's code | Low | High | Interchange-only boundary (rule 9); no producer imports this code; confirm with counsel before M4 |
| R5 | Large fill jobs exceed a machine limit or run very long | Medium | Medium | G9 measurement; split jobs across the queue (one green runs the queue) |
| R6 | Shared driver changes break the Express | Low | High | Byte-identical defaults; goldens; upstream maintainer hardware check (G14) |
| R7 | A one-sample value (`PZ` units) becomes a hard limit | Medium | Medium | Rule 4; G4 before M1 exit |
| R8 | GUI work crowds out the tooling program | Medium | High | M1 bench window limited to F08; operator features wait for M3 |
| R9 | Windows 10 LTSC driver or Qt floor problems | Medium | Medium | Kubuntu first; G12 in M5; Qt minor capped for 1809 |
| R10 | Tool wear or breakage on aluminum fills | Medium | Medium | Recipe-level tool notes; F25 post-v1; inspect first article per batch |

## 12. Open questions

| Question | Recommended answer | Owner answer |
|---|---|---|
| Where does the desktop app live? | `desktop/` in the fork; shares CI and the golden corpus; never upstreamed | |
| Package and import names | Product "GratisGraph Desktop"; packages `ggdesk` and `ggdesk_app`; bundle `GratisGraphDesktop` | |
| Licence | GPL-3.0 (forced by the driver import) | |
| Python version | 3.12, upper bound below 3.14, confirm at M0 (G16) | |
| Fill geometry library | Shapely, if licence and wheels check out at M0; otherwise a small offsetting module with property tests | |
| Point&Shoot in v1? | No. Fixture-based placement first; Point&Shoot is M6 | |
| Linux packaging format | PyInstaller one-folder tarball with an install script (udev rule); `.deb` later if needed | |
| Operator mode protection | Local setting only, stated as such; no login in v1 | |
| Who verifies the Express for upstream PRs? | Upstream maintainer (G14) | |
| Dog tag blank supplier and finish | Owner to choose before M2 (G1) | |
