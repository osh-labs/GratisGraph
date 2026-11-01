"""ggdesk check JOB.ggj FILE.m20: gates the FILE's bytes with the intent from building the job.
ggdesk.build.build is replaced with monkeypatch until slice M1.1 lands. Exit 0 pass, 3 refused, 1 error."""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

import pytest

import ggdesk.build
from ggdesk.build import BuildResult
from ggdesk.cli import main
from ggdesk.library import resolve
from tests.conftest import DESKTOP
from tests.unit.test_gate_support import FIXTURES, SQUARE, build_bytes, make_inputs

JOB = DESKTOP / "docs" / "examples" / "square-10mm.ggj"
FLAGS = ["--recipe", "test-confirmed-trace", "--fixture", "test-clamps", "--library", str(FIXTURES)]


@pytest.fixture
def fake_build(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def build(job: Any, lib: Any, sel: Any, *, job_text: str | None = None) -> BuildResult:
        calls.append({"job": job, "sel": sel, "job_text": job_text})
        resolve(lib, job, sel)   # selection, override and lookup errors as the real build raises them
        inputs = make_inputs(SQUARE, part=job.part, recipe=sel.recipe, fixture=sel.fixture, lib=lib)
        data = build_bytes(SQUARE, inputs)
        assert inputs.intent is not None
        return BuildResult(data, inputs.intent, SQUARE, inputs.resolved, "job-sha", 1.0, 0)

    monkeypatch.setattr(ggdesk.build, "build", build)
    return calls


def _m20(tmp_path: Path, pz: int = 50) -> Path:
    inputs = make_inputs(SQUARE)
    data = bytearray(build_bytes(SQUARE, inputs))
    i = data.index(b"\xff\xfdPZ")
    struct.pack_into(">H", data, i + 4, pz)
    p = tmp_path / "job.m20"
    p.write_bytes(bytes(data))
    return p


def test_check_pass(tmp_path: Path, fake_build: list[dict[str, Any]], capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["check", str(JOB), str(_m20(tmp_path)), *FLAGS])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "Gate report  PASS" in out and "Residual status" in out
    assert fake_build[0]["sel"].recipe == "test-confirmed-trace"
    assert fake_build[0]["job_text"] == JOB.read_text(encoding="utf-8")


def test_check_refused_gates_the_file_not_the_rebuild(tmp_path: Path, fake_build: list[dict[str, Any]],
                                                       capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["check", str(JOB), str(_m20(tmp_path, pz=51)), *FLAGS])
    out = capsys.readouterr().out
    assert rc == 3
    assert "REFUSED" in out and "H5" in out


def test_check_soft_flags_pass_with_ack_line(tmp_path: Path, fake_build: list[dict[str, Any]],
                                              capsys: pytest.CaptureFixture[str]) -> None:
    flags = ["--recipe", "test-confirmed-trace", "--fixture", "bare-bed", "--library", str(FIXTURES)]
    rc = main(["check", str(JOB), str(_m20(tmp_path)), *flags])
    out = capsys.readouterr().out
    assert rc == 0 and "To send, type: I ACCEPT 1 FLAG" in out


def test_check_build_error_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def refuse(*a: Any, **k: Any) -> BuildResult:
        raise ggdesk.build.BuildError("cannot build")

    mp = pytest.MonkeyPatch()
    mp.setattr(ggdesk.build, "build", refuse)
    try:
        rc = main(["check", str(JOB), str(_m20(tmp_path)), *FLAGS])
    finally:
        mp.undo()
    assert rc == 1 and "cannot build" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [
    ["check", str(JOB), "missing.m20", *FLAGS],
    ["check", "missing.ggj", "x.m20", *FLAGS],
    ["check", str(JOB), "x.m20", "--fixture", "test-clamps"],                     # no recipe
    ["check", str(JOB), "x.m20", "--recipe", "nope"],                             # unknown recipe
    ["check", str(JOB), "x.m20", *FLAGS, "--set", "pz=80"],                       # override on a confirmed recipe
])
def test_check_usage_errors(argv: list[str], tmp_path: Path, fake_build: list[dict[str, Any]],
                            capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.m20").write_bytes(_m20(tmp_path).read_bytes())
    assert main(argv) == 1
    assert capsys.readouterr().err.startswith("ggdesk check:")
