"""Text box on the canvas: moving, resizing, rotating and in-place editing.

The item's local coordinates are the box's own coordinates ((0,0) is the top-left corner);
position and rotation are applied with setTransform(text_transform(data)). The screen,
merging and export therefore all use the same transform.

While dragging, the item only updates itself (preview); when the mouse is released a single
undo command is created.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsObject,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from ..core.text_data import TextData
from ..core.text_layout import TextLayout, layout_changed, paint_text, text_transform
from ..i18n import tr

if TYPE_CHECKING:
    from .page_scene import PageScene

HANDLE_PX = 9.0  # handle size (screen pixels)
ROT_OFFSET_PX = 28.0  # distance of the rotation handle from the box
MIN_BOX = 16.0
ACCENT = QColor("#4c8dff")
RESIZE_HANDLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")
_HANDLE_ANGLE = {"e": 0, "se": 45, "s": 90, "sw": 135, "w": 180, "nw": 225, "n": 270, "ne": 315}


class TextItemView(QGraphicsObject):
    def __init__(self, ctrl: "PageScene", data: TextData) -> None:
        super().__init__()
        self.ctrl = ctrl
        self.data = data
        self.layout = TextLayout(data)
        self._ink = self.layout.ink_rect()
        self.setTransform(text_transform(data))
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.interactive = True
        self.pending_new = False  # not yet added to the page (first edit still in progress)
        # editing state
        self.editing = False
        self.edit_base: TextData | None = None
        self.cursor = 0
        self.anchor = 0
        self._preferred_x: float | None = None
        self._edit_undo: list[tuple[str, int, int]] = []
        self._edit_redo: list[tuple[str, int, int]] = []
        self._last_edit_kind: str | None = None
        self._caret_on = True
        self._blink = QTimer(self)
        self._blink.setInterval(530)
        self._blink.timeout.connect(self._toggle_caret)
        self._drag: tuple | None = None
        self._hover = False

    # ------------------------------------------------------------------ veri
    @property
    def text_id(self) -> str:
        return self.data.id

    def set_data(self, data: TextData) -> None:
        if data == self.data:
            return
        relayout = layout_changed(self.data, data)
        self.prepareGeometryChange()
        self.data = data
        if relayout:
            self.layout = TextLayout(data)
            self._ink = self.layout.ink_rect()
        self.setTransform(text_transform(data))
        n = len(data.text)
        self.cursor = min(self.cursor, n)
        self.anchor = min(self.anchor, n)
        self.update()

    def set_interactive(self, on: bool) -> None:
        self.interactive = on
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton if on else Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(on)
        if not on:
            self._hover = False
            self.unsetCursor()
        self.update()

    def view_scale_changed(self) -> None:
        self.prepareGeometryChange()
        self.update()

    # ------------------------------------------------------------------ geometri
    def _px(self) -> float:
        """The local-coordinate size of one screen pixel."""
        return 1.0 / max(self.ctrl.view_scale, 1e-6)

    def box(self) -> QRectF:
        return QRectF(0, 0, self.data.width, self.data.height)

    def boundingRect(self) -> QRectF:
        m = (ROT_OFFSET_PX + HANDLE_PX + 2) * self._px()
        return self._ink.united(self.box().adjusted(-m, -m, m, m))

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        if self.isSelected() and not self.editing:
            m = HANDLE_PX * self._px()
            path.addRect(self.box().adjusted(-m, -m, m, m))
            rot = self.handle_points()["rot"]
            path.addEllipse(rot, m, m)
        else:
            m = 3 * self._px()
            path.addRect(self.box().adjusted(-m, -m, m, m))
        return path

    def handle_points(self) -> dict[str, QPointF]:
        w, h = self.data.width, self.data.height
        return {
            "nw": QPointF(0, 0), "n": QPointF(w / 2, 0), "ne": QPointF(w, 0), "e": QPointF(w, h / 2),
            "se": QPointF(w, h), "s": QPointF(w / 2, h), "sw": QPointF(0, h), "w": QPointF(0, h / 2),
            "rot": QPointF(w / 2, -ROT_OFFSET_PX * self._px()),
        }

    def handle_at(self, p: QPointF) -> str | None:
        if not self.isSelected() or self.editing:
            return None
        tol = HANDLE_PX * self._px()
        best, best_d = None, tol
        for name, pt in self.handle_points().items():
            d = math.hypot(p.x() - pt.x(), p.y() - pt.y())
            if d <= best_d:
                best, best_d = name, d
        return best

    # ------------------------------------------------------------------ drawing
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        paint_text(painter, self.layout)
        selected = self.isSelected()
        if not (selected or self.editing or (self._hover and self.interactive)):
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.editing:
            sel_color = QColor(ACCENT)
            sel_color.setAlpha(90)
            for r in self.layout.selection_rects(self.anchor, self.cursor):
                painter.fillRect(r, sel_color)
        pen = QPen(ACCENT if (selected or self.editing) else QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 140), 1)
        pen.setCosmetic(True)
        if not (selected or self.editing):
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.box())
        if self.editing and self._caret_on and self.anchor == self.cursor:
            r = self.layout.caret_rect(self.cursor)
            for color, width in ((QColor(255, 255, 255), 3.0), (QColor(0, 0, 0), 1.5)):
                cp = QPen(color, width)
                cp.setCosmetic(True)
                painter.setPen(cp)
                painter.drawLine(r.topLeft(), r.bottomLeft())
        if selected and not self.editing:
            px = self._px()
            hs = HANDLE_PX * px
            pts = self.handle_points()
            painter.setPen(pen)
            painter.drawLine(pts["n"], pts["rot"])
            painter.setBrush(QColor(255, 255, 255))
            for name in RESIZE_HANDLES:
                c = pts[name]
                painter.drawRect(QRectF(c.x() - hs / 2, c.y() - hs / 2, hs, hs))
            painter.setBrush(ACCENT)
            painter.drawEllipse(pts["rot"], hs * 0.6, hs * 0.6)
        painter.restore()

    # ------------------------------------------------------------------ fare
    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self._hover = False
        self.unsetCursor()
        self.update()

    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        p = event.pos()
        if self.editing and self.box().contains(p):
            self.setCursor(Qt.CursorShape.IBeamCursor)
            return
        h = self.handle_at(p)
        if h == "rot":
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif h:
            angle = (_HANDLE_ANGLE[h] + self.data.rotation) % 180
            shapes = (Qt.CursorShape.SizeHorCursor, Qt.CursorShape.SizeFDiagCursor,
                      Qt.CursorShape.SizeVerCursor, Qt.CursorShape.SizeBDiagCursor)
            self.setCursor(shapes[int(((angle + 22.5) % 180) // 45)])
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self.interactive:
            event.ignore()
            return
        p = event.pos()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self.editing:
            if self.box().adjusted(-4, -4, 4, 4).contains(p):
                idx = self.layout.hit_test(p)
                self.cursor = idx
                if not shift:
                    self.anchor = idx
                self._preferred_x = None
                self._drag = ("select",)
                self._restart_blink()
                event.accept()
                return
            self.ctrl.finish_editing()
        handle = self.handle_at(p)
        if not self.isSelected():
            if not shift:
                self.ctrl.clearSelection()
            self.setSelected(True)
            handle = None
        start = self.data
        if handle == "rot":
            self._drag = ("rotate", start)
        elif handle:
            self._drag = ("resize", start, handle, text_transform(start))
        else:
            self._drag = ("move", start, event.scenePos())
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        d = self._drag
        if d is None:
            return
        kind = d[0]
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if kind == "select":
            self.cursor = self.layout.hit_test(event.pos())
            self.update()
        elif kind == "move":
            start, origin = d[1], d[2]
            delta = event.scenePos() - origin
            self.set_data(start.with_(x=start.x + delta.x(), y=start.y + delta.y()))
        elif kind == "rotate":
            start = d[1]
            c = QPointF(start.x + start.width / 2, start.y + start.height / 2)
            v = event.scenePos() - c
            angle = math.degrees(math.atan2(v.y(), v.x())) + 90.0
            if shift:
                angle = round(angle / 15.0) * 15.0
            angle = (angle + 180.0) % 360.0 - 180.0
            self.set_data(start.with_(rotation=round(angle, 2)))
        elif kind == "resize":
            self.set_data(self._resized(d[1], d[2], d[3], event.scenePos()))
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        d, self._drag = self._drag, None
        if d is not None and d[0] in ("move", "rotate", "resize") and self.data != d[1]:
            labels = {"move": tr("Metni taşı"), "rotate": tr("Metni döndür"),
                      "resize": tr("Metin kutusunu boyutlandır")}
            self.ctrl.commit_text_change(self, d[1], self.data, labels[d[0]])
        event.accept()

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self.interactive:
            event.ignore()
            return
        idx = self.layout.hit_test(event.pos())
        if self.editing:
            self._select_word(idx)
        else:
            self.ctrl.start_editing(self, idx)
        event.accept()

    @staticmethod
    def _resized(start: TextData, handle: str, t, scene_pos: QPointF) -> TextData:
        inv, _ok = t.inverted()
        lp = inv.map(scene_pos)
        left, top, right, bottom = 0.0, 0.0, start.width, start.height
        if "w" in handle:
            left = min(lp.x(), right - MIN_BOX)
        if "e" in handle:
            right = max(lp.x(), left + MIN_BOX)
        if "n" in handle:
            top = min(lp.y(), bottom - MIN_BOX)
        if "s" in handle:
            bottom = max(lp.y(), top + MIN_BOX)
        w, h = right - left, bottom - top
        # The opposite edge stays in place on the scene (also for a rotated box).
        center = t.map(QPointF((left + right) / 2, (top + bottom) / 2))
        return start.with_(x=center.x() - w / 2, y=center.y() - h / 2, width=w, height=h)

    # ------------------------------------------------------------------ editing
    def begin_edit(self, cursor: int | None = None) -> None:
        self.editing = True
        self.edit_base = self.data
        n = len(self.data.text)
        self.cursor = n if cursor is None else max(0, min(cursor, n))
        self.anchor = self.cursor
        self._edit_undo.clear()
        self._edit_redo.clear()
        self._last_edit_kind = None
        self._preferred_x = None
        self.prepareGeometryChange()
        self._restart_blink()

    def end_edit(self) -> None:
        self.editing = False
        self._blink.stop()
        self._drag = None
        self.prepareGeometryChange()
        self.update()

    def _toggle_caret(self) -> None:
        self._caret_on = not self._caret_on
        self.update()

    def _restart_blink(self) -> None:
        self._caret_on = True
        self._blink.start()
        self.update()

    def has_selection(self) -> bool:
        return self.cursor != self.anchor

    def selected_text(self) -> str:
        a, b = sorted((self.cursor, self.anchor))
        return self.data.text[a:b]

    def _snapshot(self, kind: str) -> None:
        # Consecutive typed letters form one undo step (word by word).
        if not (kind == "type" and self._last_edit_kind == "type"):
            self._edit_undo.append((self.data.text, self.cursor, self.anchor))
            if len(self._edit_undo) > 500:
                del self._edit_undo[0]
        self._edit_redo.clear()
        self._last_edit_kind = kind

    def _set_text(self, text: str, cursor: int, anchor: int | None = None) -> None:
        self.set_data(self.data.with_(text=text))
        self.cursor = cursor
        self.anchor = cursor if anchor is None else anchor
        self._preferred_x = None
        self._restart_blink()

    def insert(self, s: str, kind: str = "type") -> None:
        s = s.replace("\r\n", "\n").replace("\r", "\n")
        a, b = sorted((self.cursor, self.anchor))
        if kind == "type" and (s.isspace() or self.has_selection()):
            kind = "space"
        self._snapshot(kind)
        t = self.data.text
        self._set_text(t[:a] + s + t[b:], a + len(s))

    def delete(self, forward: bool, word: bool = False) -> None:
        t = self.data.text
        if self.has_selection():
            a, b = sorted((self.cursor, self.anchor))
        elif forward:
            a = self.cursor
            b = self._word_right(a) if word else min(len(t), a + 1)
        else:
            b = self.cursor
            a = self._word_left(b) if word else max(0, b - 1)
        if a == b:
            return
        self._snapshot("delete")
        self._set_text(t[:a] + t[b:], a)

    def _word_left(self, i: int) -> int:
        t = self.data.text
        while i > 0 and t[i - 1].isspace():
            i -= 1
        while i > 0 and not t[i - 1].isspace():
            i -= 1
        return i

    def _word_right(self, i: int) -> int:
        t = self.data.text
        n = len(t)
        while i < n and not t[i].isspace():
            i += 1
        while i < n and t[i].isspace() and t[i] != "\n":
            i += 1
        return i

    def _select_word(self, idx: int) -> None:
        t = self.data.text
        a = idx
        while a > 0 and not t[a - 1].isspace():
            a -= 1
        b = idx
        while b < len(t) and not t[b].isspace():
            b += 1
        self.anchor, self.cursor = a, b
        self._restart_blink()

    def _move(self, pos: int, keep_anchor: bool, keep_x: bool = False) -> None:
        self.cursor = max(0, min(len(self.data.text), pos))
        if not keep_anchor:
            self.anchor = self.cursor
        if not keep_x:
            self._preferred_x = None
        self._restart_blink()

    def _line_end(self, i: int) -> int:
        ln = self.layout.lines[i]
        end = ln.end
        if self.layout.is_soft_wrapped(i) and end > ln.start and self.data.text[end - 1].isspace():
            end -= 1
        return end

    def handle_key(self, event: QKeyEvent) -> bool:
        """Keys pressed while editing. Returns True if the key was handled."""
        key = event.key()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        K = Qt.Key
        t = self.data.text
        if key == K.Key_Escape:
            self.ctrl.finish_editing()
            return True
        if ctrl and not alt:  # AltGr (Ctrl+Alt) produces characters on Turkish keyboards
            if key == K.Key_A:
                self.anchor, self.cursor = 0, len(t)
                self._restart_blink()
            elif key in (K.Key_C, K.Key_X):
                if self.has_selection():
                    QGuiApplication.clipboard().setText(self.selected_text())
                    if key == K.Key_X:
                        self.delete(False)
            elif key == K.Key_V:
                s = QGuiApplication.clipboard().text()
                if s:
                    self.insert(s, "paste")
            elif key == K.Key_Z and not shift:
                self.edit_undo()
            elif key in (K.Key_Y,) or (key == K.Key_Z and shift):
                self.edit_redo()
            elif key == K.Key_Left:
                self._move(self._word_left(self.cursor), shift)
            elif key == K.Key_Right:
                self._move(self._word_right(self.cursor), shift)
            elif key == K.Key_Home:
                self._move(0, shift)
            elif key == K.Key_End:
                self._move(len(t), shift)
            elif key == K.Key_Backspace:
                self.delete(False, word=True)
            elif key == K.Key_Delete:
                self.delete(True, word=True)
            else:
                return False
            return True
        if key == K.Key_Left:
            if self.has_selection() and not shift:
                self._move(min(self.cursor, self.anchor), False)
            else:
                self._move(self.cursor - 1, shift)
        elif key == K.Key_Right:
            if self.has_selection() and not shift:
                self._move(max(self.cursor, self.anchor), False)
            else:
                self._move(self.cursor + 1, shift)
        elif key in (K.Key_Up, K.Key_Down):
            i = self.layout.line_of_index(self.cursor)
            if self._preferred_x is None:
                self._preferred_x = self.layout.caret_x(self.cursor, i)
            j = i - 1 if key == K.Key_Up else i + 1
            if j < 0:
                self._move(0, shift, keep_x=True)
            elif j >= len(self.layout.lines):
                self._move(len(t), shift, keep_x=True)
            else:
                self._move(self.layout.index_at_x(j, self._preferred_x), shift, keep_x=True)
        elif key == K.Key_Home:
            self._move(self.layout.lines[self.layout.line_of_index(self.cursor)].start, shift)
        elif key == K.Key_End:
            self._move(self._line_end(self.layout.line_of_index(self.cursor)), shift)
        elif key == K.Key_Backspace:
            self.delete(False)
        elif key == K.Key_Delete:
            self.delete(True)
        elif key in (K.Key_Return, K.Key_Enter):
            self.insert("\n", "newline")  # manual line break
        elif key == K.Key_Tab:
            pass  # keep the focus where it is
        else:
            s = event.text()
            if s and s.isprintable():
                self.insert(s)
            else:
                return False
        return True

    def edit_undo(self) -> None:
        if not self._edit_undo:
            return
        self._edit_redo.append((self.data.text, self.cursor, self.anchor))
        text, c, a = self._edit_undo.pop()
        self._last_edit_kind = None
        self._set_text(text, c, a)

    def edit_redo(self) -> None:
        if not self._edit_redo:
            return
        self._edit_undo.append((self.data.text, self.cursor, self.anchor))
        text, c, a = self._edit_redo.pop()
        self._last_edit_kind = None
        self._set_text(text, c, a)
