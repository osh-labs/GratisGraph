# Bench-day checklist

Status: ready. One page, in run order. Each stage's sheet has the detail and the log table.

## Before you start

- [ ] Station: Kubuntu, udev rule installed, repository on `main`, `pip install -e . -e desktop` done.
- [ ] `ggdesk version`, `ggdesk library validate` (0 errors), `python desktop/bench/make_bench.py` ("up to date").
- [ ] `python -m ggdesk_app.app --self-test` prints `self-test ok`.
- [ ] Rotary diamond, regulating nose, knob 5 notches, pressure 2. Scrap at least 40 x 40 mm. Calipers, loupe
      with scale, marker, camera. Tool can be fitted reversed.
- [ ] Panel stop within reach. Every new file runs tool-reversed first.

## Order

1. [ ] V0 `V0-builder-rotary.md`: builder rotary square vs probe run 3 (run A reversed, run B cut).
2. [ ] V1 `V1-asymmetric.md`: asymmetric "F" + arrows + crosshair; orientation and position (G15).
3. [ ] V2 `V2-pz-sweep-and-stop.md`: `PZ` 20/50/80/100 x3 with `--capture` (G4); panel stop and Ctrl-C
      (`!1B 0;`) mid-job, tool reversed (G10).
4. [ ] Stop here if V1 showed a mirrored or offset part, or V2 a stop that did not stop: bring it to the desk.
5. [ ] V3 `V3-tooling-matrix.md` on scrap (or on a measured tag blank): A trace ladder, B line width, C
      stepover ladder, D fill ladder (regenerate with B and C first), E job-size ladder (reversed), F corners.
6. [ ] Record V3 values in the library (`measurements-needed.md`, "How to record a value"); regenerate the
      bench package.
7. [ ] V4 `V4-first-article.md` once the blank is measured and the nest is cut: A nest datum (5 blanks), B first
      articles in both modes from the bench window, C 10-tag repeatability.

## Every send

`ggdesk send FILE.m20 --report FILE.gate.json --job FILE.ggj --ack "<phrase from the report>"
--operator <name> --capture desktop/work/<stage>-<run>.jsonl`. Check the sha256 against
`desktop/bench/MANIFEST.md` first. A refusal is a finding, never something to work around.

## After the day

- [ ] Fill in each sheet's log; save photos and capture files beside it.
- [ ] Commit logs, captures and any library updates in one PR per stage, citing the logs as sources.
