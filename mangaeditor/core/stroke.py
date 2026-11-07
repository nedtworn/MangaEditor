"""Brush and eraser strokes.

Brush: the stroke is drawn at full opacity into a separate buffer; when it ends, the buffer
is merged into the layer in one step at the brush opacity (no blotches with a
semi-transparent brush). Eraser: removes alpha directly from the paint layer (DestinationOut).
The original image is kept separately, so the eraser always reveals the original again.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QLineF, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen

from .commands import StrokeCommand
from .page import PageDocument, blank_layer

BRUSH = "brush"
ERASER = "eraser"


class StrokeSession:
    def __init__(
        self,
        page: PageDocument,
        mode: str,
        size: float,
        color: QColor | None = None,
        opacity: float = 1.0,
        on_buffer_update: Optional[Callable[[QRect], None]] = None,
    ) -> None:
        assert page.paint is not None, "page is not loaded"
        assert mode in (BRUSH, ERASER)
        self.page = page
        self.mode = mode
        self.size = max(1.0, float(size))
        self.color = QColor(color) if color is not None else QColor(0, 0, 0)
        self.color.setAlpha(255)
        self.opacity = max(0.0, min(1.0, opacity))
        self._on_buffer_update = on_buffer_update
        self._before = page.paint.copy()
        self.dirty = QRect()
        self._last: QPointF | None = None
        self.buffer: QImage | None = blank_layer(page.size) if mode == BRUSH else None
        self.finished = False

    # ---------------------------------------------------------------- drawing
    def _target(self) -> QImage:
        return self.buffer if self.buffer is not None else self.page.paint  # type: ignore[return-value]

    def add_point(self, p: QPointF) -> None:
        if self.finished:
            return
        p = QPointF(p)
        painter = QPainter(self._target())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.mode == ERASER:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        r = self.size / 2.0
        if self._last is None or QLineF(self._last, p).length() < 0.01:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.color)
            painter.drawEllipse(p, r, r)
            seg = QRectF(p.x() - r, p.y() - r, 2 * r, 2 * r)
        else:
            pen = QPen(self.color, self.size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(QLineF(self._last, p))
            seg = QRectF(self._last, p).normalized().adjusted(-r, -r, r, r)
        painter.end()
        self._last = p
        changed = seg.adjusted(-2, -2, 2, 2).toAlignedRect().intersected(self.page.rect)
        if changed.isEmpty():
            return
        self.dirty = self.dirty.united(changed) if not self.dirty.isEmpty() else changed
        if self.mode == ERASER:
            self.page.notify_paint_changed(changed)
        elif self._on_buffer_update is not None:
            self._on_buffer_update(changed)

    def finish(self, label: str | None = None) -> StrokeCommand | None:
        """Merges the stroke into the layer and returns the undo command (the caller pushes it
        on the stack). None if no pixel was affected."""
        if self.finished:
            return None
        self.finished = True
        if self.dirty.isEmpty():
            self.buffer = None
            return None
        paint = self.page.paint
        assert paint is not None
        if self.buffer is not None:
            painter = QPainter(paint)
            painter.setOpacity(self.opacity)
            painter.drawImage(self.dirty.topLeft(), self.buffer, self.dirty)
            painter.end()
            self.buffer = None
            self.page.notify_paint_changed(self.dirty)
        before = self._before.copy(self.dirty)
        after = paint.copy(self.dirty)
        self._before = QImage()
        if label is None:
            label = "Fırça" if self.mode == BRUSH else "Silgi"
        return StrokeCommand(self.page, self.dirty, before, after, label)

    def cancel(self) -> None:
        if self.finished:
            return
        self.finished = True
        if self.mode == ERASER and not self.dirty.isEmpty():
            self.page.write_paint_region(self.dirty, self._before.copy(self.dirty))
        self.buffer = None
