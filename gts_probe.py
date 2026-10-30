#!/usr/bin/env python3
"""
gts_probe.py — Targeted hardware probes for unconfirmed protocol features.

Each case changes ONE thing relative to a known-good baseline (a 10 mm
square centred at (50, 50) mm, pen/drag tool, MC 0) and captures everything the
machine sends back, using the same decoder as gts_capture.py.

    python gts_probe.py list
    python gts_probe.py run square
    python gts_probe.py run accel --accel 1100 --duration 60

Reports land in data/probes/<timestamp>-<case>.txt with a raw RX dump
beside them (.bin). Jobs are stamped with the identified model_code, so
they are accepted by an M20 IQ as well as an Express. Cases are listed in
the order they should be run: no-motion probes first, spindle last.
"""

import argparse
import os
import struct
import sys
import time

from gts_api import GTSConnection, MAGIC, _cmd, _seg, build_gts, build_home_gts
from gts_capture import CaptureSummary

HERE      = os.path.dirname(os.path.abspath(__file__))
PROBE_DIR = os.path.join(HERE, 'data', 'probes')

HEADER_LEN = 94
SETUP_LEN  = 6 * 6         # DR MC VS VZ PZ DZ
TRAILER    = 12 + 6        # return-to-home segment + JF

SQUARE = [(4500, 4500, [(1000, 0), (0, 1000), (-1000, 0), (0, -1000)])]


def counted(tag: str, *ints: int) -> bytes:
    """Host->machine counted command: '!XX N;' + N bytes of int32 BE."""
    payload = b''.join(struct.pack('>i', v) for v in ints)
    return f'!{tag} {len(payload)};'.encode('ascii') + payload


def square(pre: bytes = b'', post: bytes = b'', setup: bytes = b'',
           mc: int = 0, pz: int = None) -> bytes:
    """
    Baseline square with opcodes spliced in: `setup` after the setup block,
    `pre` before the first stroke, `post` before the return-to-home.
    """
    kw = {} if pz is None else {'pz': pz}
    job = bytearray(build_gts(SQUARE, **kw))
    struct.pack_into('>H', job, HEADER_LEN + 6 + 4, mc)    # MC argument
    split = HEADER_LEN + SETUP_LEN
    return bytes(job[:split] + setup + pre + job[split:-TRAILER]
                 + post + job[-TRAILER:])


def line_job(accel: int, length_units: int = 2000) -> bytes:
    """One 20 mm horizontal line (x 40-60, y 50 mm) with a chosen segment accel."""
    job = bytearray(build_gts([(4000, 5000, [(length_units, 0)])]))
    seg_at = HEADER_LEN + SETUP_LEN + 12 + 12    # header seg, ZA, PD
    struct.pack_into('>h', job, seg_at + 6, accel)
    return bytes(job)


def lcd_text(text: str) -> bytes:
    """LB carries two ASCII chars per opcode."""
    text = text + ' ' * (len(text) % 2)
    return b''.join(_cmd(b'LB', (ord(a) << 8) | ord(b))
                    for a, b in zip(text[::2], text[1::2]))


def parked_rapid(dx: int = 500, dy: int = 500) -> bytes:
    """
    Tool-up rapid to job (dx, dy), park at NR 1 until green, rapid back.
    No ZA/PD anywhere, so the tool never descends.
    """
    job = bytearray(build_home_gts()[:HEADER_LEN])
    job += _cmd(b'DR', 0) + _cmd(b'MC', 0) + _cmd(b'VS', 25) + _cmd(b'VZ', 25)
    job += _cmd(b'PU', 1) + _seg(dx, dy) + _cmd(b'NR', 1) + _seg(-dx, -dy)
    job += _cmd(b'JF', 0)
    return bytes(job)


def spindle_rapid(rpm: int = None, early: bool = False) -> bytes:
    """
    Spindle on with the tool UP for three 20 mm out-and-back rapids inside
    the centre box (x 40-60, y 50 mm), then off. No ZA/PD anywhere, so the
    spindle never descends.
    """
    job = bytearray(build_home_gts()[:HEADER_LEN])
    job += _cmd(b'DR', 0)
    if early:                                  # Quick-style: MC 1 in setup
        job += _cmd(b'MC', 1)
    job += _cmd(b'VS', 25) + _cmd(b'VZ', 25)
    if rpm is not None:
        job += _cmd(b'VR', rpm)
    job += _cmd(b'PU', 1) + _seg(4000, 5000)
    if not early:
        job += _cmd(b'MC', 1)
    job += (_seg(2000, 0) + _seg(-2000, 0)) * 3
    job += _cmd(b'MC', 0) + _seg(-4000, -5000) + _cmd(b'PU', 1) + _cmd(b'JF', 0)
    return bytes(job)


# ---------------------------------------------------------------------------
# Cases: name -> (stage, what it tests, builder(args, model_code) -> [steps])
# A step is ('job', bytes) — homed + stamped like send_gts — or
# ('raw', bytes) sent verbatim, or ('wait', seconds).
# ---------------------------------------------------------------------------

CASES = {
    'ident': ('A no motion',
              'Does !ID 0; answer after the machine has been idle?',
              lambda a, mc: [('wait', 10), ('raw', b'!ID 0;\r\n')]),
    'beep': ('A no motion',
             '!BE 4; + int32 — expect a beep (seen only in vendor installers)',
             lambda a, mc: [('raw', counted('BE', a.value or 1))]),
    'dl': ('A no motion',
           '!DL 4; + model_code alone — what does the machine reply?',
           lambda a, mc: [('raw', counted('DL', mc))]),

    'home': ('B baseline',
             'Home job only (DR 0, MC 0, PU 1, JF) — press green to home the head',
             lambda a, mc: [('raw', build_home_gts())]),
    'square': ('B baseline',
               'GATE: 10 mm square centred at (50,50) — does an engrave job execute on this machine?',
               lambda a, mc: [('job', square())]),

    'lcd': ('C one opcode',
            'LB 0, LB "HI", LB 1 before the first stroke — text on the LCD?',
            lambda a, mc: [('job', square(pre=_cmd(b'LB', 0) + lcd_text('HI')
                                          + _cmd(b'LB', 1)))]),
    'lcd-pause': ('C one opcode',
                  'As lcd, plus NR 1 — does it wait for the operator?',
                  lambda a, mc: [('job', square(pre=_cmd(b'LB', 0) + lcd_text('HI')
                                                + _cmd(b'NR', 1) + _cmd(b'LB', 1)))]),
    'vd': ('C one opcode',
           'VD 15 (plunge speed) in the setup block — accepted, slower PD?',
           lambda a, mc: [('job', square(setup=_cmd(b'VD', a.value or 15)))]),
    '2d': ('C one opcode',
           '2D 0 (movement type) in the setup block — accepted unchanged?',
           lambda a, mc: [('job', square(setup=_cmd(b'2D', 0)))]),
    'accel': ('C one opcode',
              '20 mm line with segment accel=--accel (run 551 first, then others); compare !MX timing',
              lambda a, mc: [('job', line_job(a.accel))]),
    'aux': ('C one opcode',
            'OU +6 before the square, OU -6 after — any audible/visible output?',
            lambda a, mc: [('job', square(pre=_cmd(b'OU', 6), post=_cmd(b'OU', -6)))]),
    'coolant': ('C one opcode',
                'OU +5 / OU -5 (coolant) around the square',
                lambda a, mc: [('job', square(pre=_cmd(b'OU', 5), post=_cmd(b'OU', -5)))]),

    'ps': ('D pointer',
           'Point&Shoot: !DL + !PS 20 [mc, accessory 0, dia 0, red 1, method 0]; jog, press Enter',
           lambda a, mc: [('raw', counted('DL', mc)),
                          ('raw', counted('PS', mc, 0, 0, 1, 0))]),
    'ps-abort': ('D pointer',
                 'Point&Shoot, then !1B 0; after 25 s while the pointer is still live — does cancel work?',
                 lambda a, mc: [('raw', counted('DL', mc)),
                                ('raw', counted('PS', mc, 0, 0, 1, 0)),
                                ('wait', 25), ('raw', b'!1B 0;')]),
    'ps-method': ('D pointer',
                  'Point&Shoot with ps_method=--value (default 1) — a second point requested?',
                  lambda a, mc: [('raw', counted('DL', mc)),
                                 ('raw', counted('PS', mc, 0, 0, 1,
                                                 1 if a.value is None else a.value))]),
    'listen': ('D pointer',
               'Send nothing; capture what panel keys (Shift+Left pointer, arrows, Check) report',
               lambda a, mc: []),
    'origin-probe': ('D pointer',
                     'After a ps shot: tool-up rapid to job (5,5) mm, NO home first, park at NR until green',
                     lambda a, mc: [('raw', parked_rapid())]),
    'ps-cancel': ('D pointer',
                  '!1B 0; — cancel Point&Shoot (head to origin, pointer off)',
                  lambda a, mc: [('raw', b'!1B 0;')]),

    'spindle': ('E spindle — CUTTER, tool up',
                'MC 1 with tool up over three 20 mm rapids at the centre — does the spindle run?',
                lambda a, mc: [('job', spindle_rapid())]),
    'spindle-vr': ('E spindle — CUTTER, tool up',
                   'As spindle, plus VR --value (rpm) — audible speed change?',
                   lambda a, mc: [('job', spindle_rapid(rpm=a.value or 8000))]),
    'spindle-setup': ('E spindle — CUTTER, tool up',
                      'MC 1 in the setup block (as Quick sends it), VR --value, same tool-up rapids',
                      lambda a, mc: [('job', spindle_rapid(rpm=a.value or 8000, early=True))]),
    'pz-vr': ('E spindle — CUTTER, scrap stock',
              'As pz (PZ 10) plus VR --value rpm in the setup block — spindle with speed + plunge',
              lambda a, mc: [('job', square(mc=1, pz=10, setup=_cmd(b'VR', a.value or 8000),
                                            post=_cmd(b'MC', 0)))]),
    'pz': ('E spindle — CUTTER, scrap stock',
           'Square cut with MC 1 at PZ --value; measure the depth (hypothesis: 0.01 mm units)',
           lambda a, mc: [('job', square(mc=1, pz=a.value or 10, post=_cmd(b'MC', 0)))]),
}


def run(case: str, args) -> str:
    stage, desc, build = CASES[case]
    summary = CaptureSummary(cap_bytes=32768)
    raw = []
    conn = GTSConnection(verbose=args.verbose)
    conn.add_tap(summary.add)
    conn.add_raw_tap(raw.append)

    print('Connecting (waiting up to 60s)...')
    if not conn.connect(timeout_s=60.0, wait=True):
        raise SystemExit('Machine not found on USB. Check power and cable.')
    summary.add_tx('!ID 0; (identity query, sent during connect)')
    print(f'[{case}] {desc}')

    try:
        for kind, val in build(args, conn.model_code):
            if kind == 'wait':
                time.sleep(val)
                continue
            if kind == 'job':
                home = conn._stamp_model_code(build_home_gts())
                job = conn._stamp_model_code(val)
                summary.add_tx(f'home job ({len(home)}B)')
                conn.send_raw(home)
                summary.add_tx(f'probe job ({len(job)}B): '
                               f'{job[HEADER_LEN:].hex(" ")[:240]}')
                conn.send_raw(job)
            else:
                val = conn._stamp_model_code(val)   # no-op unless GTS
                summary.add_tx(f'raw ({len(val)}B): {val!r}')
                conn.send_raw(val)

        print(f'Capturing for {args.duration:.0f}s — press green if the job '
              f'beeped; note anything you see/hear. Ctrl-C to stop early.')
        try:
            time.sleep(args.duration)
        except KeyboardInterrupt:
            print('\nStopped early.')
        notes = args.notes
        if notes is None and sys.stdin.isatty():
            notes = input('Observations (one line, Enter to skip): ').strip()
        machine = {'vid': conn.vid, 'pid': conn.pid,
                   'platform': conn.config_code, 'model_code': conn.model_code,
                   'boot_ver': conn.boot_ver, 'prog_ver': conn.prog_ver,
                   'profile': conn.profile.name}
        trailing = bytes(conn._rx_buf)
    finally:
        conn.disconnect()

    report = (f'probe: {case}  ({stage})\n{desc}\n'
              f'observations: {notes or "(none)"}\n\n'
              + summary.render(machine=machine, duration_s=args.duration,
                               trailing_buf=trailing))
    os.makedirs(PROBE_DIR, exist_ok=True)
    base = os.path.join(PROBE_DIR, time.strftime('%Y%m%d-%H%M%S') + f'-{case}')
    with open(base + '.txt', 'w') as f:
        f.write(report)
    with open(base + '.bin', 'wb') as f:
        f.write(b''.join(raw))
    print(report)
    print(f'Report written → {base}.txt')
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('list', help='List probe cases in run order')
    r = sub.add_parser('run', help='Run one probe case')
    r.add_argument('case', choices=list(CASES))
    r.add_argument('--duration', type=float, default=45.0)
    r.add_argument('--value', type=int, default=None,
                   help='Case parameter (beep arg, VD speed, VR rpm, PZ depth)')
    r.add_argument('--accel', type=int, default=551)
    r.add_argument('--dry-run', action='store_true',
                   help='Print the bytes that would be sent; no USB')
    r.add_argument('--notes', default=None,
                   help='Observations to record (skips the prompt)')
    r.add_argument('--verbose', action='store_true')
    args = ap.parse_args()

    if args.cmd == 'list':
        for name, (stage, desc, _) in CASES.items():
            print(f'{stage:32s} {name:11s} {desc}')
        return
    if args.dry_run:
        for kind, val in CASES[args.case][2](args, 0x020D):
            if kind == 'job':
                assert val.startswith(MAGIC)
                print(f'job ({len(val)}B) body: {val[HEADER_LEN:].hex(" ")}')
            else:
                print(f'{kind}: {val!r}')
        return
    run(args.case, args)


if __name__ == '__main__':
    main()
