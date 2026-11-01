"""Job and selection panel: open a job; choose recipe, fixture, nest; bench overrides; per-job keep-outs.

It only edits the session's Selection (`session.select`); the bench window then
asks the worker for a fresh build and gate. Bench overrides change draft recipe
values for this run (they are printed in the gate report's residual lines);
they are not a gate override, and confirmed recipes refuse them.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ggdesk.commands.selection import UsageError, parse_keep_out, parse_overrides
from ggdesk.library import Selection
from ggdesk.library.select import DEFAULT_MACHINE
from ggdesk_app import theme
from ggdesk_app.panels.recipe import RecipeSelector
from ggdesk_app.session import BenchSession, SessionState

JOB_FILTER = "GratisGraph job (*.ggj);;All files (*)"


def parse_override_text(text: str) -> dict[str, object]:
    """'pz=80, vs=20' -> {'pz': 80, 'vs': 20} (same value rules as `ggdesk build --set`)."""
    items = [t.strip() for t in text.replace(";", ",").split(",") if t.strip()]
    return parse_overrides(items)


def parse_keep_out_text(text: str) -> tuple[tuple[tuple[float, float], ...], ...]:
    """'x0,y0,x1,y1; x0,y0,x1,y1' -> rectangles in machine mm (same rules as `--keep-out`)."""
    return tuple(parse_keep_out(t.strip()) for t in text.split(";") if t.strip())


class JobPanel(QWidget):
    selection_changed = Signal()

    def __init__(self, session: BenchSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        lib = session.library
        self.open_btn = QPushButton("&Open job...")
        self.open_btn.setAutoDefault(False)
        self.job_label = QLabel("No job loaded.")
        self.job_label.setWordWrap(True)
        self.machine = DEFAULT_MACHINE if DEFAULT_MACHINE in lib.machines else next(iter(sorted(lib.machines)), "")
        self.recipe = RecipeSelector(session, self.machine)     # id, mode, status; draft marked (M2.4)
        self.fixture = QComboBox()
        self.fixture.addItems(sorted(lib.fixtures))
        if "bare-bed" in lib.fixtures:
            self.fixture.setCurrentText("bare-bed")
        self.nest = QComboBox()
        self.overrides = QLineEdit()
        self.overrides.setPlaceholderText("draft recipe only, e.g. pz=60, vs=12")
        self.keep_outs = QLineEdit()
        self.keep_outs.setPlaceholderText("x0,y0,x1,y1; ... (mm, machine frame)")
        self.problem = QLabel("")
        self.problem.setWordWrap(True)
        self.problem.setStyleSheet(theme.text_style("error"))
        for w, name in ((self.recipe, "Recipe"), (self.fixture, "Fixture"), (self.nest, "Nest"),
                        (self.overrides, "Bench overrides"), (self.keep_outs, "Per-job keep-outs")):
            w.setAccessibleName(name)

        form = QFormLayout()
        form.addRow("&Recipe:", self.recipe)
        form.addRow("&Fixture:", self.fixture)
        form.addRow("&Nest:", self.nest)
        form.addRow("Bench o&verrides:", self.overrides)
        form.addRow("&Keep-outs:", self.keep_outs)
        lay = QVBoxLayout(self)
        lay.addWidget(self.open_btn)
        lay.addWidget(self.job_label)
        lay.addLayout(form)
        lay.addWidget(self.problem)
        lay.addStretch(1)

        self._fill_nests()
        self.open_btn.clicked.connect(self._open_dialog)
        self.fixture.currentTextChanged.connect(self._fixture_changed)
        self.recipe.currentIndexChanged.connect(self.apply)
        self.nest.currentTextChanged.connect(self.apply)
        self.overrides.editingFinished.connect(self.apply)
        self.keep_outs.editingFinished.connect(self.apply)
        session.subscribe(self._on_state)
        self._on_state(session.state)

    def _fill_nests(self) -> None:
        fx = self.session.library.fixtures.get(self.fixture.currentText())
        self.nest.blockSignals(True)
        self.nest.clear()
        if fx is not None:
            self.nest.addItems([n.id for n in fx.nests])
        self.nest.blockSignals(False)
        fx_per_job = fx is not None and fx.keep_outs_per_job
        self.keep_outs.setEnabled(fx_per_job)

    def _fixture_changed(self) -> None:
        self._fill_nests()
        self.apply()

    def _on_state(self, st: SessionState) -> None:
        if st.job_path is None and st.job is not None:
            self.job_label.setText(f"{st.job_label or 'generated job'}  (part {st.job.part}, "
                                   f"{len(st.job.operations)} operation(s))")
        elif st.job_path is None:
            self.job_label.setText("No job loaded.")
        elif st.job is None:
            self.job_label.setText(f"{st.job_path.name}: rejected")
        else:
            self.job_label.setText(f"{st.job_path.name}  (part {st.job.part}, "
                                   f"{len(st.job.operations)} operation(s))")

    def _open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open job", "", JOB_FILTER)
        if path:
            self.open_job(Path(path))

    def open_job(self, path: Path) -> None:
        self.session.open_job(path)
        self.apply()

    def selection(self) -> Selection:
        """The selection the widgets describe (raises UsageError on unreadable text)."""
        kos = parse_keep_out_text(self.keep_outs.text()) if self.keep_outs.isEnabled() else ()
        return Selection(self.machine, self.recipe.recipe_id(), self.fixture.currentText(),
                         self.nest.currentText(), parse_override_text(self.overrides.text()), kos)

    def apply(self) -> None:
        try:
            sel = self.selection()
        except UsageError as e:
            self.problem.setText(str(e))
            # The widgets no longer describe the gated selection: drop the report so Send cannot stay enabled.
            self.session.select(self.session.state.selection)
            return
        self.problem.setText("")
        if sel == self.session.state.selection and self.session.state.report is not None:
            return
        self.session.select(sel)
        self.selection_changed.emit()
