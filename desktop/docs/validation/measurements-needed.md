# Measurements needed

Status: current for the seed library at the end of M2 software (2026-11-01). A unit test
(`tests/unit/test_measurements_doc.py`) fails if a `needs_measurement` fact in `desktop/library/` is missing
from the table below, so this list cannot fall behind the library.

## Bottom line

21 library facts are `needs_measurement`. Nine block jobs on the tag (the blank outline, holes and margin;
the nest datum, origin and keep-outs): until they are measured the gate refuses any tag job (H7/H8), and the
bench runs on scrap with `bare-bed` and `bench-scrap-40`. The rest are flags or recipe values the V1 to V4
sheets measure. Nothing here may be filled in from a catalogue guess: each value comes from the sheet's
procedure, with the log entry as its source.

## How to record a value

1. Fill in the sheet's log table (`desktop/docs/validation/V*.md`) with the readings, photos and files.
2. Change the fact in the library entry from `null = true` / `needs_measurement = true` to
   `value = ...`, `src = "<a [sources] key pointing at the filled log>"`, `ref = "<sheet, run, table row>"`,
   `confidence = "CONFIRMED"` (measured on our machine and parts), and bump the entry's `version`.
3. Commit the entry and the log together in one PR (`desktop/library/` for shared facts; a user-library
   override only for station-specific values). `ggdesk library validate` must pass, and every bench file whose
   gate report lists that entry must be regenerated with `python desktop/bench/make_bench.py --write`, with the
   reason in the commit message.

## Table

| Entry | Field | Gap | Measured by | Effect while unmeasured |
|---|---|---|---|---|
| `machines/m20-iq` | `max_job_bytes` | G9 | V3 part E, job-size ladder (tool reversed) | H11 inactive (residual line) |
| `tools/rotary-diamond` | `tip_width_mm` | G3 | V3 part B, line-width measurement | Fill builds need `--set tip_width_mm=` (placeholder) |
| `recipes/scrap-rotary-diamond-trace` | `min_char_height_mm` | G5 | V3 part A, character-height ladder (trace) | S2 inactive (residual line) |
| `recipes/scrap-rotary-diamond-fill` | `min_char_height_mm` | G5 | V3 part D, character-height ladder (fill) | S2 inactive (residual line) |
| `recipes/scrap-rotary-diamond-fill` | `stepover_mm` | G6 | V3 part C, stepover ladder | Fill builds need `--set stepover_mm=` (placeholder) |
| `fixtures/bare-bed` | `tolerance_mm` | G15 | V1 step 4 (placement readings over 3 pieces) | S4 flag on every bench job |
| `fixtures/dog-tag-nest` | `datum_mm` | G2 | V4 part A, datum crosshair on 5 blanks | Tag jobs refused (H7) |
| `fixtures/dog-tag-nest` | `nests.centre.origin_mm` | G2 | Nest drawing (`ggdesk drawing nest`) + V4 part A | Tag jobs refused (H7) |
| `fixtures/dog-tag-nest` | `keep_outs` | G2 | Calipers on the built nest (V4 part A setup) | Tag jobs refused (H8) |
| `fixtures/dog-tag-nest` | `tolerance_mm` | G2 | V4 part A, spread of the 5 crosshair offsets | S4 flag |
| `parts/dog-tag-blank` | `outline` | G1 | Calipers on 5 blanks (V4 part A setup) | Tag jobs refused (H7); nest drawing marked UNMEASURED |
| `parts/dog-tag-blank` | `holes` | G1 | Calipers on 5 blanks | Tag jobs refused (H7); nest drawing marked UNMEASURED |
| `parts/dog-tag-blank` | `keep_out_margin_mm` | G1 | Rolled-edge / nest-lip distance plus the V4 tolerance | Tag jobs refused (H7) |
| `parts/dog-tag-blank` | `thickness_mm` | G1 | Calipers on 5 blanks | None in the gate; recorded for the recipe |
| `parts/bench-scrap-40` | `thickness_mm` | G1 | Calipers on the scrap, each bench day | None in the gate |
| `materials/tag-aluminum` | `alloy` | G1 | Supplier specification sheet | None in the gate |
| `materials/tag-aluminum` | `finish` | G1 | Supplier + by eye on 5 blanks | None in the gate |
| `materials/tag-aluminum` | `thickness_mm` | G1 | Calipers on 5 blanks | None in the gate |
| `materials/scrap-aluminum` | `alloy` | G1 | Only if the stock is identified | None in the gate |
| `materials/scrap-aluminum` | `finish` | G1 | By eye, each bench day | None in the gate |
| `materials/scrap-aluminum` | `thickness_mm` | G1 | Calipers, each bench day | None in the gate |

## Not library facts, but measured on the bench

| Item | Gap | Sheet | Where it goes |
|---|---|---|---|
| `PZ` units and effect with the nose | G4 | V2 part A | GTS_FORMAT.md 5.3 and PROTOCOL_FINDINGS.md evidence tags; `observed.pz` in `machines/m20-iq` |
| Panel stop and `!1B 0;` behaviour mid-job | G10 | V2 part B | Operator procedure; build plan gap register |
| Machine frame vs part frame (orientation) | G15 | V1 | Build plan gap register |
| Corner quality at `accel` 551 | G7 | V3 part F | Build plan gap register (close, or defer with reason) |
| Repeatability over 10 tags | G11 | V4 part C | Build plan gap register |
| Values run on the IQ (`observed.*`) | - | V2, V3 | `machines/m20-iq` `observed.*` ranges (S6) |
