"""M2.4 pattern panel: list from PATTERNS, form from ParamSpecs, coerce, Generate opens the job.

The real registry is empty until slice M2.3 merges, so these tests register fake
patterns with ggdesk.patterns.register and remove them afterwards. No USB: the
session's runner factory is a fake that fails if it is ever called.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QLineEdit, QSpinBox

from ggdesk import patterns as pat
from ggdesk.formats import job as jf
from ggdesk.library import Library, Selection, load_library
from ggdesk.model.geometry import Polyline
from ggdesk.model.job import Job, TraceOp
from ggdesk.patterns import ParamSpec, PatternError
from ggdesk_app.app import MainWindow
from ggdesk_app.bench import BenchWidget
from ggdesk_app.panels.patterns import PatternPanel
from ggdesk_app.session import BenchSession

RECIPE = "scrap-rotary-diamond-trace"


def _no_runner() -> Any:
    raise AssertionError("pattern tests never send")


@dataclass
class FakePattern:
    name: str = "test-square"
    title: str = "Test square (fake, GUI tests only)"
    mode: str = "trace"
    params: tuple[ParamSpec, ...] = (
        ParamSpec("size", float, 10.0, "side in mm"),
        ParamSpec("step", float, 0.0125, "a value needing more than 4 decimals"),
        ParamSpec("count", int, 1, "number of squares"),
        ParamSpec("closed", bool, True, "close the outline"),
        ParamSpec("label", str, "A", "text"),
    )
    calls: list[dict[str, Any]] = field(default_factory=list)

    def generate(self, **params: Any) -> Job:
        self.calls.append(params)
        s = params["size"] / 2
        if s <= 0:
            raise PatternError(f"{self.name}: parameter size must be > 0, got {params['size']}")
        if s > 1000:
            raise RuntimeError("unexpected failure inside the pattern")
        ring = ((-s, -s), (s, -s), (s, s), (-s, s))
        ops = tuple(TraceOp((Polyline(ring, params["closed"]),)) for _ in range(params["count"]))
        return Job("bench-scrap-40", ops)


@pytest.fixture
def fake() -> Iterator[FakePattern]:
    p = FakePattern()
    pat.register(p)  # type: ignore[arg-type]
    other = FakePattern(name="test-empty", title="No parameters", params=())
    pat.register(other)  # type: ignore[arg-type]
    try:
        yield p
    finally:
        pat.PATTERNS.pop(p.name, None)
        pat.PATTERNS.pop(other.name, None)


@pytest.fixture(scope="module")
def lib() -> Library:
    return load_library()


def _panel(qtbot: Any, lib: Library) -> tuple[BenchSession, PatternPanel]:
    s = BenchSession(lib, runner_factory=_no_runner)
    s.select(Selection(recipe=RECIPE))
    p = PatternPanel(s)
    qtbot.addWidget(p)
    return s, p


def test_lists_registered_patterns_with_title(qtbot: Any, lib: Library, fake: FakePattern) -> None:
    _, p = _panel(qtbot, lib)
    names = [p.list.item(i).text() for i in range(p.list.count())]
    assert names == sorted(pat.PATTERNS) and "test-square" in names
    p.list.setCurrentRow(names.index("test-square"))
    assert p.title.text() == "Test square (fake, GUI tests only)  (trace)"


def test_empty_registry_says_so(qtbot: Any, lib: Library, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pat, "PATTERNS", {})          # independent of what slice M2.3 registers
    _, p = _panel(qtbot, lib)
    assert p.list.count() == 0
    assert "No bench patterns" in p.title.text()
    assert not p.generate_btn.isEnabled() and p.generate() is False


def test_form_widgets_follow_param_specs(qtbot: Any, lib: Library, fake: FakePattern) -> None:
    _, p = _panel(qtbot, lib)
    p.list.setCurrentRow([p.list.item(i).text() for i in range(p.list.count())].index("test-square"))
    f = p.fields
    assert list(f) == ["size", "step", "count", "closed", "label"]
    assert isinstance(f["size"], QDoubleSpinBox) and isinstance(f["step"], QDoubleSpinBox)
    assert isinstance(f["count"], QSpinBox) and isinstance(f["closed"], QCheckBox)
    assert isinstance(f["label"], QLineEdit)
    assert f["size"].toolTip() == "side in mm"
    # untouched form == the ParamSpec defaults exactly (no spin-box rounding of 0.0125)
    assert p.values() == {"size": 10.0, "step": 0.0125, "count": 1, "closed": True, "label": "A"}
    assert pat.coerce(fake, p.values()) == {s.name: s.default for s in fake.params}  # type: ignore[arg-type]


def test_switching_pattern_rebuilds_the_form(qtbot: Any, lib: Library, fake: FakePattern) -> None:
    _, p = _panel(qtbot, lib)
    names = [p.list.item(i).text() for i in range(p.list.count())]
    p.list.setCurrentRow(names.index("test-empty"))
    assert p.fields == {} and p.form.rowCount() == 0 and p.generate_btn.isEnabled()
    p.list.setCurrentRow(names.index("test-square"))
    assert p.form.rowCount() == 5


def test_generate_passes_coerced_values_and_opens_the_job(qtbot: Any, lib: Library, fake: FakePattern) -> None:
    s, p = _panel(qtbot, lib)
    p.list.setCurrentRow([p.list.item(i).text() for i in range(p.list.count())].index("test-square"))
    p.fields["size"].setValue(20.0)          # type: ignore[attr-defined]
    p.fields["count"].setValue(2)            # type: ignore[attr-defined]
    p.fields["closed"].setChecked(False)     # type: ignore[attr-defined]
    p.fields["label"].setText("B")           # type: ignore[attr-defined]
    with qtbot.waitSignal(p.generated, timeout=1000) as sig:
        qtbot.mouseClick(p.generate_btn, Qt.MouseButton.LeftButton)
    assert sig.args == ["test-square"]
    assert fake.calls == [{"size": 20.0, "step": 0.0125, "count": 2, "closed": False, "label": "B"}]
    assert isinstance(fake.calls[0]["count"], int) and isinstance(fake.calls[0]["size"], float)
    st = s.state
    assert st.job is not None and len(st.job.operations) == 2 and st.job_path is None
    assert st.job_sha256 == hashlib.sha256(jf.dumps(st.job).encode("utf-8")).hexdigest()
    assert st.job_label is not None and st.job_label.startswith("pattern test-square")
    assert st.selection == Selection(recipe=RECIPE)        # generating keeps the selection
    assert p.error.text() == ""


def test_pattern_error_is_shown_not_swallowed(qtbot: Any, lib: Library, fake: FakePattern) -> None:
    s, p = _panel(qtbot, lib)
    p.list.setCurrentRow([p.list.item(i).text() for i in range(p.list.count())].index("test-square"))
    p.fields["size"].setValue(-1.0)          # type: ignore[attr-defined]
    emitted: list[str] = []
    p.generated.connect(emitted.append)
    assert p.generate() is False
    assert "parameter size must be > 0" in p.error.text()
    assert s.state.job is None and emitted == []


def test_unexpected_error_is_shown(qtbot: Any, lib: Library, fake: FakePattern) -> None:
    s, p = _panel(qtbot, lib)
    p.list.setCurrentRow([p.list.item(i).text() for i in range(p.list.count())].index("test-square"))
    p.fields["size"].setValue(5000.0)        # type: ignore[attr-defined]
    assert p.generate() is False
    assert "RuntimeError: unexpected failure inside the pattern" in p.error.text()
    assert s.state.job is None


def test_session_generate_refuses_unknown_parameter(lib: Library, fake: FakePattern) -> None:
    s = BenchSession(lib, runner_factory=_no_runner)
    with pytest.raises(PatternError, match="unknown parameter"):
        s.generate_pattern("test-square", {"nope": 1})
    with pytest.raises(PatternError, match="expects int"):
        s.generate_pattern("test-square", {"count": "many"})
    assert s.state.job is None and fake.calls == []


def test_generate_in_main_window_builds_and_gates(qtbot: Any, lib: Library, fake: FakePattern) -> None:
    s = BenchSession(lib, runner_factory=_no_runner)
    w = MainWindow(s)
    qtbot.addWidget(w)
    bench = w.centralWidget()
    assert isinstance(bench, BenchWidget)
    assert bench.job_panel.recipe.select_recipe(RECIPE)
    panel: PatternPanel = w.patterns_panel  # type: ignore[attr-defined]
    assert not bench.isAncestorOf(panel)    # the pattern form lives in a dock, outside the bench
    panel.list.setCurrentRow([panel.list.item(i).text() for i in range(panel.list.count())].index("test-square"))
    assert panel.generate()
    qtbot.waitUntil(lambda: s.state.report is not None, timeout=5000)
    assert s.state.report is not None and s.state.data is not None
    assert s.state.report.bound_to(s.state.data) and s.state.report.passed
    assert "pattern test-square" in bench.job_panel.job_label.text()
    assert "bench-scrap-40" in bench.job_panel.job_label.text()
