# M2 handoff report

Status: M1 and M2 software complete and merged to `main`, 2026-11-01. Bench package ready. Hardware stages V0
to V4 not yet run. Nothing blocked.

## Bottom line

GratisGraph Desktop can now take a `gratisgraph-job` file or a built-in bench pattern, turn it into trace or
fill toolpaths, place it through a fixture, build the `.m20` bytes, check them with an independent output gate
(H1 to H11 hard, S1 to S6 soft, report bound to the SHA-256), preview the decoded bytes, and send them through
the one gated path, from the CLI or the bench window. No machine was attached: every send-path test uses a fake
connection. Bench testing on the M20 IQ+ can start with the one-page checklist
`desktop/docs/validation/bench-day.md`: V0, V1, V2 on scrap now; V3 on scrap or a measured tag blank; V4 once
the blank is measured and a nest is cut from `ggdesk drawing nest`. Two unanchored reviews found no Blocker;
every Major finding is fixed. 79 decisions taken under delegated authority this session are logged for confirmation.

## 1. What was built

| Feature | What | PRs |
|---|---|---|
| Plans | `m1-plan.md`, `m2-plan.md` (contracts, slices, owner questions) | #7, #15 |
| F03 | `gratisgraph-job` v1 reader/writer, JSON Schema, spec `docs/job-format.md`, examples | #8 |
| F04 | Trace operation; ordering wrapper (driver optimiser, no merging; TSP up to 128 strokes) | #10, #20 |
| F05 | Part frame -> machine frame (Y flip), one quantisation; asymmetric golden locks orientation | #8, #10 |
| F06 | Output gate: independent decoder, H1 to H11, S1 to S5 (+ S6 from the M1 review), home-job check, residual lines, hash-bound report; record grammar and header checks | #12, #13, #14 |
| F06 | Gated send: `ggdesk.run.Runner` is the only caller of the driver's send; queue of one; completion on `!ET`; job log; abort (`!1B 0;`) | #9, #13, #14 |
| F07 | CLI: `check`, `build`, `preview`, `send` (re-gates from the report, `--capture`), `pattern`, `library validate`, `inspect`, `version`, `drawing nest` | #8 to #13, #19, #21 |
| F08 | Bench window: preview from decoded bytes (same draw list as SVG), gate report with typed acknowledgement, send/abort off the UI thread; M2 panels: patterns, recipe selector, library browser, setup card | #11, #13, #18 |
| F09 | Fill: Shapely, mitre inward offset tip/2, hatch at angle/stepover, contour pass, narrow regions reported (S3) | #20, #23 |
| F10 | Patterns: asymmetric, pz-square, datum-crosshair, char-ladder-trace, char-ladder-fill, stepover-ladder, corner-test, job-size-ladder, repeat-batch; bench text (Hershey port byte-identical to TS, Arimo outlines) | #17, #21 |
| F11 | Library schema, validators, seed library (m20-iq, rotary-diamond, materials, dog-tag-blank, dog-tag-nest, bench-scrap-40, bare-bed, scrap trace and fill recipes) | #8, #14, #16 |
| F13 (early) | Read-only setup card sharing the gate's manual-depth line | #16, #18 |
| F20 | Run-time estimate in every report (S5) | #8, #12 |
| G2 support | Parametric nest plate drawing, SVG and DXF R12, UNMEASURED placeholders | #19 |
| Integration | M1.Z #13, M1 review fixes #14, M2.Z #22, M2 review fixes #23, this report | |

Tests: 789 desktop tests (unit, GUI offscreen, goldens, gate mutants, property tests, bench package rebuild),
on Linux and Windows CI with Python 3.12 and 3.14, plus the root driver suite and TypeScript suite unchanged.
Traces: `docs/m1-acceptance.md`, `docs/m2-acceptance.md`.

## 2. Exit tables at the end of the session

### M1

| Exit item | State | Evidence |
|---|---|---|
| 100 % of gate mutants rejected; 100 % of known-good corpus accepted | met | #12, #13, #14; `m1-acceptance.md` section 2 |
| Asymmetric test engraved in the previewed orientation and position | open (Chris) | `validation/V1-asymmetric.md`, `desktop/bench/V1/` |
| G4, G10, G15 closed | open (Chris) | `validation/V1-asymmetric.md`, `validation/V2-pz-sweep-and-stop.md` |
| Bench window runs offscreen in CI; packaged self-test stub passes | met | #11, #13; desktop.yml GUI job |

### M2

| Exit item | State | Evidence |
|---|---|---|
| Two confirmed recipes (trace, fill) for the chosen blank | open (Chris) | `validation/V3-tooling-matrix.md`, `V4-first-article.md` |
| Fixture datum measured over 5 blanks with a stated tolerance | open (Chris) | `V4-first-article.md` part A |
| 10-tag repeatability run logged | open (Chris) | `V4-first-article.md` part C |
| First-article tags (both modes) photographed and logged with gate reports | open (Chris) | `V4-first-article.md` part B |
| G1, G2, G3, G5, G6, G9, G11 closed; G7 closed or deferred | open (Chris) | `validation/measurements-needed.md` |

The build plan's tables (`docs/build-plan.md` section 7) carry the same states; its gap register notes where the
software for each gap is ready.

## 3. Decisions taken

All in `desktop/docs/decisions.md` with Source `coding agent (owner to confirm)` (79 rows from this session;
7 earlier rows from M0 are also unconfirmed). The ones most worth confirming first:

| Topic | Decision (decisions.md) |
|---|---|
| Job format | `.ggj` JSON v1, draft until M4 |
| Part frame | Origin at engrave-area centre, +Y up as read; Y flip to the machine |
| Bench fixture and part | `bare-bed` (nest at work-field centre, DEFINED); `bench-scrap-40` (declared 40 x 40 mm, DEFINED) |
| Unmeasured geometry | Refused (H7/H8); unmeasured tolerance flags (S4) |
| Machine ranges | Hard ranges = documented envelope; values not yet run on the IQ flag S6 (`observed.*`) |
| Opcode allow-list | `DR MC VS VZ PZ DZ VD ZA PD PU JF`; `LB NR` reserved |
| Bench overrides | `--set` on draft recipes only, printed on every report; used for the `PZ` sweep and fill placeholders |
| Home job | The driver's home job is gated before every send |
| Ordering | Driver optimiser without merging; TSP only up to 128 strokes; bidirectional pass off |
| Fill | Shapely, mitre offsets; hatch 0 deg and contour on as DEFINED choices; stepover needs_measurement |
| Text | Hershey port held to TS by fixture (CI regenerates it); Arimo via fontTools; bench only |
| Dependencies | `shapely>=2.1,<2.3`, `fonttools>=4.50`, `fastjsonschema` (dev); licences and wheels checked |
| Nest | Drawing placeholders labelled UNMEASURED; nest origin recorded DEFINED before cutting, then measured |

## 4. Review findings and disposition

| Review | Blocker | Major | Minor | Record |
|---|---|---|---|---|
| M1 (unanchored, code only) | 0 | 4, all fixed (segment/header checks, record grammar, GUI runner missing the machine entry, ranges wider than observed -> S6) | 8: 7 fixed, 1 answered (fail-safe report mismatch across OSes at a margin boundary) | `docs/reviews/m1-review.md` |
| M2 (unanchored, code only) | 0 | 2, both fixed (fill narrow-region report missed acute corners; thin regions with contour off) | 7: 5 fixed, 2 answered (0.007 mm quantisation past tip/2; S3 width text depends on GEOS version) | `docs/reviews/m2-review.md` |

Found and fixed during integration rather than review: Windows CRLF checkouts changed library entry hashes and
bench report bytes (hashes now LF-normalised; LF pinned); the driver's 2-opt was too slow for fill and its
bidirectional pass un-snaked hatch lines (ordering wrapper); a GEOS `union_all` artefact in a property test.

## 5. Bench package

| Item | Where |
|---|---|
| One-page run order | `docs/validation/bench-day.md` |
| Operator sheets | `docs/validation/V0-builder-rotary.md`, `V1-asymmetric.md`, `V2-pz-sweep-and-stop.md`, `V3-tooling-matrix.md`, `V4-first-article.md` |
| Jobs, `.m20`, gate reports, previews | `desktop/bench/V1` to `V4` (20 jobs; the 3 largest job-size files by command and sha256 only) |
| sha256 and exact regeneration command per file | `desktop/bench/MANIFEST.md`; `python desktop/bench/make_bench.py` checks, `--write` regenerates |
| Unmeasured fields, gap, sheet, where to record | `docs/validation/measurements-needed.md` |
| Nest drawing | `ggdesk drawing nest --part dog-tag-blank --fixture dog-tag-nest -o OUT` (NOT FOR CUTTING until G1 is recorded) |

Every bench file targets `bare-bed` and `bench-scrap-40` and says so. Fill files carry PLACEHOLDER tip width
0.2 mm and stepover 0.1 mm, printed in their reports; V3 says to regenerate them with measured values.

## 6. Open gaps and what measures each

| Gap | Measured by | Recorded in |
|---|---|---|
| G1 blank | Calipers on 5 blanks (V3 step 0 / V4 setup) | `parts/dog-tag-blank`, `materials/tag-aluminum` |
| G2 nest datum | V4 part A (crosshair on 5 blanks) | `fixtures/dog-tag-nest` |
| G3 tip width | V3 part B | `tools/rotary-diamond` |
| G4 `PZ` units | V2 part A with `--capture` | GTS_FORMAT/PROTOCOL_FINDINGS tags; `observed.pz` |
| G5 minimum character height | V3 parts A and D | both recipes' `min_char_height_mm` (activates S2) |
| G6 stepover | V3 part C | fill recipe `stepover_mm` |
| G7 corners | V3 part F (close at accel 551 or defer) | build plan gap register |
| G9 job size | V3 part E, tool reversed | `machines/m20-iq` `max_job_bytes` (activates H11) |
| G10 stop behaviour | V2 part B | build plan gap register, operator procedure |
| G11 repeatability | V4 part C | build plan gap register |
| G15 frame | V1 | build plan gap register; `bare-bed` tolerance |
| G8 (hardware half) | V0 | build plan gap register |

## 7. Blocked

Nothing. No stop condition in the session brief was hit: no wire-format, driver-output or existing-golden
change was needed (root goldens and TS fixtures untouched); every dependency passed the licence and wheel
check; the plan did not contradict itself in scope or a gate rule; CI on `main` stayed green; no decision
needed the machine. One commit message on #13 contains a bullet describing a change that had already landed in
#12; a force-push to correct it was refused by the session's permissions, so it is noted in the PR body instead.

## 8. Recommended next session (M3 operator app)

1. Run the bench day (V0, V1, V2; V3 on scrap). Record results; update the library with each value in its own
   PR; regenerate the bench package. If V1 or V2 shows a finding, fix that before M3 code.
2. Confirm or change the decisions in section 3, especially the part frame, S6 and the bench overrides.
3. Write `m3-plan.md`: job queue (several jobs per green press, re-run last, F12), setup card confirmed before
   each load (F13), job log UI (F14), bench and operator modes (F15: operator mode allows confirmed recipes and
   job-source jobs only, no `--set`), watched-folder job source (F16), first-article prompt (F19).
4. Once G1 and G2 close: create the two tag recipes from the V3 values, run V4, promote them to `confirmed`.
5. Consider a driver option to send without re-stamping the model code (M1 review finding 5) as a small,
   default-preserving upstream PR.
