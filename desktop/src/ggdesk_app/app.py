"""Application entry point.

M0 shell only: a main window with the version and a status line. The bench
window (preview, gate report, send) is M1 (build plan F08).
"""
from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

from ggdesk import __version__

TITLE = "GratisGraph Desktop"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{TITLE} {__version__}")
        self.setCentralWidget(QLabel("No job loaded."))
        self.statusBar().showMessage("Machine: not connected")
        self.resize(960, 640)


def self_test() -> int:
    """Headless check for packaged builds: core imports, window constructs."""
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    ok = w.windowTitle().startswith(TITLE)
    w.close()
    del app
    print("self-test", "ok" if ok else "FAILED")
    return 0 if ok else 1


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
