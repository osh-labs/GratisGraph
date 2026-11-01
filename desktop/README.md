# GratisGraph Desktop

A desktop application for Gravograph M20-family rotary engravers, built on the
GratisGraph driver in this repository. It takes 2D geometry in a documented job
format, turns it into toolpaths for a tool, material and fixture, checks the
final machine bytes with an independent output gate, previews exactly what will
be sent, queues jobs and runs the machine.

Status: M0 (foundation). Read [`docs/build-plan.md`](docs/build-plan.md) for
scope and milestones and [`docs/decisions.md`](docs/decisions.md) for decisions.
Kubuntu Linux first, Windows 10 LTSC (1809) and newer second.

## Development setup

From the repository root:

```sh
python3 -m pip install -e . -e "desktop[dev]"   # driver + core
python3 -m pip install -e "desktop[gui]" pytest-qt   # GUI (PySide6)
desktop/tools/check.sh
```

Linux needs the Qt runtime libraries for the GUI (`libegl1 libxkbcommon0
libfontconfig1`) and the GratisGraph udev rule for unprivileged USB access.

## Commands (M0)

```sh
ggdesk version
ggdesk inspect job.m20      # decode a job: setup opcodes, strokes, extent, JF, sha256
ggdesk-gui                  # shell window (bench window arrives in M1)
```

## Licence

GPL-3.0-or-later, as the rest of GratisGraph. Gravograph, Gravotech and
Gravostyle are trademarks of Gravotech Group; this project is not affiliated
with or endorsed by Gravotech.
