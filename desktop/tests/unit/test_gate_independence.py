"""The gate judges the bytes on its own: no module under src/ggdesk/gate/ may import the builder
(ggdesk.build, ggdesk.toolpath) or the driver's job builders (gts_api, gts_prepare,
gts_translator). gts_optimise is allowed for the run-time estimate (S5)."""
from __future__ import annotations

import ast
from pathlib import Path

from tests.conftest import DESKTOP

GATE = DESKTOP / "src" / "ggdesk" / "gate"
BANNED = ("ggdesk.build", "ggdesk.toolpath", "gts_api", "gts_prepare", "gts_translator")


def _imports(path: Path) -> list[str]:
    out: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            out.append(mod)
            out += [f"{mod}.{a.name}" for a in node.names]
    return out


def test_gate_does_not_import_the_builder() -> None:
    files = sorted(GATE.glob("*.py"))
    assert len(files) >= 6
    bad = [(p.name, m) for p in files for m in _imports(p)
           if any(m == b or m.startswith(b + ".") for b in BANNED)]
    assert bad == []


def test_textual_grep_too() -> None:
    # belt and braces: catch importlib or string tricks
    for p in sorted(GATE.glob("*.py")):
        text = p.read_text(encoding="utf-8")
        for b in BANNED:
            assert b not in text, f"{p.name} mentions {b}"
