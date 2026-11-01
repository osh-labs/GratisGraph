# M1 acceptance: bench app

Status: software complete 2026-11-01; hardware stages V1 and V2 ready, not yet run (owner).

## Bottom line

Every M1 feature (F03 to F08, F11 schema, F20) is implemented and traced to tests below. The gate has all
rules H1 to H11 and S1 to S5, each with at least the mutant named in build plan section 9, and accepts its
known-good corpus 100 %. The bench window builds, gates, previews the decoded bytes and sends through the
same gated path as the CLI; every send-path test uses a fake connection. Hardware exit items (asymmetric
test, G4, G10, G15) wait on the operator sheets V1 and V2.

All paths are under `desktop/`. PRs: #7 plan, #8 M1.0 contracts, #10 M1.1 build, #12 M1.2 gate, #9 M1.3
run, #11 M1.4 bench window, M1.Z integration (this document's PR).

## 1. Feature trace

| ID | Feature | Code | Tests |
|---|---|---|---|
| F03 | Job format reader/writer (`gratisgraph-job` v1) | `src/ggdesk/formats/job.py`, `formats/job.schema.json`, `docs/job-format.md`, `docs/examples/` | `tests/unit/test_job_format.py` (examples round-trip and match the schema; 16 malformed documents rejected with their JSON path; unknown keys kept; deterministic output) |
| F04 | Trace operation | `src/ggdesk/toolpath/trace.py`, `toolpath/order.py` | `test_toolpath_trace.py`, `test_toolpath_order.py` (ordering only reorders/reverses, never merges), `test_build.py`, goldens in `tests/golden/` via `test_build_golden.py` |
| F05 | Fixture transform, part to machine | `src/ggdesk/model/geometry.py` (`Placement`), `toolpath/transform.py`, `library/model.py` (`Fixture.placement`) | `test_toolpath_transform.py` (Y flip; one quantisation per point, half to even; property test), orientation lock in `test_build_golden.py` (F top at smaller machine Y; crosshair at (50.00, 50.00); +Y tip at (62.00, 45.00)), `test_library.py::test_resolve_bare_bed` |
| F06 | Output gate with hash-bound report | `src/ggdesk/gate/` (`rules_hard.py`, `rules_soft.py`, `geometry.py`, `home.py`, `residual.py`, `types.py`), `gts_read.py` | `test_gate_mutants.py` (section 2), `test_gate_corpus.py`, `test_gate_decoder.py` (agrees with `gts_preview.parse_gts`, property test), `test_gate_geometry.py`, `test_gate_home.py`, `test_gate_independence.py` (no builder imports), `test_gate_contract.py` (binding, ack phrase, residual lines, no timestamp) |
| F06 | Only the gated path sends | `src/ggdesk/run.py` | `test_run.py::test_only_run_py_calls_the_driver_send`, every refusal case in `test_run.py`, `test_send_cmd.py` (stale, edited or unbound reports refused), `test_m1_end_to_end.py` |
| F07 | CLI for every core operation | `src/ggdesk/cli.py`, `commands/{build,check,send,preview,library}.py` | `test_build_cli.py`, `test_gate_check_command.py`, `test_send_cmd.py`, `test_render.py::test_cli_preview_*`, `test_commands_stub.py`, `test_cli.py`, `test_m1_end_to_end.py::test_build_check_send` |
| F08 | Bench window | `src/ggdesk_app/bench.py`, `panels/`, `workers.py`, `theme.py`, `session.py`, `render/` | `tests/gui/test_bench.py` (preview equals draw list equals SVG; Send enabled only by the exact phrase; no override control; worker debounce, stale results dropped, errors visible; send off the UI thread; abort), `test_render.py`, `test_m1_end_to_end.py::test_gui_session_sends_through_the_real_runner`, `tests/gui/test_shell.py::test_self_test` |
| F11 | Library schema and validators (values in M2) | `src/ggdesk/library/`, `desktop/library/` | `test_library.py` (seed and test overlay valid; gap and procedure required; [HYPOTHESIS] refused in hard limits; invalid entries listed, not skipped; user override by id; overrides on draft recipes only) |
| F20 | Estimated run time | `gate/__init__.py` (`_estimate`), `build.py` | `test_gate_contract.py::test_estimate_present`, `test_gate_mutants.py::test_s5_*`, `test_build.py` (estimate) |

## 2. Gate rules and mutants

Each mutant test asserts that exactly its rule fires (`tests/unit/test_gate_mutants.py`).

| Rule | Build plan mutant | Tests |
|---|---|---|
| H1 work field | Rapid 0.01 mm past the edge | `test_h1_rapid_past_field_edge`, `test_h1_rapid_past_origin`, `test_h1_field_edges_inclusive` |
| H2 model code | Job stamped 0x0204 for an IQ | `test_h2_express_code_for_iq`, `test_h2_connected_machine_differs` |
| H3 framing, single final JF | Two JF; JF before the last stroke | `test_h3_two_jf`, `test_h3_jf_before_last_stroke`, `test_h3_no_jf`, `test_h3_header_byte_changed`, `test_h3_job_does_not_return_home` |
| H4 opcode allow-list | Job containing `TO` | `test_h4_opcode_not_allowed` (TO, OU, LB, NR) |
| H5 setup equals recipe, ranges | `PZ` changed by 1 | `test_h5_pz_changed_by_one`, `test_h5_segment_speed_differs`, `test_h5_mc0_before_return_missing`, `test_h5_speed_change_mid_job`, `test_h5_vd_*`, `test_h5_value_outside_machine_range` |
| H6 spindle matches tool | Rotary recipe with `MC 0` | `test_h6_rotary_recipe_with_mc0`, `test_h6_drag_tool_with_mc1` |
| H7 part outline minus margin | Stroke 0.1 mm into the margin | `test_h7_stroke_into_margin`, boundary tests both sides, hole, rounded corner, `test_h7_unmeasured_part`, `test_h7_h8_unmeasured_fixture` |
| H8 fixture keep-outs | Rapid through a jaw zone | `test_h8_rapid_through_clamp`, `test_h8_keep_out_edge`, `test_h8_per_job_keep_out`, `test_h8_home_rapid_through_jaws` |
| H9 PU 1 before rapids, block shape, segment fields | `PU 1` removed | `test_h9_pu1_removed_before_rapid`, `test_h9_za_removed`, `test_h9_pu1_replaced_by_pu0`, `test_h9_segment_field_not_observed_value` |
| H10 decoded equals intent | One delta altered by 1 unit | `test_h10_one_delta_altered`, `test_h10_no_intent`, `test_h10_stroke_missing_and_extra`, `test_h10_reversed_stroke_accepted` |
| H11 job size | Oversized job (inactive while G9 open) | `test_h11_inactive_while_unmeasured`, `test_h11_oversized` |
| S1 draft recipe | Draft recipe | `test_s1_draft_recipe` |
| S2 character height | 0.1 mm under minimum | `test_s2_char_height`, `test_s2_unknown_minimum_is_residual_only` |
| S3 narrow regions | Hairline region | `test_s3_one_flag_per_narrow_region` (fill produces them in M2) |
| S4 fixture tolerance | Null tolerance | `test_s4_fixture_tolerance_unknown` |
| S5 run time | Long job | `test_s5_long_fill`, `test_s5_limit_boundary` |
| Home job | Driver's fixed home job | `tests/unit/test_gate_home.py` |
| Decode | Unexplained bytes | `test_gate_contract.py::test_decode_failure_is_hard`, `test_gts_read.py` |

Known-good corpus: `tests/unit/test_gate_corpus.py` (9 jobs, 100 % accepted with no hard findings), the
desktop goldens and every bench file (`test_bench_package.py`). The 16 root golden Express jobs are refused
for the IQ (H2), as intended.

## 3. Exit criteria (build plan section 7, M1)

| Exit item | State | Evidence |
|---|---|---|
| 100 % of gate mutants rejected; 100 % of known-good corpus accepted | met | `test_gate_mutants.py`, `test_gate_corpus.py`, `test_bench_package.py`; CI on Linux and Windows (PRs #12 and M1.Z) |
| Asymmetric test engraved in the previewed orientation and position (photo, measured offset) | open (Chris) | Operator sheet `docs/validation/V1-asymmetric.md`; files `desktop/bench/V1/` |
| G4, G10, G15 closed | open (Chris) | Sheets V1 (G15) and V2 (G4, G10, `docs/validation/V2-pz-sweep-and-stop.md`); `ggdesk send --capture` records the `!MZ` telemetry V2 needs |
| Bench window runs offscreen in CI; packaged self-test stub passes | met | `tests/gui/test_bench.py` in the GUI CI job; `python -m ggdesk_app.app --self-test` (library, build, gate, window; no USB) in the same job |

## 4. Known limits carried forward

- The vise jaws are not modelled on `bare-bed`; V1 and V2 start tool-reversed so the operator can watch
  clearance. Per-job keep-outs (`--keep-out`) exist for when the jaw positions are measured.
- Run-time estimate uses the driver's Express-characterised motion model (`gts_optimise`); not measured on
  the IQ.
- The job log records sends made by the app only; a green-press re-run on the machine panel is not logged.
