"""The bench window (feature F08): job and selection, bed preview, gate report, Send and Abort.

Installed into the main window by extensions.INSTALLERS ("ggdesk_app.bench:install").
The window never builds, gates or sends itself: the session does, build and
gate on the BuildWorker thread and the send on the SendWorker thread. The
preview is drawn from the session's final bytes (decoded), never from build state.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDockWidget, QHBoxLayout, QLabel, QLineEdit, QMenu, QSplitter, QVBoxLayout, QWidget

from ggdesk.gts_read import GtsFormatError
from ggdesk.library import Resolved, resolve
from ggdesk.render import DrawList, draw_list
from ggdesk_app import theme
from ggdesk_app.panels.gate_report import GateReportPanel
from ggdesk_app.panels.job import JobPanel
from ggdesk_app.panels.preview import PreviewView
from ggdesk_app.session import BenchSession, SessionState
from ggdesk_app.workers import BuildWorker, SendWorker


class BenchWidget(QWidget):
    def __init__(self, session: BenchSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.job_panel = JobPanel(session)
        self.preview = PreviewView()
        self.gate_panel = GateReportPanel(session)
        self.operator = QLineEdit()
        self.operator.setAccessibleName("Operator")
        self.operator.setPlaceholderText("operator name or initials (job log)")
        self.status = QLabel(session.state.status)
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Status")
        self.build_worker = BuildWorker(session, parent=self)
        self.send_worker = SendWorker(session, parent=self)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.gate_panel, 1)
        op_row = QHBoxLayout()
        op_label = QLabel("O&perator:")
        op_label.setBuddy(self.operator)
        op_row.addWidget(op_label)
        op_row.addWidget(self.operator, 1)
        rl.addLayout(op_row)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self.job_panel)
        split.addWidget(self.preview)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setStretchFactor(2, 0)
        lay = QVBoxLayout(self)
        lay.addWidget(split, 1)
        lay.addWidget(self.status)

        self.job_panel.selection_changed.connect(self.build_worker.request)
        self.gate_panel.send_requested.connect(self._send)
        self.send_worker.finished.connect(self._send_finished)
        session.subscribe(self._on_state)
        self.setTabOrder(self.gate_panel.abort_btn, self.operator)

    # --- state -> preview and status ------------------------------------------------------

    def _resolved(self, st: SessionState) -> Resolved | None:
        if st.job is None:
            return None
        try:
            return resolve(self.session.library, st.job, st.selection)
        except (ValueError, KeyError):
            return None

    def _on_state(self, st: SessionState) -> None:
        dl: DrawList | None = None
        problem = st.error
        if st.data is not None:
            try:
                dl = draw_list(st.data, self._resolved(st))
            except GtsFormatError as e:
                problem = f"Preview: the bytes do not decode ({e})."
        self.preview.set_draw_list(dl)
        self.status.setText(st.status + (f"  {problem}" if problem else ""))
        self.status.setStyleSheet(theme.text_style("error" if problem else "muted"))
        win = self.window()
        if win is not self and hasattr(win, "statusBar"):
            win.statusBar().showMessage(st.status)

    # --- send ------------------------------------------------------------------------------

    def _send(self, typed_ack: str) -> None:
        if self.send_worker.start(typed_ack, self.operator.text().strip()):
            self.gate_panel.set_busy(True)
            self.job_panel.setEnabled(False)
            self.session.note("Sending to the machine...")

    def _send_finished(self, _result: Any, _error: str | None) -> None:
        self.gate_panel.set_busy(False)
        self.job_panel.setEnabled(True)


def install(window: Any) -> None:
    """Extension hook: put the bench in the main window's centre."""
    bench = BenchWidget(window.session, window)
    window.setCentralWidget(bench)
    window.bench = bench


def add_dock(window: Any, widget: QWidget, title: str, area: Qt.DockWidgetArea, name: str,
             tabify_with: QDockWidget | None = None) -> QDockWidget:
    """Host an M2 panel beside the bench (outside BenchWidget) as a dock with a View menu toggle.

    Docks keep the bench's own widget tree unchanged (its tests check that it
    holds no check box or override control); a pattern form's check boxes live here.
    """
    dock = QDockWidget(title, window)
    dock.setObjectName(name)
    dock.setWidget(widget)
    dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable
                     | QDockWidget.DockWidgetFeature.DockWidgetFloatable
                     | QDockWidget.DockWidgetFeature.DockWidgetClosable)
    window.addDockWidget(area, dock)
    if tabify_with is not None:
        window.tabifyDockWidget(tabify_with, dock)
    menu = getattr(window, "view_menu", None)
    if not isinstance(menu, QMenu):
        menu = window.menuBar().addMenu("&View")
        window.view_menu = menu
    menu.addAction(dock.toggleViewAction())
    return dock
