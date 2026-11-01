# gratisgraph-job v1

Status: draft (2026-11-01). Frozen at M4; until then fields may change with a decisions.md row.

## Bottom line

A `.ggj` file is UTF-8 JSON describing what to engrave on one part, in mm, in the part's own frame. It
carries geometry and intent only: no machine parameters, tool, speed or depth. GratisGraph Desktop picks
the recipe, fixture and nest, applies the fixture transform, builds the `.m20` bytes and gates them. The
JSON Schema is `desktop/src/ggdesk/formats/job.schema.json`; examples are in `desktop/docs/examples/`.

## 1. Top level

| Key | Type | Required | Meaning |
|---|---|---|---|
| `format` | `"gratisgraph-job"` | yes | |
| `version` | `1` | yes | |
| `units` | `"mm"` | yes | All lengths |
| `part` | string | yes | Library id of the blank (a `parts/` entry), e.g. `dog-tag-blank` |
| `quantity` | integer >= 1 | no (1) | Copies to make |
| `reference` | string | no | Opaque producer reference (order, design code). Not interpreted |
| `source` | `{name, version}` | no | Producer name and version |
| `chord_tolerance_mm` | number, `0 < t <= 0.01` | no (0.01) | Tolerance the producer used to flatten curves |
| `operations` | array, >= 1 | yes | In engrave order of intent (the app may reorder strokes within the job) |

Unknown keys at the top level and inside an operation are preserved on read and write and otherwise
ignored. Unknown keys inside a path, region or `source` are an error.

## 2. Frame

The part frame has its origin at the centre of the part's engrave area (as defined by the part entry),
+X to the right and +Y up as the operator reads the finished part. The app maps it to the machine frame
through the fixture: machine = nest origin + (x, -y). The machine's +Y points toward the operator
(`docs/GTS_FORMAT.md` section 1), hence the Y flip.

## 3. Operations

`trace`: engrave on the path (single-line lettering, outlines).

```json
{"op": "trace", "mode_hint": "trace", "char_height_mm": 5.0,
 "paths": [{"points": [[-5.0, -5.0], [5.0, -5.0], [5.0, 5.0], [-5.0, 5.0]], "closed": true}]}
```

A path has at least 2 points (3 if closed). A closed path does not repeat its first point; the app adds
the closing segment.

`fill`: clear the inside of closed regions (filled lettering). Built from M2.

```json
{"op": "fill", "mode_hint": "fill", "char_height_mm": 8.0,
 "regions": [{"outer": [[-4, -4], [4, -4], [4, 4], [-4, 4]], "holes": [[[-1, -1], [-1, 1], [1, 1], [1, -1]]]}]}
```

Rings have at least 3 points and do not repeat their first point. Orientation is free.

`mode_hint` (default: the operation name) is the lettering mode the recipe lookup uses. `char_height_mm`
(optional) is the nominal character height of text in the operation; the gate compares it with the
recipe's validated minimum (soft rule S2).

## 4. What the app does with a job

1. Resolve the part, recipe, fixture and nest from the library and the operator's selection.
2. Trace or fill each operation, transform to the machine frame, quantise once to 0.01 mm
   (round half to even), order strokes, build the `.m20` bytes.
3. Gate the final bytes against the job and the library. A refused job is never sent.

## 5. Validation

`ggdesk check` and the reader report the JSON path of the first problem, for example
`$.operations[0].paths[2].points: needs at least 2 points, got 1`.
