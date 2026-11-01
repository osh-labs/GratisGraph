"""Application entry point.

Shell: the main window, its BenchSession and the installers in extensions.py.
"""
from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

from ggdesk import __version__
from ggdesk_app import extensions
from ggdesk_app.session import BenchSession

TITLE = "GratisGraph Desktop"


class MainWindow(QMainWindow):
    def __init__(self, session: BenchSession | None = None) -> None:
        super().__init__()
        self.session = session if session is not None else BenchSession()
        self.setWindowTitle(f"{TITLE} {__version__}")
        self.setCentralWidget(QLabel("No job loaded."))
        self.statusBar().showMessage("Machine: not connected")
        self.resize(960, 640)
        extensions.install_all(self)


def _core_check() -> list[str]:
    """Build and gate a 10 mm square from the seed library, offline (no USB). Returns problems."""
    from ggdesk import gate
    from ggdesk.build import build, gate_inputs
    from ggdesk.library import Selection, load_library
    from ggdesk.model.geometry import Polyline
    from ggdesk.model.job import Job, TraceOp

    problems: list[str] = []
    lib = load_library()
    problems += [f"library: {e}" for e in lib.errors]
    job = Job("bench-scrap-40", (TraceOp((Polyline(((-5.0, -5.0), (5.0, -5.0), (5.0, 5.0), (-5.0, 5.0)), True),)),))
    sel = Selection(recipe="scrap-rotary-diamond-trace")
    result = build(job, lib, sel)
    rep = gate.run_gate(result.data, gate_inputs(result, sel))
    if not rep.passed or len(gate.RULES) < 16:
        problems.append("gate: the self-test square did not pass, or rules are missing")
    return problems


def self_test() -> int:
    """Headless check for packaged builds: library loads, build + gate run, window constructs. No USB."""
    problems = _core_check()
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    if not w.windowTitle().startswith(TITLE):
        problems.append("window title")
    w.close()
    del app
    for p in problems:
        print("self-test problem:", p)
    print("self-test", "ok" if not problems else "FAILED")
    return 0 if not problems else 1


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in args:
        return self_test()
    app = QApplication(sys.argv[:1] + args)
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
