"""Pattern panel (F10 in the bench window): pick a bench pattern, set its parameters, Generate.

The list comes from `session.patterns()` (ggdesk.patterns.PATTERNS); the form is
built from the pattern's ParamSpecs: a spin box for int and float, a check box
for bool, a line edit for str. Generate passes the form values to
`session.generate_pattern`, which coerces them (ggdesk.patterns.coerce),
generates the job and opens it in the session; the bench window then builds and
gates it like any opened job. Errors are shown in the panel, never swallowed.

Generation runs on the UI thread (the plan's budget is under 1 s per pattern).
"""
from __future__ import annotations

import sys
import traceback
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ggdesk.patterns import ParamSpec, PatternError
from ggdesk_app import theme
from ggdesk_app.session import BenchSession

INT_LIMIT = 2_000_000_000          # QSpinBox holds a 32-bit int
FLOAT_LIMIT = 1.0e9
MAX_DECIMALS = 10




def param_widget(spec: ParamSpec) -> QWidget:
    """The form widget for one ParamSpec, holding its default."""
    w: QWidget
    if spec.type is bool:
        cb = QCheckBox()
        cb.setChecked(bool(spec.default))
        w = cb
    elif spec.type is int:
        sb = QSpinBox()
        sb.setRange(-INT_LIMIT, INT_LIMIT)
        sb.setValue(int(spec.default))
        w = sb
    elif spec.type is float:
        db = QDoubleSpinBox()
        db.setDecimals(MAX_DECIMALS)   # never round what the operator types (M2 review, finding 7)
        db.setRange(-FLOAT_LIMIT, FLOAT_LIMIT)
        db.setValue(float(spec.default))
        w = db
    else:
        le = QLineEdit("" if spec.default is None else str(spec.default))
        w = le
    w.setAccessibleName(spec.name)
    w.setToolTip(spec.help)
    return w


def widget_value(w: QWidget) -> Any:
    if isinstance(w, QCheckBox):
        return w.isChecked()
    if isinstance(w, (QSpinBox, QDoubleSpinBox)):
        return w.value()
    if isinstance(w, QLineEdit):
        return w.text()
    raise TypeError(f"no value for {type(w).__name__}")


class PatternPanel(QWidget):
    generated = Signal(str)            # pattern name, after the job is open in the session

    def __init__(self, session: BenchSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.list = QListWidget()
        self.list.setAccessibleName("Patterns")
        self.title = QLabel("")
        self.title.setWordWrap(True)
        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        self.generate_btn = QPushButton("&Generate")
        self.generate_btn.setAutoDefault(False)
        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.setAccessibleName("Pattern error")
        self.error.setStyleSheet(theme.text_style("error"))
        self.fields: dict[str, QWidget] = {}

        lay = QVBoxLayout(self)
        lay.addWidget(self.list, 1)
        lay.addWidget(self.title)
        lay.addWidget(self.form_host)
        lay.addWidget(self.generate_btn)
        lay.addWidget(self.error)

        self.list.currentTextChanged.connect(self._show)
        self.generate_btn.clicked.connect(self.generate)
        self.refresh()

    def refresh(self) -> None:
        """Re-read the registry (patterns registered after the window opened appear)."""
        keep = self.current_name()
        self.list.blockSignals(True)
        self.list.clear()
        names = sorted(self.session.patterns())
        self.list.addItems(names)
        self.list.blockSignals(False)
        if not names:
            self._show("")
            return
        self.list.setCurrentRow(names.index(keep) if keep in names else 0)
        self._show(self.current_name())

    def current_name(self) -> str:
        item = self.list.currentItem()
        return item.text() if item is not None else ""

    def _show(self, name: str) -> None:
        while self.form.rowCount():
            self.form.removeRow(0)
        self.fields = {}
        self.error.setText("")
        p = self.session.patterns().get(name)
        if p is None:
            self.title.setText("No bench patterns are registered." if not self.list.count() else "")
            self.generate_btn.setEnabled(False)
            return
        self.title.setText(f"{p.title}  ({p.mode})")
        for spec in p.params:
            w = param_widget(spec)
            self.fields[spec.name] = w
            self.form.addRow(f"{spec.name}:", w)
        self.generate_btn.setEnabled(True)

    def values(self) -> dict[str, Any]:
        return {k: widget_value(w) for k, w in self.fields.items()}

    def generate(self) -> bool:
        """Generate the current pattern with the form values and open it. False on an error (shown)."""
        name = self.current_name()
        if not name:
            return False
        try:
            self.session.generate_pattern(name, self.values())
        except PatternError as e:
            self.error.setText(str(e))
            return False
        except Exception as e:  # shown to the operator, never swallowed
            traceback.print_exc(file=sys.stderr)
            self.error.setText(f"{name}: {type(e).__name__}: {e}")
            return False
        self.error.setText("")
        self.generated.emit(name)
        return True


def install(window: Any) -> None:
    """Extension hook (extensions.INSTALLERS): a dock beside the bench."""
    from ggdesk_app.bench import add_dock

    panel = PatternPanel(window.session)
    window.patterns_panel = panel
    window.patterns_dock = add_dock(window, panel, "Patterns", Qt.DockWidgetArea.LeftDockWidgetArea, "patterns_dock")
    bench = getattr(window, "bench", None)
    if bench is not None:
        # a generated job is opened in the session; the job panel then asks the worker to build and gate it
        panel.generated.connect(bench.job_panel.apply)
