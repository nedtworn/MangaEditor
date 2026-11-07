"""Simple tool icons drawn in code (no external icon files needed)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap

ICON_COLOR = QColor("#d7dae0")
_SIZE = 48  # drawn at 2x for high DPI, shown at 24px


def _canvas() -> tuple[QPixmap, QPainter]:
    pm = QPixmap(_SIZE, _SIZE)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(_SIZE / 24.0, _SIZE / 24.0)
    return pm, p


def _pen(width: float = 1.8) -> QPen:
    return QPen(ICON_COLOR, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


def brush_icon() -> QIcon:
    pm, p = _canvas()
    p.setPen(_pen())
    p.drawLine(QPointF(19.5, 4.5), QPointF(10.5, 13.5))
    tip = QPainterPath(QPointF(10.5, 13.5))
    tip.cubicTo(QPointF(6.5, 12.5), QPointF(4.5, 16.5), QPointF(4.5, 19.5))
    tip.cubicTo(QPointF(8.5, 19.5), QPointF(11.5, 17.5), QPointF(10.5, 13.5))
    p.setBrush(ICON_COLOR)
    p.drawPath(tip)
    p.end()
    return QIcon(pm)


def eraser_icon() -> QIcon:
    pm, p = _canvas()
    p.setPen(_pen())
    p.translate(12, 12)
    p.rotate(-45)
    body = QRectF(-8, -4.5, 16, 9)
    p.drawRoundedRect(body, 2, 2)
    p.setBrush(ICON_COLOR)
    p.drawRoundedRect(QRectF(-8, -4.5, 6, 9), 2, 2)
    p.end()
    return QIcon(pm)


def clone_icon() -> QIcon:
    """Stamp: handle + body + base."""
    pm, p = _canvas()
    p.setPen(_pen())
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(12, 6.2), 3.2, 3.2)  # handle knob
    p.drawLine(QPointF(12, 9.4), QPointF(12, 13.5))  # sap
    p.setBrush(ICON_COLOR)
    p.drawRoundedRect(QRectF(7, 13.5, 10, 3.6), 1.2, 1.2)  # body
    p.drawLine(QPointF(4.5, 20), QPointF(19.5, 20))  # taban
    p.end()
    return QIcon(pm)


def eyedropper_icon() -> QIcon:
    pm, p = _canvas()
    p.setPen(_pen())
    p.drawLine(QPointF(14.5, 9.5), QPointF(5.5, 18.5))
    p.drawLine(QPointF(5.5, 18.5), QPointF(4.5, 19.5))
    p.setBrush(ICON_COLOR)
    p.drawEllipse(QPointF(17, 7), 3.6, 3.6)
    p.drawLine(QPointF(12, 7), QPointF(17, 12))
    p.end()
    return QIcon(pm)


def text_icon() -> QIcon:
    pm, p = _canvas()
    f = QFont("Segoe UI")
    f.setPixelSize(19)
    f.setBold(True)
    p.setFont(f)
    p.setPen(ICON_COLOR)
    p.drawText(QRectF(0, 0, 24, 24), Qt.AlignmentFlag.AlignCenter, "T")
    p.end()
    return QIcon(pm)
