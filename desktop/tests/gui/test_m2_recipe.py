"""M2.4 recipe selector: every recipe of the machine, id + mode + status, draft marked; choosing rebuilds."""
from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any

import pytest
from PySide6.QtCore import Qt

import ggdesk.build
from ggdesk.build import BuildResult
from ggdesk.library import Library, Selection, load_library, resolve
from ggdesk.model.job import Job
from ggdesk.model.toolpath import Intent
from ggdesk_app import theme
from ggdesk_app.bench import BenchWidget
from ggdesk_app.panels.recipe import ID_ROLE, RecipeSelector, recipe_label
from ggdesk_app.session import BenchSession
from tests.conftest import DESKTOP
from tests.unit.test_render import job_bytes

SQUARE = DESKTOP / "docs" / "examples" / "square-10mm.ggj"
TESTLIB = DESKTOP / "tests" / "fixtures" / "library"
TRACE = "scrap-rotary-diamond-trace"
FILL = "scrap-rotary-diamond-fill"


def _no_runner() -> Any:
    raise AssertionError("recipe tests never send")


@pytest.fixture(scope="module")
def lib() -> Library:
    return load_library(None, None, TESTLIB)       # seed drafts plus confirmed test recipes


def test_lists_every_machine_recipe_with_mode_and_status(qtbot: Any, lib: Library) -> None:
    s = BenchSession(lib, runner_factory=_no_runner)
    sel = RecipeSelector(s, "m20-iq")
    qtbot.addWidget(sel)
    expected = sorted(r for r, e in lib.recipes.items() if e.machine == "m20-iq")
    assert sel.recipe_ids() == expected == [r.ref.id for r in s.recipes_for("m20-iq")]
    assert {"test-confirmed-trace", TRACE, FILL} <= set(expected)
    texts = {sel.itemData(i, ID_ROLE): sel.itemText(i) for i in range(sel.count())}
    assert texts[TRACE] == f"{TRACE}  (trace, DRAFT, not validated)"
    assert texts[FILL] == f"{FILL}  (fill, DRAFT, not validated)"
    assert texts["test-confirmed-trace"] == "test-confirmed-trace  (trace, CONFIRMED)"
    for i in range(sel.count()):
        rid = sel.itemData(i, ID_ROLE)
        assert sel.itemText(i) == recipe_label(lib.recipes[rid])
        fg = sel.itemData(i, Qt.ItemDataRole.ForegroundRole)
        if lib.recipes[rid].status == "draft":
            assert fg is not None and fg.color() == theme.status_colour("draft")
        else:
            assert fg is None


def test_other_machine_recipes_are_not_listed(qtbot: Any, lib: Library) -> None:
    s = BenchSession(lib, runner_factory=_no_runner)
    sel = RecipeSelector(s, "no-such-machine")
    qtbot.addWidget(sel)
    assert sel.count() == 0 and sel.recipe_id() == "" and not sel.select_recipe(TRACE)


def test_select_recipe_by_id(qtbot: Any, lib: Library) -> None:
    s = BenchSession(lib, runner_factory=_no_runner)
    sel = RecipeSelector(s, "m20-iq")
    qtbot.addWidget(sel)
    assert sel.select_recipe(FILL) and sel.recipe_id() == FILL
    assert not sel.select_recipe("missing") and sel.recipe_id() == FILL


class FakeBuild:
    """Counts builds (the real build is not needed to show that choosing a recipe regates)."""

    def __init__(self) -> None:
        self.calls: list[Selection] = []

    def __call__(self, job: Job, lib: Library, sel: Selection, *, job_text: str | None = None) -> BuildResult:
        self.calls.append(sel)
        return BuildResult(job_bytes(), Intent(()), (), resolve(lib, job, sel), None, 1.0, 0)


@pytest.fixture
def fake_build(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeBuild]:
    fb = FakeBuild()
    monkeypatch.setattr(ggdesk.build, "build", fb)
    yield fb


def test_choosing_a_recipe_updates_selection_and_regates(qtbot: Any, lib: Library, fake_build: FakeBuild) -> None:
    s = BenchSession(lib, runner_factory=_no_runner)
    b = BenchWidget(s)
    qtbot.addWidget(b)
    assert isinstance(b.job_panel.recipe, RecipeSelector)
    assert b.job_panel.recipe.select_recipe(TRACE)
    b.job_panel.open_job(SQUARE)
    qtbot.waitUntil(lambda: s.state.report is not None, timeout=3000)
    assert s.state.report is not None and s.state.report.selection.recipe == TRACE
    n = len(fake_build.calls)
    assert b.job_panel.recipe.select_recipe("test-confirmed-trace")
    assert s.state.selection.recipe == "test-confirmed-trace"
    assert s.state.report is None                  # the old report is dropped at once
    qtbot.waitUntil(lambda: s.state.report is not None, timeout=3000)
    assert s.state.report is not None and s.state.report.selection.recipe == "test-confirmed-trace"
    assert [c.recipe for c in fake_build.calls[n:]] == ["test-confirmed-trace"]
    assert threading.current_thread() is threading.main_thread()


def test_selection_uses_the_id_not_the_label(qtbot: Any, lib: Library) -> None:
    s = BenchSession(lib, runner_factory=_no_runner)
    b = BenchWidget(s)
    qtbot.addWidget(b)
    b.job_panel.recipe.select_recipe(FILL)
    assert b.job_panel.selection().recipe == FILL
    assert "(" in b.job_panel.recipe.currentText()      # the label shows mode and status
