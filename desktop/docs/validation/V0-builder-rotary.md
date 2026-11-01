# V0: builder-produced rotary job on the M20 IQ+

Status: ready to run. Not yet run. Stage V0 of the build plan (section 10), closes the hardware half of
gap G8.

## Bottom line

The normal job path (`gts_ctl.py` → `gts_prepare.from_file` → `build_gts`) now produces rotary jobs. In
software it already produces the exact bytes `gts_probe.py` sent for the clean rotary diamond cut on
2026-10-29 (run 3): same 244 bytes, sha256 below. This stage confirms on the machine that the job sent
through the normal path behaves the same. Two runs: tool reversed first, then a real cut on the same
scrap as run 3.

## Job

| Item | Value |
|---|---|
| Input | `desktop/docs/validation/v0_square_10mm.gc` (10 mm square, machine X 45 to 55, Y 45 to 55 mm) |
| Setup | `DR 0, MC 1, VS 10, VZ 5, PZ 50, DZ 500`; `MC 0` before the return home |
| Bytes before send | 244, sha256 `dfcbb6a078912ce18355faaf6a4748d2eb9aeda63a12bc8ffc0f49da56ed0a07` |
| Same as | `gts_probe.py pz --value 50 --speed 10 --vz 5` (run 3), checked by `tests/test_rotary_params.py` |

The driver writes the IQ's model code (0x020D) at header offset 0x24 when it sends, so the bytes on the
wire differ from the file at that one field only.

## Machine setup (as run 3 ended)

- Rotary diamond in the cutter, regulating nose fitted.
- Depth knob 5 notches, nose pressure 2.
- Same scrap stock as run 3, clamped in the vise. The square sits about the vise centre.
- Hands clear; panel stop within reach.

## Procedure

From the repository root on the station (Kubuntu, udev rule installed, driver from `main`):

1. Build and check the file:
   ```sh
   mkdir -p desktop/work
   python3 gts_ctl.py desktop/docs/validation/v0_square_10mm.gc desktop/work/v0.m20 \
       --speed 10 --pz 50 --vz 5 --mc 1
   ggdesk inspect desktop/work/v0.m20
   ```
   The sha256 must match the table above, and the setup line must read
   `DR 0 MC 1 VS 10 VZ 5 PZ 50 DZ 500`. If either differs, stop.
2. Run A, tool reversed (blunt end down), stock in place:
   ```sh
   python3 gts_ctl.py desktop/docs/validation/v0_square_10mm.gc \
       --speed 10 --pz 50 --vz 5 --mc 1 --send --verbose 2>&1 | tee desktop/work/v0-runA.log
   ```
   The home job and the square queue (beeps). Press green. Record: spindle off during the rapid out,
   on while the tool is down on the square, off for the return home; the `!ET` value; whether the
   command reported completion on `!ET`.
3. Run B, tool the right way round: repeat step 2 with `v0-runB.log`. Inspect the cut against run 3.

## Pass criteria

| Item | Pass |
|---|---|
| File | sha256 and setup line as above |
| Queue | Job beeps on receipt; runs on green |
| Spindle | On only while the tool is down (run A) |
| Cut | Clean 10 mm square, depth by eye comparable to run 3 (run B) |
| Position | Square at the same place as run 3 on the stock |
| Completion | Driver reports done on `!ET`, not early |

Any failure is a finding to bring back to the desk, not something to retry with changed settings.

## Log

| Field | Run A | Run B |
|---|---|---|
| Date, operator | | |
| Station OS, driver commit | | |
| sha256 checked | | |
| Spindle behaviour | | |
| `!ET` | | |
| Completion reported on `!ET` | | |
| Cut quality vs run 3 | n/a | |
| Photos (file names) | | |
| Result (pass / finding) | | |

Save the filled table here, with photos alongside as `V0-runB-*.jpg`, and the two logs.
