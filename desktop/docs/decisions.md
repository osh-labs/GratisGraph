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
