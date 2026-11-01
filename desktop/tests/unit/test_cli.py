from __future__ import annotations

from pathlib import Path

import pytest

from ggdesk.cli import main
from tests.conftest import GOLDEN


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == 0
    assert capsys.readouterr().out.startswith("ggdesk ")


def test_inspect_golden(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["inspect", str(GOLDEN / "outputs" / "square_20mm.m20")]) == 0
    out = capsys.readouterr().out
    assert "setup       DR 0 MC 0 VS 25 VZ 25 PZ 30 DZ 500" in out
    assert "ends home   yes" in out
    assert "cut mm      X 10.00..30.00  Y 10.00..30.00" in out
    assert "1 (final record)" in out


def test_inspect_rejects_garbage(tmp_path: Path) -> None:
    bad = tmp_path / "bad.m20"
    bad.write_bytes(b"not a job")
    assert main(["inspect", str(bad)]) == 1
