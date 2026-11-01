"""Desktop goldens (tests/golden/) recomputed on every platform, and the orientation lock.

Goldens are the test: never regenerate one to make this pass. An intended output change
is made with `python tests/golden/make_goldens.py --write` in a commit that explains why.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from ggdesk import gts_read
from ggdesk.library import Library
from tests.golden import make_goldens as mg


@pytest.fixture(scope="module")
def lib() -> Library:
    return mg.snapshot_library()


REQUIRED = ("asymmetric_f_arrow", "square_10mm", "square_10mm_pz80", "multi_stroke")


def test_required_cases_exist() -> None:
    assert set(REQUIRED) <= set(mg.case_names())


@pytest.mark.parametrize("name", mg.case_names())
def test_golden_bytes(name: str, lib: Library) -> None:
    data = mg.build_case(name, lib).data
    golden = (mg.OUTPUTS / f"{name}.m20").read_bytes()
    assert data == golden, f"{name}: build output differs from the golden"
    entry = json.loads(mg.MANIFEST.read_text(encoding="utf-8"))["cases"][name]
    assert entry == {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def test_check_mode_is_clean() -> None:
    assert mg.check() == []


def test_pz80_differs_only_in_pz(lib: Library) -> None:
    a = gts_read.read_job(mg.build_case("square_10mm", lib).data)
    b = gts_read.read_job(mg.build_case("square_10mm_pz80", lib).data)
    assert dict(a.setup())["PZ"] == 50 and dict(b.setup())["PZ"] == 80
    assert [s.points for s in a.strokes()] == [s.points for s in b.strokes()]


# --- orientation lock --------------------------------------------------------
# Part frame: +X right, +Y up as the operator reads the part. Machine frame: home back-left,
# +X right, +Y TOWARD THE OPERATOR. bare-bed nest centre puts the part origin at (50, 50) mm.

def _cut_points(lib: Library) -> set[tuple[int, int]]:
    job = gts_read.read_job((mg.OUTPUTS / "asymmetric_f_arrow.m20").read_bytes())
    assert job.model_code == 0x020D
    return {p for s in job.strokes() for p in s.points}


def _stroke_with(lib: Library, *pts: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    job = gts_read.read_job((mg.OUTPUTS / "asymmetric_f_arrow.m20").read_bytes())
    for s in job.strokes():
        if all(p in s.points for p in pts):
            return s.points
    raise AssertionError(f"no decoded stroke through {pts}")


def test_orientation_x_stem_left_of_x_arrow(lib: Library) -> None:
    stem = _stroke_with(lib, (3600, 4800), (3600, 3600))          # F stem, part x = -14
    arrow_tip = (5800, 6000)                                      # +X arrow tip, part (8, -10)
    assert arrow_tip in _cut_points(lib)
    assert max(x for x, _ in stem) < arrow_tip[0]


def test_orientation_f_top_has_smaller_machine_y_than_bottom(lib: Library) -> None:
    stem = _stroke_with(lib, (3600, 4800), (3600, 3600))
    top_y = 50_00 - 14_00      # part y = 14
    bottom_y = 50_00 - 2_00    # part y = 2
    assert top_y < bottom_y
    ys = [y for _, y in stem]
    assert min(ys) == top_y and max(ys) == bottom_y
    # the F's top bar runs right from the top of the stem
    assert (4200, top_y) in stem


def test_orientation_crosshair_centre_at_machine_50_50(lib: Library) -> None:
    v = _stroke_with(lib, (5000, 4700), (5000, 5300))
    h = _stroke_with(lib, (4700, 5000), (5300, 5000))
    # the two crosshair strokes cross at (50.00, 50.00) mm
    assert {x for x, _ in v} == {5000} and {y for _, y in h} == {5000}


def test_orientation_y_arrow_tip(lib: Library) -> None:
    tip = (6200, 4500)            # part (12, 5) -> machine (62.00, 45.00) mm
    shaft = _stroke_with(lib, (6200, 5500), tip)
    head = _stroke_with(lib, (6000, 4700), tip, (6400, 4700))
    assert tip in shaft and head[1] == tip
    # the +Y arrow points away from the operator: its tip has the smallest machine Y of the shaft
    assert tip[1] == min(y for _, y in shaft)
