"""M2.4 library browser: read-only tree by kind; facts with value, confidence and source; unmeasured with steps."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
)

from ggdesk.library import Library, load_library, unmeasured
from ggdesk.library.model import KINDS
from ggdesk_app.app import MainWindow
from ggdesk_app.panels.library import LibraryBrowser, entry_rows, fmt_value
from ggdesk_app.session import BenchSession


def _no_runner() -> Any:
    raise AssertionError("library tests never send")


@pytest.fixture(scope="module")
def lib() -> Library:
    return load_library()


def _browser(qtbot: Any, lib: Library) -> LibraryBrowser:
    b = LibraryBrowser(BenchSession(lib, runner_factory=_no_runner))
    qtbot.addWidget(b)
    return b


def test_every_entry_listed_by_kind(qtbot: Any, lib: Library) -> None:
    b = _browser(qtbot, lib)
    assert b.tree.topLevelItemCount() == len(KINDS)
    for i, kind in enumerate(KINDS):
        top = b.tree.topLevelItem(i)
        assert top is not None
        table = getattr(lib, kind + "s")
        assert top.text(0) == f"{kind}s ({len(table)})"
        ids = [top.child(j).text(0).split()[0] for j in range(top.childCount())]  # type: ignore[union-attr]
        assert ids == sorted(table)


def test_known_fact_shows_value_confidence_and_source(qtbot: Any, lib: Library) -> None:
    b = _browser(qtbot, lib)
    r = lib.recipes["scrap-rotary-diamond-fill"]
    src = lib.sources[("recipe", r.ref.id)][r.vs.src or ""]
    expected = f"vs: {r.vs.value} [{r.vs.confidence}]  source {r.vs.src} ({src.title}), ref {r.vs.ref}"
    assert expected in [i.text(0) for i in b.find_items("vs: ")]
    assert r.vs.confidence == "HYPOTHESIS" and "[HYPOTHESIS]" in expected


def test_unmeasured_facts_show_gap_and_measure_steps(qtbot: Any, lib: Library) -> None:
    b = _browser(qtbot, lib)
    facts = unmeasured(lib)
    assert facts, "the seed library has needs_measurement facts (G1, G2, G6...)"
    for kind, eid, path, fact in facts:
        top = b.tree.topLevelItem(KINDS.index(kind))
        assert top is not None
        entry = next(top.child(j) for j in range(top.childCount())
                     if top.child(j).text(0).split()[0] == eid)  # type: ignore[union-attr]
        assert entry is not None
        want = f"{path}: needs measurement ({fact.gap})"
        rows = [entry.child(j) for j in range(entry.childCount()) if entry.child(j).text(0) == want]  # type: ignore[union-attr]
        assert len(rows) == 1, (kind, eid, want)
        row = rows[0]
        assert row is not None
        steps = [row.child(k).text(0) for k in range(row.childCount())]  # type: ignore[union-attr]
        assert steps == [f"measure {n}: {m}" for n, m in enumerate(fact.measure, 1)]
        assert steps


def test_rows_cover_every_fact(lib: Library) -> None:
    part = lib.parts["dog-tag-blank"]
    rows = entry_rows(part, lib.sources[("part", "dog-tag-blank")])
    paths = [r.path for r in rows]
    assert {"name", "material", "outline", "holes", "keep_out_margin_mm", "thickness_mm"} <= set(paths)
    fx = lib.fixtures["bare-bed"]
    rows = entry_rows(fx, lib.sources[("fixture", "bare-bed")])
    nest_ids = [n.id for n in fx.nests]
    assert all(f"nests.{n}.origin_mm" in [r.path for r in rows] for n in nest_ids)
    m = lib.machines["m20-iq"]
    rpaths = [r.path for r in entry_rows(m, lib.sources[("machine", "m20-iq")])]
    assert all(f"ranges.{k}" in rpaths for k in m.ranges)
    rec = lib.recipes["scrap-rotary-diamond-trace"]
    rpaths = [r.path for r in entry_rows(rec, lib.sources[("recipe", rec.ref.id)])]
    assert {"manual.nose_fitted", "manual.knob_notches", "manual.pressure", "mode", "status"} <= set(rpaths)


def test_value_formatting() -> None:
    from ggdesk.library import Range
    from ggdesk.library.model import Outline

    assert fmt_value(Range(0, 255)) == "0..255"
    assert fmt_value(Outline("rect", 40.0, 40.0)) == "rect 40 x 40 mm"
    assert fmt_value((1.5, 2.0)) == "[1.5, 2]"
    assert fmt_value(True) == "true"


def test_load_errors_listed_at_the_top(qtbot: Any, tmp_path: Path) -> None:
    bad = tmp_path / "recipes"
    bad.mkdir()
    (bad / "broken.toml").write_text('schema_version = 1\nkind = "recipe"\nid = "broken"\n', encoding="utf-8")
    lib = load_library(None, tmp_path)
    assert lib.errors
    b = _browser(qtbot, lib)
    assert not b.errors.isHidden()
    assert b.errors.count() == len(lib.errors)
    assert "broken.toml" in b.errors.item(0).text()
    assert "invalid and not loaded" in b.errors_title.text()
    lay = b.layout()
    assert lay is not None and lay.indexOf(b.errors) < lay.indexOf(b.tree)


def test_no_errors_says_so(qtbot: Any, lib: Library) -> None:
    assert not lib.errors
    b = _browser(qtbot, lib)
    assert b.errors.isHidden() and b.errors_title.text() == "No library load errors."


def test_read_only(qtbot: Any, lib: Library) -> None:
    b = _browser(qtbot, lib)
    for cls in (QAbstractButton, QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox):
        assert not b.findChildren(cls), cls.__name__
    for view in (b.tree, b.errors):
        assert view.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers


def test_main_window_hosts_the_browser(qtbot: Any, lib: Library) -> None:
    w = MainWindow(BenchSession(lib, runner_factory=_no_runner))
    qtbot.addWidget(w)
    assert isinstance(w.library_panel, LibraryBrowser)  # type: ignore[attr-defined]
    assert w.library_dock.toggleViewAction() in w.view_menu.actions()  # type: ignore[attr-defined]
