"""Setup card panel: what the operator sets by hand for the current job and selection.

Lines come from `session.setup_card()` (ggdesk.setupcard.setup_card on the
resolved selection), so the manual-depth line is the gate report's residual
line, verbatim. Refreshed whenever the job or the selection changes. Read-only.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import QLabel, QListWidget, QVBoxLayout, QWidget

from ggdesk.library import Selection
from ggdesk.model.job import Job
from ggdesk_app import theme
from ggdesk_app.session import BenchSession, SessionState

NO_JOB = "Open or generate a job to see its setup card."


class SetupCardPanel(QWidget):
    def __init__(self, session: BenchSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.title = QLabel(NO_JOB)
        self.title.setWordWrap(True)
        self.title.setAccessibleName("Setup card title")
        self.lines = QListWidget()
        self.lines.setAccessibleName("Setup card")
        self.lines.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addWidget(self.title)
        lay.addWidget(self.lines, 1)
        self._shown: tuple[Job | None, Selection] | None = None
        session.subscribe(self._on_state)
        self._on_state(session.state)

    def texts(self) -> list[str]:
        return [self.lines.item(i).text() for i in range(self.lines.count())]

    def _on_state(self, st: SessionState) -> None:
        shown = self._shown
        if shown is not None and shown[0] is st.job and shown[1] == st.selection:
            return                         # status notes and build results do not change the card
        self._shown = (st.job, st.selection)
        self.refresh()

    def refresh(self) -> None:
        self.lines.clear()
        try:
            card = self.session.setup_card()
        except (ValueError, KeyError) as e:
            msg = e.args[0] if isinstance(e, KeyError) and e.args else e
            self.title.setText(f"No setup card: {msg}")
            self.title.setStyleSheet(theme.text_style("error"))
            return
        if card is None:
            self.title.setText(NO_JOB)
            self.title.setStyleSheet(theme.text_style("muted"))
            return
        self.title.setText(card.title)
        self.title.setStyleSheet(theme.text_style("muted", bold=True))
        for line in card.lines:
            self.lines.addItem(line)
            if "DRAFT" in line:
                self.lines.item(self.lines.count() - 1).setForeground(QBrush(theme.status_colour("draft")))


def install(window: Any) -> None:
    """Extension hook (extensions.INSTALLERS): a dock beside the bench."""
    from ggdesk_app.bench import add_dock

    panel = SetupCardPanel(window.session)
    window.setup_card_panel = panel
    window.setup_card_dock = add_dock(window, panel, "Setup card", Qt.DockWidgetArea.RightDockWidgetArea,
                                      "setup_card_dock")
