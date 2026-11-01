"""Recipe selector: every recipe of the selected machine, with its mode and status.

A combo box whose items read "<id>  (<mode>, <STATUS>)"; a draft recipe is
marked DRAFT and drawn in the theme's draft colour. The item data holds the
recipe id, which is what the selection uses (`recipe_id()`). Choosing a recipe
emits `currentIndexChanged`; the job panel turns that into `session.select`,
and the bench window into a rebuild and regate on the build worker.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import QComboBox, QWidget

from ggdesk.library import Recipe
from ggdesk_app import theme
from ggdesk_app.session import BenchSession

ID_ROLE = Qt.ItemDataRole.UserRole


def recipe_label(r: Recipe) -> str:
    """'<id>  (<mode>, <STATUS>)'; a draft adds 'not validated' so it reads as a warning, not a tag."""
    status = "DRAFT, not validated" if r.status == "draft" else r.status.upper()
    return f"{r.ref.id}  ({r.mode}, {status})"


class RecipeSelector(QComboBox):
    def __init__(self, session: BenchSession, machine: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.setAccessibleName("Recipe")
        self.set_machine(machine)

    def set_machine(self, machine: str) -> None:
        """Fill the list with `machine`'s recipes; the current recipe is kept when it is still there."""
        keep = self.recipe_id()
        self.blockSignals(True)
        self.clear()
        for r in self.session.recipes_for(machine):
            self.addItem(recipe_label(r), r.ref.id)
            i = self.count() - 1
            self.setItemData(i, f"{r.name}\nmode {r.mode}, status {r.status}, v{r.ref.version}",
                             Qt.ItemDataRole.ToolTipRole)
            if r.status == "draft":
                self.setItemData(i, QBrush(theme.status_colour("draft")), Qt.ItemDataRole.ForegroundRole)
        self.machine = machine
        if keep:
            self.select_recipe(keep)
        self.blockSignals(False)

    def recipe_id(self) -> str:
        """The id of the chosen recipe ('' when the machine has none)."""
        v = self.currentData(ID_ROLE)
        return v if isinstance(v, str) else ""

    def recipe_ids(self) -> list[str]:
        return [str(self.itemData(i, ID_ROLE)) for i in range(self.count())]

    def select_recipe(self, recipe_id: str) -> bool:
        """Choose a recipe by id. False (nothing changed) when this machine has no such recipe."""
        i = self.findData(recipe_id, ID_ROLE)
        if i < 0:
            return False
        self.setCurrentIndex(i)
        return True
