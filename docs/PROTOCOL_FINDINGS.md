# GTS Protocol Findings
**Project:** GratisGraph — open-source Python driver for Gravograph M20 engraving machines
**Licence:** GPL v3
**Target:** M20 machine USB protocol & binary format
**Vendor driver (Windows):** GT Smartstream 4.06 (Gravograph)
**Last updated:** 2026-10-29 — M20 IQ hardware probes (Point&Shoot confirmed, LB/NR/VD/2D/OU accepted, new machine packets)
**Status:** 🟢 Protocol fully confirmed — G-Code → GTS binary → USB working end-to-end

> **Note:** the normative wire-format reference is now [`GTS_FORMAT.md`](GTS_FORMAT.md).
> This document is the research log: how findings were made, what changed, and what
> remains open. Where the two disagree, GTS_FORMAT.md wins.

---

## Legal Notice

This document describes findings from interoperability research conducted on hardware owned by the authors, pursuant to the right to study and observe software under normal use, and for the purpose of developing an independent open-source driver. No proprietary source code was used or reproduced. Gravograph, Gravotech, Gravostyle, and GT Smartstream are trademarks of Gravotech Group. This project is not affiliated with or endorsed by Gravotech.

---

## Naming Note

"GT Smartstream" is the name of the **Windows driver package** (Language Monitor + OEM UNIDRV plugin), not the name of the underlying machine protocol. The machine protocol has no publicly documented name. Within this project we use **GTS** as a shorthand for the binary format, and **`.m20`** as the file extension for M20-targeted binaries. Future machine variants (M40 etc.) would use their own extension (`.m40`) while sharing the same GTS format family.

---

## USB Device

- **VID:PID:** `0xFFFD:0x0001` — confirmed from live USB enumeration
- **Product string:** `USB Printer`
- **USB Class:** Printer Class (bInterfaceClass=0x07), Bidirectional protocol
- **Endpoints:** EP 0x01 Bulk OUT (host→machine), EP 0x82 Bulk IN (machine→host). Both 64-byte max packet.
- **USB Speed:** Full Speed (12 Mbit/s)
- **macOS:** AppleUSBPrinter DriverKit extension claims interface 0 exclusively. `detach_kernel_driver()` requires `sudo`. Do **not** call `usb.util.release_interface()` — hold the claim for the process lifetime. Releasing immediately allows the extension to reattach.

---

## Execution Model (Confirmed on Hardware, 2026-06-09)

This supersedes earlier, partially contradictory notes ("connected workflow executes
without green" and "two green presses" were both **wrong**).

- Jobs **queue** on receipt — the machine beeps once per job and does **not**
  execute while connected.
- ~2 s after queueing, the machine emits **`!JF 0;` per job** on EP IN. This is a
  **receipt acknowledgement**, *not* a completion signal — it arrives before any
  execution. (An earlier driver build treated it as completion and disconnected
  with the job unexecuted.)
- **One green press executes the entire queue in order** — a home job and an
  engrave job both ran on a single press.
- The last executed sequence persists in the buffer; pressing green again re-runs
  it. Cleared by power cycle.
- Disconnecting triggers a ~15 s end-of-stream timeout: the machine **re-beeps**
  for queued jobs but does **not** execute them unless armed (below).
- **Auto-execution:** `!CM 4;\x00\x00\x00\x01` (10 bytes) sent after a job arms it
  to execute after the disconnect timeout, pausing at the first `PD` for a green
  press if one is present. `PD` is the deliberate operator confirmation gate.
- **Job completion detection:** axis telemetry returning to 0 plus `!MN`
  heartbeats. Never `!JF`. (M20 IQ: `!ET` after `!CM 4;` = 1 instead; see
  open question 8.)
- `!ID 0;` only responds shortly after power-on, not while long-term idle
  (mechanism unknown — open question).

---

## Device → Host Packet Framing (Confirmed 2026-06-09)

Every machine response uses **counted framing**: `!XX N;` + exactly N payload
bytes, where N is the ASCII decimal before the `;`. Confirmed live:
`!ID 28;`+28B, `!MX 4;`+4B, `!JF 0;`+0B. A parser that assumes a fixed length
desynchronises on `!JF 0;`. Some firmware revisions prepend a stray NUL byte.

Axis telemetry streams continuously during execution on EP IN:
`!MX/!MY/!MZ` (absolute position, **0.01 mm units** — characterised Session 10
against known 90 mm travel), `!MN` (heartbeat counter), `!ME` (motion
end/encoder marker). Packets arrive in bursts. Real-time position tracking and
stall detection are feasible features.

---

## Coordinate System (Confirmed from Hardware)

- **Home (0,0) = back-left corner** of work area (nearest the gantry, farthest from the operator; top-left from the operator's view)
- **+X = mark moves right**
- **+Y = mark moves toward the operator** (the table translates away from the operator; confirmed with a felt-tip marker fiducial — supersedes the earlier provisional "front-left, +Y to back" reading)
- **1 unit = 0.01mm** (`UNITS_PER_MM = 100`) — confirmed from hardware: 20mm square measured 20mm, 90mm wordmark measured 90mm
- **Software work envelope:** 100 × 100mm
- **Physical envelope:** ~120 × 120mm (conservative safe limit)

**LightBurn / Y-up G-Code:** Pass `flip_y=True` to `gts_prepare.from_gcode()` or use `--flip-y` on the CLI. Applies: `y_machine = envelope_height_mm - y_source`.

---

## GTS Binary Format

Full normative specification: [`GTS_FORMAT.md`](GTS_FORMAT.md). Research notes:

- 94-byte header (`!MM88;` magic), setup block `DR MC VS VZ PZ DZ`, stroke
  blocks (`hdr / ZA / PD / segments / PU×3`), final return-to-home, **one** `JF`.
- Segment records: 12 raw bytes `>hhhhhh` = pw1, pw2, speed, accel, dx, dy;
  `accel=551` in every observed record. dx/dy are relative deltas.
- `DZ`/`PZ` have minimal effect on actual Z travel — depth is set by the physical
  spring-tension knob; the solenoid pulls a fixed distance: **≈ 6 mm stroke,
  measured 2026-06-09**. No force/pressure value has been confirmed in the
  protocol. Practical consequence: the tool tip must rest within ~6 mm of the
  work surface at pen-up (tool seating / work height is the adjustment, not
  protocol values).
- Per-job `!JF` receipt acks confirmed 1:1 on hardware: two jobs sent → two
  beeps → two `!JF 0;` acks (2026-06-09).
- `NR` is **not present in any captured job** — it was an early mistaken
  assumption, since ruled out against real captures. Do not emit.
- Emitting `JF` per stroke stops the machine after the first stroke.
- The ASCII `!PS/!OR/!MM` envelope is a Windows print-path artefact consumed by
  the spooler stack — it never reaches the wire on the direct USB path.
  (Separately, the vendor's bidirectional driver sends counted `!PS 20;` and
  `!DL 4;` commands for Point&Shoot. Those are machine commands, not the print
  envelope. See the Gravostyle 7 section below.)

### Stroke-header semantics — RESOLVED: RELATIVE (2026-06-09)

Confirmed by paired runs with felt-tip marking AND axis telemetry: absolute
headers + separate inter-stroke rapid double-offset stroke 2 to (60,80) mm
(`!MY` peak 7999); delta headers with no inter-stroke rapid landed both
strokes at commanded positions (`!MY` peak 3999 = 39.99 mm). Every wire
coordinate is a relative delta. `build_gts` emits the proven format
(byte-locked by regression test); `gts_preview` integrates deltas. The
earlier "inter-stroke rapid" reading of the wire layout was a
misinterpretation of the double-emission bug's own output. Telemetry doubles
as a 0.01 mm position-verification instrument — better than a ruler.

Newly observed during these runs: `!ET 4;` + uint32 at end of motion
(13 for the longer job, 9 for the shorter — plausibly execution seconds;
semantics provisional).

---

## !ID Identity Response

Reply to `!ID 0;\r\n`: `!ID 28;` + 28 bytes = 7 × big-endian int32:
boot_ver (major, minor), prog_ver (major, minor), platform_type, model_code,
model_code_alt. Live M20 Express: boot 1.2, prog 1.30, platform 4, model 0x0204,
alt 0.

**Platform types:** 3 = K2000/M20 standard, 4 = Sirius/M20 Express. Platform
type is a **firmware-family** identifier, not a product identifier —
implementations must key machine behaviour on **model_code**. (An early driver
build keyed profile selection on platform_type; profile auto-selection silently
never matched. Fixed 2026-06-09.)

---

## Model Code Table

| Code | Machine | Profile |
|------|---------|---------|
| `0x0204` | M20 / M20 Express | M20_PROFILE — **live confirmed** |
| `0x0205` | M20 XL | M20_PROFILE |
| `0x0206` | M20 Jewel | M20_PROFILE |
| `0x0207` | M20 PIX | M20_PROFILE |
| `0x0209` | M20 Jewel 2 | M20_PROFILE |
| `0x020D` | M20 IQ | M20_PROFILE — **live: identifies and queues jobs** (prog 1.81, 2026-10-28; needs header model_code, execution not yet confirmed) |
| `0x020E` | M20 XL IQ | M20_PROFILE |
| `0x020F` | M20 Jewel IQ | M20_PROFILE |
| `0x0202` | M40 | M40_PROFILE |
| `0x0203` | M40G | M40_PROFILE |
| `0x0210` | M40 IQ | M40_PROFILE |
| `0x0211` | M40G IQ | M40_PROFILE |
| `0x0212` | M10 Jewel | M10_JEWEL_PROFILE (negate_x) |

---

## Machine Compatibility

### Confirmed Compatible (same GTS format)
All use `MAC_BIN_Gii_2d.DLL`, `ModeBidi=1`, `XyzMul=400,-400,-400`:
M20, M20 XL, M20 IQ, M20 XL IQ, M20 PIX, M20 Jewel, M20 Jewel 2, M20 Jewel IQ, M40, M40G, M40 IQ, M40G IQ

### Conditional
| Machine | Difference | Profile |
|---------|------------|---------|
| M10 Jewel | `XyzMul=-400` — negate X | `M10_JEWEL_PROFILE` |
| IS400 IQ | `XyzMul=500` — scale × 1.25 | `IS400_IQ_PROFILE` |

Both read from the published GT Smartstream INF/GPD files, never confirmed on live hardware.

### Not Compatible
| Machine | Reason |
|---------|--------|
| IS200/IS400 (binary) | No GT Smartstream bidi support |
| IS6000/7000/8000 | 3D CNC driver, different protocol |
| IM4E | RS-232 serial only |
| All laser machines | Different driver stack entirely |

---

## Firmware

Both platform firmware files use `!VP N;` framing for upload. Firmware body is encrypted via a hardware OTP key — its contents cannot be read without physical chip access. Not required for the primary project goal.

**Sirius mainboard confirmed from photo (JDE 49726/F2600-C, 2026-06-09):**
CPU is a **Freescale ColdFire MCF5272VM66** (66 MHz) with a silkscreened
26-pin BDM header (bottom-right). The earlier H8S/2600 reference was a
misread of the Micron MT48LC2M32B9 SDRAM beside it. Motion engine is an
Altera **Cyclone II FPGA** (own JTAG header); per-axis drive is 3× ST
**L6258EX** PWM stepper drivers (Axe X/Y/Z). Consequence for any future
firmware study: a BDM dump yields ColdFire code, but real-time motion logic
likely lives in the FPGA bitstream — a much harder target and the true
comprehension bottleneck.

| Platform | Boot | Prog |
|----------|------|------|
| K2000 (M20 std) | v1.1 | v2.46 |
| Sirius (M20 Express) | v1.2 | v1.30 |
| Sirius (M20 IQ, live 2026-10-28) | v1.2 | v1.81 |
| IM4E | v1.2 | v2.19 |

---

## Gravograph Quick Capture Findings (2026-06-09)

Captured Quick driving the M20 through the RP2040 sniffer (11 captures,
data/quick_capture/). Headline: **Quick's wire format IS GTS exactly as documented here** — `!MM88;` header, the `0x0204`/`0x0DE4` header
constants, `FF FD` opcodes, and 12-byte segment records with pw1=pw2=1,
speed, accel=0x0227(551), dx/dy — byte-for-byte identical to our independent
implementation. Independent confirmation of the entire format.

Corrections and new facts from vendor ground truth:
- **`MC` is the SPINDLE enable, not "machine coordinates."** `MC 1`=spindle on,
  `MC 0`=off. Isolated by diffing spindle-on vs spindle-off job captures: the
  single changed byte was MC's argument. Our driver always sent MC 0 (correct
  for diamond drag; we never had spindle control).
- **`PZ` is ENGRAVING DEPTH**, driven by Quick's depth field: 0.01"→PZ 25,
  0.99"→PZ 100, default→PZ 0. Reopens our "PZ minimal effect" finding (which
  was measured with diamond drag + spring tension at PZ 30).
- **Material selection (alu vs steel) changes toolpath pass count, NOT any
  wire-level depth/force parameter** — identical setup blocks, different
  segment counts.
- **Quick's identification = our `!ID 0;`**, sent 3× with `!1B 0;` interleaved
  (new opcode, likely reset/init probe). Confirms our handshake is correct.
- Depth field is imperial inches on this install, UI-capped at ~0.393"≈10mm.

- **Machine→host origin report decoded (`11_set_center_xy`).** Jogging the head
  and confirming on the panel makes the M20 send `!MX`/`!MY` (live position,
  0.01mm) then **`!OR 8;`** carrying packed (X, Y) = the confirmed origin
  (captured: X=5002=50.02mm, Y=4887=48.87mm). `!OR` is a NEW opcode and the
  first machine-initiated response beyond passive telemetry. NOTE: this traffic
  is on EP2 (0x82 IN); the summariser was initially filtering EP1 only and
  missed it — fixed to keep both EP1 (OUT jobs) and EP2 (IN telemetry).

Open from these captures: the `13` (PZ 100 / 0.99") capture is anomalously
large (~500KB job) — not yet explained; `!1B` semantics; whether PZ has real
Z effect on our hardware across its range.

## M20 IQ on Linux (2026-10-28)

First live session on an **M20 IQ** (model_code 0x020D, platform 4,
boot 1.2 / prog 1.81) with rotary spindle and red laser pointer. It identified
and selected M20_PROFILE without changes, unprivileged on Linux behind a udev
rule (the kernel's `usblp` detaches cleanly).

**Header model_code is enforced.** Jobs built with the Express's `02 04` at
header offset 0x24 got a `!JF 0;` receipt ack but no beep, and green did
nothing. The same homing job with `02 0D` at 0x24 beeped twice, and the
machine also sent `!ME`, `!CM 4;` (value 1), and `!ET 4;` (value 1), which
the rejected job never produced. `send_gts` now stamps the identified
model_code into 0x24. Engrave-job execution on the IQ is not yet confirmed.

Also observed: after the rejected jobs, the motion monitor treated repeated
idle `!MY` status (Y holding at 46.17 mm) as motion and reported "done". The
completion heuristic was characterised on the Express and does not hold on
the IQ. (Fixed 2026-10-29: see open question 8.)

---

## Gravostyle 7 Static Analysis (2026-10-28)

**Method.** Read-only static analysis of the Gravostyle 7 Build 6 install
media (2015) for interoperability. Nothing was executed. The sources were:
plain-text post-processors (`POSTPROGS/*.MAC`), the US manual, and two DLLs
unpacked from the InstallShield cab:

- `mac_bin_gii_2d.dll`, the job writer. Opcodes were enumerated from the
  emit call sites. The DLL has a built-in text-trace mode whose format strings
  name several opcodes and header fields, and each function names itself in
  an error string (`UsiSendGoToProf`, `UsiStartAux`, …).
- `DriverGravoDLL.dll`, the bidirectional machine manager. Its exports carry
  method names (`CmdPointAndShootPlaque`, `SetPointeurRouge`, …).

Only facts are recorded here, no vendor code. None of the *vendor* findings
have been seen on the wire yet. Treat them as strong leads, not confirmation.

**Header model_code confirmed independently.** `G2_M20.MAC` has
`IdMachine=516` (0x0204), and `G2_M20_IQ.MAC` has `IdMachine=525` (0x020D).

**Opcode roles.** The job writer's internal function names (French) group
the opcodes:

| Vendor function | Meaning | Opcodes |
|---|---|---|
| `UsiSendGoToProf` | go to depth | `ZA` then `PD 0` |
| `UsiSendDegZentrePasse` | Z clearance between passes | `PU 0` |
| `UsiSendDegZsecurite` | Z safety height | `PU 1` |
| `UsiSendElemForSliceCur` | per-pass parameters | `VD VZ PZ VS VZ DZ` (+ `DR` if non-zero) |
| `UsiStartAux` / `UsiStopAux` | auxiliaries | `MC` (spindle), `OU` (outputs) |
| `UsiSetTypeDepl` | movement type | `2D` / `3D`, or `V2` after raster |
| `UsiSendMessage` | LCD message | `LB 0`, `LB <2 chars>`…, `NR 1`, `LB 1` |

Other opcodes and what ties them to their meaning:

- `VR`: only when `WithSpindleSpeed=1`, so spindle RPM.
- `TO n`: next to the "Turret position is [%d]" check, so the tool-changer turret position.
- `OP 0`: follows the explicit move to the plate (`ExplicitMoveULplate` + `AddCdeOP`) or table (`…table` + `AddCdeOT`) corner, so it sets the origin.
- `BD 0/1`: trace text says "Braille dispenser UP/DOWN".
- `ME n`: a counter emitted only for `TestMode` 1/3 (border tests).
- `RX`/`RY`/`C3`/`C4`/`PW`: only in the photo-raster path (8-bit bitmap library calls).

The complete table is in GTS_FORMAT.md §5.3. The trace mode labels segment
records `MOVE RATIO DANG DX DY [DZ]`, and has a separate `CIRC` record
(native arcs), whose layout is unmapped.

**Header variants.** Gravostyle 7 writes `!AS n;` (no photo mode) or
`!PH 72;` (`ModePH=1`, which includes the M20 IQ) instead of Quick's
`!MM88;`. Layouts are in GTS_FORMAT.md §5.7.

**Point&Shoot and the red pointer.** The post-processor has `RedLaserOk=1`
("laser pointer present") on the M20 IQ. The manual's Point&Shoot (set plate,
line or origin by jogging the red pointer) is implemented by
`CGestMacBidiGii::CmdPointAndShootPlaque/Ligne/NouvelleOrigine`, which send
`!DL 4;` + model_code, then `!PS 20;` + five int32 BE fields. The field
setters are exported:

| Field | Setter |
|---|---|
| 1. model_code | from `!ID` |
| 2. accessory type | `SetTypeAccessoire` |
| 3. accessory diameter | `SetDiametreAccess` |
| 4. red pointer | `SetPointeurRouge` |
| 5. Point&Shoot method | `SetMethodePS` |

Cancel is `!1B 0;`. The `*APF_Laser` exports send `!RA 32;` and appear to
belong to an automatic plate-feeder accessory, not the pointer. The pointer
is never switched inside a job: `RedLaserOk` is not read by the job writer.
The LED-vs-spindle test modes are carried in the header.

**M20 IQ post-processor parameters** (`G2_M20_IQ.MAC`):

| Parameter | Value |
|---|---|
| `ModePH` | 1 |
| `FIQ` | 1 |
| `Fmax` / `Frmax` | 3.0 m/min (M20: 1.5) |
| `Fzmax` | 6 (M20: 1.5) |
| `WithCoolant` | 1, `ValCoolantOn`/`Off` = +5/−5 |
| `WithAux0` | 1, values ±6 |
| `ZrefAuto` | 1 |
| `TestMode` | 0 |
| `MethodePS` | 0 |
| `AddCdeOP` / `AddCdeOT` | 1 |
| `RedLaserOk` | 1 |

**Also in the media:**

- `!BE 4;` appears in the firmware updater and driver installer (probably beep).
- `DriverGravoDLL.dll` parses `!NC`, `!TT` and `!RA` replies, and contains
  the literals `!PS6;` and `!OR6;` (no space), which differ from the
  `!OR 8;` captured from the Express. Their role is ⚠ OPEN.

---

## M20 IQ Hardware Probes (2026-10-29)

**Method.** `gts_probe.py` sends one change per case relative to a baseline
(a 10 mm square, diamond scribe, `MC 0`) and captures everything the machine
returns. Each run's report and raw dump are kept locally in `data/probes/`.
The machine was an M20 IQ+ (0x020D, prog 1.81) with **no LCD** (9-key panel),
a rotary spindle, a red pointer, and a vise. The operator manual (M20 series,
EN_C) was used to interpret panel behaviour. The origin is the centre of the
vise, so engrave-job probes were kept within a 20 mm box around (50, 50) mm.
Squares placed at (20, 20) mm hit the vise jaws.

**Baseline.** Engrave jobs execute on the IQ (also confirmed via the web UI).
Per queued job the IQ sends `!JF 0;` then `!ME` = 1001. A green press gives
`!CM 4;` = 1, then telemetry, `!ME` 1002→1004→1000 and `!ET`. A home job
reports `!ET` = 0.

**In-job opcodes** (one per run, all jobs executed normally):

| Probe | Result |
|---|---|
| `LB 0`, `LB "HI"`, `LB 1` | Accepted; nothing visible (no LCD) |
| …plus `NR 1` | **Pauses before the first stroke until green is pressed again.** During the pause the IQ sends `!CM 4;` = 3 and relays the message as `!LB 3;` + `"HI\0"`; a second green resumes (`!CM 4;` = 1) |
| `VD 15` in setup | Accepted; `!ET` 6 vs 5 baseline (one run) |
| `2D 0` in setup | Accepted; no change (`!ET` 5) |
| segment `accel` 100 vs 551 | 20 mm straight line: no visible or timing difference (`!ET` 7 both) |
| `OU +6` / `OU −6` | Accepted; nothing observable (no aux accessory). The manual's rear Sub-D 15 has four open-collector outputs: a candidate target |

**ASCII commands (no motion):**

- `!ID 0;` answered at connect and again 10 s later, but the machine had
  just been powered on, so this doesn't settle the long-idle question.
- `!BE 4;` + 1 → `!BE 8;` (1, 1). **No beep.**
- `!DL 4;` + model_code → `!DL 8;` (2170, 0).

**Point&Shoot (confirmed).** `!DL` + `!PS 20;` [0x020D, 0, 0, 1, 0] turns
the red pointer on. The operator jogs with the arrows (telemetry streams) and
presses **Check** (green does nothing). The machine beeps and replies
`!PS 16;` (6949, 4991, −1, −1), then the pointer turns off and the head homes.
The last telemetry before the confirm was (4778, 4991). The X difference,
2171, equals the `!DL` reply, so **`!DL` returns the pointer-to-tool offset**,
and method 0 reports the tool position over the aimed spot. The manual's
machine adjustment stores a separate "diode zero point" **in X only**, which
explains the 0 Y offset.

With `ps_method` = 1, each Check press gives its own `!PS 16;` with the raw
head position, (2496, 4222) and (5889, 7104), both matching telemetry exactly
with no offset. The pointer stayed on after two points. `!1B 0;` (sent with no
active session, or during one) turns the pointer off and homes the head. It
gets no reply, and the return move sends no telemetry. A Point&Shoot session
survives a USB reconnect.

**Method 0 needs two Check presses, and the origin does not move.** In a
repeat run the operator aimed the pointer at the scrap centre. Telemetry
read (4702, 4743), so telemetry follows the pointer spot during a session.
The first Check gave `!PS 16;` (6872, 4743, −1, −1), the spot + offset. The
session stayed open: green was ignored, and a job sent meanwhile was received
(`!JF`, `!ME` 1001) but did not start. A second Check gave `!PS 16;`
(0, 0, 4702, 4743) and the head homed. Green then ran the queued job, a
tool-up rapid to job (5, 5) mm parked at `NR`: telemetry (499, 499), i.e.
ordinary machine coordinates. **Floating origin is host-side.** The host must
add the shot point to the job itself. (The first method-0 run's "head home"
was the second press, not the later `!1B`.)

**Spindle (`MC`/`VR`).** Tested with no cutter: the tool was fitted reversed
(blunt end down) so plunges were harmless. A turning spindle is hard to see;
two early "no spin" results were wrong and were rerun.

| Job | `MC` | `VR` | `ZA`/`PD` plunge | Spindle |
|---|---|---|---|---|
| tool-up rapids, `MC 1` mid-job | 1 | — / 8000 | no | off |
| tool-up rapids, `MC 1` in setup | 1 | 8000 | no | off (rerun) |
| 10 mm square, `PZ 10` | 1 | — | yes | **on** (rerun) |
| 10 mm square, `PZ 10` | 1 | 8000 | yes | **on** |
| 10 mm square (baseline) | 0 | — | yes | off |

So **the IQ turns the spindle only with `MC 1` and the tool down**, and `VR`
is not required. The panel's Shift+✓ spins it regardless (no tool interlock).
`!ET` reported 10 for the tool-up spindle jobs and 0 for a tool-up job
without `MC 1`.

**`VR` does not change the speed** (as far as could be observed). The same
plunge job with `VR 4000` and then `VR 16000` spun at the same speed by eye
(the operator used a video tachometer but couldn't get a clean reading).
Laptop-microphone audio showed the same pattern in both runs: 174 Hz during
moves (steppers), and a 245–254 Hz tone only during the plunged square. If
that tone is the spindle, it would mean a fixed ≈ 14 700–15 200 rpm
(unconfirmed). `!ET` was 9 for both. `PZ` depth is still untested (needs a
real cutter).

**Spindle speed is not host-controllable on the M20 IQ** (desk research +
two runs, 2026-10-29). In the job writer (`mac_bin_gii_2d.dll`):

- `VR` is emitted only when `WithSpindleSpeed` ≠ 0 (default 0). No M20
  post-processor sets it; even the IS-series spindle machines ship with 0.
- Value: `(clamp(rpm, Smin, Smax) − Smin) × StoMac + SmMin`, truncated to
  16 bits. Defaults when the `.MAC` omits them (all M20s): Smin 5000,
  Smax 18 000, StoMac 1, SmMin 0. The IS machines set Smax 60 000,
  StoMac 0.1. A non-zero SmMin rescales StoMac so Smax maps to StoMac × Smax.
- Order: `VR`, then `MC 1` (spindle start).
  `SpindleRotationOnSvalue` suppresses `MC 1` when the S value is 0.
- The `!PH 72;` header has no spindle field.

On hardware, the `pz-vr-first` probe sent `VR` then `MC 1` before the first
stroke (vendor order), with the tool reversed. `VR 2000` and `VR 13000` gave
the same plunge tone: 246–252 Hz per second, and 295.0 vs 296.0 Hz
averaged over the plunge (< 0.5 % apart). Either `VR` reading (absolute rpm,
or offset from 5000) predicts a 2.6–6.5× difference. The operator heard at
most a very slight difference. The IQ spindle runs at a fixed speed;
`MC 1` with the tool down is the only control.

**Panel keys over USB** (passive capture). Jogging produces `!MX`/`!MY`
telemetry and bursts of `!CM 4;` = −1. Pointer on/off (Shift+◀) and spindle
on/off (Shift+✓) send **nothing**, so the host cannot know their state.

**Rotary diamond cut (`pz`, 2026-10-29).** Three real cuts on scrap, 10 mm
squares, `MC 1`, auto ZRef (descend, touch, back off, plunge):

| Run | Setup | `PZ` / `VS` / `VZ` | Result |
|---|---|---|---|
| 1 | no nose, pressure 4 | 10 / 25 / 25 | Very aggressive; tool slid up in the cutter button |
| 2 | no nose, pressure 4, tool re-tightened | 5 / 15 / 5 | Chatter and skipping; tool held |
| 3 | regulating nose, knob 2 notches, pressure 2 | 50 / 10 / 5 | Clean but light; knob → 5 notches and green pressed again: clean, good depth |

Without the nose the head goes to a fixed Z, so a 0.05 mm target is smaller
than the vise's 0.1 mm flatness spec: the tip skips the low spots and digs into
the high ones. With the nose, the scaled knob sets depth (0.025 mm/notch) and
`PZ` only sets how far past the touch-off the head goes to load the spring. In
run 3 `!MZ` read 2316 near the touch and then held 2366 through both passes:
50 counts for `PZ 50`. That fits `PZ` and IQ `!MZ` both in 0.01 mm (0.5 mm
overtravel, the manual's 0.5–1 mm guidance, p. 50) but rests on one sample
near the touch. The IQ's motorised Z also reached 22.1 and 16.2 mm on the
same stock before and after the tool was re-seated about 6 mm longer, again
consistent with 0.01 mm. (4b below is about the Express's solenoid Z.)

`!ET` was 10, 16 and 24 for runs 1–3, tracking the slower `VS`/`VZ`, which
supports the execution-time-in-seconds reading. **A green press after a job
finishes re-runs the last job** (`!CM 4;` = 1, same telemetry, same `!ET`)
with no new upload, so the operator can adjust the knob and re-cut.

---

## Resolved Questions (formerly open)

1. **Axis telemetry units** — resolved Session 10: absolute position, 0.01 mm
   units (100 units/mm), characterised against known 90 mm travel.
2. **Motion constants for duration estimation** — resolved Session 10: cruise
   velocity linear in VS at ~0.995 mm/s per VS unit; rapids ≈ engrave speed;
   implemented in `gts_optimise.estimate_duration()`.
3. **Execution model / green-press semantics** — resolved Session 11 (above).
4. **`!JF` meaning** — resolved Session 11: per-job receipt acknowledgement.

## Open Questions

1. **`!ID 0;` idle behaviour** — machine only responds shortly after power-on.
3. **Machine serial number — RESOLVED (negative), 2026-06-09.** The M20
   Express exposes NO serial over USB. Quick captures show: device-descriptor
   iSerialNumber index = 0 (no serial string exists), only string descriptor is
   "USB Printer", IEEE-1284 device ID (0xA1) returns empty MFG:;CMD:;MDL:;, and
   !ID model_code_alt = 0. Quick's licensing keys on something other than a
   machine serial.
4. **`accel=551` field** — constant in all captures. M20 IQ 2026-10-29:
   100 vs 551 on one straight 20 mm segment made no difference. Next: a
   multi-segment shape with corners, since the vendor trace calls the
   field `DANG` (likely an angle term).
4. **`!ET` packet semantics** — execution-time-in-seconds hypothesis
   strengthened: two byte-identical jobs both reported 9; a longer job
   reported 13; reproducible. Across all three runs the wall-clock motion
   window exceeds the value by a consistent ~4 s — possibly the home job's
   execution excluded, i.e. !ET may report the engrave job only.
4b. **`!MZ` telemetry scaling** — Z values (12 idle, 1295–2262 during
   pen-down dips) are incompatible with the 0.01 mm X/Y scale (22.6 mm >
   the ~6 mm solenoid stroke). Consistent with 0.001 mm units (2.26 mm ≈
   the shimmed tip-to-work gap) or a non-position counter. Do not treat
   !MZ as 0.01 mm position.
5. **`DZ` depth value** — "minimal effect" is from normal-range observation,
   not a systematic sweep; a `DZ 50` vs `DZ 5000` comparison has never been run.
6. **Vendor-only opcodes still untried**: `VR`, `TO`, `OP`, `3D`, `V2`,
   `ME`, `BD`, raster set. `LB`, `NR`, `VD`, `2D`, `OU`, `MC`/`VR` and
   Point&Shoot were tried on the M20 IQ 2026-10-29 (see that section).
   Spindle speed is fixed on the IQ (`VR` ignored in either order). With
   the nose fitted, `PZ` is spring overtravel (likely 0.01 mm, see the
   rotary diamond cut). Still open: a no-nose `PZ` sweep on flat stock.
7. **`DR` and `PW` meaning** — `DR` is a per-pass value ×1000, sent only when
   non-zero; `PW 15` is a raster-setup constant.
8. **IQ job-completion detection** — resolved in the driver 2026-10-29 from
   the probe dumps: once any `!CM` arrives, `_monitor_job` ignores axis
   telemetry and completes on the `!ET` after `!CM 4;` = 1 (`!CM` = 3 NR
   pauses extend the timeout). Axis motion now means a *changed* value, so
   repeated idle reports no longer arm the silence fallback. Confirmed
   live the same day: a `gts_ctl --send` of a 10 mm square returned on
   `!ET 7`, 12 s after `!CM 1`, with no early "done". Still open: whether
   the Express also sends one `!ET` per queue (it stays on the axis
   heuristic until then).
9. **Point&Shoot remainder** — normal end of a `ps_method` 1 session; the
   (0, 0) first pair of the closing method-0 reply. (Resolved 2026-10-29: the
   shot point does NOT become the job origin; the host must offset the job.)
10. **`!CM 4;` value set** — 1 (running), 3 (paused at `NR`), −1 (panel/jog
    mode) seen so far.
