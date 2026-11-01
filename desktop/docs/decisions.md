# GratisGraph Desktop decisions log

Append-only. One line per row. A supersession is a new row; the old row gets an italic
"(Superseded YYYY-MM-DD: ...)" note in a docs-only PR. `.gitattributes`: `desktop/docs/decisions.md merge=union`.

| Date | Decision | Source |
|------|----------|--------|
| 2026-11-01 | Build GratisGraph Desktop in the GratisGraph fork, with generic branding (public repo). | Chris |
| 2026-11-01 | Target platforms: Kubuntu Linux first; Windows 10 LTSC (1809) and newer second. macOS not targeted in v1. | Chris |
| 2026-11-01 | First reference article: aluminum dog tag, in both lettering modes (single-line trace and filled). Minimum character height to be measured in M2. | Chris |
| 2026-11-01 | Users: owner (bench) and shop staff (operator). | Chris |
| 2026-11-01 | M20 IQ driver fixes go to upstream GratisGraph. | Chris |
| 2026-11-01 | Stack: Python + PySide6 (Qt LTS) + PyInstaller one-folder, per the desktop blueprint; exact versions confirmed at M0. | coding agent (owner to confirm) |
| 2026-11-01 | Split of responsibility: producers (e.g. a product configurator) own layout, fonts and text; the app owns toolpaths, recipes, fixtures and the gate. Interface is the gratisgraph-job format only. | Chris (direction); coding agent (detail, owner to confirm) |
| 2026-11-01 | The desktop app owns the USB connection directly through the driver; it does not run beside the tray or local server. | coding agent (owner to confirm) |
| 2026-11-01 | No user extension SDK in v1 (blueprint rule 7 dropped: no user-written generators are planned). | coding agent (owner to confirm) |
| 2026-11-01 | Stack pin: Python >=3.12,<3.15 (CI on 3.12 and 3.14); PySide6 >=6.11,<6.12. Qt 6.11 (patched to 6.11.3) lists Windows 10 1809; Qt 6.12 is the last series with Windows 10 support, so the pin may move to 6.12 but no further while Windows 10 LTSC is a target; wheels need glibc 2.34 (Kubuntu 24.04 has 2.39). Whether 6.11 is an LTS was not confirmed. Source: PyPI PySide6 metadata; doc.qt.io/qt-6.11/windows.html. | coding agent (owner to confirm) |
| 2026-11-01 | Driver packaged by a root pyproject.toml (flat modules unchanged); desktop depends on it as `gratisgraph`. | coding agent (owner to confirm) |
| 2026-11-01 | Builder depth names: `pz`/`dz` are canonical; `depth`/`lift` (which set DZ/PZ) kept as deprecated aliases with their old mapping so existing callers get the same bytes. | coding agent (owner to confirm) |
| 2026-11-01 | Rotary job layout: `MC 1` in setup, `VD` after `DZ` when given, `MC 0` before the return home; this is the byte layout of probe run 3. | coding agent, from the 2026-10-29 bench run |
| 2026-11-01 | No Claude session-start hook for desktop/: hooks load from the repository root, which is upstream territory. Setup steps live in desktop/README.md. | coding agent (owner to confirm) |
