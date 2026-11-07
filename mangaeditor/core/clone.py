"""Klonlama (Clone Stamp) darbesi.

Logic
  * offset = source − target (integers). Every target pixel is an exact copy of the source
    pixel that lies offset away (no resampling, no blur).
  * The source is the view at the START of the stroke: the original image plus the paint
    layer as it was then. A long stroke therefore never copies its own paint, and the
    result does not depend on the speed or sampling of the mouse events.
  * The gaps between mouse events are filled with the mask of a straight capsule (a line
    with round ends), so fast strokes have no holes.
  * Parts that leave the source or target image are skipped (no crash, nothing is written
    outside the image).
  * The result is written to the paint layer; the original image is never changed. Undo
    uses the same StrokeCommand as the brush and eraser (only the affected rectangle is kept).
"""
from __future__ import annotations

import math
from typing import Callable, Optional

from PySide6.QtCore import QLineF, QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen

from .commands import StrokeCommand
from .page import PAINT_FORMAT, PageDocument, blank_layer

LABEL = "Klonlama"


def offset_between(source: QPointF, target: QPointF) -> QPoint:
    """source − target, rounded to the nearest integer (for exact pixel copies)."""
    import math

    return QPoint(math.floor(source.x() - target.x() + 0.5), math.floor(source.y() - target.y() + 0.5))


class CloneSession:
    def __init__(
        self,
        page: PageDocument,
        offset: QPoint,
        size: float,
        on_update: Optional[Callable[[QRect], None]] = None,
    ) -> None:
        assert page.paint is not None and page.original is not None, "page is not loaded"
        self.page = page
        self.offset = QPoint(offset)
        self.size = max(1.0, float(size))
        self._on_update = on_update
        self._before = page.paint.copy()  # paint layer at the start of the stroke: undo + source
        self.dirty = QRect()
        self._last: QPointF | None = None
        self.finished = False

    # ---------------------------------------------------------------- kaynak
    def _source_patch(self, rect: QRect) -> QImage | None:
        """The source view for rect, shifted by the offset (outside the image = transparent).
        None if the whole source lies outside the image: there is nothing to do."""
        src_rect = rect.translated(self.offset)
        clip = src_rect.intersected(self.page.rect)
        if clip.isEmpty():
            return None
        patch = blank_layer(rect.size())
        pos = clip.topLeft() - src_rect.topLeft()
        p = QPainter(patch)
        p.drawImage(pos, self.page.original, clip)
        p.drawImage(pos, self._before, clip)
        p.end()
        return patch

    # ---------------------------------------------------------------- drawing
    def add_point(self, point: QPointF) -> None:
        if self.finished:
            return
        p = QPointF(point)
        r = self.size / 2.0
        if self._last is None:
            bounds = QRectF(p.x() - r, p.y() - r, 2 * r, 2 * r)
        else:
            bounds = QRectF(self._last, p).normalized().adjusted(-r, -r, r, r)
        rect = bounds.adjusted(-2, -2, 2, 2).toAlignedRect().intersected(self.page.rect)
        last, self._last = self._last, p
        if rect.isEmpty():
            return

        patch = self._source_patch(rect)
        if patch is None:
            return  # source outside the image: skip silently

        mask = QImage(rect.size(), PAINT_FORMAT)
        mask.fill(QColor(0, 0, 0, 0))
        mp = QPainter(mask)
        mp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        mp.translate(-rect.x(), -rect.y())
        white = QColor(255, 255, 255)
        if last is None or QLineF(last, p).length() < 0.01:
            mp.setPen(Qt.PenStyle.NoPen)
            mp.setBrush(white)
            mp.drawEllipse(p, r, r)
        else:
            mp.setPen(QPen(white, self.size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            mp.drawLine(QLineF(last, p))
        mp.end()

        pp = QPainter(patch)
        pp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        pp.drawImage(0, 0, mask)  # kaynak ∩ maske
        pp.end()

        assert self.page.paint is not None
        dp = QPainter(self.page.paint)
        dp.drawImage(rect.topLeft(), patch)  # SourceOver
        dp.end()

        self.dirty = self.dirty.united(rect) if not self.dirty.isEmpty() else QRect(rect)
        self.page.notify_paint_changed(rect)
        if self._on_update is not None:
            self._on_update(rect)

    def finish(self, label: str = LABEL) -> StrokeCommand | None:
        """Completes the stroke and returns the undo command (the caller pushes it on the stack).
        None if no pixel was affected."""
        if self.finished:
            return None
        self.finished = True
        if self.dirty.isEmpty():
            return None
        assert self.page.paint is not None
        before = self._before.copy(self.dirty)
        after = self.page.paint.copy(self.dirty)
        self._before = QImage()
        if before == after:
            return None  # no pixel changed: do not create an empty undo record
        return StrokeCommand(self.page, self.dirty, before, after, label)

    def cancel(self) -> None:
        if self.finished:
            return
        self.finished = True
        if not self.dirty.isEmpty():
            self.page.write_paint_region(self.dirty, self._before.copy(self.dirty))



# ======================================================================
# Non-aligned mode: FIXED source area, tiled like a pattern
# ======================================================================
class SourcePatch:
    """The square source AREA fixed at K+click: center, side (the brush size at that moment)
    and a copy of the CONTENT at that moment (original + paint layer). Clipped to the image.

    The target is tiled with copies of this square. The tiling grid is fixed to the square's
    position in the IMAGE: target pixel q <- corner + ((q - corner) mod side). So wherever the
    cursor goes, whether or not the mouse is released, and whichever stroke runs, the same
    pixel always gets the same value: no shifting, no stretching, no seams; nothing outside
    the area is read. Changing the brush size later or painting over the source does not
    change the area; only a new K+click creates a new SourcePatch."""

    def __init__(self, center: QPointF, size: float, origin: QPoint, image: QImage) -> None:
        self.center = QPointF(center)
        self.size = float(size)  # brush size at the moment of selection (requested side)
        self.origin = QPoint(origin)  # top-left corner of the square in the image
        self.image = image  # PAINT_FORMAT, content of the clipped square

    @property
    def bounds(self) -> QRect:
        return QRect(self.origin, self.image.size())

    @property
    def width(self) -> int:
        return self.image.width()

    @property
    def height(self) -> int:
        return self.image.height()

    @classmethod
    def capture(cls, page: PageDocument, center: QPointF, size: float) -> "SourcePatch | None":
        assert page.original is not None and page.paint is not None
        side = max(1, int(round(size)))
        left = int(math.floor(center.x() - side / 2.0 + 0.5))
        top = int(math.floor(center.y() - side / 2.0 + 0.5))
        bounds = QRect(left, top, side, side).intersected(page.rect)
        if bounds.isEmpty():
            return None
        img = blank_layer(bounds.size())
        p = QPainter(img)
        p.drawImage(0, 0, page.original, bounds.x(), bounds.y(), bounds.width(), bounds.height())
        p.drawImage(0, 0, page.paint, bounds.x(), bounds.y(), bounds.width(), bounds.height())
        p.end()
        return cls(center, size, bounds.topLeft(), img)

    def contains(self, x: int, y: int) -> bool:
        return self.bounds.contains(x, y)

    def source_of(self, x: int, y: int) -> tuple[int, int]:
        """Which source pixel the target pixel (x, y) comes from (tiling rule)."""
        return (self.origin.x() + (x - self.origin.x()) % self.width,
                self.origin.y() + (y - self.origin.y()) % self.height)

    def tiled(self, rect: QRect) -> QImage:
        """Fills the rect (image coordinates) with the pattern (exact pixels, no scaling)."""
        out = blank_layer(rect.size())
        p = QPainter(out)
        brush = QBrush(self.image)
        p.setBrushOrigin(self.origin - rect.topLeft())  # grid is fixed to the image
        p.fillRect(QRect(0, 0, rect.width(), rect.height()), brush)
        p.end()
        return out


class PatternCloneSession:
    """Non-aligned stroke: the area the brush passes over is painted with repeats of the
    fixed source area, like a pattern. Because a target pixel always gets the same value,
    overlapping passes shift and stretch nothing. Gaps between mouse events are filled with
    a capsule mask (no holes). The mask has hard edges: each painted pixel is an exact copy
    of ONE pixel of the source area."""

    def __init__(self, page: PageDocument, patch: SourcePatch, size: float,
                 on_update: Optional[Callable[[QRect], None]] = None) -> None:
        assert page.paint is not None, "page is not loaded"
        self.page = page
        self.patch = patch
        self.size = max(1.0, float(size))
        self._on_update = on_update
        self._before = page.paint.copy()
        self.dirty = QRect()
        self._last: QPointF | None = None
        self.finished = False

    def add_point(self, point: QPointF) -> None:
        if self.finished:
            return
        p = QPointF(point)
        r = self.size / 2.0
        last, self._last = self._last, p
        if last is None:
            bounds = QRectF(p.x() - r, p.y() - r, 2 * r, 2 * r)
        else:
            bounds = QRectF(last, p).normalized().adjusted(-r, -r, r, r)
        rect = bounds.adjusted(-2, -2, 2, 2).toAlignedRect().intersected(self.page.rect)
        if rect.isEmpty():
            return
        mask = blank_layer(rect.size())
        mp = QPainter(mask)  # antialiasing OFF: do not produce blended pixels
        mp.translate(-rect.x(), -rect.y())
        white = QColor(255, 255, 255)
        if last is None or QLineF(last, p).length() < 0.01:
            mp.setPen(Qt.PenStyle.NoPen)
            mp.setBrush(white)
            mp.drawEllipse(p, r, r)
        else:
            mp.setPen(QPen(white, self.size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            mp.drawLine(QLineF(last, p))
        mp.end()
        src = self.patch.tiled(rect)
        sp = QPainter(src)
        sp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        sp.drawImage(0, 0, mask)
        sp.end()
        assert self.page.paint is not None
        dp = QPainter(self.page.paint)
        dp.drawImage(rect.topLeft(), src)
        dp.end()
        self.dirty = self.dirty.united(rect) if not self.dirty.isEmpty() else QRect(rect)
        self.page.notify_paint_changed(rect)
        if self._on_update is not None:
            self._on_update(rect)

    def finish(self, label: str = LABEL) -> StrokeCommand | None:
        if self.finished:
            return None
        self.finished = True
        if self.dirty.isEmpty():
            return None
        assert self.page.paint is not None
        before = self._before.copy(self.dirty)
        after = self.page.paint.copy(self.dirty)
        self._before = QImage()
        if before == after:
            return None
        return StrokeCommand(self.page, self.dirty, before, after, label)

    def cancel(self) -> None:
        if self.finished:
            return
        self.finished = True
        if not self.dirty.isEmpty():
            self.page.write_paint_region(self.dirty, self._before.copy(self.dirty))
