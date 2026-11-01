"""ggdesk pattern: --list, writing the job, --build (bytes, gate reports, SVG as build and preview
would write them) and the exit codes 0 / 1 / 2 / 3 of `ggdesk build`."""
from __future__ import annotations

from pathlib import Path

import pytest

from ggdesk import gate
from ggdesk.cli import main
from ggdesk.gate import Finding, GateReport, Severity
from ggdesk.patterns import PATTERNS
from tests.conftest import DESKTOP

GOLDEN = DESKTOP / "tests" / "golden"
TRACE = ["--recipe", "scrap-rotary-diamond-trace", "--fixture", "bare-bed"]
FILL = ["--recipe", "scrap-rotary-diamond-fill", "--fixture", "bare-bed",
        "--set", "tip_width_mm=0.2", "--set", "stepover_mm=0.1"]


def test_list_prints_names_titles_and_parameters(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["pattern", "--list"]) == 0
    out = capsys.readouterr().out
    for name, p in PATTERNS.items():
        assert f"{name}  ({p.mode})  {p.title}" in out
        for s in p.params:
            assert f"-p {s.name}=" in out and s.help in out
    assert "-p compact=false  (bool)" in out and "-p target_kb=16  (int)" in out


def test_writes_the_golden_job(tmp_path: Path) -> None:
    out = tmp_path / "s.ggj"
    assert main(["pattern", "stepover-ladder", "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == (GOLDEN / "patterns" / "stepover-ladder.ggj").read_text(encoding="utf-8")
    assert not out.with_suffix(".m20").exists()


def test_params_reach_the_pattern(tmp_path: Path) -> None:
    out = tmp_path / "q.ggj"
    assert main(["pattern", "pz-square", "-p", "size_mm=4", "-p", "compact=true", "-p", "part=test-plate-100",
                 "-o", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert '"part": "test-plate-100"' in text and "size_mm=4.0" in text and "compact=true" in text


def test_build_writes_bytes_reports_and_svg(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "corner.ggj"
    assert main(["pattern", "corner-test", "-o", str(out), "--build", *TRACE]) == 0
    data = (tmp_path / "corner.m20").read_bytes()
    assert data == (GOLDEN / "outputs" / "pattern_corner_test.m20").read_bytes()
    rep = GateReport.from_json((tmp_path / "corner.gate.json").read_text(encoding="utf-8"))
    assert rep.bound_to(data) and rep.passed
    assert (tmp_path / "corner.gate.txt").read_text(encoding="utf-8") == rep.to_text()
    svg = (tmp_path / "corner.svg").read_text(encoding="utf-8")
    assert svg.startswith("<svg") or svg.startswith("<?xml")
    # the same files `ggdesk build` and `ggdesk preview` write for this job
    ref = tmp_path / "ref"
    ref.mkdir()
    assert main(["build", str(out), "-o", str(ref / "corner.m20"), *TRACE]) == 0
    assert main(["preview", str(ref / "corner.m20"), "-o", str(ref / "corner.svg"), "--job", str(out), *TRACE]) == 0
    assert (ref / "corner.m20").read_bytes() == data
    assert (ref / "corner.svg").read_text(encoding="utf-8") == svg
    ref_rep = GateReport.from_json((ref / "corner.gate.json").read_text(encoding="utf-8"))
    assert ref_rep.findings == rep.findings and ref_rep.sha256 == rep.sha256


def test_build_fill_pattern_with_placeholders(tmp_path: Path) -> None:
    out = tmp_path / "fill.ggj"
    assert main(["pattern", "char-ladder-fill", "-o", str(out), "--build", *FILL]) == 0
    assert (tmp_path / "fill.m20").read_bytes() == (GOLDEN / "outputs" / "pattern_char_ladder_fill.m20").read_bytes()
    rep = GateReport.from_json((tmp_path / "fill.gate.json").read_text(encoding="utf-8"))
    assert rep.passed and rep.selection.overrides == {"tip_width_mm": 0.2, "stepover_mm": 0.1}
    assert (tmp_path / "fill.svg").is_file()


def test_build_error_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "fill.ggj"
    assert main(["pattern", "char-ladder-fill", "-o", str(out), "--build", *TRACE]) == 1
    assert "a fill operation needs a fill recipe" in capsys.readouterr().err
    assert out.is_file() and not out.with_suffix(".m20").exists() and not out.with_suffix(".svg").exists()


def test_refused_exits_3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class AlwaysHard:
        id, severity, title = "HX", Severity.HARD, "test"

        def check(self, data: bytes, job: object, inputs: object) -> list[Finding]:
            return [Finding("HX", Severity.HARD, "test refusal")]

    monkeypatch.setattr(gate, "RULES", (AlwaysHard(),))
    out = tmp_path / "a.ggj"
    assert main(["pattern", "asymmetric", "-o", str(out), "--build", *TRACE]) == 3
    rep = GateReport.from_json((tmp_path / "a.gate.json").read_text(encoding="utf-8"))
    assert not rep.passed
    assert (tmp_path / "a.svg").is_file()


@pytest.mark.parametrize(("argv", "msg"), [
    (["pattern"], "--list"),
    (["pattern", "no-such", "-o", "X.ggj"], "unknown pattern"),
    (["pattern", "asymmetric"], "-o"),
    (["pattern", "asymmetric", "-o", "X.ggj", "--build"], "--recipe"),
    (["pattern", "asymmetric", "-o", "X.ggj", "-p", "compact"], "KEY=VALUE"),
    (["pattern", "asymmetric", "-o", "X.ggj", "-p", "size=1"], "size"),
    (["pattern", "pz-square", "-o", "X.ggj", "-p", "size_mm=-2"], "size_mm"),
    (["pattern", "char-ladder-trace", "-o", "X.ggj", "-p", "set=9"], "parameter set"),
])
def test_usage_and_parameter_errors_exit_2(argv: list[str], msg: str, tmp_path: Path,
                                            monkeypatch: pytest.MonkeyPatch,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(argv) == 2
    assert msg in capsys.readouterr().err
    assert not (tmp_path / "X.ggj").exists()


def test_unwritable_output_exits_1(tmp_path: Path) -> None:
    assert main(["pattern", "asymmetric", "-o", str(tmp_path / "missing-dir" / "a.ggj")]) == 1
