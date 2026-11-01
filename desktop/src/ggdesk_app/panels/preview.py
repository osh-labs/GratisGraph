"""Bed preview: a QGraphicsView painting exactly the items of a render.DrawList.

Scene units are machine mm with +Y down (no flip), the convention of
ggdesk.render.drawlist: home at the top-left, the operator's front edge at the
bottom, labelled "operator". The view never decodes or builds anything; it is
handed a DrawList made from the decoded bytes.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QPainter, QPainterPath, QPen, QResizeEvent
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QWidget,
)

from ggdesk.model.geometry import Pt
from ggdesk.render import OPERATOR_LABEL, DrawList
from ggdesk_app import theme

KIND_KEY = 0          # QGraphicsItem.data(KIND_KEY) holds the draw-list kind, or "label"
MARGIN_MM = 6.0
FILLED = {"part": "part_fill", "keep_out": "keep_out_fill"}


class PreviewView(QGraphicsView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setBackgroundBrush(QBrush(theme.colour("background")))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Bed preview")
        self.draw_list: DrawList | None = None

    def set_draw_list(self, dl: DrawList | None) -> None:
        scene = self.scene()
        scene.clear()
        self.draw_list = dl
        if dl is None:
            return
        for z, item in enumerate(dl.items):
            g = self._item(item.kind, item.points)
            g.setData(KIND_KEY, item.kind)
            g.setZValue(z)
            scene.addItem(g)
        x0, y0, x1, y1 = dl.bounds()
        label = QGraphicsSimpleTextItem(OPERATOR_LABEL)
        label.setData(KIND_KEY, "label")
        label.setBrush(QBrush(theme.colour("label")))
        label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        label.setPos((x0 + x1) / 2, y1 + MARGIN_MM / 4)    # front edge, below the bed
        label.setZValue(len(dl.items))
        scene.addItem(label)
        rect = QRectF(x0 - MARGIN_MM, y0 - MARGIN_MM, (x1 - x0) + 2 * MARGIN_MM, (y1 - y0) + 2 * MARGIN_MM)
        scene.setSceneRect(rect)
        self.fit()

    def _item(self, kind: str, points: tuple[Pt, ...]) -> QGraphicsItem:
        if kind == "start":
            r = theme.START_RADIUS_MM
            x, y = points[0]
            e = QGraphicsEllipseItem(x - r, y - r, 2 * r, 2 * r)
            e.setBrush(QBrush(theme.colour("start")))
            e.setPen(QPen(Qt.PenStyle.NoPen))
            return e
        path = QPainterPath(QPointF(*points[0]))
        for p in points[1:]:
            path.lineTo(QPointF(*p))
        g = QGraphicsPathItem(path)
        pen = QPen(theme.colour(kind), theme.PEN_PX.get(kind, 1.0))
        pen.setCosmetic(True)
        if kind in ("rapid", "field"):
            pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        g.setPen(pen)
        if kind in FILLED:
            fill = theme.colour(FILLED[kind])
            if kind == "keep_out":
                fill.setAlpha(theme.KEEP_OUT_FILL_ALPHA)
            g.setBrush(QBrush(fill))
        return g

    def fit(self) -> None:
        if self.draw_list is not None:
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.fit()

    def scene_items(self) -> list[tuple[str, tuple[Pt, ...]]]:
        """(kind, points) read back from the painted Qt items, in paint order (labels excluded).

        Read from the items' own geometry, so a test comparing this with the
        draw list and the SVG catches any drift between screen and file.
        """
        out: list[tuple[float, str, tuple[Pt, ...]]] = []
        for g in self.scene().items():
            kind = g.data(KIND_KEY)
            if kind is None or kind == "label":
                continue
            if isinstance(g, QGraphicsEllipseItem):
                c = g.rect().center()
                pts: tuple[Pt, ...] = ((c.x(), c.y()),)
            elif isinstance(g, QGraphicsPathItem):
                path = g.path()
                pts = tuple((path.elementAt(i).x, path.elementAt(i).y) for i in range(path.elementCount()))
            else:
                continue
            out.append((g.zValue(), str(kind), pts))
        out.sort(key=lambda t: t[0])
        return [(k, p) for _, k, p in out]
