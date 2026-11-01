# M2 review: findings and disposition

Status: closed 2026-11-01. Both Major findings fixed; Minor findings fixed or answered below.

## Bottom line

An unanchored review subagent read the merged M2 diff (`df8406f..16a685c`, desktop/) with the code only and
the plans as reference, re-ran the suite, and re-ran the golden, fill and pattern tests on Shapely 2.1.2
(GEOS 3.13.1) as well as 2.2.0 (GEOS 3.14.1) with identical results. It found no Blocker: M2 opens no new
path to USB (`ggdesk pattern --build` and the GUI pattern panel end in the existing build -> gate ->
bound report -> `Runner` path), the Hershey port matches the TypeScript operation for operation, and
placeholders are labelled. It found two Major defects in how fill reports what it leaves unengraved, and
seven Minor items.

## Findings

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | Major | Narrow-region report re-expanded the offset area with a mitre buffer, which gives convex corners back exactly, so material a round tip cannot reach in acute corners (letter apexes, star points) was never reported (S3 silent) | Fixed: the report-only reach is a round buffer of the tool-centre area. Bytes unchanged (it does not feed the toolpath). `test_corners_are_not_narrow` replaced by `test_acute_corners_are_reported` (and right-angle corners stay below the 0.01 mm^2 sliver threshold), plus `test_wedge_tip_reported` (the review's 10 degree wedge) |
| 2 | Major | With the contour pass off, a component thinner than the stepover could fall between hatch lines: no path and no report | Fixed: without a contour pass only components a hatch line enters count as reached. `test_thin_region_between_hatch_lines_reported_without_contour` (the review's 0.28 mm strip) and a property test `test_every_region_is_cut_or_reported` |
| 3 | Minor | Quantising path end points (half to even, 0.01 mm) can move the tool edge up to about 0.007 mm past the tip/2 offset | Answered: inherent to the 0.01 mm machine unit and below it; the part keep-out margin (H7) is what protects the part edge, and it is checked on the quantised bytes. Recorded in the M2 acceptance known limits |
| 4 | Minor | The Hershey fixture was compared in CI but never regenerated from the TypeScript | Fixed: desktop CI job `hershey` runs `generate.mjs --check` with Node; the workflow now also triggers on `web/src/hershey.ts` and `web/app/fonts/**` |
| 5 | Minor | `tests/golden/TIES.md`, referenced by the fill module, did not exist | Fixed: created (empty table, rules for adding a tie) |
| 6 | Minor | The S3 width text comes from GEOS `maximum_inscribed_circle` and may differ between Shapely versions | Answered: report text only, never bytes; the bench package check pins the current text in CI, so a dependency bump that changes it shows up as a reviewed regeneration. The Shapely range stays `>=2.1,<2.3` (the reviewer found identical results on both ends) |
| 7 | Minor | Float fields in the pattern panel rounded typed input to the default's decimals | Fixed: float spin boxes use the maximum precision |
| 8 | Minor | `test_builds_and_passes_gate_without_h7` asserted no hard findings at all | Fixed: renamed `test_builds_and_passes_gate_with_no_hard_findings` |
| 9 | Minor | Gate report did not say the fill stepover is unmeasured when a bench override supplies it | Fixed: residual line "Not measured: fill stepover (G6): a bench override is in use (placeholder until V3 part C)." The two fill bench reports are regenerated for this line (bytes unchanged) |
