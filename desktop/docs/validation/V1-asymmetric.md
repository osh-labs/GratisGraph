# V1: asymmetric orientation and position test on scrap

Status: ready to run. Not yet run. Stage V1 of the build plan (section 10); closes G15 (machine frame vs
fixture frame, including the Y direction) and gives the first measurement of the `bare-bed` placement
error (fixture tolerance, gate rule S4).

## Bottom line

One trace job through the whole app path (job file -> build -> gate -> send) engraves an "F", a +X arrow,
a +Y arrow and a crosshair on scrap. If the machine frame matches the documented frame, the F reads
correctly from the operator's side, the +X arrow points to the operator's right, the +Y arrow points away
from the operator, and the crosshair centre sits at machine (50, 50) mm. A mirrored or offset part shows
immediately because the pattern has no symmetry. Two runs: tool reversed (no cut) first, then a real cut.

## Job

| Item | Value |
|---|---|
| Job | `desktop/bench/V1/v1-asymmetric.ggj` (part `bench-scrap-40`, part frame, mm) |
| Bytes | `desktop/bench/V1/v1-asymmetric.m20`, 622 bytes, sha256 in `desktop/bench/MANIFEST.md` |
| Gate report | `v1-asymmetric.gate.txt` / `.gate.json`: PASS, 2 flags (S1 draft recipe, S4 bare-bed tolerance unmeasured); ack `I ACCEPT 2 FLAGS` |
| Preview | `v1-asymmetric.svg` (drawn from the decoded bytes; screen +Y down = toward the operator) |
| Recipe | `scrap-rotary-diamond-trace` (probe run 3: `MC 1`, `VS 10`, `VZ 5`, `PZ 50`, `DZ 500`), draft |
| Fixture | `bare-bed`: part origin at machine (50, 50) mm; vise jaws not modelled |
| Regenerate | `ggdesk build desktop/bench/V1/v1-asymmetric.ggj -o desktop/bench/V1/v1-asymmetric.m20 --recipe scrap-rotary-diamond-trace --fixture bare-bed` |

Expected machine positions (mm, machine frame: X right, Y toward the operator):

| Feature | Part frame | Machine frame |
|---|---|---|
| Crosshair centre | (0, 0) | (50.00, 50.00) |
| F stem, top end | (-14, 14) | (36.00, 36.00) |
| F stem, bottom end | (-14, 2) | (36.00, 48.00) |
| F top bar, right end | (-8, 14) | (42.00, 36.00) |
| +X arrow tip | (8, -10) | (58.00, 60.00) |
| +Y arrow tip | (12, 5) | (62.00, 45.00) |

So, seen from the operator's position: F at the upper left (toward the gantry), its bars pointing right;
+X arrow below the crosshair (toward the operator) pointing right; +Y arrow at the right pointing away from
the operator.

## Machine setup

- Rotary diamond, regulating nose fitted, knob 5 notches, pressure 2 (as run 3; the gate report's first
  residual line repeats this).
- Scrap aluminum at least 40 x 40 mm, clamped in the vise with its centre near the vise centre. Mark the
  stock's top edge (away from you) with a marker line before clamping.
- Panel stop within reach. The `bare-bed` fixture does not know where the jaws are: watch run A.

## Procedure

From the repository root on the station (Kubuntu, udev rule installed, `main` checked out):

1. Check the files and the gate:
   ```sh
   ggdesk inspect desktop/bench/V1/v1-asymmetric.m20
   ggdesk check desktop/bench/V1/v1-asymmetric.ggj desktop/bench/V1/v1-asymmetric.m20 \
       --recipe scrap-rotary-diamond-trace --fixture bare-bed
   ```
   The sha256 must match `desktop/bench/MANIFEST.md`; the check must print `PASS`. Open
   `v1-asymmetric.svg` and keep it beside the machine.
2. Run A, tool reversed (blunt end down):
   ```sh
   ggdesk send desktop/bench/V1/v1-asymmetric.m20 --report desktop/bench/V1/v1-asymmetric.gate.json \
       --job desktop/bench/V1/v1-asymmetric.ggj --ack "I ACCEPT 2 FLAGS" --operator <name> \
       --capture desktop/work/v1-runA.jsonl
   ```
   Press green. Watch the head trace the F first or last (the optimiser chooses the order), and confirm by
   eye: F at upper left, +X arrow at the front pointing right, +Y arrow at the right pointing away. The head
   must stay clear of the jaws. Record the `!ET` the command prints.
3. Run B, tool the right way round: repeat step 2 (`--capture desktop/work/v1-runB.jsonl`). Do not move the
   stock between runs.
4. Measure the cut (calipers, or a loupe with a scale):
   - distance crosshair centre to +X arrow tip, along X and along Y (expected 8.00 and 10.00 mm);
   - distance crosshair centre to +Y arrow tip (expected 12.00 and 5.00 mm);
   - F stem length (expected 12.00 mm);
   - crosshair centre from the vise's fixed jaw face and from the left stock edge (record; this is the
     first `bare-bed` placement reading, not a pass/fail value).
5. Photograph the stock from the operator's position with the marked top edge visible.

## Pass criteria

| Item | Pass |
|---|---|
| File | sha256 matches the manifest; `ggdesk check` prints PASS |
| Orientation (run A and B) | As in the expected-position table: no mirror in X or Y |
| Scale | Each measured distance within 0.10 mm of expected |
| Clearance | Head clear of the jaws in run A |
| Completion | `ggdesk send` reports `completed (!ET n)`; the job log has `sent` then `completed` |

A mirrored or offset result is a finding to bring back to the desk (it would mean the Y flip in the part
frame decision or the bed frame in GTS_FORMAT.md 1 is wrong). Do not retry with changed settings.

## Log

| Field | Run A | Run B |
|---|---|---|
| Date, operator | | |
| Station OS, `main` commit, `ggdesk version` | | |
| sha256 checked | | |
| Orientation as expected (F, +X, +Y) | | |
| Head clear of jaws | | n/a |
| `!ET`, completion reported | | |
| Crosshair to +X tip (X, Y) mm | n/a | |
| Crosshair to +Y tip (X, Y) mm | n/a | |
| F stem length mm | n/a | |
| Crosshair from fixed jaw / left edge mm | n/a | |
| Capture file | | |
| Photos (file names) | | |
| Result (pass / finding) | | |

Save the filled table here, photos as `V1-runB-*.jpg`, and the capture files beside them. Then record the
outcome against G15 in the build plan's gap register (integration PR) and, if the placement readings over
3 pieces are available, the `bare-bed` `tolerance_mm` in a user-library override with the readings as its
source.
