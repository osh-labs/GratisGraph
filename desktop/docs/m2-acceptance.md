# M2 acceptance: tooling program software and bench package

Status: software complete 2026-11-01; hardware stages V3 and V4 ready, not yet run (owner). V4 waits on the tag
blank (G1) and its nest (G2).

## Bottom line

Every M2 feature (F09 fill, F10 test patterns, F11 library values as far as they can be known without the
machine) is implemented and traced to tests below, plus the M2 additions from the owner's brief: bench text,
the setup card, the bench-window panels and the parametric nest drawing. The bench package (operator sheets
V1 to V4, generated jobs with gate reports and regeneration commands, the measurements-needed list and the
bench-day checklist) is under `desktop/docs/validation/` and `desktop/bench/`. Every M2 exit item in the build
plan is a hardware result and stays `open (Chris)` with its sheet.

All paths are under `desktop/`. PRs: #15 plan, #16 M2.0 contracts, #20 M2.1 fill (with the ordering fix),
#17 M2.2 text, #21 M2.3 patterns, #18 M2.4 GUI panels, #19 M2.5 nest drawing, M2.Z integration (this
document's PR), and the M2 review-fix PR (`docs/reviews/m2-review.md`).

## 1. Feature trace

| ID | Feature | Code | Tests |
|---|---|---|---|
| F09 | Fill: hatch at recipe stepover and angle, optional contour pass, inward offset of half the tip width; narrow regions reported | `src/ggdesk/toolpath/fill.py`, FillOp branch of `build.py` | `tests/unit/test_fill.py` (offsets, hatch positions and directions, contour first, narrow and vanishing regions, invalid regions, determinism, speed), `test_fill_properties.py` (hypothesis: points tip/2 inside, footprint inside the region, spacing = stepover, vertex-order independence), `test_fill_build.py` (fill jobs pass the gate with no hard finding; S3 from narrow regions; G3/G6 refusals; overrides), fill goldens `fill_square_hole`, `fill_hatch45`, `fill_narrow` |
| F09 | Ordering that scales to fill jobs | `src/ggdesk/toolpath/order.py` | `test_toolpath_order.py::test_large_jobs_order_fast_and_keep_the_multiset`, `::test_parallel_lines_snake_below_the_limit` |
| F10 | Test patterns: character-height ladders (trace, fill), stepover ladder, corner test, datum crosshair, repeatability batch, job-size ladder (plus `asymmetric`, `pz-square`) | `src/ggdesk/patterns/builtin.py`, `_layout.py`, `commands/pattern.py` | `tests/unit/test_patterns.py` (every pattern builds and passes the hard rules, default and compact; fits its area; determinism; job and `.m20` goldens; geometry checks; job-size within 5 %), `test_patterns_cli.py` (`--list`, `--build` identical to `build` + `preview`) |
| F10 | Bench text (Hershey port byte-identical to TS; Arimo filled outlines) | `src/ggdesk/text/hershey.py`, `text/outline.py` | `test_text_hershey.py` (78 TS conformance cases incl. exact 0.005 mm ties), `test_text_outline.py` (holes, regions, validity, flattening bound, cap height) |
| F11 | Library values: tag blank, tag material, nest (all `needs_measurement`), fill recipe on scrap (draft), machine `observed` ranges | `desktop/library/` | `test_library.py`, `test_m2_contracts.py::test_fill_recipe`, `test_measurements_doc.py` (every unmeasured fact listed in `validation/measurements-needed.md`) |
| F13 (early, read-only) | Setup card sharing the gate's manual-depth line | `src/ggdesk/setupcard.py`, `gate/residual.py` | `test_m2_contracts.py::test_setup_card_repeats_the_gate_line`, `tests/gui/test_m2_setup_card.py` (equals the gate report's first residual line on real builds) |
| F08 additions | Pattern panel, recipe selector, read-only library browser, setup card panel | `src/ggdesk_app/panels/{patterns,recipe,library,setup_card}.py`, `session.py` | `tests/gui/test_m2_patterns.py`, `test_m2_recipe.py`, `test_m2_library.py`, `test_m2_setup_card.py` |
| (G2 support) | Parametric nest plate drawing, SVG and DXF R12, UNMEASURED placeholders | `src/ggdesk/drawings/nest.py`, `commands/drawing.py` | `tests/unit/test_drawing_nest.py` (DXF read back, placeholders listed, NOT FOR CUTTING title, measured case clean) |
| Bench package | Generated jobs, gate reports, previews, manifest | `desktop/bench/make_bench.py`, `desktop/bench/` | `test_bench_package.py` (rebuilds every file on Linux and Windows CI; every report passes and is bound) |

## 2. Exit criteria (build plan section 7, M2)

| Exit item | State | Evidence |
|---|---|---|
| Two confirmed recipes (trace, fill) for the chosen blank, with manual settings and minimum character height | open (Chris) | Measured by `validation/V3-tooling-matrix.md`; promoted after `V4-first-article.md` |
| Fixture datum measured over 5 blanks with a stated tolerance | open (Chris) | `V4-first-article.md` part A; nest from `ggdesk drawing nest` |
| 10-tag repeatability run logged (position and depth inspection) | open (Chris) | `V4-first-article.md` part C; `desktop/bench/V4/v4-repeat-batch.m20` |
| First-article tags (both modes) photographed and logged with gate reports | open (Chris) | `V4-first-article.md` part B; rehearsal files `desktop/bench/V4/v4-first-article-{trace,fill}.m20` |
| G1, G2, G3, G5, G6, G9, G11 closed; G7 closed or deferred with reason | open (Chris) | `validation/measurements-needed.md` maps each gap to its sheet and library field |

Software delivered for these items: met (sections 1 and 3; CI green on `main`).

## 3. Bench package

| Item | Where |
|---|---|
| Operator sheets | `docs/validation/V1-asymmetric.md`, `V2-pz-sweep-and-stop.md`, `V3-tooling-matrix.md`, `V4-first-article.md` (and V0 from M0) |
| Jobs, `.m20`, gate reports (`.gate.json`, `.gate.txt`), SVG previews | `desktop/bench/V1` to `V4` |
| sha256 and the exact regeneration command per file | `desktop/bench/MANIFEST.md` (job-size files above 64 KB: sha256 and command only, not committed) |
| Every `needs_measurement` field, its gap, the sheet that measures it, where to record it | `docs/validation/measurements-needed.md` |
| Bench-day order | `docs/validation/bench-day.md` |

All bench files target `bare-bed` and `bench-scrap-40` because the tag blank and nest are unmeasured, and
say so in the manifest and sheets. Fill files carry PLACEHOLDER tip width 0.2 mm and stepover 0.1 mm as
bench overrides, printed in their gate reports; the V3 sheet regenerates them with measured values before
cutting.

## 4. Known limits carried forward

- G7 alternatives (`accel` other than 551) need a driver change; deferred unless V3 part F shows defects.
- The nest origin is a design choice recorded DEFINED before cutting, then measured in V4 part A.
- Ordering above 128 strokes keeps the toolpath order (no TSP); patterns and fill emit sensible orders.
- Fill end points are quantised to 0.01 mm after the tip/2 offset, so the tool edge may pass the region edge by up to
  about 0.007 mm; the part margin (H7, on the bytes) protects the part (M2 review, finding 3).
- The M2 review (`docs/reviews/m2-review.md`) found no Blocker; its two Majors (fill narrow-region reporting) are fixed.
