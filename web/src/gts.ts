/**
 * gts.ts — GTS binary builder. Port of gts_api.py's build_gts and primitives.
 *
 * Normative spec: docs/GTS_FORMAT.md. Reference implementation: gts_api.py.
 * This must produce byte-identical output to the Python build_gts for the
 * same integer stroke list; the golden corpus (tests/golden/) is the oracle.
 *
 * Units: device units = 0.01 mm integers. Stroke starts are ABSOLUTE from
 * home; everything emitted on the wire is a RELATIVE delta (headers included,
 * hardware-confirmed 2026-06-09).
 */

// ── Constants (from gts_api.py, verified) ───────────────────────────────────
const MAGIC = new Uint8Array([0x21, 0x4d, 0x4d, 0x38, 0x38, 0x3b]); // "!MM88;"
const METADATA = new Uint8Array([                                    // "ot : 1\0" UTF-16LE
  0x6f, 0x00, 0x74, 0x00, 0x20, 0x00, 0x3a, 0x00,
  0x20, 0x00, 0x31, 0x00, 0x00, 0x00,
]);
const BOX_DIM = 0x0de4;
const DEFAULT_SPEED = 25;
const DEFAULT_ACCEL = 551;     // 0x0227
const PEN_W_RAMP = 1;
const DEFAULT_ZA = 1;
const DEFAULT_PZ = 30;
const DEFAULT_DZ = 500;

// A stroke: absolute start (device units) + ordered pen-down deltas.
export interface Stroke {
  start: [number, number];      // absolute, device units
  deltas: [number, number][];   // relative pen-down segments
}

// ── Byte-writing helpers (big-endian, matching Python struct '>') ───────────
function pushU16BE(out: number[], v: number): void {
  out.push((v >> 8) & 0xff, v & 0xff);
}
function pushS16BE(out: number[], v: number): void {
  pushU16BE(out, v & 0xffff);   // two's complement, low 16 bits
}

/** 6-byte FF FD opcode command: FF FD <2-char op> <u16 BE arg>. */
function cmd(out: number[], op: string, arg: number): void {
  out.push(0xff, 0xfd, op.charCodeAt(0), op.charCodeAt(1));
  pushU16BE(out, arg & 0xffff);
}

/** 12-byte raw segment / stroke-header record (NO FF FD prefix). */
function seg(out: number[], dx: number, dy: number, speed = DEFAULT_SPEED): void {
  pushS16BE(out, PEN_W_RAMP);
  pushS16BE(out, PEN_W_RAMP);
  pushS16BE(out, speed);
  pushS16BE(out, DEFAULT_ACCEL);
  pushS16BE(out, dx);
  pushS16BE(out, dy);
}

function header(out: number[]): void {
  const hdr = new Array(94).fill(0);
  for (let i = 0; i < MAGIC.length; i++) hdr[i] = MAGIC[i];
  for (let i = 0; i < METADATA.length; i++) hdr[0x0a + i] = METADATA[i];
  hdr[0x24] = 0x02; hdr[0x25] = 0x04;
  hdr[0x30] = (BOX_DIM >> 8) & 0xff; hdr[0x31] = BOX_DIM & 0xff;
  hdr[0x34] = (BOX_DIM >> 8) & 0xff; hdr[0x35] = BOX_DIM & 0xff;
  hdr[0x3d] = 0x02; hdr[0x5d] = 0x04;
  for (const b of hdr) out.push(b);
}

/** Opcode arguments are uint16 on the wire; refuse anything that would wrap. */
function checkArg(name: string, v: number): number {
  if (!Number.isInteger(v) || v < 0 || v > 0xffff) {
    throw new Error(`buildGts: ${name} must be an integer in 0..65535, got ${v}`);
  }
  return v;
}

/**
 * Setup block. Defaults reproduce 00013.m20: DR 0, MC 0, VS, VZ (= VS), PZ, DZ.
 * Rotary jobs: mc = 1, optional vz, optional vd (appended after DZ).
 * Mirrors gts_api._gts_setup.
 */
function setup(out: number[], speed: number, pz: number, dz: number,
               mc: number, vz: number, vd: number | undefined): void {
  cmd(out, 'DR', 0);
  cmd(out, 'MC', mc);
  cmd(out, 'VS', checkArg('speed', speed));
  cmd(out, 'VZ', checkArg('vz', vz));
  cmd(out, 'PZ', checkArg('pz', pz));
  cmd(out, 'DZ', checkArg('dz', dz));
  if (vd !== undefined) cmd(out, 'VD', checkArg('vd', vd));
}

export interface BuildOptions {
  speed?: number;
  /** PZ: engraving depth value (M20 IQ with nose: Z overtravel past touch-off). */
  pz?: number;
  /** DZ: Z clearance. */
  dz?: number;
  /** MC: 1 runs the spindle (rotary tools); MC 0 is sent before the return home. */
  mc?: 0 | 1;
  /** VZ: Z speed; defaults to speed. */
  vz?: number;
  /** VD: plunge speed; not sent unless given. */
  vd?: number;
}

/**
 * Assemble a multi-stroke GTS job. Byte-exact port of gts_api.build_gts.
 * Each stroke header is the rapid delta from the previous stroke's END
 * (first stroke: from home). One return-home delta + one JF close the job.
 */
export function buildGts(strokes: Stroke[], opts: BuildOptions = {}): Uint8Array {
  if (strokes.length === 0) {
    throw new Error('buildGts: strokes list is empty — no job to build');
  }
  const speed = opts.speed ?? DEFAULT_SPEED;
  const pz = opts.pz ?? DEFAULT_PZ;
  const dz = opts.dz ?? DEFAULT_DZ;
  const mc = opts.mc ?? 0;
  if (mc !== 0 && mc !== 1) throw new Error(`buildGts: mc must be 0 or 1, got ${mc}`);
  const vz = opts.vz ?? speed;

  const out: number[] = [];
  header(out);
  setup(out, speed, pz, dz, mc, vz, opts.vd);

  let curX = 0, curY = 0;
  for (const stroke of strokes) {
    const [sx, sy] = stroke.start;
    seg(out, sx - curX, sy - curY, speed);   // header = rapid delta to start
    cmd(out, 'ZA', DEFAULT_ZA);
    cmd(out, 'PD', 0);
    for (const [dx, dy] of stroke.deltas) seg(out, dx, dy, speed);
    cmd(out, 'PU', 0); cmd(out, 'PU', 0); cmd(out, 'PU', 1);
    curX = sx + stroke.deltas.reduce((a, [dx]) => a + dx, 0);
    curY = sy + stroke.deltas.reduce((a, [, dy]) => a + dy, 0);
  }

  if (mc === 1) cmd(out, 'MC', 0);  // spindle off before the return home
  seg(out, -curX, -curY, speed);   // return to home (delta)
  cmd(out, 'JF', 0);

  return new Uint8Array(out);
}
