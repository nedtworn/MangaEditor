"""Layer composition: export, the eyedropper and "Merge page" use the same function,
so what is seen on screen is what is written to the file."""
from __future__ import annotations

import math
from typing import Iterable

from PySide6.QtCore import QPointF, QRect
from PySide6.QtGui import QColor, QImage, QPainter

from .page import PAINT_FORMAT, PageDocument
from .text_data import TextData


def draw_texts(painter: QPainter, texts: Iterable[TextData]) -> None:
    """Draws the texts in image coordinates (the painter's transform is kept)."""
    from .text_layout import paint_text_data  # avoid a circular import

    for data in texts:
        paint_text_data(painter, data)


def compose_page(
    page: PageDocument,
    rect: QRect | None = None,
    include_texts: bool = True,
    background: QColor | None = None,
) -> QImage:
    """Original + paint layer (+ texts) → one image."""
    page.ensure_loaded()
    assert page.original is not None and page.paint is not None
    rect = page.rect if rect is None else rect.intersected(page.rect)
    out = QImage(rect.size(), PAINT_FORMAT)
    out.fill(background if background is not None else QColor(0, 0, 0, 0))
    if rect.isEmpty():
        return out
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    p.translate(-rect.x(), -rect.y())
    p.drawImage(rect.topLeft(), page.original, rect)
    p.drawImage(rect.topLeft(), page.paint, rect)
    if include_texts and page.texts:
        draw_texts(p, page.texts)
    p.end()
    return out





def sample_color(page: PageDocument, point: QPointF, include_texts: bool = True) -> QColor | None:
    """Returns the real color of the pixel as it appears on screen (None outside the image).
    The eyedropper samples only the single pixel right under the cursor."""
    x, y = math.floor(point.x()), math.floor(point.y())
    if not page.rect.contains(x, y):
        return None
    img = compose_page(page, QRect(x, y, 1, 1), include_texts=include_texts)
    return img.pixelColor(0, 0)
