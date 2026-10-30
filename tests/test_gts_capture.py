"""tests/test_gts_capture.py — Summariser tests (pure, no USB)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from gts_capture import CaptureSummary


def _motor(axis, value):
    return {'type': 'motor', 'axis': axis, 'value': value,
            'raw': b'\x00' * 10, 'text': ''}

def _ack(cmd, value):
    return {'type': 'ack', 'cmd': cmd, 'value': value,
            'raw': b'\x00' * (6 if value is None else 10), 'text': ''}

def _id_packet():
    return {'type': 'long', 'platform_type': 4, 'model_code': 0x0204,
            'boot_ver': '1.2', 'prog_ver': '1.30', 'platform': 'M20Express',
            'text': ''}


def test_motor_burst_collapses_to_one_line():
    s = CaptureSummary()
    for v in range(0, 9001, 100):          # 91 monotonic !MX packets
        s.add(_motor('X', v))
    report = s.render(duration_s=10.0)
    assert report.count('!MX') == 1
    assert '\u00d791' in report and '0\u20139000' in report
    assert 'monotonic\u2191' in report

def test_interleaved_axes_stay_in_order():
    s = CaptureSummary()
    for v in (1, 2, 3): s.add(_motor('X', v))
    s.add(_motor('Y', 5))
    for v in (4, 5): s.add(_motor('X', v))
    report = s.render(duration_s=1.0)
    x_first = report.index('!MX'); y = report.index('!MY')
    x_second = report.index('!MX', x_first + 1)
    assert x_first < y < x_second          # three runs, arrival order

def test_identical_acks_collapse():
    s = CaptureSummary()
    for _ in range(5): s.add(_ack('!MN 4;', 0x1F5))
    report = s.render(duration_s=1.0)
    assert report.count('!MN') == 1 and '\u00d75' in report

def test_id_packet_renders_fields():
    s = CaptureSummary()
    s.add(_id_packet())
    report = s.render(duration_s=1.0,
                      machine={'vid': 0xFFFD, 'pid': 1, 'platform': 4,
                               'model_code': 0x0204, 'boot_ver': '1.2',
                               'prog_ver': '1.30', 'profile': 'M20'})
    assert 'model=0x0204' in report and 'boot=1.2' in report
    assert '(M20)' in report               # model code resolved to a name

def test_unknown_bytes_capped_and_sectioned():
    s = CaptureSummary(unknown_max_items=3, unknown_max_bytes=4)
    for i in range(6):
        s.add(f'[BIN] {"aa " * 10}'.strip())
    report = s.render(duration_s=1.0)
    assert report.count('UNRECOGNISED') == 3
    assert 'omitted' in report
    # hex per entry capped at 4 bytes
    line = [l for l in report.splitlines() if 'UNRECOGNISED' in l][0]
    assert line.count('aa') == 4 and '(10B)' in line

def test_trailing_buffer_reported():
    s = CaptureSummary()
    report = s.render(duration_s=1.0, trailing_buf=b'\xde\xad\xbe\xef')
    assert 'unparsed trailing buffer (4B)' in report
    assert 'de ad be ef' in report

def test_report_size_hard_cap():
    s = CaptureSummary(cap_bytes=2048)
    for i in range(2000):                  # alternate so nothing collapses
        s.add(_ack('!TU 4;' if i % 2 else '!GA 4;', i))
    report = s.render(duration_s=60.0)
    assert len(report.encode()) <= 2048
    assert 'elided (size cap)' in report

def test_tx_log_included():
    s = CaptureSummary()
    s.add_tx('GTS job from test.m20 (268 bytes)')
    report = s.render(duration_s=1.0)
    assert 'tx (sent by this tool)' in report
    assert 'test.m20 (268 bytes)' in report

def test_ack_payloads_rendered_not_dropped():
    from gts_api import decode_ack_payload
    def ack(cmd, payload):
        value, values, label = decode_ack_payload(payload)
        return {'type': 'ack', 'cmd': cmd, 'value': value, 'values': values,
                'label': label, 'payload': payload,
                'raw': cmd.encode() + payload, 'text': ''}
    s = CaptureSummary()
    s.add(ack('!DL 8;', b'\x00\x00\x08z\x00\x00\x00\x00'))
    s.add(ack('!LB 3;', b'HI\x00'))
    # two different !PS replies back to back must not collapse
    s.add(ack('!PS 16;', b'\x00\x00\x1a\xd8\x00\x00\x12\x87' + b'\xff' * 8))
    s.add(ack('!PS 16;', b'\x00\x00\x00\x00\x00\x00\x00\x00' + b'\xff' * 8))
    s.add(ack('!JF 0;', b''))
    report = s.render(duration_s=1.0)
    assert 'values=(2170, 0)' in report
    assert "label='HI'" in report
    assert 'values=(6872, 4743, -1, -1)' in report
    assert 'values=(0, 0, -1, -1)' in report
    assert report.count('(no payload)') == 1      # only the genuine !JF 0;
