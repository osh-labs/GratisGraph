# V2: `PZ` sweep and stop behaviour

Status: ready to run. Not yet run. Stage V2 of the build plan (section 10); closes G4 (`PZ` units and
effect with the nose fitted) and G10 (what the panel stop and `!1B 0;` do mid-job on the IQ).

## Bottom line

Part A cuts the same 10 mm square at `PZ` 20, 50, 80 and 100 with the nose fitted, three times each, and
records the `!MZ` telemetry. If `PZ` is overtravel in 0.01 mm past the auto-ZRef touch (the run-3
[HYPOTHESIS]), `!MZ` during the cut should sit about 20, 50, 80 and 100 counts above the touch reading, and
the depth should change little because the knob sets the depth. Part B stops a longer job mid-run, once
with the panel stop and once with `!1B 0;` from the app, and records what the machine does. Until G4
closes, `PZ` values only enter the gate as exact recipe matches inside the observed range 0..100; no limit
depends on its unit.

## Jobs

All built with recipe `scrap-rotary-diamond-trace` (draft) and fixture `bare-bed`, part `bench-scrap-40`.
Sha256 and the exact regeneration command of each file are in `desktop/bench/MANIFEST.md`. Each report
passes with 2 flags (S1 draft recipe, S4 bare-bed tolerance): ack `I ACCEPT 2 FLAGS`. The bench override
`pz = N` is printed in each report's residual lines.

| File | Content | `PZ` |
|---|---|---|
| `desktop/bench/V2/v2-pz20.m20` | 10 mm square at machine X 45..55, Y 45..55 | 20 |
| `desktop/bench/V2/v2-pz50.m20` | same | 50 (run 3) |
| `desktop/bench/V2/v2-pz80.m20` | same | 80 |
| `desktop/bench/V2/v2-pz100.m20` | same | 100 |
| `desktop/bench/V2/v2-stop.m20` | 17 concentric squares, 2 to 34 mm, about 2 min at `VS 10` | 50 |

The four sweep files differ only in the `PZ` argument (and the report's sha256 binding).

## Machine setup

- Rotary diamond, regulating nose fitted, knob 5 notches, pressure 2. Do not touch the knob or pressure
  during the sweep: the point is to see what `PZ` alone does.
- Flat scrap, clamped; the four squares need separate places, so shift the stock 15 mm between `PZ`
  values (or use a fresh piece per value) and label each square with a marker.
- Panel stop within reach.

## Procedure

### A. `PZ` sweep (G4)

For each `N` in 20, 50, 80, 100, and for each repeat r in 1, 2, 3:

```sh
ggdesk send desktop/bench/V2/v2-pzN.m20 --report desktop/bench/V2/v2-pzN.gate.json \
    --job desktop/bench/V2/v2-square-10mm.ggj --ack "I ACCEPT 2 FLAGS" --operator <name> \
    --capture desktop/work/v2-pzN-rr.jsonl
```

Press green; let it finish. Repeat r = 2, 3 on the same square by pressing green again only if the
command has already returned (the machine re-runs the last job; that re-run is not logged by the app, so
prefer re-sending with the command above). After each run:

- from the capture file, the `!MZ` value just before the plunge (touch) and the steady value during the
  cut (the app does not interpret `!MZ`; read the `item` lines with axis `Z`, or `cmd` `!MZ`);
- the `!ET` value;
- depth by eye and, if available, groove depth with a depth gauge or by focus on a microscope.

### B. Stop behaviour (G10), tool reversed

B1, panel stop: send `v2-stop.m20` (same command form, `--capture desktop/work/v2-stop-panel.jsonl`), press
green, and press the panel stop about 30 s in. Record: does the head stop at once, lift, return home? What
packets arrive (capture file)? Does `ggdesk send` report `unconfirmed` (no `!ET`) or `completed`? Does a
second green press resume, restart or do nothing?

B2, `!1B 0;`: send `v2-stop.m20` again, press green, and about 30 s in press Ctrl-C in the terminal that
runs `ggdesk send`. The app sends `!1B 0;` and logs `aborted`. Record the same observations as B1.

## Pass criteria

| Item | Pass |
|---|---|
| Files | sha256 match the manifest |
| Sweep | 12 runs completed and logged, each with its capture file |
| G4 reading | For each `N`, the cut `!MZ` minus the touch `!MZ` is recorded for 3 repeats; the conclusion (units, effect on depth) is written below with its evidence tag |
| Stop | B1 and B2 observations recorded, including the app's reported status and the job log lines |

There is no numeric pass for G4: the stage passes when the measurement exists. A result that contradicts
the run-3 [HYPOTHESIS] (for example, `!MZ` not tracking `PZ`) is a finding for the desk.

## Log

### A. Sweep

| `PZ` | Run | Touch `!MZ` | Cut `!MZ` | Difference | `!ET` | Depth (eye / gauge) | Capture file |
|---|---|---|---|---|---|---|---|
| 20 | 1 | | | | | | |
| 20 | 2 | | | | | | |
| 20 | 3 | | | | | | |
| 50 | 1 | | | | | | |
| 50 | 2 | | | | | | |
| 50 | 3 | | | | | | |
| 80 | 1 | | | | | | |
| 80 | 2 | | | | | | |
| 80 | 3 | | | | | | |
| 100 | 1 | | | | | | |
| 100 | 2 | | | | | | |
| 100 | 3 | | | | | | |

Conclusion on `PZ` units and effect (with evidence tag):

### B. Stop

| Field | B1 panel stop | B2 `!1B 0;` |
|---|---|---|
| Date, operator | | |
| Seconds into the job | | |
| Head behaviour (stop, lift, home) | | |
| Spindle behaviour | | |
| Packets after the stop (capture) | | |
| `ggdesk send` status and exit code | | |
| Job log lines (event) | | |
| Second green press does | | |

Save the filled tables here and the capture files beside them. The integration PR then records G4 and G10
in the build plan gap register and, if `PZ` units are confirmed, retags the `PZ` lines in the library and
GTS_FORMAT.md with the new evidence.
