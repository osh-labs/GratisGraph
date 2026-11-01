"""Library browser: a read-only tree of every library entry, by kind.

Each fact shows its value, confidence and source (key, title and ref), or
"needs measurement (G#)" with its measure steps as children. Library load
errors are listed at the top. There are no edit controls: the library is data
under `library/` and changes through reviewed TOML files only.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, fields, is_dataclass
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import QAbstractItemView, QLabel, QListWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ggdesk.library import Fact, Library, Range
from ggdesk.library.model import KINDS, Outline, Source
from ggdesk_app import theme
from ggdesk_app.session import BenchSession

SKIP_FIELDS = ("ref", "overrides")


@dataclass(frozen=True)
class Row:
    """One line under an entry: a fact (fact set) or a plain field (fact None)."""
    path: str
    text: str
    fact: Fact[Any] | None = None


def fmt_value(v: Any) -> str:
    if isinstance(v, Range):
        return f"{v.min}..{v.max}"
    if isinstance(v, Outline):
        if v.kind == "rect":
            r = f", corner radius {v.corner_radius_mm:g}" if v.corner_radius_mm else ""
            c = f", centre ({v.centre_mm[0]:g}, {v.centre_mm[1]:g})" if v.centre_mm != (0.0, 0.0) else ""
            return f"rect {v.width_mm:g} x {v.height_mm:g} mm{r}{c}"
        return f"polygon, {len(v.points)} points"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, tuple):
        return "[" + ", ".join(fmt_value(x) for x in v) + "]"
    return str(v)


def fact_text(path: str, f: Fact[Any], sources: Mapping[str, Source]) -> str:
    if f.needs_measurement:
        return f"{path}: needs measurement ({f.gap or 'gap not named'})"
    if f.value is None:
        return f"{path}: not set"
    src = sources.get(f.src or "")
    where = f.src or "no source"
    if src is not None and src.title:
        where += f" ({src.title})"
    return f"{path}: {fmt_value(f.value)} [{f.confidence}]  source {where}, ref {f.ref}"


def entry_rows(entry: Any, sources: Mapping[str, Source]) -> list[Row]:
    """Every field of one entry, facts with provenance, nested tables flattened to dotted paths."""
    rows: list[Row] = []

    def walk(path: str, obj: Any) -> None:
        if isinstance(obj, Fact):
            rows.append(Row(path, fact_text(path, obj, sources), obj))
        elif isinstance(obj, Mapping):
            if not obj:
                rows.append(Row(path, f"{path}: none"))
            for k in sorted(obj):
                walk(f"{path}.{k}", obj[k])
        elif is_dataclass(obj) and not isinstance(obj, type) and not isinstance(obj, (Range, Outline)):
            label = getattr(obj, "id", None)
            for f in fields(obj):
                if f.name == "id":
                    continue
                walk(f"{path}.{label}.{f.name}" if label else f"{path}.{f.name}", getattr(obj, f.name))
        elif isinstance(obj, tuple) and obj and all(is_dataclass(x) for x in obj):
            for x in obj:
                walk(path, x)
        else:
            rows.append(Row(path, f"{path}: {fmt_value(obj)}"))

    for f in fields(entry):
        if f.name not in SKIP_FIELDS:
            walk(f.name, getattr(entry, f.name))
    return rows


def iter_entries(lib: Library) -> Iterator[tuple[str, list[tuple[str, Any]]]]:
    """(kind, [(id, entry), ...]) in KINDS order, ids sorted."""
    for kind in KINDS:
        table: Mapping[str, Any] = getattr(lib, kind + "s")
        yield kind, [(k, table[k]) for k in sorted(table)]


class LibraryBrowser(QWidget):
    def __init__(self, session: BenchSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        lib = session.library
        self.errors_title = QLabel("")
        self.errors_title.setWordWrap(True)
        self.errors = QListWidget()
        self.errors.setAccessibleName("Library errors")
        self.errors.setWordWrap(True)
        self.errors.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree = QTreeWidget()
        self.tree.setAccessibleName("Library entries")
        self.tree.setHeaderHidden(True)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.addWidget(self.errors_title)
        lay.addWidget(self.errors)
        lay.addWidget(self.tree, 1)

        if lib.errors:
            self.errors_title.setText(f"{len(lib.errors)} library entr{'y is' if len(lib.errors) == 1 else 'ies are'}"
                                      " invalid and not loaded:")
            self.errors_title.setStyleSheet(theme.text_style("error", bold=True))
            for e in lib.errors:
                self.errors.addItem(str(e))
        else:
            self.errors_title.setText("No library load errors.")
            self.errors_title.setStyleSheet(theme.text_style("muted"))
            self.errors.hide()
        self._fill(lib)

    def _fill(self, lib: Library) -> None:
        unmeasured = QBrush(theme.status_colour("unmeasured"))
        for kind, entries in iter_entries(lib):
            k_item = QTreeWidgetItem([f"{kind}s ({len(entries)})"])
            self.tree.addTopLevelItem(k_item)
            for eid, entry in entries:
                ref = entry.ref
                status = f", {entry.status.upper()}" if kind == "recipe" else ""
                e_item = QTreeWidgetItem([f"{eid}  v{ref.version}{status}: {entry.name}"])
                e_item.setToolTip(0, f"sha256 {ref.sha256}\n{lib.files.get((kind, eid), '')}")
                k_item.addChild(e_item)
                for row in entry_rows(entry, lib.sources.get((kind, eid), {})):
                    r_item = QTreeWidgetItem([row.text])
                    e_item.addChild(r_item)
                    if row.fact is not None and row.fact.needs_measurement:
                        r_item.setForeground(0, unmeasured)
                        for n, step in enumerate(row.fact.measure, 1):
                            r_item.addChild(QTreeWidgetItem([f"measure {n}: {step}"]))
            k_item.setExpanded(True)

    def find_items(self, text: str) -> list[QTreeWidgetItem]:
        """Tree items whose text contains `text` (any depth), in tree order."""
        out: list[QTreeWidgetItem] = []

        def walk(item: QTreeWidgetItem | None) -> None:
            if item is None:
                return
            if text in item.text(0):
                out.append(item)
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return out


def install(window: Any) -> None:
    """Extension hook (extensions.INSTALLERS): a dock beside the bench."""
    from ggdesk_app.bench import add_dock

    panel = LibraryBrowser(window.session)
    window.library_panel = panel
    window.library_dock = add_dock(window, panel, "Library", Qt.DockWidgetArea.RightDockWidgetArea, "library_dock",
                                   tabify_with=getattr(window, "setup_card_dock", None))
