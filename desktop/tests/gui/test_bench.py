"""Bench window (F08): preview = draw list = SVG, gate panel, gated send through a fake runner, workers.

No test here touches USB: every runner is a fake injected through runner_factory.
GUI tests do not depend on M1.1/M1.2: bytes come from gts_api.build_gts (stamped
0x020D) and ggdesk.build.build is monkeypatched where a build is needed.
"""
from __future__ import annotations

import re
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractButton, QCheckBox, QLineEdit, QPushButton, QRadioButton

import ggdesk.build
from ggdesk.build import BuildResult
from ggdesk.formats import job as jf
from ggdesk.gate import Finding, GateInputs, GateReport, Severity, run_gate
from ggdesk.gts_read import Job as GtsJob
from ggdesk.library import Library, Selection, load_library, resolve
from ggdesk.model.job import Job
from ggdesk.model.toolpath import Intent
from ggdesk.render import DrawItem, DrawList, draw_list, to_svg
from ggdesk_app.app import MainWindow
from ggdesk_app.bench import BenchWidget
from ggdesk_app.panels.preview import KIND_KEY
from ggdesk_app.session import BenchSession, SendNotAllowed
from tests.conftest import DESKTOP
from tests.unit.test_render import job_bytes, svg_matches

SQUARE = DESKTOP / "docs" / "examples" / "square-10mm.ggj"
RECIPE = "scrap-rotary-diamond-trace"
APP_SRC = DESKTOP / "src" / "ggdesk_app"


@dataclass
class FakeRule:
    id: str
    severity: Severity
    n: int = 1
    title: str = "fake"

    def check(self, data: bytes, job: GtsJob, inputs: GateInputs) -> list[Finding]:
        return [Finding(self.id, self.severity, f"fake finding {i}") for i in range(self.n)]


@dataclass
class FakeRunner:
    result: Any = field(default_factory=lambda: SimpleNamespace(status="completed", et=7))
    error: Exception | None = None
    sent: list[tuple[bytes, GateReport, str]] = field(default_factory=list)
    threads: list[threading.Thread] = field(default_factory=list)
    aborted: int = 0

    def send_gated(self, data: bytes, report: GateReport, ack: str = "") -> Any:
        self.threads.append(threading.current_thread())
        self.sent.append((data, report, ack))
        if self.error is not None:
            raise self.error
        return self.result

    def abort(self) -> None:
        self.aborted += 1


class Factory:
    def __init__(self, runner: FakeRunner) -> None:
        self.runner = runner
        self.calls = 0

    def __call__(self) -> FakeRunner:
        self.calls += 1
        return self.runner


@pytest.fixture(scope="module")
def lib() -> Library:
    return load_library()


def _session(lib: Library, factory: Factory | None = None) -> BenchSession:
    s = BenchSession(lib, runner_factory=factory or Factory(FakeRunner()))
    s.open_job(SQUARE)
    s.select(Selection(recipe=RECIPE))
    return s


def _gate(s: BenchSession, *rules: FakeRule) -> None:
    """Put stamped bytes and a report from run_gate (with fake rules) into the session."""
    assert s.state.job is not None
    data = job_bytes()
    inputs = GateInputs(resolve(s.library, s.state.job, s.state.selection), None, None, s.state.selection)
    report = run_gate(data, inputs, rules=tuple(rules))
    assert s.apply_build(s.state.job, s.state.selection, data, report, None, "Gate passed.")


def _bench(qtbot: Any, s: BenchSession) -> BenchWidget:
    b = BenchWidget(s)
    qtbot.addWidget(b)
    b.resize(1200, 700)
    return b


# --- preview: screen == draw list == SVG -------------------------------------------------------

def test_preview_scene_matches_draw_list_and_svg(qtbot: Any, lib: Library) -> None:
    s = _session(lib)
    b = _bench(qtbot, s)
    _gate(s)
    assert s.state.data is not None and s.state.job is not None
    dl = draw_list(s.state.data, resolve(lib, s.state.job, s.state.selection))
    scene = b.preview.scene_items()
    assert [k for k, _ in scene] == [i.kind for i in dl.items]
    for (_, pts), item in zip(scene, dl.items, strict=True):
        assert [c for p in pts for c in p] == pytest.approx([c for p in item.points for c in p], abs=1e-9)
    assert {"field", "part", "cut", "rapid", "start"} <= {k for k, _ in scene}
    svg = to_svg(dl)
    assert svg_matches(dl, svg)
    svg_from_scene = DrawList(tuple(DrawItem(k, p) for k, p in scene), dl.extent_mm)  # type: ignore[arg-type]
    assert svg_matches(svg_from_scene, svg)


def test_preview_y_down_with_operator_label_at_front(qtbot: Any, lib: Library) -> None:
    s = _session(lib)
    b = _bench(qtbot, s)
    _gate(s)
    labels = [g for g in b.preview.scene().items() if g.data(KIND_KEY) == "label"]
    assert len(labels) == 1 and labels[0].text() == "operator"
    assert labels[0].pos().y() > 100.0          # below the field's front edge (machine +Y = screen down)
    # home (0, 0) maps to the scene's top-left region: screen Y grows toward the operator
    view = b.preview
    top = view.mapFromScene(0.0, 0.0)
    front = view.mapFromScene(0.0, 100.0)
    assert front.y() > top.y()


def test_preview_clears_without_bytes(qtbot: Any, lib: Library) -> None:
    s = _session(lib)
    b = _bench(qtbot, s)
    _gate(s)
    assert b.preview.scene_items()
    s.select(Selection(recipe=RECIPE, overrides={"pz": 60}))
    assert b.preview.scene_items() == []


# --- gate report panel ------------------------------------------------------------------------

def test_report_shows_hard_soft_and_residual(qtbot: Any, lib: Library) -> None:
    s = _session(lib)
    b = _bench(qtbot, s)
    _gate(s, FakeRule("S1", Severity.SOFT, 2), FakeRule("H7", Severity.HARD, 1))
    p = b.gate_panel
    assert p.hard.count() == 1 and p.soft.count() == 2
    assert s.state.report is not None and p.residual.count() == len(s.state.report.residual) > 0
    assert p.residual.item(0).text().startswith("Depth is set by hand")
    assert "REFUSED" in p.verdict.text()


def test_residual_lines_shown_with_zero_findings(qtbot: Any, lib: Library) -> None:
    s = _session(lib)
    b = _bench(qtbot, s)
    _gate(s)
    assert b.gate_panel.hard.count() == 0 and b.gate_panel.soft.count() == 0
    assert b.gate_panel.residual.count() > 0


def test_send_enabled_only_with_the_exact_phrase(qtbot: Any, lib: Library) -> None:
    s = _session(lib)
    b = _bench(qtbot, s)
    _gate(s, FakeRule("S1", Severity.SOFT, 2))
    p = b.gate_panel
    assert "I ACCEPT 2 FLAGS" in p.ack_hint.text()
    for typed, ok in (("", False), ("I ACCEPT 1 FLAG", False), ("i accept 2 flags", False),
                      ("I ACCEPT 3 FLAGS", False), ("I ACCEPT 2 FLAGS", True), ("  I ACCEPT 2 FLAGS ", True)):
        p.ack.setText(typed)
        assert p.send_btn.isEnabled() is ok, typed
        assert p.send_btn.isEnabled() == s.can_send(typed)


def test_no_flags_send_enabled_without_ack(qtbot: Any, lib: Library) -> None:
    s = _session(lib)
    b = _bench(qtbot, s)
    _gate(s)
    assert b.gate_panel.send_btn.isEnabled()
    assert not b.gate_panel.ack.isEnabled()


def test_hard_finding_never_enables_send(qtbot: Any, lib: Library) -> None:
    s = _session(lib)
    b = _bench(qtbot, s)
    _gate(s, FakeRule("H1", Severity.HARD), FakeRule("S1", Severity.SOFT))
    p = b.gate_panel
    for typed in ("", "I ACCEPT 1 FLAG", "I ACCEPT 1 FLAGS"):
        p.ack.setText(typed)
        assert not p.send_btn.isEnabled()
    qtbot.mouseClick(p.send_btn, Qt.MouseButton.LeftButton)
    with pytest.raises(SendNotAllowed):
        s.send("I ACCEPT 1 FLAG")


def test_bytes_changed_after_gate_disable_send(qtbot: Any, lib: Library) -> None:
    s = _session(lib)
    b = _bench(qtbot, s)
    _gate(s)
    assert b.gate_panel.send_btn.isEnabled()
    s.state.data = job_bytes(model=0x0204)          # report no longer bound to the bytes
    s.note("bytes replaced")
    assert not b.gate_panel.send_btn.isEnabled()


def test_gate_panel_has_no_override_control(qtbot: Any, lib: Library) -> None:
    s = _session(lib)
    b = _bench(qtbot, s)
    _gate(s, FakeRule("S1", Severity.SOFT))
    p = b.gate_panel
    assert p.findChildren(QLineEdit) == [p.ack]
    assert set(p.findChildren(QPushButton)) == {p.send_btn, p.abort_btn}
    assert not b.findChildren(QCheckBox) and not b.findChildren(QRadioButton)
    for w in b.findChildren(QAbstractButton):
        assert not re.search(r"override|force|ignore|bypass|skip", w.text(), re.I), w.text()


# --- send and abort through a fake runner ----------------------------------------------------

def test_send_runs_through_the_runner_off_the_ui_thread(qtbot: Any, lib: Library) -> None:
    runner = FakeRunner()
    factory = Factory(runner)
    s = _session(lib, factory)
    b = _bench(qtbot, s)
    _gate(s, FakeRule("S1", Severity.SOFT, 2))
    assert factory.calls == 0                       # no connection until Send
    b.gate_panel.ack.setText("I ACCEPT 2 FLAGS")
    b.operator.setText("op1")
    qtbot.mouseClick(b.gate_panel.send_btn, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: s.state.status == "Run completed (machine time 7 s).", timeout=3000)
    assert factory.calls == 1 and len(runner.sent) == 1
    data, report, ack = runner.sent[0]
    assert data == s.state.data and report is s.state.report and ack == "I ACCEPT 2 FLAGS"
    assert runner.threads[0] is not threading.main_thread()
    assert s.operator == "op1"
    assert b.status.text().startswith("Run completed")
    assert b.gate_panel.send_btn.isEnabled() and b.job_panel.isEnabled()


@pytest.mark.parametrize("status,text", [("unconfirmed", "did not confirm completion"), ("aborted", "Run aborted.")])
def test_status_line_from_run_result(qtbot: Any, lib: Library, status: str, text: str) -> None:
    s = _session(lib, Factory(FakeRunner(result=SimpleNamespace(status=status, et=None))))
    b = _bench(qtbot, s)
    _gate(s)
    qtbot.mouseClick(b.gate_panel.send_btn, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: text in s.state.status, timeout=3000)


def test_send_failure_is_visible(qtbot: Any, lib: Library) -> None:
    s = _session(lib, Factory(FakeRunner(error=RuntimeError("model code mismatch"))))
    b = _bench(qtbot, s)
    _gate(s)
    qtbot.mouseClick(b.gate_panel.send_btn, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: s.state.status.startswith("Send failed"), timeout=3000)
    assert "model code mismatch" in b.status.text()


def test_send_refused_without_ack_never_makes_a_runner(lib: Library) -> None:
    factory = Factory(FakeRunner())
    s = _session(lib, factory)
    _gate(s, FakeRule("S1", Severity.SOFT))
    with pytest.raises(SendNotAllowed):
        s.send("")
    assert factory.calls == 0


def test_abort_calls_the_runner(qtbot: Any, lib: Library) -> None:
    runner = FakeRunner()
    s = _session(lib, Factory(runner))
    b = _bench(qtbot, s)
    _gate(s)
    qtbot.mouseClick(b.gate_panel.abort_btn, Qt.MouseButton.LeftButton)
    assert runner.aborted == 0 and "Nothing to abort" in s.state.status
    qtbot.mouseClick(b.gate_panel.send_btn, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: bool(runner.sent), timeout=3000)
    qtbot.mouseClick(b.gate_panel.abort_btn, Qt.MouseButton.LeftButton)
    assert runner.aborted == 1


def test_default_runner_factory_is_not_called_on_open(qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import ggdesk_app.session as session_mod

    def boom() -> Any:
        raise AssertionError("the real connection must not open without Send")

    monkeypatch.setattr(session_mod, "default_runner_factory", boom)
    w = MainWindow(BenchSession())
    qtbot.addWidget(w)
    assert isinstance(w.centralWidget(), BenchWidget)
    assert w.session.runner is None


# --- build worker -----------------------------------------------------------------------------

class FakeBuild:
    """Stands in for ggdesk.build.build (slice M1.1) so these tests run before it lands."""

    def __init__(self) -> None:
        self.calls: list[Selection] = []
        self.gate = threading.Event()
        self.gate.set()
        self.started = threading.Event()
        self.error: Exception | None = None

    def __call__(self, job: Job, lib: Library, sel: Selection, *, job_text: str | None = None) -> BuildResult:
        self.calls.append(sel)
        self.started.set()
        assert self.gate.wait(5)
        if self.error is not None:
            raise self.error
        return BuildResult(job_bytes(), Intent(()), (), resolve(lib, job, sel), None, 1.0, 0)


@pytest.fixture
def fake_build(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeBuild]:
    fb = FakeBuild()
    monkeypatch.setattr(ggdesk.build, "build", fb)
    yield fb
    fb.gate.set()


def test_worker_builds_and_gates_after_opening(qtbot: Any, lib: Library, fake_build: FakeBuild) -> None:
    s = BenchSession(lib, runner_factory=Factory(FakeRunner()))
    b = _bench(qtbot, s)
    b.job_panel.recipe.setCurrentText(RECIPE)
    b.job_panel.open_job(SQUARE)
    qtbot.waitUntil(lambda: s.state.report is not None, timeout=3000)
    assert s.state.data == job_bytes() and s.state.report is not None and s.state.report.bound_to(s.state.data)
    assert [k for k, _ in b.preview.scene_items()].count("cut") == 2
    assert threading.main_thread() is threading.current_thread()


def test_worker_debounces_a_burst(qtbot: Any, lib: Library, fake_build: FakeBuild) -> None:
    s = _session(lib)
    b = _bench(qtbot, s)
    for _ in range(5):
        b.build_worker.request()
    qtbot.waitUntil(lambda: s.state.report is not None, timeout=3000)
    assert len(fake_build.calls) == 1


def test_worker_drops_a_stale_result(qtbot: Any, lib: Library, fake_build: FakeBuild) -> None:
    s = _session(lib)
    b = _bench(qtbot, s)
    dropped: list[int] = []
    b.build_worker.dropped.connect(dropped.append)
    fake_build.gate.clear()
    b.build_worker.request()
    qtbot.waitUntil(fake_build.started.is_set, timeout=3000)   # first build is running, held
    b.job_panel.overrides.setText("pz=60")
    b.job_panel.apply()                              # new selection: requests a second build
    fake_build.gate.set()
    qtbot.waitUntil(lambda: s.state.report is not None, timeout=3000)
    assert dropped, "the first (stale) result must be dropped"
    assert s.state.selection.overrides == {"pz": 60}
    assert s.state.report is not None and s.state.report.selection.overrides == {"pz": 60}
    assert [c.overrides for c in fake_build.calls] == [{}, {"pz": 60}]


def test_worker_exception_is_visible(qtbot: Any, lib: Library, fake_build: FakeBuild) -> None:
    s = _session(lib)
    b = _bench(qtbot, s)
    fake_build.error = RuntimeError("boom")
    b.build_worker.request()
    qtbot.waitUntil(lambda: s.state.error is not None, timeout=3000)
    assert s.state.error == "RuntimeError: boom"
    assert s.state.data is None and s.state.report is None
    assert "boom" in b.status.text()
    assert not b.gate_panel.send_btn.isEnabled()


def test_build_error_is_visible(qtbot: Any, lib: Library, fake_build: FakeBuild) -> None:
    s = _session(lib)
    b = _bench(qtbot, s)
    fake_build.error = ggdesk.build.BuildError("no strokes")
    b.build_worker.request()
    qtbot.waitUntil(lambda: s.state.error is not None, timeout=3000)
    assert s.state.status == "Build refused." and "no strokes" in b.status.text()


def test_unreadable_override_text_drops_the_report(qtbot: Any, lib: Library) -> None:
    s = _session(lib)
    b = _bench(qtbot, s)
    _gate(s)
    b.job_panel.overrides.setText("pz")
    b.job_panel.apply()
    assert "KEY=VALUE" in b.job_panel.problem.text()
    assert s.state.report is None and not b.gate_panel.send_btn.isEnabled()


# --- theme, keyboard, scaling -----------------------------------------------------------------

COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|QColor\(\s*[\d\"']|GlobalColor|Qt\.(?:red|green|blue|"
                    r"black|white|gray|yellow|cyan|magenta)\b|\bcolor\s*:")


def test_colour_literals_only_in_theme() -> None:
    offenders = []
    for path in sorted(APP_SRC.rglob("*.py")):
        if path.name == "theme.py":
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if COLOUR.search(line):
                offenders.append(f"{path.relative_to(APP_SRC)}:{n}: {line.strip()}")
    assert not offenders, offenders


def test_no_fixed_pixel_sizes_outside_theme() -> None:
    pat = re.compile(r"setFixed(Size|Width|Height)|setPixelSize|\d+px")
    for path in sorted(APP_SRC.rglob("*.py")):
        if path.name != "theme.py":
            assert not pat.search(path.read_text(encoding="utf-8")), path


def test_buttons_are_keyboard_reachable(qtbot: Any, lib: Library) -> None:
    s = _session(lib)
    b = _bench(qtbot, s)
    for btn in (b.job_panel.open_btn, b.gate_panel.send_btn, b.gate_panel.abort_btn):
        assert btn.focusPolicy() & Qt.FocusPolicy.TabFocus
        assert "&" in btn.text()                     # Alt mnemonic


@pytest.mark.parametrize("scale", [1.0, 1.5])
def test_readable_at_scale(qtbot: Any, lib: Library, scale: float) -> None:
    s = _session(lib)
    b = _bench(qtbot, s)
    f = b.font()
    f.setPointSizeF(f.pointSizeF() * scale)
    b.setFont(f)
    _gate(s, FakeRule("S1", Severity.SOFT))
    b.show()
    qtbot.waitExposed(b)
    for w in (b.gate_panel.send_btn, b.gate_panel.abort_btn, b.gate_panel.verdict, b.job_panel.open_btn):
        assert w.width() >= w.minimumSizeHint().width()
        assert w.height() >= w.fontMetrics().height()
    assert b.preview.scene_items()


def test_job_file_path_is_shown(qtbot: Any, lib: Library) -> None:
    s = BenchSession(lib, runner_factory=Factory(FakeRunner()))
    b = _bench(qtbot, s)
    b.job_panel.open_job(Path(SQUARE))
    assert SQUARE.name in b.job_panel.job_label.text()
    assert jf.load(SQUARE).part in b.job_panel.job_label.text()
