# Build prompt: GratisGraph Desktop M1 and M2, up to bench testing

Status: ready, 2026-11-01. Paste everything below the line into a new Claude Code cloud session on
`osh-labs/GratisGraph`. The session runs hands-off: it plans, builds with subagents, merges its own
green PRs, and stops when every software exit item of M1 and M2 is met and the bench package is
ready. Hardware stages are left for the owner.

---

You are the lead engineer for GratisGraph Desktop, working in `osh-labs/GratisGraph` (the `desktop/`
directory). I am Chris Lee, the owner. I am not available during this session. Build milestones M1 and
M2 of `desktop/docs/build-plan.md` up to the point where bench testing on the M20 IQ+ can start, using
subagents, and with no questions to me unless a stop condition in section 7 is hit.

## 1. Authority I am giving you for this session

- Create branches, commit, push, open PRs on `osh-labs/GratisGraph`, and **merge your own PRs into
  `main` once CI is green on the current head**. Use merge commits.
- Decide every owner question in the milestone plans yourself, using the defaults in section 5 where
  they apply and the build plan's recommended answers elsewhere. Log each one in
  `desktop/docs/decisions.md` with Source `coding agent (owner to confirm)`.
- Add Python dependencies to `desktop/pyproject.toml` if their licence is GPL-3.0-compatible and they
  have wheels for Linux x86_64 and Windows x64 on Python 3.12 to 3.14. Log each in decisions.md.
- Run subagents in parallel (worktree isolation) for independent slices; at most 4 at a time.

Not authorized: opening PRs or issues on any other repository (including upstream GratisGraph);
changing repository settings, secrets or branch protection; publishing releases or tags; anything
on `osh-labs/SEM-Configurator`.

## 2. Read first, in this order

1. `desktop/CLAUDE.md` (non-negotiables; they bind you and every subagent).
2. `desktop/docs/build-plan.md` (scope, feature IDs, gate rules, gaps, milestones, risks).
3. `desktop/docs/decisions.md`.
4. `docs/GTS_FORMAT.md` (wire format; normative), `docs/STROKE_SCHEMA.md` (rounding),
   `docs/PROTOCOL_FINDINGS.md` sections "M20 IQ Hardware Probes" and "Rotary diamond cut".
5. Code: `desktop/src/ggdesk/` (numerics, gts_read, cli), `desktop/src/ggdesk_app/app.py`,
   `gts_api.py` (`build_gts` with `mc`/`vz`/`vd`, `GTSConnection`, `send_gts`, `_monitor_job`),
   `gts_optimise.py`, `gts_preview.py`, `tests/test_gts_server.py` (its `FakeConn` pattern),
   `web/src/hershey.ts`, `web/src/ttf.ts`, `web/app/fonts/` (Hershey `futural.jhf`, OFL Arimo,
   MIT Open Gorton).
6. The desktop blueprint skill (`anthropic-skills:desktop-app-blueprint`), if available in this
   session: `references/architecture.md`, `references/build-process.md`,
   `references/agent-workflow.md`, `references/lessons.md`, and the milestone plan template.

## 3. Goal and finish line

Deliver M1 and M2 software. The session is finished when all of this is true:

1. Every M1 and M2 feature ID marked for those milestones in build plan section 3.3 is implemented
   and traced to tests in `desktop/docs/m1-acceptance.md` and `desktop/docs/m2-acceptance.md`.
2. Every software exit item of M1 and M2 is `met` with a PR or test link in the build plan's exit
   tables. Hardware exit items stay `open (Chris)` with a ready operator sheet.
3. The **bench package** exists (section 6) and is merged to `main`.
4. An unanchored review subagent has reviewed each milestone's merged diff, and its Blocker and Major
   findings are fixed or answered in `desktop/docs/reviews/`.
5. `desktop/docs/handoff/m2-report.md` is written and merged (section 8).
6. CI is green on `main`.

Do not try to close gaps that need the machine (G1 to G7, G9 to G11, G15). Build the software that
measures them, write the operator sheets, and leave the values `needs_measurement`.

## 4. Non-negotiables (repeat these to every subagent)

1. No job reaches USB without passing the output gate on its final bytes. The gate decodes with its
   own reader (`ggdesk.gts_read`, extend it), never the builder's state. Hard rules refuse; soft rules
   need typed acknowledgement repeating the count (`I ACCEPT 3 FLAGS`); no override; the gate never
   repairs. Only the gated send path may call the driver's send.
2. Determinism: same job + library + recipe gives the same bytes on Linux and Windows. All rounding
   and platform-sensitive maths through `ggdesk.numerics` (ruff bans the rest; a test bans `round(`).
3. Golden files are the test. Never regenerate a golden to make a test pass; an intended output
   change is explained in the commit.
4. Never invent physical values. Library values come from the sources in build plan section 1 with
   evidence tags, or are `null` with `needs_measurement = true` and a `measure = [...]` procedure.
   A [HYPOTHESIS] value (e.g. `PZ` units) never sets a hard limit.
5. Qt never enters `src/ggdesk/`.
6. Root driver modules (`gts_*.py`, `web/`) change only if unavoidable, in a separate small PR whose
   default output is byte-identical (all goldens and TS fixtures unchanged). Prefer wrapping in the
   core.
7. Never skip, disable, xfail or weaken a test to get green. Never push an empty commit to re-run CI.
8. No producer-specific (SEM) names, URLs, credentials or product rules anywhere in this repository.
   The dog tag is a generic "dog tag blank" part.
9. No machine is attached to this session. Never attempt USB access. Every send-path test uses a
   fake connection.

## 5. Decisions made in advance (log each in decisions.md when you rely on it)

| Topic | Decision |
|---|---|
| Job file | Extension `.ggj`, JSON, `"format": "gratisgraph-job"`, `"version": 1`, units mm, per build plan 6.3. Spec in `desktop/docs/job-format.md` with a JSON Schema in `desktop/src/ggdesk/formats/job.schema.json` and example files. Version 1 is draft until M4 freezes it |
| Part frame | Origin at the centre of the part's engrave area; +X right and +Y up as the operator reads the finished part. The fixture entry maps part frame to machine frame (machine +Y points toward the operator, so the map includes a Y flip). An asymmetric golden ("F" plus an arrow) locks the orientation (lesson: symmetric tests hide mirrored axes) |
| Bench frame | Patterns may target a built-in fixture `bare-bed`: datum = machine home, identity map apart from the Y flip, keep-outs entered per job. This is the only fixture usable before G2 is measured |
| Unmeasured geometry | A job whose part or fixture has `needs_measurement` geometry that the gate needs (outline, datum, keep-outs) is refused (hard). Unmeasured tolerance only flags (S4) |
| Seed library | `machines/m20-iq.toml` from build plan section 1; `tools/rotary-diamond.toml`; `recipes/scrap-rotary-diamond-trace.toml` from probe run 3 (draft); `parts/dog-tag-blank.toml` and `fixtures/dog-tag-nest.toml` with all geometry `needs_measurement`; `fixtures/bare-bed.toml`. Test-only parts and fixtures live under `desktop/tests/fixtures/library/`, never in the seed library |
| Opcode allow-list (H4) | Wire-confirmed on the IQ only: `DR MC VS VZ PZ DZ VD ZA PD PU JF` (+ `LB NR` reserved, not emitted in M1/M2) |
| Fill geometry | Shapely 2.x (BSD-3) if it passes the licence and wheel check; otherwise a small polygon-offset module with property tests. Hatch at recipe angle and stepover, optional contour pass, inward offset of half the tip width; regions narrower than the tool are reported (S3), never dropped silently |
| Single-line text | Python port of `web/src/hershey.ts` reading `web/app/fonts/futural.jhf`, held byte-for-byte to the TS output by a conformance fixture generated from TS. Bench patterns only |
| Filled text for ladders | Glyph outlines from the bundled OFL Arimo via fontTools (MIT), bench patterns only. Production text arrives as geometry from producers |
| Ordering | The driver's `gts_optimise.optimise_strokes`, wrapped; no new optimiser |
| GUI | One main window. M1: bench window (F08). M2 adds a pattern panel, recipe selector, read-only library browser and the setup card. Theme colours in `ggdesk_app/theme.py` only. GUI tests offscreen |
| Send path | `ggdesk.run` wraps `GTSConnection`; one queue item in M1; completion from the driver's IQ monitor; job log as JSON lines in the user data directory. Tests use a `FakeConn` like `tests/test_gts_server.py` |
| Fixture drawing (M2) | Parametric nest plate drawing (SVG and DXF) from the tag blank and fixture entries, so the owner can cut a nest once the blank is measured; rendered with placeholder dimensions clearly marked `UNMEASURED` until then |
| CLI | `ggdesk check | build | preview | send | pattern | library validate | inspect | version`. `send` refuses without a passing gate report bound to the file's sha256 |

## 6. Bench package (the M2 hand-off to the owner)

Merged under `desktop/docs/validation/` and `desktop/bench/`:

- Operator sheets V1 (asymmetric orientation and position), V2 (`PZ` sweep 20/50/80/100 with `!MZ`
  capture, ×3; stop-button and `!1B 0;` behaviour mid-job), V3 (tooling matrix on the tag blank:
  character-height ladders both modes, stepover ladder, corner test, job-size ladder), V4 (first-article
  tags both modes; 10-tag repeatability). Each with procedure, pass criteria and a log table, in the
  style of `V0-builder-rotary.md`.
- For every sheet, the generated `.ggj` and `.m20` files, each `.m20` with its gate report and
  sha256, and the exact `ggdesk` command that regenerates it. Files that depend on unmeasured
  geometry are generated against `bare-bed` and say so.
- `desktop/docs/validation/measurements-needed.md`: every `needs_measurement` field in the seed
  library, its gap ID, the sheet that measures it, and where to record the value.
- A one-page bench-day checklist in the order the stages should run (V0, V1, V2, then V3 and V4 once
  the blank and nest exist).

## 7. Stop conditions (the only reasons to stop early)

Stop and write the handoff report (section 8) with the question in section "Blocked" if:

1. A change to the wire format, the driver's default output, or any existing golden seems necessary.
2. A needed dependency fails the licence or wheel check and there is no reasonable alternative.
3. The build plan contradicts itself in a way that changes scope or a gate rule.
4. CI on `main` is red for a reason you cannot fix within this repository after two attempts.
5. A decision can only be made by observing the machine.

Anything else: decide, log it, continue. If one slice is blocked, finish the others first.

## 8. Handoff report

`desktop/docs/handoff/m2-report.md`, opening with `Status:` and `Bottom line`, then: what was built
(by feature ID, with PRs); exit tables as of the end; decisions taken (links to decisions.md rows);
review findings and their disposition; bench package contents; open gaps and what measures each;
blocked items, if any, with the exact question; recommended next session (M3). Your final message in
the session is a short summary of the same, with the report's path.

## 9. How to run the work

### Phase 0: orientation (you, no subagents)

1. `python -m pip install -e . -e "desktop[dev,gui]" pytest-qt`; install Qt runtime libraries
   (`libegl1 libxkbcommon0 libfontconfig1 libdbus-1-3`) if missing; `QT_QPA_PLATFORM=offscreen`.
   Run `desktop/tools/check.sh --all`, the root `pytest`, and `npm test` in `web/` to confirm green.
2. Write `desktop/docs/m1-plan.md` from the blueprint's milestone template: principles table,
   components and contracts (exact module names, dataclasses, function signatures), CI changes, slice
   table with owned files and allowed shared-file hooks, merge order, owner questions answered from
   section 5. Merge it as a docs PR before any code.

### Phase 1: M1

- **M1.0 contracts (you, serial, one PR):** `ggdesk/model/` dataclasses; `ggdesk/formats/job.py` +
  schema + `docs/job-format.md` + examples; `ggdesk/library/` loader and validators + seed entries;
  `ggdesk/gate/` rule interface, finding and report types (no rules yet); CLI subcommand stubs that
  exit with "not implemented in this build" until their slice lands; `ggdesk_app` extension points
  (`extensions.py`, `session.py`).
- **Wave 2 (parallel subagents, one PR each):**
  - M1.1 toolpath and build: trace op, fixture transform, ordering wrapper, `build.py` (job + recipe ->
    strokes -> `build_gts` -> bytes), goldens for job -> bytes including the asymmetric case.
  - M1.2 gate: rules H1 to H10 (H11 present, inactive while the limit is null), S1 to S5, residual
    status lines, report bound to sha256 and library versions, one mutant per rule, known-good corpus
    accepted 100 %.
  - M1.3 run: gated send, queue of one, completion, job log, `FakeConn` tests including refusal of
    unreported or mismatched bytes.
  - M1.4 bench window: preview drawn from decoded bytes (one draw list shared with SVG preview, with a
    test comparing them), part and fixture outlines, gate report panel with typed acknowledgement,
    send and status wired to `ggdesk.run` (fake in tests).
- **M1.Z integration (you):** wiring, `m1-acceptance.md`, exit table, V1 and V2 sheets and their
  generated jobs, unanchored review subagent, fixes. Status lines change only here.

### Phase 2: M2

- Write and merge `desktop/docs/m2-plan.md` first.
- **M2.0 contracts (you):** fill op interface, pattern interface, recipe schema additions (stepover,
  hatch angle, contour pass, minimum character height, manual settings), tag part and fixture
  entries (unmeasured).
- **Wave 2 (parallel):**
  - M2.1 fill: hatch, contour, inward offset, narrow-region report; property tests (output inside the
    region offset by half the tip width; no stroke outside the part keep-out).
  - M2.2 single-line text: Hershey port with TS conformance fixture.
  - M2.3 test patterns: character-height ladders (trace and fill), stepover ladder, corner test, datum
    crosshair, repeatability batch, job-size ladder; each emits a `.ggj` and builds through the gate.
  - M2.4 GUI: pattern panel, recipe selector, read-only library browser, setup card (manual settings
    and the residual "depth is set by hand" lines).
  - M2.5 fixture drawing: parametric nest plate SVG/DXF, marked `UNMEASURED` until G1/G2 close.
- **M2.Z integration (you):** `m2-acceptance.md`, exit table, bench package (section 6), review,
  handoff report.

### Subagent brief (use for every slice)

Give each subagent: the slice goal and feature IDs; the files it owns and the only shared-file hooks
it may add; the contracts from M*.0 it builds on (paths); the non-negotiables in section 4 verbatim;
"run `desktop/tools/check.sh` before every push; open one PR from the latest `main`; do not merge;
report the PR number, what was tested, and any decision you took that is not in the plan". Use
worktree isolation. Verify each returned PR yourself (read the diff, run the check) before merging.

### PR and CI rules

- One PR per slice, from the latest `main`. Merge `main` into a PR only on a conflict or a CI failure
  caused by `main`.
- Subscribe to each PR's activity and wait for CI events; do not poll. When CI is red, reproduce the
  failing test locally, fix, run the check, push once.
- Merge as soon as a PR is green and you have verified it. Unsubscribe after merging.
- `desktop/docs/decisions.md` is append-only (`merge=union`). Slices never edit status lines, exit
  tables or acceptance docs; integration PRs do.
- Commit messages explain why; any golden change says why it is intended.
