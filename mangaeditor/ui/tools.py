"""Active tool and tool settings (shared by all pages)."""
from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor

from ..core.text_data import TextData


class Tool(str, Enum):
    BRUSH = "brush"
    ERASER = "eraser"
    CLONE = "clone"
    EYEDROPPER = "eyedropper"
    TEXT = "text"


# Display names (Turkish source strings; translated with i18n.tr where shown).
TOOL_LABELS = {
    Tool.BRUSH: "Fırça",
    Tool.ERASER: "Silgi",
    Tool.CLONE: "Klonlama",
    Tool.EYEDROPPER: "Damlalık",
    Tool.TEXT: "Metin",
}


class ToolSettings(QObject):
    toolChanged = Signal(object)  # Tool
    brushChanged = Signal()
    eraserChanged = Signal()
    cloneChanged = Signal()
    cloneModeChanged = Signal()
    textDefaultsChanged = Signal()

    MIN_SIZE = 1
    MAX_SIZE = 500

    def __init__(self) -> None:
        super().__init__()
        self._tool = Tool.BRUSH
        self._previous_tool = Tool.BRUSH
        # White is the color used most often when cleaning up a page.
        self.brush_color = QColor(255, 255, 255)
        self.brush_size = 24
        self.brush_opacity = 1.0
        self.eraser_size = 32
        self.clone_size = 40
        # Aligned: the source-target offset is kept between strokes. Non-aligned: every stroke
        # starts again from the marked source. The source point and the brush size are independent.
        self.clone_aligned = True
        self.text_defaults = TextData()

    # ---------------------------------------------------------------- tool
    @property
    def tool(self) -> Tool:
        return self._tool

    @property
    def previous_tool(self) -> Tool:
        return self._previous_tool

    def set_tool(self, tool: Tool) -> None:
        if tool == self._tool:
            return
        self._previous_tool = self._tool
        self._tool = tool
        self.toolChanged.emit(tool)

    # ---------------------------------------------------------------- brush / eraser
    def _clamp_size(self, size: float) -> int:
        return int(max(self.MIN_SIZE, min(self.MAX_SIZE, round(size))))

    def set_brush_size(self, size: float) -> None:
        size = self._clamp_size(size)
        if size != self.brush_size:
            self.brush_size = size
            self.brushChanged.emit()

    def set_brush_color(self, color: QColor) -> None:
        color = QColor(color)
        color.setAlpha(255)  # transparency is handled by the opacity setting
        if color != self.brush_color:
            self.brush_color = color
            self.brushChanged.emit()

    def set_brush_opacity(self, opacity: float) -> None:
        opacity = max(0.01, min(1.0, float(opacity)))
        if abs(opacity - self.brush_opacity) > 1e-6:
            self.brush_opacity = opacity
            self.brushChanged.emit()

    def set_eraser_size(self, size: float) -> None:
        size = self._clamp_size(size)
        if size != self.eraser_size:
            self.eraser_size = size
            self.eraserChanged.emit()

    def set_clone_size(self, size: float) -> None:
        size = self._clamp_size(size)
        if size != self.clone_size:
            self.clone_size = size
            self.cloneChanged.emit()

    def set_clone_aligned(self, aligned: bool) -> None:
        aligned = bool(aligned)
        if aligned != self.clone_aligned:
            self.clone_aligned = aligned
            self.cloneModeChanged.emit()

    def active_size(self) -> int:
        if self._tool == Tool.ERASER:
            return self.eraser_size
        if self._tool == Tool.CLONE:
            return self.clone_size
        return self.brush_size

    def set_active_size(self, size: float) -> None:
        if self._tool == Tool.ERASER:
            self.set_eraser_size(size)
        elif self._tool == Tool.CLONE:
            self.set_clone_size(size)
        elif self._tool == Tool.BRUSH:
            self.set_brush_size(size)

    # ---------------------------------------------------------------- text
    def set_text_defaults(self, data: TextData) -> None:
        data = data.with_(id="", text="", x=0.0, y=0.0, rotation=0.0)
        if data != self.text_defaults:
            self.text_defaults = data
            self.textDefaultsChanged.emit()
