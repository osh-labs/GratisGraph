# M1 review: findings and disposition

Status: closed 2026-11-01. Every Blocker and Major finding is fixed; Minor findings are fixed or answered
below.

## Bottom line

An unanchored review subagent read the merged M1 diff (`c947a5c..3fd7eca`, desktop/) with the code only
and the build plan as reference, and ran a probe script that edited golden bytes against the gate. It
found no Blocker: on every traced path, bytes reach the driver's `send_gts` only through
`Runner.send_gated` after the binding, pass, acknowledgement, model-code and home-job checks. It found
four Major issues (two gate rules looser than the wire format allows, the GUI send path refusing every
send, and machine ranges wider than what the IQ has run) and eight Minor ones. Fixes landed in the M1.Z
integration PR (#13) and the review-fix PR that adds this document.

## Findings

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | Major | Gate passed segments with `pw1`, `pw2` or `accel` other than 1, 1, 551, and header metadata bytes other than the model code | Fixed (#13): H9 refuses any segment field other than the observed 1, 1, 551; H3 compares all 94 header bytes with the GTS_FORMAT 5.2 template, model code aside. Mutants `test_h9_segment_field_not_observed_value`, `test_h3_header_byte_changed` |
| 1a | Major (part of 1) | A segment whose `pw1` is -3 begins with `FF FD` and is read as a command, so record boundaries shift | Answered: the builder never emits such a segment (H9 now requires `pw1 = 1` on every segment it does decode), and a shifted stream must then also pass H4 (allow-list), the new record grammar (finding 2), H5 and H10 (exact strokes equal to the job's intent) to be sent. No constructible job passes all of them; the machine's own parser behaviour on such bytes is unobserved and not needed |
| 2 | Major | Stray `PU n` between strokes and `JF n` with a non-zero argument passed | Fixed: H9 checks the full motion-record grammar of GTS_FORMAT 5.1/5.5 (`(rapid+, ZA 1, PD 0, segment+, PU 0, PU 0, PU 1)*`, `rapid+`, `JF`); H3 requires `JF 0`. Mutants `test_h9_stray_structural_record` (3 cases), `test_h3_jf_argument` |
| 3 | Major | Every GUI send refused: the default runner factory did not pass the machine entry; the cached runner would keep its first machine | Fixed: #13 passes the machine and the operator; this PR sets `runner.machine` from each report's selection on every send. Tests `test_gui_session_sends_through_the_real_runner`, `test_session_runner_follows_the_reports_machine` (real Runner, fake connection) |
| 4 | Major | Machine ranges (`PZ` to 100, `DZ` from 100, `VS` to 40) are wider than what the IQ has run | Fixed: the machine entry gains `observed.*` (values actually run on the IQ: VS 10..25, VZ 5..25, PZ 5..50, DZ 500, VD 15, MC 0..1, all CONFIRMED with references). New soft rule S6 flags a setup value inside the hard range but outside the observed one, so the operator must acknowledge running an untried value. Hard ranges stay (they are the documented scale; the V2 sweep needs PZ 80 and 100). Mutants `test_s6_value_not_run_on_this_machine` (5 cases) |
| 5 | Minor | The driver re-reads the model code at stamp time; a late `!ID` could change the header between check and send | Fixed: the Runner snapshots the code and, if it changed during the send, logs an error and reports `unconfirmed` instead of `completed` (`test_model_code_change_during_send_is_not_completed`). A driver option to skip re-stamping would close it fully; not taken (root module change for a case not expected with one machine) |
| 6 | Minor | The Runner could stay "in flight" if the log write raised or Ctrl-C hit the settle wait | Fixed: `try/finally` clears the flag (`test_in_flight_cleared_when_the_log_fails`) |
| 7 | Minor | GUI sends logged no operator | Fixed in #13 |
| 8 | Minor | Dead fallback to `joblog.open_connection` | Fixed: removed |
| 9 | Minor | Invalid library entries hidden in the GUI | Fixed: the bench session's status line lists them (`test_session_reports_invalid_library_entries`) |
| 10 | Minor | Decoder test name overstated its coverage | Fixed: renamed `test_decoder_refuses_truncation_and_non_ascii_opcodes`; the wider coverage is in the H3/H9 mutants above |
| 11 | Minor | The send-path guard test was a regex easy to bypass | Fixed: `test_no_other_path_to_the_device` walks the AST of every core and GUI module: no attribute, name or exact string naming a driver write method outside `run.py`, and no `usb` import or `dev.write` anywhere |
| 12 | Minor | Rounded-corner outline vertices use libm angles, so a gate finding at a margin boundary could differ by OS, and `ggdesk send` then refuses a report made on the other OS | Answered: fails safe (the send refuses; bytes are unaffected). Reports are re-checked on the station that sends. Revisit if the tag outline has rounded corners and reports are moved between OSes |

The reviewer also confirmed the part-to-machine transform (x+, y- with the Y flip), keep-outs in machine
axes, the preview's +Y-down convention, rounding only in `numerics.py`, and the gate's independence from
the builder.
