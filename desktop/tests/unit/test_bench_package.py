"""The committed bench package matches what the current code builds (Linux and Windows CI)."""
from __future__ import annotations

import importlib.util
import json
import sys

from ggdesk.gate import GateReport
from tests.conftest import DESKTOP

BENCH = DESKTOP / "bench"


def _make_bench():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("make_bench", BENCH / "make_bench.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["make_bench"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_bench_package_up_to_date() -> None:
    assert _make_bench().main([]) == 0


def test_every_bench_job_passes_the_gate_and_is_bound() -> None:
    mb = _make_bench()
    for e in mb.ENTRIES:
        m20 = BENCH / e.stage / f"{e.name}.m20"
        rep = GateReport.from_json((BENCH / e.stage / f"{e.name}.gate.json").read_text(encoding="utf-8"))
        assert rep.passed and rep.bound_to(m20.read_bytes()), e.name
        assert rep.selection.fixture == "bare-bed"
        assert json.loads((BENCH / e.stage / e.job).read_text(encoding="utf-8"))["part"] == "bench-scrap-40"
