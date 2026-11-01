"""The independent reader accounts for every byte of every golden job and
agrees with the driver's own preview parser on geometry."""
from __future__ import annotations

import json

import gts_preview
import pytest

from ggdesk.gts_read import Command, GtsFormatError, read_job
from ggdesk.numerics import to_mm
from tests.conftest import GOLDEN

MANIFEST = json.loads((GOLDEN / "manifest.json").read_text(encoding="utf-8"))
CASES = sorted(MANIFEST["cases"])


def _bytes(name: str) -> bytes:
    return (GOLDEN / MANIFEST["cases"][name]["output"]).read_bytes()


@pytest.mark.parametrize("name", CASES)
def test_reader_walks_every_golden(name: str) -> None:
    data = _bytes(name)
    job = read_job(data)
    last = job.records[-1]
    assert isinstance(last, Command) and last.op == "JF"
    assert sum(1 for c in job.commands if c.op == "JF") == 1
    assert job.positions()[-1] == (0, 0)          # returns home
    end = last.offset + 6
    assert end == len(data)                         # every byte accounted for


@pytest.mark.parametrize("name", CASES)
def test_reader_agrees_with_driver_preview(name: str) -> None:
    data = _bytes(name)
    strokes, _rapids, bounds = gts_preview.parse_gts(data)
    job = read_job(data)
    assert sum(1 for c in job.commands if c.op == "PD") == len(strokes)
    cut = job.cut_points()
    xs = [to_mm(p[0]) for p in cut]
    ys = [to_mm(p[1]) for p in cut]
    assert (min(xs), min(ys), max(xs), max(ys)) == pytest.approx(bounds)


def test_rotary_setup_decoded() -> None:
    job = read_job(_bytes("rotary_square_20mm"))
    assert job.setup()[:7] == [("DR", 0), ("MC", 1), ("VS", 10), ("VZ", 5),
                               ("PZ", 50), ("DZ", 500), ("VD", 15)]


@pytest.mark.parametrize("bad", [b"", b"!MM88;" + b"\0" * 10, b"XXXXXX" + b"\0" * 88])
def test_refuses_malformed(bad: bytes) -> None:
    with pytest.raises(GtsFormatError):
        read_job(bad)


def test_refuses_truncated_segment() -> None:
    data = _bytes("line_single")
    with pytest.raises(GtsFormatError):
        read_job(data + b"\x00\x01\x00")
