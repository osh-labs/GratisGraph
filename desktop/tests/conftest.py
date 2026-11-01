from __future__ import annotations

from pathlib import Path

DESKTOP = Path(__file__).resolve().parents[1]
REPO = DESKTOP.parent
GOLDEN = REPO / "tests" / "golden"
