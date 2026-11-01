# V4: first-article tags and 10-tag repeatability

Status: blocked on the tag blank (G1) and its nest (G2); the files for practice on scrap are ready. Not yet
run. Stage V4 of the build plan (section 10); measures the nest datum and tolerance (G2), repeatability (G11),
and produces the M2 first articles in both lettering modes.

## Bottom line

Once the blank is measured and a nest is cut from `ggdesk drawing nest`, this stage (A) measures where the nest
puts the blank by engraving a datum crosshair on 5 blanks, (B) engraves one first-article tag in each lettering
mode from a hand-written job file through the bench window, and (C) engraves 10 consecutive tags to measure
repeatability. Until G1 and G2 are recorded the gate refuses every job on `dog-tag-blank` / `dog-tag-nest`
(H7, H8): that is intended. The pre-built files under `desktop/bench/V4/` target `bare-bed` and
`bench-scrap-40` so the layouts and the flow can be rehearsed on scrap; they are not first articles.

## Files

| Part | File | Content | Recipe |
|---|---|---|---|
| A | `v4-datum-crosshair.m20` | `datum-crosshair` pattern | `scrap-rotary-diamond-trace` |
| B | `v4-first-article-trace.m20` | Hand-written job `v4-first-article-trace.ggj`: a generic two-line tag layout in single-line Hershey text | `scrap-rotary-diamond-trace` |
| B | `v4-first-article-fill.m20` | Hand-written job `v4-first-article-fill.ggj`: the same layout in filled Arimo text | `scrap-rotary-diamond-fill` + PLACEHOLDER `tip_width_mm`, `stepover_mm` |
| C | `v4-repeat-batch.m20` | `repeat-batch` pattern (`quantity` 10) | `scrap-rotary-diamond-trace` |

Sha256, flags and regeneration commands: `desktop/bench/MANIFEST.md`. The text on the first-article jobs is
placeholder layout text, not a product design: production text arrives as geometry from a producer.

## Before the stage

1. G1: measure 5 blanks and record `parts/dog-tag-blank` and `materials/tag-aluminum`
   (`measurements-needed.md`).
2. Choose the nest position, then draw and cut the nest. The nest origin is a design choice before it is a
   measurement, so record the chosen pocket position first (the drawing's default puts the pocket one plate
   margin from the plate's back-left datum corner) in `fixtures/dog-tag-nest` `nests.centre.origin_mm` with
   `confidence = "DEFINED"` and the drawing as its source. Then
   `ggdesk drawing nest --part dog-tag-blank --fixture dog-tag-nest -o desktop/work/nest` must report no
   UNMEASURED item; cut the plate from `nest.dxf`. Record the nest's keep-outs (clamps, lips) measured on the
   built nest. Part A then measures where the nest really puts the blank and replaces the DEFINED values with
   CONFIRMED ones.
3. V3 done: tip width, stepover and both minimum heights recorded.
4. Regenerate every V4 file against the tag: replace `--fixture bare-bed` with `--fixture dog-tag-nest` and
   the part with `dog-tag-blank` (`-p part=dog-tag-blank -p compact=true` for patterns; edit `"part"` in the two
   hand-written jobs), and drop the PLACEHOLDER `--set` values that V3 replaced with library values.

## Procedure

### A. Nest datum and tolerance (G2)

Engrave the datum crosshair on 5 blanks, reloading the nest each time. Measure each crosshair centre from the
blank outline (calipers or loupe scale). Datum correction = commanded - mean measured; tolerance = largest
deviation from the mean. Record both in `fixtures/dog-tag-nest` (`datum_mm` corrected, `tolerance_mm`), then
regenerate and re-send one crosshair to confirm it lands within the tolerance of the blank centre.

### B. First articles, both modes

In the bench window: open `v4-first-article-trace.ggj`, choose recipe and fixture, read the setup card, set the
machine as it says, check the preview against the blank, acknowledge the flags, Send. Repeat with
`v4-first-article-fill.ggj`. Photograph both; keep their gate reports with the log.

### C. Repeatability (G11)

Send `v4-repeat-batch.m20` 10 times, one blank per run, without touching the depth settings. For each tag
measure the crosshair offset from the blank centre (X, Y) and inspect depth by eye against tag 1.

## Pass criteria

| Item | Pass |
|---|---|
| A | 5 offsets recorded; datum and tolerance written to the library with this log as source |
| B | Both tags engraved in the previewed position, legible at the recipe's minimum height; photos and gate reports logged |
| C | 10 offsets recorded; spread within the nest tolerance; depth visually consistent |

When A to C pass, the two tag recipes can be created from the scrap recipes with the measured values and
promoted to `confirmed` (M2 exit item), in a PR that cites this log.

## Log

### A

| Blank | Offset X mm | Offset Y mm | Notes |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |
| Mean / max deviation | | | |

### B

| Mode | Date, operator | sha256 (first 12) | Flags acknowledged | Photo | Result |
|---|---|---|---|---|---|
| Trace | | | | | |
| Fill | | | | | |

### C

| Tag | Offset X mm | Offset Y mm | Depth vs tag 1 | `!ET` |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |
| 6 | | | | |
| 7 | | | | |
| 8 | | | | |
| 9 | | | | |
| 10 | | | | |
