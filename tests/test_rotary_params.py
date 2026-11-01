"""Rotary setup parameters (MC, VZ, VD) and the PZ/DZ naming fix.

Anchor: the builder's rotary output must equal, byte for byte, the job
gts_probe.py built for the clean rotary diamond cut on the M20 IQ
(PROTOCOL_FINDINGS.md, "Rotary diamond cut", run 3: MC 1, PZ 50, VS 10,
VZ 5, MC 0 before the return home).
"""
import warnings

import pytest

from gts_api import (DEFAULT_DZ, DEFAULT_PZ, MC_ON, _cmd, build_gts)
from gts_prepare import from_gcode, square
import gts_probe

SQUARE = gts_probe.SQUARE
SETUP_AT = 94           # header length


def _setup_ops(job: bytes, n: int):
    """Decode the first n opcode commands after the header."""
    ops = []
    for i in range(n):
        rec = job[SETUP_AT + 6 * i: SETUP_AT + 6 * (i + 1)]
        assert rec[:2] == b'\xff\xfd'
        ops.append((rec[2:4].decode(), int.from_bytes(rec[4:6], 'big')))
    return ops


def test_defaults_unchanged():
    """No new arguments -> the same bytes as the Express-era setup."""
    job = build_gts(SQUARE)
    assert _setup_ops(job, 6) == [('DR', 0), ('MC', 0), ('VS', 25), ('VZ', 25),
                                  ('PZ', DEFAULT_PZ), ('DZ', DEFAULT_DZ)]
    assert b'\xff\xfdVD' not in job
    assert job.count(b'\xff\xfdMC') == 1


def test_builder_matches_probe_run3_bytes():
    probe = gts_probe.square(mc=1, pz=50, speed=10, vz=5, post=_cmd(b'MC', 0))
    built = build_gts(SQUARE, speed=10, pz=50, mc=MC_ON, vz=5)
    assert built == probe


def test_rotary_setup_and_spindle_off_before_home():
    job = build_gts(SQUARE, speed=10, pz=50, mc=1, vz=5, vd=15)
    assert _setup_ops(job, 7) == [('DR', 0), ('MC', 1), ('VS', 10), ('VZ', 5),
                                  ('PZ', 50), ('DZ', DEFAULT_DZ), ('VD', 15)]
    # MC 0, then the 12-byte return-home record, then JF
    assert job[-6:] == _cmd(b'JF', 0)
    assert job[-24:-18] == _cmd(b'MC', 0)


@pytest.mark.parametrize('kw', [{'mc': 2}, {'pz': -1}, {'vz': 70000},
                                {'vd': -5}, {'mc': True}])
def test_out_of_range_refused(kw):
    with pytest.raises(ValueError):
        build_gts(SQUARE, **kw)


GC = 'G21 G90\nG0 X45 Y45\nG1 Z-1\nG1 X55\nG1 Y55\nG1 X45\nG1 Y45\nG0 Z5\n'


def test_prepare_passes_rotary_params():
    job = from_gcode(GC, speed=10, pz=50, mc=1, vz=5, vd=15, optimise=False)
    assert _setup_ops(job, 7)[1:] == [('MC', 1), ('VS', 10), ('VZ', 5),
                                      ('PZ', 50), ('DZ', DEFAULT_DZ), ('VD', 15)]


def test_deprecated_names_keep_old_mapping():
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        new = from_gcode(GC, pz=40, dz=300, optimise=False)
    with pytest.warns(DeprecationWarning):
        old = from_gcode(GC, lift=40, depth=300, optimise=False)
    assert old == new
    with pytest.warns(DeprecationWarning):
        assert square(depth=300) == square(dz=300)


def test_deprecated_and_new_together_refused():
    with pytest.raises(ValueError):
        from_gcode(GC, pz=40, lift=40)
