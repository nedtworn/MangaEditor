"""Scene item that draws the paint layer.

During a brush stroke the stroke is drawn at full opacity into a separate buffer, and the
buffer is shown over the layer at the brush opacity. When the stroke ends the buffer is
merged into the layer in one step. This way overlapping segments of a semi-transparent
brush do not get darker (no blotches).
"""
from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

from ..core.page import PageDocument


class PaintLayerItem(QGraphicsItem):
    def __init__(self, page: PageDocument) -> None:
        super().__init__()
        self.page = page
        self.stroke_buffer: QImage | None = None
        self.stroke_opacity = 1.0
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption, True)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        page.paintChanged.connect(self._on_paint_changed)

    def _on_paint_changed(self, rect: QRect) -> None:
        self.update(QRectF(rect))

    def boundingRect(self) -> QRectF:
        return QRectF(self.page.rect)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        layer = self.page.paint
        if layer is None:
            return
        r = option.exposedRect.toAlignedRect().adjusted(-1, -1, 1, 1).intersected(self.page.rect)
        if r.isEmpty():
            return
        painter.drawImage(r, layer, r)
        if self.stroke_buffer is not None:
            painter.setOpacity(self.stroke_opacity)
            painter.drawImage(r, self.stroke_buffer, r)
            painter.setOpacity(1.0)
