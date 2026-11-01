"""Gate report panel: findings, residual lines, the typed acknowledgement, Send and Abort.

There is no override control of any kind. Send is enabled only while
`session.can_send(typed_ack)` is true (a passing report bound to the current
bytes and, with soft flags, the exact phrase repeating the count). Pressing
Send asks the bench to run `session.send` off the UI thread; Abort calls
`session.abort()` directly.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ggdesk.gate import GateReport, Severity
from ggdesk_app import theme
from ggdesk_app.session import BenchSession, SessionState


def _list(name: str) -> QListWidget:
    w = QListWidget()
    w.setAccessibleName(name)
    w.setWordWrap(True)
    w.setAlternatingRowColors(False)
    return w


class GateReportPanel(QWidget):
    send_requested = Signal(str)          # the typed acknowledgement

    def __init__(self, session: BenchSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self._busy = False

        self.verdict = QLabel("No report.")
        self.verdict.setWordWrap(True)
        self.verdict.setAccessibleName("Gate verdict")
        self.hard = _list("Hard findings")
        self.soft = _list("Soft findings")
        self.residual = _list("Residual status")
        self.ack_hint = QLabel("")
        self.ack_hint.setWordWrap(True)
        self.ack = QLineEdit()
        self.ack.setAccessibleName("Acknowledgement")
        self.ack.setPlaceholderText("Type the phrase shown above to accept the flags")
        ack_label = QLabel("&Acknowledge:")
        ack_label.setBuddy(self.ack)
        self.send_btn = QPushButton("&Send to machine")
        self.send_btn.setEnabled(False)
        self.abort_btn = QPushButton("A&bort")
        for b in (self.send_btn, self.abort_btn):
            b.setAutoDefault(False)

        lay = QVBoxLayout(self)
        lay.addWidget(self.verdict)
        for title, w in (("Hard findings (block)", self.hard), ("Soft findings (flag)", self.soft),
                         ("Residual status (always shown)", self.residual)):
            box = QGroupBox(title)
            QVBoxLayout(box).addWidget(w)
            lay.addWidget(box, 1)
        lay.addWidget(self.ack_hint)
        row = QHBoxLayout()
        row.addWidget(ack_label)
        row.addWidget(self.ack, 1)
        lay.addLayout(row)
        buttons = QHBoxLayout()
        buttons.addWidget(self.send_btn)
        buttons.addWidget(self.abort_btn)
        lay.addLayout(buttons)

        self.ack.textChanged.connect(self._update_send)
        self.send_btn.clicked.connect(self._send)
        self.abort_btn.clicked.connect(self._abort)
        session.subscribe(self._on_state)
        self._on_state(session.state)

    # --- state -> widgets ---------------------------------------------------------------

    def _on_state(self, st: SessionState) -> None:
        self.show_report(st.report)
        self._update_send()

    def show_report(self, r: GateReport | None) -> None:
        for w in (self.hard, self.soft, self.residual):
            w.clear()
        if r is None:
            self.verdict.setText("No report." if self.session.state.error is None
                                 else "No report: " + self.session.state.error)
            self.verdict.setStyleSheet(theme.text_style("muted" if self.session.state.error is None else "error"))
            self.ack_hint.setText("")
            return
        hard = [f for f in r.findings if f.severity is Severity.HARD]
        soft = [f for f in r.findings if f.severity is Severity.SOFT]
        for f in hard:
            self.hard.addItem(f"{f.rule}  {f.message}" + (f"  @{f.offset}" if f.offset is not None else ""))
        for f in soft:
            self.soft.addItem(f"{f.rule}  {f.message}")
        for line in r.residual:
            self.residual.addItem(line)
        if not r.passed:
            self.verdict.setText(f"REFUSED: {len(hard)} hard finding(s). This job cannot be sent.")
            self.verdict.setStyleSheet(theme.text_style("hard", bold=True))
        elif r.flags:
            self.verdict.setText(f"PASS with {r.flags} flag(s) to acknowledge.")
            self.verdict.setStyleSheet(theme.text_style("soft", bold=True))
        else:
            self.verdict.setText("PASS. No flags.")
            self.verdict.setStyleSheet(theme.text_style("pass", bold=True))
        self.ack_hint.setText(f"To send, type: {r.ack_phrase}" if r.passed and r.flags else "")
        self.ack.setEnabled(r.passed and r.flags > 0)

    def _update_send(self) -> None:
        self.send_btn.setEnabled(not self._busy and self.session.can_send(self.ack.text()))

    def set_busy(self, busy: bool) -> None:
        """While a send runs, Send stays disabled; Abort stays available."""
        self._busy = busy
        self._update_send()

    # --- actions -------------------------------------------------------------------------

    def _send(self) -> None:
        text = self.ack.text()
        if self.session.can_send(text):       # re-checked; the button state is not trusted
            self.send_requested.emit(text)

    def _abort(self) -> None:
        if self.session.abort():
            self.session.note("Abort sent to the machine.")
        else:
            self.session.note("Nothing to abort: no job has been sent from this window.")
