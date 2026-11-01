"""Locations of the seed library and the per-OS user library.

The seed library is desktop/library/ (read-only). In a frozen (PyInstaller)
build the bundle root sys._MEIPASS takes its place. GGDESK_SEED_LIBRARY
overrides either. The user library lives in the OS data directory and
overrides seed entries by id.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import platformdirs

FROZEN = bool(getattr(sys, "frozen", False)) and hasattr(sys, "_MEIPASS")
if FROZEN:
    ROOT = Path(sys._MEIPASS).resolve()  # type: ignore[attr-defined]
else:
    ROOT = Path(__file__).resolve().parents[2]  # desktop/
SEED_LIBRARY = Path(os.environ.get("GGDESK_SEED_LIBRARY", str(ROOT / "library")))


def user_library() -> Path:
    """Per-OS user data directory. GGDESK_USER_LIBRARY overrides (tests, portable installs)."""
    env = os.environ.get("GGDESK_USER_LIBRARY")
    if env:
        return Path(env)
    name = "gratisgraph-desktop" if sys.platform.startswith("linux") else "GratisGraph Desktop"
    return Path(platformdirs.user_data_dir(name, appauthor=False, roaming=True)) / "library"
