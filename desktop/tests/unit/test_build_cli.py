"""ggdesk build: writes the job, gates it, writes both reports; exit codes 0 / 1 / 2 / 3."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ggdesk import gate
from ggdesk.cli import main
from ggdesk.gate import Finding, GateReport, Severity
from tests.conftest import DESKTOP

EX = DESKTOP / "docs" / "examples"
FIXLIB = str(DESKTOP / "tests" / "fixtures" / "library")


def _build(tmp_path: Path, *extra: str, job: Path = EX / "asymmetric-f-arrow.ggj") -> tuple[int, Path]:
    out = tmp_path / "out.m20"
    rc = main(["build", str(job), "-o", str(out), "--recipe", "scrap-rotary-diamond-trace", *extra])
    return rc, out


def test_build_writes_bytes_and_reports(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc, out = _build(tmp_path)
    assert rc == 0
    data = out.read_bytes()
    golden = (DESKTOP / "tests" / "golden" / "outputs" / "asymmetric_f_arrow.m20").read_bytes()
    assert data == golden
    rep = GateReport.from_json((tmp_path / "out.gate.json").read_text(encoding="utf-8"))
    assert rep.bound_to(data) and rep.passed
    text = (tmp_path / "out.gate.txt").read_text(encoding="utf-8")
    assert text == rep.to_text()
    assert text in capsys.readouterr().out
    job_text = (EX / "asymmetric-f-arrow.ggj").read_text(encoding="utf-8")
    assert rep.job_sha256 == hashlib.sha256(job_text.encode("utf-8")).hexdigest()


def test_selection_flags(tmp_path: Path) -> None:
    rc, out = _build(tmp_path, "--set", "pz=80", "--keep-out", "80,0,90,10", "--library", FIXLIB,
                     job=EX / "square-10mm.ggj")
    assert rc == 0
    assert out.read_bytes() == (DESKTOP / "tests" / "golden" / "outputs" / "square_10mm_pz80.m20").read_bytes()
    rep = GateReport.from_json((tmp_path / "out.gate.json").read_text(encoding="utf-8"))
    assert rep.selection.overrides == {"pz": 80}
    assert rep.selection.extra_keep_outs == (((80.0, 0.0), (90.0, 0.0), (90.0, 10.0), (80.0, 10.0)),)


def test_refused_exits_3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class AlwaysHard:
        id, severity, title = "HX", Severity.HARD, "test"

        def check(self, data: bytes, job: object, inputs: object) -> list[Finding]:
            return [Finding("HX", Severity.HARD, "test refusal")]

    monkeypatch.setattr(gate, "RULES", (AlwaysHard(),))
    rc, out = _build(tmp_path)
    assert rc == 3
    assert out.is_file()   # the bytes are written; the report says they are refused
    rep = GateReport.from_json((tmp_path / "out.gate.json").read_text(encoding="utf-8"))
    assert not rep.passed and rep.rules_run == ("HX",)


def test_build_error_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc, out = _build(tmp_path, job=EX / "fill-square-hole.ggj")
    assert rc == 1
    assert "fill operations are not implemented" in capsys.readouterr().err
    assert not out.exists()


def test_bad_job_file_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.ggj"
    bad.write_text("{}", encoding="utf-8")
    assert _build(tmp_path, job=bad)[0] == 1
    assert _build(tmp_path, job=tmp_path / "missing.ggj")[0] == 1


def test_usage_errors_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "o.m20"
    assert main(["build", str(EX / "square-10mm.ggj"), "-o", str(out)]) == 2             # no --recipe
    assert "--recipe is required" in capsys.readouterr().err
    assert _build(tmp_path, "--set", "pz")[0] == 2
    assert _build(tmp_path, "--keep-out", "1,2,3")[0] == 2
    with pytest.raises(SystemExit) as e:
        main(["build", str(EX / "square-10mm.ggj")])                                      # no -o
    assert e.value.code == 2
    assert not out.exists()
