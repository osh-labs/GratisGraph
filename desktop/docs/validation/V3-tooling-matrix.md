# V3: tooling matrix on the tag blank

Status: ready to run on scrap; on the tag blank once its outline is measured (G1). Not yet run. Stage V3 of
the build plan (section 10); measures G3 (tip width), G5 (minimum character height, both modes), G6 (fill
stepover), G7 (corner quality, close or defer) and G9 (job size limit).

## Bottom line

Six bench patterns, each built by the app and gated like any job, answer one tooling question each. Parts A to
C need nothing but the run-3 recipe; part D (filled lettering) uses the tip width from B and the stepover from
C, so its pre-built file carries PLACEHOLDER values and must be regenerated before cutting. Part E sends jobs
of increasing size with the tool reversed to find the largest the IQ accepts. Every pre-built file targets
`bare-bed` and `bench-scrap-40` (scrap at least 40 x 40 mm). On a tag blank, first record its outline (step 0),
then regenerate the files with `-p part=dog-tag-blank -p compact=true` so the gate checks them against the
real blank.

## Files

Pre-built under `desktop/bench/V3/`; sha256, flags and the exact regeneration command of each are in
`desktop/bench/MANIFEST.md`. Every report passes (no hard finding); acknowledge with the phrase the manifest
gives.

| Part | File | Pattern | Recipe | Measures |
|---|---|---|---|---|
| A | `v3-char-ladder-trace.m20` | `char-ladder-trace` | `scrap-rotary-diamond-trace` | G5 trace |
| B | `v3-line-width.m20` | `pz-square` | `scrap-rotary-diamond-trace` | G3 tip width |
| C | `v3-stepover-ladder.m20` | `stepover-ladder` | `scrap-rotary-diamond-trace` | G6 stepover |
| D | `v3-char-ladder-fill.m20` | `char-ladder-fill` | `scrap-rotary-diamond-fill` + PLACEHOLDER `tip_width_mm=0.2`, `stepover_mm=0.1` | G5 fill |
| E | `v3-job-size-<n>kb.m20` (16 and 64 KB committed; 256, 512, 1024 KB: run the manifest command, check the sha256) | `job-size-ladder` | `scrap-rotary-diamond-trace` | G9 |
| F | `v3-corner-test.m20` | `corner-test` | `scrap-rotary-diamond-trace` | G7 |

## Machine setup

As V1: rotary diamond, nose fitted, knob 5 notches, pressure 2 (the setup card in the bench window and the
first residual line of every report repeat this). Fresh scrap or a tag blank for each part, labelled. Run every
new file tool-reversed first; keep the panel stop within reach.

## Procedure

0. Tag blank only: measure 5 blanks (outline, corner radius, holes, thickness) and record them in
   `desktop/library/parts/dog-tag-blank.toml` and `materials/tag-aluminum.toml` as
   `measurements-needed.md` describes. Then regenerate each file below with
   `-p part=dog-tag-blank -p compact=true` added to its `ggdesk pattern` command (and `--set` values as
   noted), and hold the blank centred in the vise.
1. Part A, character-height ladder (trace). Send `v3-char-ladder-trace.m20`
   (`ggdesk send ... --ack "<phrase>" --capture desktop/work/v3-A.jsonl`). Three people read each row without
   magnification at arm's length. Record the smallest row everyone reads correctly. That height is the trace
   `min_char_height_mm` (G5).
2. Part B, line width. Send `v3-line-width.m20` (a 10 mm square). Measure the groove width at 3 points on
   each side with a loupe scale or microscope. Record the mean and range; the mean is the tool's
   `tip_width_mm` at these settings (G3).
3. Part C, stepover ladder. Send `v3-stepover-ladder.m20`. Inspect each square at arm's length and under the
   loupe. Record the largest stepover with no visible ridges between lines. That is the fill recipe's
   `stepover_mm` (G6).
4. Part D, character-height ladder (fill). Regenerate first with the measured values:
   ```sh
   ggdesk pattern char-ladder-fill -o desktop/work/v3-D.ggj --build --recipe scrap-rotary-diamond-fill \
       --fixture bare-bed --set tip_width_mm=<B mean> --set stepover_mm=<C value>
   ```
   Do not cut the pre-built PLACEHOLDER file. Read the rows as in part A; record the fill
   `min_char_height_mm` (G5). Note any narrow-region flags (S3) the report lists: those strokes are left
   unengraved by design.
5. Part E, job-size ladder, tool reversed. Send `v3-job-size-16kb.m20`, then 64, 256, 512 and 1024 KB, one at a
   time. For each, record whether the machine beeps and acknowledges (`!JF` in the capture), whether green runs
   it, `!ET`, and anything unusual. The largest accepted size, with margin, becomes `max_job_bytes` (G9);
   H11 then refuses larger jobs.
6. Part F, corner test. Send `v3-corner-test.m20`. Inspect each corner under the loupe for overshoot,
   rounding or chatter. If corners are clean, G7 is closed at `accel` 551. If not, record the defects: testing
   other `accel` values needs a driver change (G7 stays open, deferred with this evidence).

## Pass criteria

| Item | Pass |
|---|---|
| Files | sha256 match the manifest (or the regenerated file's report is attached to the log) |
| A, D | Minimum readable height recorded per mode, 3 readers |
| B | Groove width, 6 readings, mean and range |
| C | Chosen stepover with a photo of the ladder |
| E | Acceptance and `!ET` recorded for each size up to the first refusal or 1024 KB |
| F | Corner verdict with photos |

The stage passes when the measurements exist. Results go into the library as `measurements-needed.md`
describes; the recipes stay draft until V4 confirms them.

## Log

| Part | Date, operator | File sha256 (first 12) | `!ET` | Readings | Photos | Result |
|---|---|---|---|---|---|---|
| A | | | | Smallest readable height (3 readers): | | |
| B | | | | Groove width x6: | | |
| C | | | | Largest clean stepover: | | |
| D | | | | Tip, stepover used: ; smallest readable: | | |
| E 16 KB | | | | Beep / `!JF` / ran: | | |
| E 64 KB | | | | | | |
| E 256 KB | | | | | | |
| E 512 KB | | | | | | |
| E 1024 KB | | | | | | |
| F | | | | Corner defects (angle: description): | | |
