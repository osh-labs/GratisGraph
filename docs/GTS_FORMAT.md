# GTS Wire Format Specification

**Status:** Confirmed on hardware (Gravograph M20 Express, Sirius FW boot 1.2 / prog 1.30).
Multi-stroke header semantics confirmed 2026-06-09 (telemetry-verified to 0.01 mm).
M20 IQ+ (model 0x020D, prog 1.81) probed 2026-10-29: engrave jobs, `NR`/`LB`,
Point&Shoot and the spindle rule confirmed; rows say "(IQ)" where only the IQ was tested.
**Scope:** The USB transport and binary job format used by Gravograph M20/M40-family
contact engraving machines. This document is the implementation contract for all
GratisGraph translators (Python reference implementation, planned TypeScript port).
If code and this document disagree, this document wins — fix the code.

> Findings here were obtained through interoperability research on hardware owned by
> the authors, by observing USB traffic between the machine and the vendor's software,
> and confirmed by independent implementation. Rows marked *vendor* come from read-only
> static analysis of the vendor's install media for interoperability (string tables,
> export names, call sites); only the resulting facts are recorded here. No proprietary
> code is reproduced.
> Gravograph, Gravotech, Gravostyle, and GT Smartstream are trademarks of Gravotech
> Group; this project is not affiliated with or endorsed by Gravotech.

---

## 1. Conventions

- All multi-byte integers are **big-endian**.
- Coordinate unit: **0.01 mm** (100 units/mm). Confirmed by physical measurement.
- Coordinate system: home (0,0) = back-left of work area (nearest the gantry,
  farthest from the operator); +X = tool right; +Y toward the operator (front).
  The table translates away from the operator to advance +Y, so home sits at
  the back. Confirmed with a felt-tip marker fiducial.
- Work envelope: 100×100 mm software, ~120×120 mm physical (M20).
- "GTS" is this project's name for the format; the vendor does not document one.
  File extension: `.m20` (per-machine extensions for future variants).

## 2. USB transport

| Property | Value |
|---|---|
| VID:PID | `0xFFFD:0x0001` (unregistered VID; product string "USB Printer") |
| Class | USB Printer Class (0x07), bidirectional |
| Speed | Full Speed (12 Mbit/s) |
| EP OUT | `0x01` bulk, 64-byte max packet (host → machine: jobs, commands) |
| EP IN | `0x82` bulk, 64-byte max packet (machine → host: telemetry, responses) |

Jobs are written to EP OUT as a raw byte stream — no envelope, no framing, no
acknowledgement handshake required before sending. (The ASCII `!PS/!OR/!MM` envelope
used on the Windows print path is consumed by the spooler stack and never
reaches the wire.)

OS note: macOS's AppleUSBPrinter claims the interface exclusively; detach requires
root. Hold the interface claim for the process lifetime — releasing it lets the
kext reattach immediately.

## 3. Device → host packets: counted framing

**Every machine response follows one framing rule** (confirmed live 2026-06-09):

```
!XX N;<N payload bytes>
```

ASCII prefix: `!`, two command characters, space, decimal byte count, `;`.
The count is the exact payload length. There are no delimiters between packets.

| Packet | Count | Payload | Meaning |
|---|---|---|---|
| `!ID 28;` | 28 | 7 × int32 BE | Identity (see §4) |
| `!MX 4;` `!MY 4;` | 4 | uint32 BE | Axis absolute position, 0.01 mm units |
| `!MZ 4;` | 4 | uint32 BE | Z axis activity — scaling DIFFERS from X/Y (values exceed physical travel at 0.01 mm; possibly 0.001 mm units or a counter). Do not interpret as 0.01 mm |
| `!MN 4;` | 4 | uint32 BE | Motor neutral / heartbeat counter |
| `!ME 4;` | 4 | uint32 BE | Motion end / encoder marker |
| `!JF 0;` | 0 | — | Job RECEIPT acknowledgement — emitted ~2s after a job is queued, BEFORE execution. NOT a completion signal (confirmed 2026-06-09) |
| `!ET 4;` | 4 | uint32 BE | End of motion. Plausibly engrave-job execution time in seconds: identical jobs reproduce the same value (9, 9); longer job → 13; wall-clock window consistently ~4 s larger (home job excluded?) |
| `!OR 8;` | 8 | 2× uint32 BE | Origin report: machine→host packed (X, Y) at 0.01mm, sent when the operator jogs the head and confirms a new origin on the panel (confirmed 2026-06-09) |
| `!TU 4;` etc. | 4 | uint32 BE | Command acknowledgements |
| `!CM 4;` | 4 | int32 BE | Machine state (M20 IQ, 2026-10-29): `1` = job started by green, `3` = paused at `NR`, `−1` = panel/manual (jog) mode |
| `!LB 3;` | 3 | 2 ASCII + NUL | LCD message text relayed to the host while a job pauses at `NR` (M20 IQ, which has no screen) |
| `!DL 8;` | 8 | 2× int32 BE | Reply to host `!DL`: red-pointer offset from the tool, (X, Y) at 0.01 mm. M20 IQ: (2170, 0). Matches the X-only "diode zero point" calibration in the operator manual |
| `!PS 16;` | 16 | 4× int32 BE | Point&Shoot point, one reply per Check press: (X, Y, −1, −1). See §8 |
| `!BE 8;` | 8 | 2× int32 BE | Reply to host `!BE 4;` + 1: payload (1, 1). No audible beep on the M20 IQ |

Packets whose payload the driver does not decode (`!CM`, `!LB`, `!DL`,
`!PS`, `!BE`) must still be consumed by their count.

Position telemetry streams continuously during job execution in bursts.
Telemetry unit mapping confirmed: values are absolute position at 100 units/mm
(characterised Session 10 against known 90 mm travel).

A parser MUST read the count rather than assuming a fixed packet length —
`!JF 0;` carries zero payload, and assuming 4 bytes desynchronises the stream.
Some firmware revisions prepend a stray NUL byte; strip leading NULs.

## 4. Identity (`!ID`)

Host sends ASCII `!ID 0;\r\n`. Machine replies `!ID 28;` + 28-byte struct
(7 × int32 BE). The machine also broadcasts this packet spontaneously on USB
attach. Note: the machine reliably answers `!ID 0;` only shortly after power-on
(⚠ OPEN: idle-state behaviour unexplained).

| Offset | Field | M20 Express live value |
|---|---|---|
| +0 / +4 | boot_ver major/minor | 1.2 |
| +8 / +12 | prog_ver major/minor | 1.30 |
| +16 | platform_type | 4 (3 = K2000/M20 std, 4 = Sirius/M20 Express; firmware family, NOT product) |
| +20 | model_code | 0x0204 |
| +24 | model_code_alt | 0 (⚠ OPEN: possible serial-number field) |

**Model codes** (from firmware updater ID blobs): 0x0202 M40, 0x0203 M40G,
0x0204 M20/Express, 0x0205 M20 XL, 0x0206 M20 Jewel, 0x0207 M20 PIX,
0x0209 M20 Jewel 2, 0x020D M20 IQ, 0x020E M20 XL IQ, 0x020F M20 Jewel IQ,
0x0210 M40 IQ, 0x0211 M40G IQ, 0x0212 M10 Jewel (negate X).
IS400 IQ uses the same format with coordinates × 1.25. Implementations MUST key
machine behaviour on model_code, never platform_type.

## 5. GTS job binary

### 5.1 Overall structure

```
[94-byte header]
[setup commands: DR MC VS VZ PZ DZ]
[stroke blocks, simply concatenated — no records between them]
[12-byte return-to-home segment (delta)]
[JF]
```

### 5.2 Header (94 bytes)

| Offset | Bytes | Value |
|---|---|---|
| 0x00 | 6 | Magic `!MM88;` |
| 0x0A | 14 | `ot : 1\0` as UTF-16LE |
| 0x24 | 2 | **model_code**, uint16 BE — must equal the target machine's `!ID` model_code (`02 04` on the M20 Express) |
| 0x30 | 2 | `0x0DE4` BE (BOX_DIM = 3556 units) |
| 0x34 | 2 | `0x0DE4` BE (repeated) |
| 0x3D | 1 | `0x02` |
| 0x5D | 1 | `0x04` |
| (rest) | — | zero |

**model_code at 0x24 (confirmed on hardware 2026-10-28):** an M20 IQ
(0x020D, prog 1.81) answers a job stamped `02 04` with `!JF 0;` but then
silently discards it — no beep, green does nothing. Stamped `02 0D` the same
job queues normally (beeps; `!ME`, `!CM`, `!ET` follow). The vendor
post-processors carry the same value as `IdMachine` (M20 = 516 = 0x0204,
M20 IQ = 525 = 0x020D). The driver stamps the identified model_code at send
time, so builders may keep emitting `02 04`.

The vendor's own software has two further header forms (`!AS n;` and
`!PH 72;`, see §5.7). The machine accepts `!MM88;` regardless.

### 5.3 Opcode commands — 6 bytes each

```
FF FD <2-char ASCII opcode> <uint16 BE argument>
```

Setup block: `DR 0` (drag reset) · `MC` (SPINDLE/motor enable: 1=on, 0=off —
confirmed from Quick capture 2026-06-09, NOT "machine coords" as previously
documented) · `VS 25` (vector speed) · `VZ 25` (= VS) · `PZ` (ENGRAVING DEPTH
— Quick sets this from its depth field: depth 0.01"→PZ 25, 0.99"→PZ 100,
default→PZ 0; confirmed 2026-06-09) · `DZ 500` (drag depth).

**Spindle (MC):** Quick sends `MC 1` to spin the cutter, `MC 0` for drag/diamond
engraving with no spindle. Our driver always sent `MC 0` (correct for diamond
drag). To run a rotary cutter, send `MC 1`.

**Depth (PZ):** Quick actively drives PZ from the operator's depth field
(imperial inches on the captured install, UI-capped ~0.393"≈10mm). PZ 0→100
scale. This REOPENS the depth question: our "PZ has minimal effect" finding
came from sending PZ 30 with a diamond drag + spring tension; PZ may have real
effect with a spindle-driven cutter or across its full range. The ≈6 mm
solenoid stroke (drag mode) finding still stands separately.

M20 IQ, rotary diamond with the regulating nose (2026-10-29): the scaled knob
sets the cut depth and `PZ` is the head's overtravel past the auto-ZRef touch.
`PZ 50` held Z 0.50 mm past the touch reading, so likely 0.01 mm units (one
sample). A clean cut came from nose + knob 5 notches + pressure 2 with
`PZ 50`, `VS 10`, `VZ 5`. Without the nose (pressure 4, `PZ` 5–10) it chattered
and skipped. See PROTOCOL_FINDINGS.md, "Rotary diamond cut".

**Full opcode vocabulary (Gravostyle 7 static analysis, 2026-10-28).** These
are the 27 opcodes the vendor's job writer can emit. *Wire* = seen in a USB
capture or sent by this driver; *vendor* = established from the vendor
software's own function names and debug-trace strings, not yet observed on
the wire. See PROTOCOL_FINDINGS.md for the evidence behind each row.

| Op | Argument | Meaning | Status |
|---|---|---|---|
| `PD` | 0 | Tool down to engraving depth (vendor: "go to depth") | wire |
| `PU` | 0 / 1 | Lift: 0 = inter-pass clearance, 1 = safety height | wire |
| `ZA` | 0 / 1 | Automatic Z reference before `PD`; 1 when `ZrefAuto=2` | wire |
| `VS` | speed | XY speed | wire |
| `VZ` | speed | Z speed | wire |
| `PZ` | depth | Engraving depth. M20 IQ with nose: Z overtravel past the auto-ZRef touch, likely 0.01 mm (`PZ 50` → +0.50 mm, one sample, 2026-10-29) | wire (IQ) |
| `DZ` | value | Z clearance (vendor: "dégagement") | wire |
| `DR` | value | Per-pass value ×1000; vendor emits it only when non-zero | wire, meaning ⚠ OPEN |
| `MC` | 1 / 0 | Spindle on / off; vendor toggles it mid-job with spindle state. **M20 IQ: the spindle turns only while `MC 1` AND the tool is down (`ZA`/`PD`)**; tool-up rapids with `MC 1` do not spin it, and a plunge job with `MC 0` does not either (2026-10-29) | wire |
| `JF` | 0 | End of job | wire |
| `VR` | uint16 | Spindle speed, sent before `MC 1` and only when `WithSpindleSpeed=1` (no M20 post-processor sets it). Vendor value = `(clamp(rpm, Smin, Smax) − Smin) × StoMac + SmMin`; defaults 5000 / 18 000 / 1 / 0, so `rpm − 5000`. **M20 IQ ignores it: fixed-speed spindle.** `VR` 4000/16000 after `MC 1`, and 2000/13000 before `MC 1` (vendor order), all gave the same ≈ 250/295 Hz spindle tone (< 0.5 % apart, 2026-10-29) | wire (IQ) |
| `VD` | speed | Plunge (descent) speed; vendor default 15. M20 IQ accepts it; `VD 15` lengthened `!ET` 5 → 6 on one run | wire (IQ) |
| `OU` | ±n | Output switch: +n on, −n off. M20 IQ: 5 = coolant, 6 = aux. IQ accepts `OU ±6`; no effect visible without an accessory (possibly the rear Sub-D 15 outputs O1–O4) | wire (IQ) |
| `TO` | n | Tool-changer turret position; 0 = return | vendor |
| `OP` | 0 | Set origin at current position (after explicit move to plate/table corner) | vendor |
| `2D` / `3D` | 0 | Movement type: 2D (dx,dy) or 3D (dx,dy,dz) segment records. IQ accepts `2D 0`, no visible change | `2D` wire (IQ) |
| `V2` | 0 | Return to vector mode after a raster section | vendor |
| `LB` | 0 / 1 / 2 chars | Machine LCD: 0 = init screen, 1 = free screen, else two ASCII chars of message text. M20 IQ (no LCD) accepts it and relays the text to the host as `!LB 3;` during an `NR` pause | wire (IQ) |
| `NR` | 1 | Operator pause after an LCD message. M20 IQ: the job stops before the next stroke (`!CM 4;` = 3) until green is pressed again | wire (IQ) |
| `ME` | n | Pass counter in border-test modes | vendor |
| `BD` | 0 / 1 | Braille bead dispenser up / down | vendor |
| `RX` / `RY` | hi, lo | Raster origin X / Y as int32, sent as two uint16 opcodes (high word first) | vendor |
| `C3` / `C4` | n words | One raster row, alternating scan direction; n uint16 pixel words follow | vendor |
| `PW` | 15 | Raster setup constant | vendor, meaning ⚠ OPEN |

Vendor per-pass defaults: `VS 15`, `VZ 5`, `VD 15`, `PZ 0`, `DZ 100`, `DR 0`.

### 5.4 Segment records — 12 bytes, raw, NO `FF FD` prefix

```
int16 BE × 6:  pw1  pw2  speed  accel  dx  dy
```

`pw1 = pw2 = 1`; `speed` = VS value; `accel = 551` (0x0227) in every observed
record. On the M20 IQ, `accel = 100` on a single 20 mm straight segment made
no visible or timing difference (`!ET` 7 both). The vendor trace labels these
fields `MOVE RATIO DANG …`, so the field may be an angle term that only
matters at corners (⚠ OPEN). `dx, dy` are **relative
deltas** in 0.01 mm units. Parsers identify segment records by `accel == 551`.

The same 12-byte record serves as the **stroke header** (pen-up rapid to stroke
start) and as the **return-to-home** block before `JF`.

### 5.5 Stroke block

```
[12-byte stroke header — pen-up rapid DELTA from previous stroke's end
                         (first stroke: from home, so delta == absolute)]
[FF FD ZA 0001]      Z approach
[FF FD PD 0000]      pen down (operator confirmation gate when armed via !CM)
[N × 12-byte segments]
[FF FD PU 0000] × 2
[FF FD PU 0001]      pen up, home flag
```

Exactly **one** `JF` per job, after the final return segment. Emitting `JF`
per-stroke stops the machine after the first stroke. `NR` does not appear in
any captured job — do not emit. (The vendor emits `NR 1` only as an operator
pause after an LCD message; see §5.3.)

### 5.6 Stroke-header coordinates — CONFIRMED RELATIVE (2026-06-09)

**Every coordinate on the wire is a relative delta — headers included.**
Confirmed by paired hardware runs with axis telemetry:

- Absolute-header emission with a separate inter-stroke rapid double-offset
  the second stroke: commanded start (30, 40) mm landed at (60, 80) mm
  (`!MY` peak 7999 = 79.99 mm).
- Delta-header emission with no inter-stroke rapid landed both strokes at
  their commanded positions (`!MY` peak 3999 = 39.99 mm), and marks on paper
  agreed.

Canonical multi-stroke form: each stroke's header is the delta from the
previous stroke's END to this stroke's start; stroke blocks are simply
concatenated; one return-to-home delta and one `JF` close the job. There is
no separate inter-stroke rapid record — the header IS the rapid. A parser
must integrate deltas to recover absolute positions.

### 5.7 Vendor header variants (Gravostyle 7, not yet seen on the wire)

Gravostyle 7 does not emit `!MM88;`. Which header it writes depends on the
post-processor's `ModePH` (photo/raster capability) setting:

- **`ModePH=0`** — `!AS n;` + n bytes. n grows with optional feature blocks:
  38 (46 with `UseRefMeasure`), 50, 66, 74, 106. Gravostyle 7 normally reaches 106.
  The debug trace labels the content: machine ID, plate length/width, file
  name, APF plate count/pressure, braille, RDF, smart-spindle, Artfoil,
  `M_OPT[n]`, `REFX`/`REFY`, test mode, end-upper-right.
- **`ModePH=1`** (M20 IQ, M20 PIX) — `!PH 72;` + 72 bytes. Bytes 0x10–0x47
  are 14 × int32 BE: reference position X/Y/Z (0x10–0x18), machine field
  (0x1C), accessory (0x20: table / vice / cylinder number, −1 for none),
  diameter (0x24), raster DPI X/Y (0x28/0x2C), plate length/width
  (0x30/0x34), auto-Z reference (0x38), strike height (0x3C), raster speed
  (0x40), 0x44 unidentified. 0x00–0x0F ⚠ OPEN (likely a name field).
  No spindle field: the `!PH` trace labels none, and smart-spindle exists
  only in `!AS`.

Byte layouts of `!AS` and of the vendor's `CIRC` (native arc) record are
⚠ OPEN.

## 6. Execution model (confirmed on hardware 2026-06-09)

- Jobs QUEUE on receipt — the machine beeps once per job and does NOT execute
  while connected. ~2 s after queueing it emits `!JF 0;` per job (receipt ack).
- **One green press executes the entire queue in order** (confirmed: a home
  job and an engrave job both ran on a single press). Earlier "one press per
  job" claims are wrong.
- The last executed sequence persists in the buffer — pressing green again
  re-runs it — until power cycle.
- Disconnecting triggers a ~15 s end-of-stream timeout: the machine re-beeps
  for queued jobs but does NOT execute them unless armed (below).
- **Auto-execution:** send `!CM 4;` + uint32 BE `1` (10 bytes:
  `21 43 4D 20 34 3B 00 00 00 01`) after the job, then disconnect; the machine
  executes after the ~15 s timeout, pausing at the first `PD` for green if
  present. `PD` is the operator confirmation gate in armed jobs.
- **Job completion detection:** M20 IQ: the `!ET` that follows `!CM 4;` = 1
  (one `!ET` per green press, covering the whole queue); the IQ's axis
  telemetry is idle position reports and does not settle at 0 first. Other
  machines: changing axis telemetry returning to 0 plus `!MN` heartbeats.
  `!JF` is a receipt ack and MUST NOT be treated as completion.

## 7. Reference captures

Byte-level regression fixtures (real Gravostyle output, confirmed on hardware)
live in `tests/regression/`: `00013.SPL` (horizontal line, start (0, 16.56 mm),
Δx 35.40 mm) and `00018.SPL` (small curved stroke). Conformance = field-level
equality with these captures for setup values, stroke positions, segments, PU
sequence, return block, and JF count, ignoring header metadata bytes.

## 8. Probed but unconfirmed commands

Host-to-device ASCII probes observed to elicit a reaction, but with
uncharacterised semantics — recorded so nobody re-discovers them:
`!GA 4;\r\n` (queues a homing job, short beep) and `!DL 4;\r\n`
(beep; presumed download mode). Not used by the driver.

**`!DL` is counted, not a bare command.** The vendor sends it as
`!DL 4;` + int32 BE model_code, immediately before a Point&Shoot request.
Host→machine ASCII commands use the same `!XX N;` + N-byte counted framing
as machine responses (§3).

**Point&Shoot / red laser pointer (confirmed on the M20 IQ, 2026-10-29;
not yet used by the driver):**

```
host:    !DL 4;  + int32 BE model_code
machine: !DL 8;  + 2× int32 BE pointer offset (X, Y), 0.01 mm   — IQ: (2170, 0)
host:    !PS 20; + 5× int32 BE [model_code, accessory, diameter, red_pointer, ps_method]
         → red pointer turns on; operator jogs with the arrow keys
           (the machine streams !MX/!MY while jogging)
         → operator presses Check (✓): beep, and
machine: !PS 16; + 4× int32 BE (X, Y, −1, −1)
host:    !1B 0;  cancel: pointer off, head returns home; no reply
```

`!PS 16;` is two (X, Y) pairs with −1 marking an unset pair. While the
pointer is active, the `!MX`/`!MY` telemetry tracks the **pointer spot**
(the scrap centre read ≈ (47, 47) mm). The method-0 first reply converts
that to the tool position over the spot by adding the `!DL` offset.

Green Start does nothing during Point&Shoot; Check confirms.
`ps_method` changes both the point count and the coordinates:

| `ps_method` | Points | Reported (X, Y) | Session end |
|---|---|---|---|
| 0 | one, then a closing Check | 1st Check: (spot **+ pointer offset**, −1, −1), the tool position over the aimed spot. 2nd Check: (0, 0, spot) | head homes after the 2nd Check |
| 1 | several, one `!PS 16;` per Check press | head position, no offset | still waiting after two points; ended with `!1B 0;` (normal end ⚠ OPEN) |

**The machine does not move the job origin.** A job queued during a
method-0 session waits until the session closes, then runs in ordinary
machine coordinates (a rapid to job (5, 5) mm parked at telemetry (499, 499)
after a shot near (69, 47)). The vendor's "floating origin" is therefore
host-side: the host adds the shot point to the job coordinates. Green is
ignored while a session is open, so queued jobs cannot start until it closes. Tested only with
`accessory` 0, `diameter` 0, `red_pointer` 1. The session is held by the
machine and survives a USB disconnect and reconnect. Turning the pointer or
spindle on or off from the panel (Shift+◀, Shift+✓) sends nothing to the host.

## 9. Open questions (consolidated)

1. **§5.6 stroke-header semantics** — the only item blocking multi-stroke
   conformance and the TypeScript port.
2. `accel=551`: live parameter or sentinel.
3. `model_code_alt` / machine serial number source.
4. `!ID 0;` unanswered while machine is long-idle.
5. `DR` and `PW` meanings (§5.3).
6. Point&Shoot: normal end of a `ps_method` 1 session; meaning of the
   (0, 0) first pair in the closing method-0 reply (§8). Still-untried vendor
   opcodes: `VR`, `TO`, `OP`, `3D`, `V2`, `ME`, `BD`, raster set (§5.3).
7. `!AS` header and `CIRC` record byte layouts (§5.7).
