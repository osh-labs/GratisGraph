"""The core package is Qt-free: every module under src/ggdesk imports with
PySide6 blocked, and none of them pulls PySide6 in. Ruff's banned-api rule
(TID251) catches the import statement; this test catches indirect imports."""
from __future__ import annotations

import subprocess
import sys

from tests.conftest import DESKTOP

PROBE = r"""
import importlib, importlib.abc, pkgutil, sys

class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in ("PySide6", "shiboken6", "PyQt5", "PyQt6"):
            raise ImportError(f"Qt import from the core: {name}")
        return None

sys.meta_path.insert(0, BlockQt())
import ggdesk
names = sorted(m.name for m in pkgutil.walk_packages(ggdesk.__path__, "ggdesk.")
               if not m.name.endswith(".__main__"))
for n in names:
    importlib.import_module(n)
leaked = sorted(m for m in sys.modules if m.split(".")[0] in ("PySide6", "shiboken6", "PyQt5", "PyQt6"))
assert not leaked, leaked
print(len(names))
"""


def test_core_imports_without_qt() -> None:
    r = subprocess.run([sys.executable, "-c", PROBE], cwd=DESKTOP / "src",
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert int(r.stdout.strip()) > 0
