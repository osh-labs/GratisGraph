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
