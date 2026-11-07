"""Text layout (line wrapping) and drawing engine.

Rules:
  * '\\n' in the text is a MANUAL line break typed with Enter. It is always kept; these
    lines never merge, however wide the box becomes.
  * Automatic line breaks are not written into the text; each layout recomputes them from
    the box width. When the box widens, words move back up to the previous line.
  * Words are never split. A word that does not fit moves whole to the next line; a single
    word wider than the box overflows the box.

The canvas, "Merge page" and the export all use the same paint_text() function, so what is
seen on screen is exactly what is written to the file.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QTransform,
)

from .text_data import TextData

_TOKEN = re.compile(r"\S+\s*|\s+")


@dataclass(frozen=True)
class Line:
    start: int  # metindeki ilk karakterin indeksi
    end: int  # index just after the last character ('\n' excluded)
    width: float  # visible width, without trailing spaces
    hard: bool  # does it end with a manual line break?


def make_font(data: TextData) -> QFont:
    f = QFont(data.font_family)
    f.setPixelSize(max(1, int(data.font_size)))
    f.setBold(data.bold)
    f.setItalic(data.italic)
    f.setKerning(True)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, float(data.letter_spacing))
    # Independent of the zoom: the same look at every zoom level.
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


def wrap_text(text: str, measure: Callable[[str], float], max_width: float) -> list[Line]:
    """Splits the text into lines. measure(s): the visible width of s."""
    lines: list[Line] = []
    paragraphs = text.split("\n")
    pos = 0
    for pi, para in enumerate(paragraphs):
        start, end = pos, pos + len(para)
        spans = _wrap_paragraph(text, start, end, measure, max_width)
        for si, (a, b) in enumerate(spans):
            is_last_of_para = si == len(spans) - 1
            hard = is_last_of_para and pi < len(paragraphs) - 1
            lines.append(Line(a, b, measure(text[a:b].rstrip()), hard))
        pos = end + 1
    return lines


def _wrap_paragraph(text: str, start: int, end: int, measure, max_w: float) -> list[tuple[int, int]]:
    """Splits a paragraph (the text between manual line breaks) at word boundaries.
    Words are NEVER split: a word that does not fit moves whole to the next line; a single
    word wider than the box stays on its own line and overflows the box."""
    if start == end:
        return [(start, end)]
    out: list[tuple[int, int]] = []
    line_start = start
    for m in _TOKEN.finditer(text[start:end]):
        ts, te = start + m.start(), start + m.end()
        if ts > line_start and measure(text[line_start:te].rstrip()) > max_w:
            out.append((line_start, ts))  # automatic line break: before the word
            line_start = ts
    out.append((line_start, end))
    return out


class TextLayout:
    """The computed layout of a TextData. Box-local coordinates:
    (0,0) top-left, (width,height) bottom-right."""

    def __init__(self, data: TextData) -> None:
        self.data = data
        self.font = make_font(data)
        self.fm = QFontMetricsF(self.font)
        self._ls = float(data.letter_spacing)
        self.lines = wrap_text(data.text, self.measure, max(1.0, data.width))
        self.ascent = self.fm.ascent()
        self.descent = self.fm.descent()
        natural = self.ascent + self.descent
        self.line_height = natural * max(0.1, data.line_spacing)
        n = len(self.lines)
        self.block_height = (n - 1) * self.line_height + natural
        if data.align_v == "top":
            self.top = 0.0
        elif data.align_v == "bottom":
            self.top = data.height - self.block_height
        else:
            self.top = (data.height - self.block_height) / 2.0
        self.line_x = [self._align_x(line.width) for line in self.lines]
        self._path: QPainterPath | None = None
        self._outline: QPainterPath | None = None

    # ---------------------------------------------------------------- measuring
    def advance(self, s: str) -> float:
        return self.fm.horizontalAdvance(s) if s else 0.0

    def measure(self, s: str) -> float:
        """Visible width: the letter spacing after the last letter is not counted."""
        return self.fm.horizontalAdvance(s) - self._ls if s else 0.0

    def _align_x(self, w: float) -> float:
        if self.data.align_h == "left":
            return 0.0
        if self.data.align_h == "right":
            return self.data.width - w
        return (self.data.width - w) / 2.0

    def line_top(self, i: int) -> float:
        return self.top + i * self.line_height

    def baseline(self, i: int) -> float:
        return self.line_top(i) + self.ascent

    def line_text(self, i: int) -> str:
        ln = self.lines[i]
        return self.data.text[ln.start:ln.end]

    def is_soft_wrapped(self, i: int) -> bool:
        return i < len(self.lines) - 1 and not self.lines[i].hard

    # ---------------------------------------------------------------- shape
    @property
    def path(self) -> QPainterPath:
        """Glyph outlines of all lines (needed for the outline and the shadow)."""
        if self._path is None:
            path = QPainterPath()
            for i in range(len(self.lines)):
                s = self.line_text(i)
                if s.strip():
                    path.addText(QPointF(self.line_x[i], self.baseline(i)), self.font, s)
            self._path = path
        return self._path

    def outline_shape(self) -> QPainterPath:
        """Filled shape including the outline (prevents double painting in a semi-transparent shadow)."""
        if self._outline is None:
            d = self.data
            if d.stroke_enabled and d.stroke_width > 0:
                stroker = QPainterPathStroker()
                stroker.setWidth(d.stroke_width * 2)
                stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
                shape = stroker.createStroke(self.path).united(self.path)
                shape.setFillRule(Qt.FillRule.WindingFill)
                self._outline = shape
            else:
                self._outline = self.path
        return self._outline

    def ink_rect(self) -> QRectF:
        """Rectangle covering everything drawn (including the outline and the shadow)."""
        d = self.data
        r = QRectF(0, 0, d.width, d.height)
        text_rect = self.path.boundingRect()
        if not text_rect.isEmpty():
            if d.stroke_enabled:
                text_rect = text_rect.adjusted(-d.stroke_width, -d.stroke_width, d.stroke_width, d.stroke_width)
            r = r.united(text_rect)
            if d.shadow_enabled:
                r = r.united(text_rect.translated(d.shadow_dx, d.shadow_dy))
        return r.adjusted(-2, -2, 2, 2)

    # ---------------------------------------------------------------- caret
    def line_of_index(self, index: int) -> int:
        """The line containing the caret index. At an automatic wrap point the caret is shown
        at the start of the next line."""
        for i, ln in enumerate(self.lines):
            if ln.start <= index <= ln.end:
                if index == ln.end and self.is_soft_wrapped(i) and self.lines[i + 1].start == index:
                    return i + 1
                return i
        return len(self.lines) - 1

    def caret_x(self, index: int, line: int | None = None) -> float:
        i = self.line_of_index(index) if line is None else line
        ln = self.lines[i]
        index = max(ln.start, min(index, ln.end))
        return self.line_x[i] + self.advance(self.data.text[ln.start:index])

    def caret_rect(self, index: int) -> QRectF:
        i = self.line_of_index(index)
        return QRectF(self.caret_x(index, i), self.line_top(i), 0.0, self.ascent + self.descent)

    def index_at_x(self, i: int, x: float) -> int:
        ln = self.lines[i]
        last = ln.end
        if self.is_soft_wrapped(i) and last > ln.start and self.data.text[last - 1].isspace():
            last -= 1  # a click right of the trailing space stays on this line
        best, best_d = ln.start, float("inf")
        base = self.line_x[i]
        for k in range(ln.start, last + 1):
            d = abs(base + self.advance(self.data.text[ln.start:k]) - x)
            if d < best_d:
                best, best_d = k, d
        return best

    def hit_test(self, p: QPointF) -> int:
        if not self.lines:
            return 0
        i = int((p.y() - self.top) // self.line_height) if self.line_height > 0 else 0
        i = max(0, min(len(self.lines) - 1, i))
        return self.index_at_x(i, p.x())

    def selection_rects(self, a: int, b: int) -> list[QRectF]:
        if a == b:
            return []
        a, b = min(a, b), max(a, b)
        rects = []
        h = self.ascent + self.descent
        for i, ln in enumerate(self.lines):
            s, e = max(a, ln.start), min(b, ln.end)
            if s > e:
                continue
            if s == e and not (ln.start == ln.end and a <= ln.start < b):
                continue  # no zero-width selection on a non-empty line
            x1 = self.caret_x(s, i)
            x2 = self.caret_x(e, i)
            if b > ln.end and ln.hard:
                x2 += self.fm.horizontalAdvance(" ") * 0.5  # also show the line end as selected
            rects.append(QRectF(x1, self.line_top(i), max(1.0, x2 - x1), h))
        return rects


# ---------------------------------------------------------------------- drawing
def text_transform(d: TextData) -> QTransform:
    """Transform from box-local to image coordinates
    (rotation around the center of the box)."""
    t = QTransform()
    t.translate(d.x + d.width / 2.0, d.y + d.height / 2.0)
    t.rotate(d.rotation)
    t.translate(-d.width / 2.0, -d.height / 2.0)
    return t


def paint_text(painter: QPainter, layout: TextLayout) -> None:
    """Draws the text in box-local coordinates."""
    d = layout.data
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if d.bg_enabled:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(d.bg_color))
        rect = QRectF(0, 0, d.width, d.height)
        if d.bg_radius > 0:
            painter.drawRoundedRect(rect, d.bg_radius, d.bg_radius)
        else:
            painter.drawRect(rect)
    path = layout.path
    if not path.isEmpty():
        if d.shadow_enabled:
            painter.save()
            painter.translate(d.shadow_dx, d.shadow_dy)
            painter.fillPath(layout.outline_shape(), QColor(d.shadow_color))
            painter.restore()
        if d.stroke_enabled and d.stroke_width > 0:
            pen = QPen(QColor(d.stroke_color), d.stroke_width * 2, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.strokePath(path, pen)
        painter.fillPath(path, QColor(d.color))
    painter.restore()


def paint_text_data(painter: QPainter, data: TextData) -> None:
    """Draws the text in image coordinates (position and rotation applied)."""
    if not data.text.strip() and not data.bg_enabled:
        return
    painter.save()
    painter.setTransform(text_transform(data), True)
    paint_text(painter, TextLayout(data))
    painter.restore()


def layout_changed(a: TextData, b: TextData) -> bool:
    """Does the layout need to be recomputed? (everything except position and rotation)"""
    return a.with_(x=0.0, y=0.0, rotation=0.0) != b.with_(x=0.0, y=0.0, rotation=0.0)
