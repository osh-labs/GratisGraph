"""Feature modules that plug into the main window, in install order.

Each entry is "module:function"; the function takes the MainWindow. A slice adds
one line here and nothing else in shared files (desktop/docs/m1-plan.md 5).
"""
from __future__ import annotations

import importlib
from typing import Any

INSTALLERS: tuple[str, ...] = (
)


def install_all(window: Any) -> None:
    for spec in INSTALLERS:
        mod_name, func = spec.split(":")
        getattr(importlib.import_module(mod_name), func)(window)
