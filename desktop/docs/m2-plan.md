# M2 plan: tooling program software and the bench package

Status: approved for build 2026-11-01 (owner questions answered by the coding agent under delegated
authority; owner to confirm). Not started.

## Bottom line

M2's software half delivers what the owner needs to run the tooling program on the M20 IQ+: the fill
operation (F09), single-line and filled bench text, the test-pattern generator (F10), library values
for the tag and its fixture as `needs_measurement` entries (F11 values part), a pattern panel, recipe
selector, read-only library browser and setup card in the bench window, and a parametric nest-plate
drawing. It ends with the bench package (operator sheets V1 to V4 with generated jobs, gate reports and
regeneration commands, the measurements-needed list and a bench-day checklist). The hardware exit items
(confirmed recipes, fixture datum, repeatability, first articles, gaps G1 to G3, G5 to G7, G9, G11) are
owner work on the machine; the software measures them and the sheets say how. One contracts PR (M2.0),
four parallel slices (M2.1 fill, M2.2 text, M2.4 GUI, M2.5 fixture drawing), one dependent slice (M2.3
patterns, after M2.1 and M2.2), and one integration PR (M2.Z).

## 1. Principles carried into M2

| Non-negotiable | How M2 keeps it |
|---|---|
| Output gate on final bytes | Fill and pattern jobs go through the same `build` -> `run_gate` -> `Runner` path. Fill adds intent (strokes and narrow regions) only; the gate rules do not change except that S3 now receives data. |
| Determinism | Fill geometry through Shapely with mitre joins only (no trig in offsets); hatch angles through `numerics.cos_sin_deg` (exact at multiples of 45 degrees); one quantisation per point. Fill goldens run on Linux and Windows CI; any reviewed per-OS tie goes in `tests/golden/TIES.md`, never a silent regeneration. |
| Goldens are the test | New desktop goldens: a fill case, a Hershey text case, a filled-text case, and one per pattern. Driver goldens and TS fixtures unchanged. |
| Never invent physical values | Tag part, tag material and nest stay `needs_measurement`. The fill recipe's stepover is `needs_measurement` (G6); its setup values are copied from run 3 and tagged [HYPOTHESIS] for fill (observed in trace cuts only). Bench files that need a tip width or stepover use explicit `--set` overrides, printed on the gate report and the sheet as placeholders to replace with V3 measurements. |
| Qt-free core | Text, fill, patterns, setup card and drawings are core modules; the GUI only shows them. |
| Driver untouched | The corner test runs at the driver's fixed `accel` 551; testing other values would need a driver change, so G7 alternatives are deferred unless V3 shows corner defects. |
| No producer names | Patterns, parts and fixtures are generic. |

## 2. Components and contracts

### 2.1 Fill (`toolpath/fill.py`, M2.1)

```python
class FillParams: tip_width_mm: float; stepover_mm: float; hatch_angle_deg: float; contour_pass: bool
class FillResult: paths: tuple[Polyline, ...]; narrow: tuple[NarrowRegion, ...]
def fill(op: FillOp, op_index: int, params: FillParams) -> FillResult      # part frame mm
```

- Inward offset of each region (outer and holes) by `tip_width_mm / 2` (mitre joins). The offset area is
  where the tool centre may go.
- Hatch: parallel lines at `hatch_angle_deg`, spacing `stepover_mm`, clipped to the offset area; lines
  ordered in alternate directions within a region (the optimiser may reorder later).
- Contour pass (when true): the boundary of the offset area as closed paths, emitted before the hatch.
- Narrow regions: any part of a region that disappears under the inward offset (area of the region
  minus the area swept by the tool over the offset area, measured with a tolerance of 0.01 mm^2) is
  reported as a `NarrowRegion(op_index, region_index, width_mm)`, never dropped silently. `width_mm`
  is an upper bound (twice the largest inscribed distance found).
- Build (`build.py`, M2.1 adds the FillOp branch): requires a fill recipe; `tip_width_mm` from
  `resolved.tip_width_mm` (override or tool), `stepover_mm`, `hatch_angle_deg`, `contour_pass` from the
  effective recipe; any unknown -> `BuildError` naming the gap. Intent gains the fill strokes and the
  narrow regions (S3).

### 2.2 Text (`text/`, M2.2)

```python
# text/hershey.py: port of web/src/hershey.ts reading web/app/fonts/futural.jhf
def load_jhf(path: Path = FUTURAL) -> tuple[HGlyph, ...]
def hershey_strokes(text: str, size_mm: float, x_mm: float = 0, y_mm: float = 0) -> HersheyStrokes
    # identical to hersheyTextToStrokes: strokes in device units, width_mm, warnings (conformance)
def hershey_paths(text: str, size_mm: float, x_mm: float = 0, y_mm: float = 0) -> TextPaths
    # same geometry as mm polylines (Y up), for patterns
# text/outline.py: glyph outlines from web/app/fonts/Arimo-Regular.ttf via fontTools
def outline_regions(text: str, size_mm: float, x_mm: float = 0, y_mm: float = 0,
                    chord_mm: float = 0.01) -> TextRegions   # regions with holes, Y up, flattened
class TextPaths: paths: tuple[Polyline, ...]; width_mm: float; cap_height_mm: float; warnings: tuple[str, ...]
class TextRegions: regions: tuple[Region, ...]; width_mm: float; cap_height_mm: float; warnings: tuple[str, ...]
```

Conformance: `desktop/tests/fixtures/hershey/` holds a fixture generated by running the TS
`hersheyTextToStrokes` (through `web/node_modules/.bin/tsx`) on a set of strings and sizes, with a
generator script and a `--check` mode; the Python port must match it exactly. The fixture is
committed; the desktop CI core job compares it. Bench patterns only; production text arrives as geometry.
`cap_height_mm` is the measured height of "H" at that size, so ladders label true letter height.

### 2.3 Patterns (`patterns/`, M2.3 after M2.1 and M2.2)

```python
class ParamSpec: name: str; type: type; default: Any; help: str
class Pattern(Protocol):
    name: str; title: str; mode: Literal["trace", "fill"]; params: tuple[ParamSpec, ...]
    def generate(self, **params: Any) -> Job      # part frame, target part `bench-scrap-40` by default
PATTERNS: Mapping[str, Pattern]                    # registry in patterns/__init__.py
```

| Pattern | Mode | Purpose (gap) |
|---|---|---|
| `asymmetric` | trace | V1 orientation and position: "F", +X and +Y arrows, crosshair (G15) |
| `pz-square` | trace | V2: 10 mm square for the `PZ` sweep (`--set pz=`) (G4) |
| `datum-crosshair` | trace | Fixture datum: crosshair plus outline ticks (G2) |
| `char-ladder-trace` | trace | Character-height ladder, Hershey, heights 0.8 to 5 mm, labelled (G5) |
| `char-ladder-fill` | fill | Character-height ladder, Arimo outlines (G5); needs tip width and stepover |
| `stepover-ladder` | trace | Hatched squares at stepovers 0.05 to 0.30 mm, explicit lines, labelled (G6) |
| `corner-test` | trace | Zigzags and stars with corner angles 15 to 150 degrees at `accel` 551 (G7) |
| `job-size-ladder` | trace | Jobs of increasing byte size (target 16 KB to 1 MB) from dense short segments (G9) |
| `repeat-batch` | trace | First-article layout repeated: `quantity = 10`, crosshair + text (G11) |

`ggdesk pattern NAME [-p key=value]... -o OUT.ggj [--build --recipe R --fixture F ...]` writes the job and,
with `--build`, the `.m20`, gate report and SVG preview next to it. Every pattern has a golden.

### 2.4 Setup card (`setupcard.py`, M2.0)

```python
class SetupCard: title: str; lines: tuple[str, ...]      # tool, nose, knob, pressure, recipe status, residual
def setup_card(resolved: Resolved) -> SetupCard
```

It repeats the gate's manual-depth residual line verbatim (one source: `gate.residual`). Shown by the
bench window (M2.4) and printed by `ggdesk build`.

### 2.5 GUI (M2.4)

Pattern panel (list from `PATTERNS`, parameter form built from `ParamSpec`, "Generate" opens the job in
the session); recipe selector (all recipes for the machine, status shown, draft marked); read-only
library browser (entries, facts with confidence, needs_measurement with gap and procedure); setup card
panel. Same rules as M1: the session is the only core caller; colours only in `theme.py`.

### 2.6 Fixture drawing (`drawings/nest.py`, M2.5)

```python
class NestDrawing: svg: str; dxf: str; unmeasured: tuple[str, ...]
def nest_plate(part: Part, fixture: Fixture, *, plate_margin_mm: float = 10.0) -> NestDrawing
```

A plate with a pocket for one blank (outline + clearance), the hole, a datum mark and the datum
crosshair position. Every dimension taken from an unmeasured fact is drawn from a placeholder, labelled
`UNMEASURED (G1)` / `(G2)`, and listed in `unmeasured`; the title block says the drawing is not for
cutting while any item is listed. DXF R12 written directly (no dependency). `ggdesk drawing nest
--part dog-tag-blank --fixture dog-tag-nest -o OUT` (a new CLI command, owned by M2.5).

## 3. Threading and performance

Fill of a 40 x 40 mm area at 0.05 mm stepover under 1 s. Pattern generation under 1 s each, except the
largest job-size step.

## 4. CI changes

`shapely>=2.1,<2.3` and `fonttools>=4.50` join the core dependencies (licences BSD-3 and MIT; wheels for
CPython 3.12 to 3.14 on Linux x86_64 and Windows x64 checked with `pip download` on 2026-11-01). The
Hershey conformance fixture is checked in the desktop core job.

## 5. Parallel slices

| Slice | Wave | Owns (files) | May add to shared files | Depends on | Estimate |
|---|---|---|---|---|---|
| M2.0 contracts | 1 | `toolpath/fill.py` (stub), `text/` (stubs), `patterns/__init__.py` (registry + `ParamSpec`), `setupcard.py`, `drawings/__init__.py`, seed `recipes/scrap-rotary-diamond-fill.toml`, `pyproject.toml` deps, decisions rows | - | M1 | 1 PR |
| M2.1 fill | 2 | `toolpath/fill.py`, FillOp branch in `build.py`, `tests/unit/test_fill*.py`, fill goldens | - | M2.0 | 1 PR |
| M2.2 text | 2 | `text/`, `tests/unit/test_text*.py`, `tests/fixtures/hershey/` | - | M2.0 | 1 PR |
| M2.4 GUI | 2 | `ggdesk_app/panels/patterns.py`, `panels/library.py`, `panels/setup_card.py`, recipe selector in `panels/`, `tests/gui/test_m2_*.py` | one installer line each in `extensions.py` | M2.0 | 1 PR |
| M2.5 fixture drawing | 2 | `drawings/`, `commands/drawing.py`, `tests/unit/test_drawing*.py` | one entry in `cli.COMMANDS` | M2.0 | 1 PR |
| M2.3 patterns | 3 | `patterns/*.py` (not the registry contract), `commands/pattern.py`, `tests/unit/test_patterns*.py`, pattern goldens | registry entries | M2.1, M2.2 | 1 PR |
| M2.Z integration | last | `m2-acceptance.md`, exit tables, status lines, `docs/validation/V3-*.md`, `V4-*.md`, `measurements-needed.md`, `bench-day.md`, `desktop/bench/`, review, handoff | | all | 1 to 2 PRs |

Merge order: M2.0; M2.1, M2.2, M2.4, M2.5 as each turns green; M2.3; M2.Z.

## 6. Owner questions (answered under delegated authority; owner to confirm)

| # | Question | Answer (coding agent, owner to confirm) |
|---|---|---|
| 1 | Fill geometry library | Shapely 2.x (BSD-3); passes the licence and wheel check. Mitre joins only |
| 2 | Hatch defaults | Recipe-level `hatch_angle_deg` and `contour_pass`; the scrap fill recipe uses 0 degrees and a contour pass (DEFINED choices); stepover `needs_measurement` (G6) |
| 3 | Single-line text | Python port of `web/src/hershey.ts` on `futural.jhf`, byte-identical to TS by a conformance fixture; bench only |
| 4 | Filled text | Arimo (OFL) outlines through fontTools (MIT); bench only |
| 5 | Bench files that need tip width or stepover | Generated with explicit `--set` placeholders, labelled PLACEHOLDER on the sheet and in the gate report; the sheet says to regenerate with the V3 values before cutting |
| 6 | Corner test `accel` | 551 only (driver fixed); alternatives need a driver change and are deferred unless V3 shows corner defects (G7) |
| 7 | Job-size ladder | Run with the tool reversed (no cut); measures acceptance and `!ET` only |
| 8 | Setup card in M2 | Yes (owner brief): read-only card from the effective recipe; the M3 confirm-before-load step stays M3 |
| 9 | Nest drawing | Parametric SVG and DXF R12; placeholder dimensions marked UNMEASURED until G1/G2 close |
