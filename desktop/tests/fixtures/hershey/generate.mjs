// Hershey conformance fixture: runs the TypeScript hersheyTextToStrokes (web/src/hershey.ts) on a
// fixed case list and writes hershey_conformance.json next to this file. The Python port
// (desktop/src/ggdesk/text/hershey.py, hershey_strokes) must reproduce every case exactly;
// desktop/tests/unit/test_text_hershey.py compares them.
//
// Regenerate (from the repository root; run `npm ci` in web/ first if web/node_modules is missing):
//   web/node_modules/.bin/tsx desktop/tests/fixtures/hershey/generate.mjs           # write
//   web/node_modules/.bin/tsx desktop/tests/fixtures/hershey/generate.mjs --check   # exit 1 if stale
//
// Any change to web/src/hershey.ts, web/src/round.ts or web/app/fonts/futural.jhf requires
// regenerating this fixture in the same pull request (and the Python port to match it).
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { hersheyTextToStrokes } from '../../../../web/src/hershey.ts';

const here = dirname(fileURLToPath(import.meta.url));
const jhfPath = join(here, '../../../../web/app/fonts/futural.jhf');
const outPath = join(here, 'hershey_conformance.json');
const jhf = readFileSync(jhfPath, 'utf8');

let printable = '';
for (let c = 32; c <= 126; c++) printable += String.fromCharCode(c);

const SIZES = [0.8, 1.0, 1.27, 2.5, 3.333, 5.0];
// Offsets: the origin, plain values, and values whose mm coordinates land on exact 0.005 mm
// ties (mm * 100 = n + 0.5 exactly in binary, e.g. 0.125, -0.375, -2.625, 0.875).
const OFFSETS = [[0, 0], [10, -3.5], [0.125, -0.375], [-2.625, 0.875], [12.345, 6.789]];

const cases = [];
for (const size of SIZES) cases.push([printable, size, 0, 0]);
for (const text of ['0123456789', 'Hello, World!']) {
  for (const size of SIZES) for (const [x, y] of OFFSETS) cases.push([text, size, x, y]);
}
// exact-binary sizes: every vertex lands on a multiple of 1/64 mm, many on exact 0.005 mm ties
for (const size of [0.5, 1.0, 2.0]) {
  for (const [x, y] of [[0, 0], [0.125, -0.375], [-2.625, 0.875]]) cases.push([printable, size, x, y]);
}
// missing glyphs: Latin-1, a dash, an astral code point, a control character; and the empty string
cases.push(['Café — Ä', 2.5, 0, 0]);
cases.push(['A\u{1F600}B\tC', 1.27, 0.125, 0]);
cases.push(['', 2.5, 1, 1]);

const out = cases.map(([text, sizeMm, xMm, yMm]) => {
  const r = hersheyTextToStrokes(jhf, text, sizeMm, xMm, yMm);
  return { text, sizeMm, xMm, yMm, strokes: r.strokes, widthMm: r.widthMm, warnings: r.warnings };
});

// one case per line keeps diffs readable
const body = '{"source": "web/src/hershey.ts hersheyTextToStrokes", "font": "web/app/fonts/futural.jhf",\n' +
  ' "cases": [\n' + out.map((c) => '  ' + JSON.stringify(c)).join(',\n') + '\n ]}\n';

if (process.argv.includes('--check')) {
  let cur = '';
  try { cur = readFileSync(outPath, 'utf8'); } catch { /* missing: stale */ }
  if (cur !== body) {
    console.error('hershey_conformance.json is stale: regenerate with generate.mjs');
    process.exit(1);
  }
  console.log(`hershey_conformance.json up to date (${out.length} cases)`);
} else {
  writeFileSync(outPath, body, 'utf8');
  console.log(`wrote ${outPath} (${out.length} cases)`);
}
