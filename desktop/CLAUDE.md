# CLAUDE.md (desktop/)

Guidance for AI agents and humans working on GratisGraph Desktop.

## What this is
**GratisGraph Desktop** (`desktop/` in the GratisGraph repository): a desktop app that runs Gravograph
M20-family rotary engravers from Kubuntu (first) and Windows 10 LTSC 1809+ (second). Python core +
PySide6. Its consequential output is the `.m20` job bytes sent to the machine.
Read [`docs/build-plan.md`](docs/build-plan.md) first; decisions are in [`docs/decisions.md`](docs/decisions.md).
The wire format is [`../docs/GTS_FORMAT.md`](../docs/GTS_FORMAT.md); research log [`../docs/PROTOCOL_FINDINGS.md`](../docs/PROTOCOL_FINDINGS.md).

## Non-negotiable constraints
1. **No job reaches the machine without passing the output gate** on its final bytes (build plan §9).
   No GUI override. The gate refuses; it never repairs. Only the gated send path writes to USB.
2. **Determinism.** Same job, library and recipe -> same bytes on Linux and Windows. Rounding and
   platform-sensitive maths only in `ggdesk.numerics` (half-to-even, docs/STROKE_SCHEMA.md).
3. **Golden files are the test.** Changing output for a reference case is intentional, explained in
   the commit, and updates the golden.
4. **Never claim machine behaviour that has not been observed.** Tag [CONFIRMED] / [STRONG] /
   [HYPOTHESIS]. A [HYPOTHESIS] value never sets a hard gate limit.
5. **Libraries are data** (TOML with provenance under `library/`). Unknown is `needs_measurement`.
6. **Qt never enters `src/ggdesk/`** (ruff TID251 + `tests/unit/test_qt_free_core.py`).
7. **Work field is a hard limit; fixture keep-outs are hard; recipe draft status is a soft flag.**
8. **Driver changes at the repository root stay small and upstreamable**: default output byte-identical
   for the Express, guarded by `../tests/golden/`. `desktop/` is never upstreamed.
9. **No producer-specific (e.g. SEM) URLs, credentials or product rules in this repository.**

## Layout
- `src/ggdesk/` Qt-free core (numerics, gts_read, cli; later formats, library, toolpath, gate, run).
- `src/ggdesk_app/` PySide6 shell.
- `tests/unit`, `tests/gui` (marker `gui`, offscreen).
- `docs/validation/` hardware stages: operator sheets and logs.

## Commands
```sh
desktop/tools/check.sh           # before each push
ggdesk inspect FILE.m20          # decode a job
```

## Working agreements
- Hardware runs are logged in `docs/validation/` with capture, photos and the job's sha256.
- Background anything slow; don't poll CI in the chat.
- `docs/decisions.md` is append-only (`merge=union`).
