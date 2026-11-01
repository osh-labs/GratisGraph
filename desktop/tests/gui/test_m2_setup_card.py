"""M2.4 setup card panel: setup_card(resolved) for the current selection; depth line == gate residual line."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ggdesk.library import Library, Selection, load_library, resolve
from ggdesk.setupcard import setup_card
from ggdesk_app.app import MainWindow
from ggdesk_app.panels.setup_card import NO_JOB, SetupCardPanel
from ggdesk_app.session import BenchSession
from tests.conftest import DESKTOP

SQUARE = DESKTOP / "docs" / "examples" / "square-10mm.ggj"
TRACE = "scrap-rotary-diamond-trace"
FILL = "scrap-rotary-diamond-fill"


def _no_runner() -> Any:
    raise AssertionError("setup card tests never send")


@pytest.fixture(scope="module")
def lib() -> Library:
    return load_library()


def _panel(qtbot: Any, lib: Library) -> tuple[BenchSession, SetupCardPanel]:
    s = BenchSession(lib, runner_factory=_no_runner)
    p = SetupCardPanel(s)
    qtbot.addWidget(p)
    return s, p


def test_no_job_no_card(qtbot: Any, lib: Library) -> None:
    _, p = _panel(qtbot, lib)
    assert p.title.text() == NO_JOB and p.texts() == []


def test_card_lines_are_the_core_card(qtbot: Any, lib: Library) -> None:
    s, p = _panel(qtbot, lib)
    s.open_job(SQUARE)
    s.select(Selection(recipe=TRACE))
    assert s.state.job is not None
    card = setup_card(resolve(lib, s.state.job, s.state.selection))
    assert p.title.text() == card.title
    assert p.texts() == list(card.lines)


@pytest.mark.parametrize("overrides", [{}, {"pz": 80}])
def test_manual_depth_line_equals_the_gate_reports_first_residual_line(
        qtbot: Any, lib: Library, overrides: dict[str, Any]) -> None:
    s, p = _panel(qtbot, lib)
    s.open_job(SQUARE)
    s.select(Selection(recipe=TRACE, overrides=overrides))
    s.build_and_gate()                        # the real build and gate
    r = s.state.report
    assert r is not None and r.residual
    depth = [t for t in p.texts() if t.startswith("Depth is set by hand")]
    assert depth == [r.residual[0]]


def test_card_refreshes_when_the_selection_changes(qtbot: Any, lib: Library) -> None:
    s, p = _panel(qtbot, lib)
    s.open_job(SQUARE)
    s.select(Selection(recipe=TRACE))
    assert any(TRACE in t for t in p.texts()) and not any(t.startswith("Fill:") for t in p.texts())
    s.select(Selection(recipe=FILL, overrides={"stepover_mm": 0.1, "tip_width_mm": 0.2}))
    assert any(FILL in t for t in p.texts())
    assert "Fill: tip width 0.2 mm, stepover 0.1 mm." in p.texts()
    assert "Bench override: stepover_mm = 0.1 (this run only)." in p.texts()


def test_status_notes_do_not_rebuild_the_card(qtbot: Any, lib: Library, monkeypatch: pytest.MonkeyPatch) -> None:
    s, p = _panel(qtbot, lib)
    s.open_job(SQUARE)
    s.select(Selection(recipe=TRACE))
    calls: list[int] = []
    orig = s.setup_card
    monkeypatch.setattr(s, "setup_card", lambda: calls.append(1) or orig())
    s.note("Building and gating...")
    assert calls == []
    s.open_job(Path(SQUARE))                  # a new job object: refreshed
    assert calls == [1]


def test_unresolvable_selection_is_shown(qtbot: Any, lib: Library) -> None:
    s, p = _panel(qtbot, lib)
    s.open_job(SQUARE)
    s.select(Selection(recipe="no-such-recipe"))
    assert p.title.text().startswith("No setup card:") and "no-such-recipe" in p.title.text()
    assert p.texts() == []


def test_main_window_hosts_the_card(qtbot: Any, lib: Library) -> None:
    s = BenchSession(lib, runner_factory=_no_runner)
    w = MainWindow(s)
    qtbot.addWidget(w)
    panel: SetupCardPanel = w.setup_card_panel  # type: ignore[attr-defined]
    w.bench.job_panel.recipe.select_recipe(TRACE)  # type: ignore[attr-defined]
    w.bench.job_panel.open_job(SQUARE)  # type: ignore[attr-defined]
    assert any(t.startswith("Depth is set by hand") for t in panel.texts())
    assert w.setup_card_dock.toggleViewAction() in w.view_menu.actions()  # type: ignore[attr-defined]
