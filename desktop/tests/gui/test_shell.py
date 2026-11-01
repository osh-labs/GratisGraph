from __future__ import annotations

from typing import Any

from ggdesk_app.app import TITLE, MainWindow, self_test


def test_main_window(qtbot: Any) -> None:
    w = MainWindow()
    qtbot.addWidget(w)
    assert w.windowTitle().startswith(TITLE)


def test_self_test() -> None:
    assert self_test() == 0
