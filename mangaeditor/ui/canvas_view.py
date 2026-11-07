"""Canvas: zoom, pan and mouse interaction of the tools."""
from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsView,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
)

from ..core.clone import CloneSession, PatternCloneSession, SourcePatch, offset_between
from ..core.compose import sample_color
from ..core.stroke import BRUSH, ERASER, StrokeSession
from ..core.text_data import new_text_id
from .page_scene import PageScene
from .shortcuts import (
    CLONE_SOURCE_HOLD,
    PAN_HOLD,
    SIZE_DOWN,
    SIZE_UP,
    TEXT_DELETE,
    TEXT_EDIT,
    ShortcutRegistry,
)
from .text_item import TextItemView
from .tools import Tool, ToolSettings
from ..i18n import tr

MIN_ZOOM = 0.02
MAX_ZOOM = 32.0
WHEEL_STEP = 1.2
CLONE_MARK_ARM = 14  # clone source marker: half-length of the cross arm (screen pixels, independent of brush size)
CLONE_MARK_RING = 10  # ring radius (screen pixels)


class CanvasView(QGraphicsView):
    zoomChanged = Signal(float)
    cursorMoved = Signal(QPointF)  # image coordinates
    colorPicked = Signal(QColor)
    message = Signal(str)  # status bar message for the user
    cloneStateChanged = Signal()  # clone source selected / reset / page changed

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setBackgroundBrush(QColor("#1b1d21"))
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._space_down = False
        self._pan_last: QPoint | None = None
        self.tools: ToolSettings | None = None
        self._stroke: StrokeSession | None = None
        self._picking = False
        self._hover: QPointF | None = None  # brush cursor position (image coordinates)
        self._create_start: QPointF | None = None  # drag start when creating a text box
        self._create_rect: QRectF | None = None
        self.shortcuts: ShortcutRegistry | None = None
        self._clone: CloneSession | None = None
        self._ping_step = 0  # short ring animation when a clone source is selected
        self._ping_timer = QTimer(self)
        self._ping_timer.setInterval(55)
        self._ping_timer.timeout.connect(self._tick_ping)

    def set_shortcuts(self, registry: ShortcutRegistry) -> None:
        """Canvas keys (pan, clone source, size, text) come from the central shortcut registry."""
        self.shortcuts = registry
        registry.holdChanged.connect(self._on_hold_changed)

    def _on_hold_changed(self, sid: str, down: bool) -> None:
        if sid == PAN_HOLD:
            # While typing text, Space is a space character, not panning.
            self.set_space_down(down and not self.is_editing_text())
        elif sid == CLONE_SOURCE_HOLD:
            self._update_cursor()
            self.viewport().update()

    def _clone_key_held(self) -> bool:
        return (self.shortcuts is not None and self.tools is not None and self.tools.tool == Tool.CLONE
                and self.shortcuts.is_held(CLONE_SOURCE_HOLD))

    def set_tools(self, tools: ToolSettings) -> None:
        self.tools = tools
        tools.toolChanged.connect(self._on_tool_changed)
        tools.brushChanged.connect(self._refresh_brush_cursor)
        tools.eraserChanged.connect(self._refresh_brush_cursor)
        tools.cloneChanged.connect(self._refresh_brush_cursor)
        tools.cloneModeChanged.connect(self._refresh_brush_cursor)
        self._update_cursor()

    def _on_tool_changed(self, _tool) -> None:
        self.finish_interaction()
        self._sync_text_interactivity()
        self._update_cursor()
        self.viewport().update()

    def _sync_text_interactivity(self) -> None:
        s = self.page_scene()
        if s is not None and self.tools is not None:
            s.set_texts_interactive(self.tools.tool == Tool.TEXT)

    def is_editing_text(self) -> bool:
        s = self.page_scene()
        return s is not None and s.editing_item is not None

    def is_stroking(self) -> bool:
        return self._stroke is not None

    def scene_pos(self, view_pos: QPointF) -> QPointF:
        """Converts a viewport position to image coordinates with sub-pixel precision."""
        inv, _ok = self.viewportTransform().inverted()
        return inv.map(QPointF(view_pos))

    def finish_interaction(self) -> None:
        """Completes an ongoing brush/clone stroke, color pick or text box creation
        (no half-finished operation may remain after a tab or tool change)."""
        if self._stroke is not None:
            self._end_stroke()
        if self._clone is not None:
            self._end_clone()
        self._picking = False
        if self._create_start is not None:
            self._create_start = None
            self._create_rect = None
            self.viewport().update()

    # ------------------------------------------------------------------ scene
    def page_scene(self) -> PageScene | None:
        s = self.scene()
        return s if isinstance(s, PageScene) else None

    def set_page_scene(self, scene: PageScene | None, fit: bool = True) -> None:
        self.finish_interaction()
        old = self.page_scene()
        if old is not None and old is not scene:
            old.finish_editing()
        self.setScene(scene)
        self._sync_text_interactivity()
        if scene is not None:
            scene.set_view_scale(self.zoom())
            if fit:
                self.fit_to_window()
        self.cloneStateChanged.emit()

    # ------------------------------------------------------------------ zoom
    def zoom(self) -> float:
        return self.transform().m11()

    def zoom_at(self, view_pos: QPointF, factor: float) -> None:
        """Zooms so that the image point under view_pos stays in place."""
        current = self.zoom()
        target = max(MIN_ZOOM, min(MAX_ZOOM, current * factor))
        if abs(target - current) < 1e-9:
            return
        anchor_scene = self.mapToScene(view_pos.toPoint())
        self.scale(target / current, target / current)
        moved = self.mapFromScene(anchor_scene)
        self.pan_by(view_pos.x() - moved.x(), view_pos.y() - moved.y())
        self._zoom_updated()

    def _center_pos(self) -> QPointF:
        return QPointF(self.viewport().rect().center())

    def zoom_in(self) -> None:
        self.zoom_at(self._center_pos(), WHEEL_STEP)

    def zoom_out(self) -> None:
        self.zoom_at(self._center_pos(), 1 / WHEEL_STEP)

    def set_zoom(self, zoom: float) -> None:
        self.zoom_at(self._center_pos(), zoom / self.zoom())

    def fit_to_window(self) -> None:
        s = self.page_scene()
        if s is None:
            return
        rect = s.image_rect
        vp = self.viewport().rect()
        if rect.isEmpty() or vp.width() < 10 or vp.height() < 10:
            return
        margin = 24
        zoom = min((vp.width() - 2 * margin) / rect.width(), (vp.height() - 2 * margin) / rect.height())
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        self.resetTransform()
        self.scale(zoom, zoom)
        self.centerOn(rect.center())
        self._zoom_updated()

    def actual_size(self) -> None:
        s = self.page_scene()
        if s is None:
            return
        self.resetTransform()
        self.centerOn(s.image_rect.center())
        self._zoom_updated()

    def _zoom_updated(self) -> None:
        z = self.zoom()
        # Show pixels sharply when zoomed in; smooth them when zoomed out.
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, z < 2.0)
        s = self.page_scene()
        if s is not None:
            s.set_view_scale(z)
        self.zoomChanged.emit(z)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return
        self.zoom_at(event.position(), WHEEL_STEP ** (delta / 120.0))
        event.accept()

    # ------------------------------------------------------------------ pan
    def pan_by(self, dx: float, dy: float) -> None:
        h, v = self.horizontalScrollBar(), self.verticalScrollBar()
        h.setValue(h.value() - round(dx))
        v.setValue(v.value() - round(dy))

    def is_panning(self) -> bool:
        return self._pan_last is not None

    def set_space_down(self, down: bool) -> None:
        self._space_down = down
        if not self.is_panning():
            self._update_cursor()

    def _start_pan(self, pos: QPoint) -> None:
        self._pan_last = pos
        self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

    def _update_cursor(self) -> None:
        if self._space_down:
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        elif self._clone_key_held():
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)  # clone source selection mode
        else:
            self.viewport().setCursor(self.tool_cursor())

    def tool_cursor(self):
        tool = self.tools.tool if self.tools else None
        if tool in (Tool.BRUSH, Tool.ERASER, Tool.CLONE, Tool.EYEDROPPER):
            return Qt.CursorShape.CrossCursor
        if tool == Tool.TEXT:
            return Qt.CursorShape.IBeamCursor
        return Qt.CursorShape.ArrowCursor

    # ------------------------------------------------------------------ mouse
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton or (
            self._space_down and event.button() == Qt.MouseButton.LeftButton
        ):
            self._start_pan(event.position().toPoint())
            event.accept()
            return
        s = self.page_scene()
        if s is not None and self.tools is not None and event.button() == Qt.MouseButton.LeftButton:
            p = self.scene_pos(event.position())
            tool = self.tools.tool
            if tool == Tool.BRUSH and event.modifiers() & Qt.KeyboardModifier.AltModifier:
                self._pick_color(p)
                event.accept()
                return
            if tool in (Tool.BRUSH, Tool.ERASER):
                self._begin_stroke(p)
                event.accept()
                return
            if tool == Tool.CLONE:
                self._clone_press(s, p)  # either selects the source OR starts cloning, never both
                event.accept()
                return
            if tool == Tool.EYEDROPPER:
                self._picking = True
                self._pick_color(p)
                event.accept()
                return
            if tool == Tool.TEXT and self.text_item_at(event.position()) is None:
                # Click on empty space: if editing, only finish the edit; otherwise (even with a
                # selection) start a new box, so consecutive speech bubbles fill quickly.
                if s.editing_item is not None:
                    s.finish_editing()
                    s.clearSelection()
                    event.accept()
                    return
                s.clearSelection()
                self._create_start = p
                self._create_rect = None
                event.accept()
                return
        super().mousePressEvent(event)

    def text_item_at(self, view_pos: QPointF) -> TextItemView | None:
        for item in self.items(view_pos.toPoint()):
            if isinstance(item, TextItemView) and item.interactive:
                return item
        return None

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position().toPoint()
        if self._pan_last is not None:
            d = pos - self._pan_last
            self._pan_last = pos
            self.pan_by(d.x(), d.y())
            event.accept()
            return
        p = self.scene_pos(event.position())
        self._set_hover(p)
        self.cursorMoved.emit(p)
        if self._stroke is not None:
            self._stroke.add_point(p)
            event.accept()
            return
        if self._clone is not None:
            self._clone.add_point(p)
            event.accept()
            return
        if self._picking:
            self._pick_color(p)
            event.accept()
            return
        if self._create_start is not None:
            self._create_rect = QRectF(self._create_start, p).normalized()
            self.viewport().update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._pan_last is not None and event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton):
            self._pan_last = None
            self._update_cursor()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if self._stroke is not None:
                self._stroke.add_point(self.scene_pos(event.position()))
                self._end_stroke()
                event.accept()
                return
            if self._clone is not None:
                self._clone.add_point(self.scene_pos(event.position()))
                self._end_clone()
                event.accept()
                return
            if self._picking:
                self._picking = False  # the eyedropper stays selected; the tool does not change
                event.accept()
                return
            if self._create_start is not None:
                self._finish_text_creation(self.scene_pos(event.position()))
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def _finish_text_creation(self, end: QPointF) -> None:
        start, self._create_start = self._create_start, None
        self._create_rect = None
        self.viewport().update()
        s = self.page_scene()
        if s is None or self.tools is None or start is None:
            return
        rect = QRectF(start, end).normalized()
        view_rect = self.mapFromScene(rect).boundingRect()
        defaults = self.tools.text_defaults
        if view_rect.width() >= 8 and view_rect.height() >= 8:
            # Box drawn by dragging
            data = defaults.with_(id=new_text_id(), x=rect.x(), y=rect.y(),
                                  width=max(16.0, rect.width()), height=max(16.0, rect.height()))
        else:
            # The clicked point becomes the center of the box (clicking the middle of a bubble is enough).
            w = max(120.0, defaults.font_size * 7.0)
            h = max(60.0, defaults.font_size * 3.2)
            data = defaults.with_(id=new_text_id(), x=start.x() - w / 2, y=start.y() - h / 2, width=w, height=h)
        s.new_text(data)
        self.setFocus()

    # ------------------------------------------------------------------ keys
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.shortcuts is not None:
            self.shortcuts.note_key_press(event)  # hold keys such as Space / K
        s = self.page_scene()
        if s is not None and s.editing_item is not None:
            if s.editing_item.handle_key(event):
                event.accept()
                return
        reg = self.shortcuts
        tool = self.tools.tool if self.tools is not None else None
        if reg is not None and tool in (Tool.BRUSH, Tool.ERASER, Tool.CLONE):
            grow, shrink = reg.matches(SIZE_UP, event), reg.matches(SIZE_DOWN, event)
            if grow or shrink:
                size = self.tools.active_size()
                step = 1 if size < 10 else max(1, round(size * 0.15))
                self.tools.set_active_size(size + (step if grow else -step))
                event.accept()
                return
        if reg is not None and s is not None and tool == Tool.TEXT:
            if reg.matches(TEXT_DELETE, event) and s.selected_text_items():
                s.delete_selected_texts()
                event.accept()
                return
            if reg.matches(TEXT_EDIT, event):
                items = s.selected_text_items()
                if len(items) == 1:
                    s.start_editing(items[0])
                    event.accept()
                    return
        if s is not None and tool == Tool.TEXT and event.key() == Qt.Key.Key_Escape and s.selectedItems():
            s.clearSelection()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if self.shortcuts is not None:
            self.shortcuts.note_key_release(event)
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event) -> None:
        # If focus leaves while a key is held, no release event arrives: do not leave it stuck.
        if self.shortcuts is not None:
            self.shortcuts.release_all()
        super().focusOutEvent(event)

    def enterEvent(self, event) -> None:
        """When the mouse enters the canvas and no text field is being typed in, take focus so
        Space and the clone source key always reach the canvas (as in image editors)."""
        fw = QApplication.focusWidget()
        typing = isinstance(fw, (QLineEdit, QAbstractSpinBox, QTextEdit, QPlainTextEdit)) or (
            isinstance(fw, QComboBox) and fw.isEditable())
        if not typing and fw is not self and self.window().isActiveWindow():
            self.setFocus(Qt.FocusReason.MouseFocusReason)
        super().enterEvent(event)

    # While editing text, these keys go to the text, not to application shortcuts.
    _EDIT_CTRL_KEYS = {
        Qt.Key.Key_A, Qt.Key.Key_C, Qt.Key.Key_X, Qt.Key.Key_V, Qt.Key.Key_Z, Qt.Key.Key_Y,
        Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Home, Qt.Key.Key_End,
        Qt.Key.Key_Backspace, Qt.Key.Key_Delete,
    }

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ShortcutOverride and self.is_editing_text():
            mods = event.modifiers()
            ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
            alt = bool(mods & Qt.KeyboardModifier.AltModifier)
            if not ctrl or alt or event.key() in self._EDIT_CTRL_KEYS:
                event.accept()  # tool shortcuts such as B, E, I must not fire while typing
                return True
        return super().event(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._set_hover(None)
        super().leaveEvent(event)

    # ------------------------------------------------------------------ tools
    def _begin_stroke(self, p: QPointF) -> None:
        s = self.page_scene()
        assert s is not None and self.tools is not None
        mode = BRUSH if self.tools.tool == Tool.BRUSH else ERASER
        item = s.paint_item
        self._stroke = StrokeSession(
            s.page, mode, self.tools.active_size(), self.tools.brush_color, self.tools.brush_opacity,
            on_buffer_update=lambda r: item.update(QRectF(r)),
        )
        if mode == BRUSH:
            item.stroke_buffer = self._stroke.buffer
            item.stroke_opacity = self.tools.brush_opacity
        self._stroke.add_point(p)

    def _end_stroke(self) -> None:
        stroke, self._stroke = self._stroke, None
        if stroke is None:
            return
        s = self.page_scene()
        if s is not None:
            s.paint_item.stroke_buffer = None
        cmd = stroke.finish()
        if cmd is not None:
            stroke.page.undo_stack.push(cmd)

    def _pick_color(self, p: QPointF) -> None:
        s = self.page_scene()
        if s is None or self.tools is None:
            return
        c = sample_color(s.page, p)
        if c is not None and c.alpha() > 0:
            self.tools.set_brush_color(c)
            self.colorPicked.emit(c)

    # ------------------------------------------------------------------ clone stamp
    def _clone_press(self, s: PageScene, p: QPointF) -> None:
        if self._clone_key_held():
            self._set_clone_source(s, p)  # only sets the source; no pixel is painted
            return
        if s.clone_source is None:
            self.message.emit(tr("Klonlamadan önce kaynak seçin: kaynak tuşunu (varsayılan K) basılı tutarak "
                                 "kopyalanacak bölgeye tıklayın."))
            self._ping_step = 0
            return
        assert self.tools is not None
        if self.tools.clone_aligned:
            # Aligned: the source-target offset is fixed at the first press and kept for later strokes.
            if s.clone_offset is None:
                s.clone_offset = offset_between(s.clone_source, p)
                self.cloneStateChanged.emit()
            offset = s.clone_offset
        else:
            # Non-aligned: the source AREA captured at K+click is tiled over the target.
            # Moving the cursor does not change the sampled area; nothing outside it is read.
            if s.clone_patch is None:
                self.message.emit(tr("Kaynak alanı yok: kaynak tuşunu basılı tutup yeniden tıklayın."))
                return
            self._clone = PatternCloneSession(s.page, s.clone_patch, self.tools.clone_size)
            self._clone.add_point(p)
            return
        # The brush size only defines the painted area on the target; it does not change the source offset.
        self._clone = CloneSession(s.page, offset, self.tools.clone_size)
        self._clone.add_point(p)

    def _set_clone_source(self, s: PageScene, p: QPointF) -> None:
        if not s.page.rect.contains(math.floor(p.x()), math.floor(p.y())):
            self.message.emit(tr("Kaynak noktası görselin içinde olmalı."))
            return
        s.clone_source = QPointF(p)
        s.clone_offset = None
        assert self.tools is not None
        # The source area is fixed at the current brush size (used by the non-aligned mode).
        s.clone_patch = SourcePatch.capture(s.page, p, self.tools.clone_size)
        self._ping_step = 7
        self._ping_timer.start()
        self.message.emit(tr("Klon kaynağı seçildi: x {x}, y {y}. ", x=int(p.x()), y=int(p.y()))
                          + tr("Şimdi tuşu bırakıp sürükleyerek klonlayın."))
        self.cloneStateChanged.emit()
        self.viewport().update()

    def _end_clone(self) -> None:
        clone, self._clone = self._clone, None
        if clone is None:
            return
        cmd = clone.finish()
        if cmd is not None:
            clone.page.undo_stack.push(cmd)

    def _tick_ping(self) -> None:
        self._ping_step = max(0, self._ping_step - 1)
        if self._ping_step == 0:
            self._ping_timer.stop()
        self.viewport().update()

    def _draw_clone_overlay(self, painter: QPainter) -> None:
        """Source indicators. ALL have a fixed screen size: they do not grow or shrink with the
        brush size (the brush size only sets the white/black circle preview on the target).
          turquoise cross + small ring : clone source
              aligned mode after the first stroke → at cursor + offset (moves with the cursor)
              other cases (non-aligned / before the first stroke) → at the marked fixed point
          orange cross + ring          : clone source selection mode while K is held (under the cursor)"""
        s = self.page_scene()
        if s is None or self.tools is None or self.tools.tool != Tool.CLONE or self.is_panning():
            return
        px = 1.0 / max(self.zoom(), 1e-6)
        held = self._clone_key_held()

        def mark(c: QPointF, color: QColor) -> None:
            arm, ring = CLONE_MARK_ARM * px, CLONE_MARK_RING * px
            for col, width in ((QColor(0, 0, 0, 190), 3.0), (color, 1.4)):
                pen = QPen(col, width)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawLine(QPointF(c.x() - arm, c.y()), QPointF(c.x() + arm, c.y()))
                painter.drawLine(QPointF(c.x(), c.y() - arm), QPointF(c.x(), c.y() + arm))
                painter.drawEllipse(c, ring, ring)

        def area(rect: QRectF, color: QColor) -> None:
            """Non-aligned mode: the real (fixed) square source area, dashed outline."""
            for col, width, style in ((QColor(0, 0, 0, 170), 3.0, Qt.PenStyle.SolidLine),
                                      (color, 1.4, Qt.PenStyle.DashLine)):
                pen = QPen(col, width, style)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if held:
            if self._hover is not None:
                mark(self._hover, QColor("#ffb020"))
                if not self.tools.clone_aligned:  # the square that will be captured on click = current brush size
                    side = float(max(1, round(self.tools.clone_size)))
                    area(QRectF(self._hover.x() - side / 2, self._hover.y() - side / 2, side, side), QColor("#ffb020"))
        elif s.clone_source is not None:
            marker = s.clone_source
            if self.tools.clone_aligned and s.clone_offset is not None and self._hover is not None:
                marker = self._hover + QPointF(s.clone_offset)  # aligned: the source moves with the cursor
            mark(marker, QColor("#35e0ff"))
            if not self.tools.clone_aligned and s.clone_patch is not None:
                area(QRectF(s.clone_patch.bounds), QColor("#35e0ff"))
        if self._ping_step > 0 and s.clone_source is not None:
            k = 7 - self._ping_step
            ring = QColor("#ffb020")
            ring.setAlpha(60 + 28 * self._ping_step)
            pen = QPen(ring, 2.5)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(s.clone_source, (CLONE_MARK_RING + 7 * k) * px, (CLONE_MARK_RING + 7 * k) * px)
        painter.restore()

    # ------------------------------------------------------------------ brush cursor
    def _brush_radius(self) -> float | None:
        if self.tools is None or self.tools.tool not in (Tool.BRUSH, Tool.ERASER, Tool.CLONE):
            return None
        return self.tools.active_size() / 2.0

    def _cursor_view_rect(self, center: QPointF | None) -> QRect:
        r = self._brush_radius()
        if center is None or r is None:
            return QRect()
        scene_rect = QRectF(center.x() - r, center.y() - r, 2 * r, 2 * r)
        return self.mapFromScene(scene_rect).boundingRect().adjusted(-3, -3, 3, 3)

    def _set_hover(self, p: QPointF | None) -> None:
        if self.tools is not None and self.tools.tool == Tool.CLONE:
            self._hover = p  # the source marker moves with the cursor too, so repaint everything
            self.viewport().update()
            return
        old = self._cursor_view_rect(self._hover)
        self._hover = p
        new = self._cursor_view_rect(p)
        if not old.isEmpty():
            self.viewport().update(old)
        if not new.isEmpty():
            self.viewport().update(new)

    def _refresh_brush_cursor(self) -> None:
        self.viewport().update()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)
        if self._create_rect is not None:
            painter.save()
            pen = QPen(QColor("#4c8dff"), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(QColor(76, 141, 255, 30))
            painter.drawRect(self._create_rect)
            painter.restore()
        self._draw_clone_overlay(painter)
        r = self._brush_radius()
        if r is None or self._hover is None or self._space_down or self.is_panning() or self._clone_key_held():
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for color, width in ((QColor(0, 0, 0, 170), 3.0), (QColor(255, 255, 255, 230), 1.0)):
            pen = QPen(color, width)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawEllipse(self._hover, r, r)
        painter.restore()
