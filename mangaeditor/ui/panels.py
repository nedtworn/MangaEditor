"""Right-hand side panel: shows only the settings of the selected tool."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from .tools import TOOL_LABELS, Tool, ToolSettings
from .widgets import ColorButton, SliderSpin


def _panel_layout(widget: QWidget, title: str) -> QVBoxLayout:
    lay = QVBoxLayout(widget)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(10)
    t = QLabel(title)
    t.setObjectName("panelTitle")
    lay.addWidget(t)
    return lay


def _hint(text: str) -> QLabel:
    h = QLabel(text)
    h.setObjectName("hint")
    h.setWordWrap(True)
    return h


class BrushPanel(QWidget):
    def __init__(self, tools: ToolSettings) -> None:
        super().__init__()
        self.tools = tools
        lay = _panel_layout(self, tr("Fırça"))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.size = SliderSpin(ToolSettings.MIN_SIZE, ToolSettings.MAX_SIZE, tools.brush_size, " px")
        self.color = ColorButton(tools.brush_color)
        self.opacity = SliderSpin(1, 100, round(tools.brush_opacity * 100), " %")
        form.addRow(tr("Boyut"), self.size)
        form.addRow(tr("Renk"), self.color)
        form.addRow(tr("Opaklık"), self.opacity)
        lay.addLayout(form)
        lay.addWidget(_hint(tr("[ ve ] tuşları boyutu değiştirir.\nAlt + tıklama: renk al.")))
        lay.addStretch(1)
        self.size.valueChanged.connect(tools.set_brush_size)
        self.color.colorChanged.connect(tools.set_brush_color)
        self.opacity.valueChanged.connect(lambda v: tools.set_brush_opacity(v / 100.0))
        tools.brushChanged.connect(self.sync)

    def sync(self) -> None:
        self.size.set_value(self.tools.brush_size)
        self.color.set_color(self.tools.brush_color)
        self.opacity.set_value(round(self.tools.brush_opacity * 100))


class EraserPanel(QWidget):
    def __init__(self, tools: ToolSettings) -> None:
        super().__init__()
        self.tools = tools
        lay = _panel_layout(self, tr("Silgi"))
        form = QFormLayout()
        self.size = SliderSpin(ToolSettings.MIN_SIZE, ToolSettings.MAX_SIZE, tools.eraser_size, " px")
        form.addRow(tr("Boyut"), self.size)
        lay.addLayout(form)
        lay.addWidget(_hint(tr("Boyanan alanları siler; altındaki orijinal görsel geri gelir. "
                               "Orijinal görsel hiçbir zaman değişmez.")))
        lay.addStretch(1)
        self.size.valueChanged.connect(tools.set_eraser_size)
        tools.eraserChanged.connect(lambda: self.size.set_value(self.tools.eraser_size))


class ClonePanel(QWidget):
    """Clone stamp settings: size, mode (aligned / non-aligned) and source status.

    The size only defines the painted area on the target; the source point and the
    source-target relationship do not depend on it."""

    def __init__(self, tools: ToolSettings) -> None:
        super().__init__()
        self.tools = tools
        lay = _panel_layout(self, tr("Klonlama"))
        form = QFormLayout()
        self.size = SliderSpin(ToolSettings.MIN_SIZE, ToolSettings.MAX_SIZE, tools.clone_size, " px")
        form.addRow(tr("Boyut"), self.size)
        lay.addLayout(form)

        self.mode_aligned = QRadioButton(tr("Hizalı"))
        self.mode_aligned.setToolTip(tr("Kaynak, imleçle birlikte kayar; kaynak-hedef uzaklığı darbeler arasında da korunur."))
        self.mode_free = QRadioButton(tr("Hizalı Değil"))
        self.mode_free.setToolTip(tr("Kaynak noktası sabit kalır; her yeni darbe aynı kaynak noktasından başlar."))
        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.mode_aligned)
        group.addButton(self.mode_free)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode_aligned)
        mode_row.addWidget(self.mode_free)
        mode_row.addStretch(1)
        form.addRow(tr("Mod"), mode_row)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.hint = _hint("")
        lay.addWidget(self.hint)
        lay.addStretch(1)
        self.size.valueChanged.connect(tools.set_clone_size)
        tools.cloneChanged.connect(lambda: self.size.set_value(self.tools.clone_size))
        self.mode_aligned.toggled.connect(lambda on: on and tools.set_clone_aligned(True))
        self.mode_free.toggled.connect(lambda on: on and tools.set_clone_aligned(False))
        tools.cloneModeChanged.connect(self._sync_mode)
        self._key = "K"
        self._src = None
        self._off = None
        self._area = None
        self._sync_mode()
        self.set_source(None, None)

    def _sync_mode(self) -> None:
        for btn, on in ((self.mode_aligned, self.tools.clone_aligned), (self.mode_free, not self.tools.clone_aligned)):
            btn.blockSignals(True)
            btn.setChecked(on)
            btn.blockSignals(False)
        self._refresh_hint()

    def set_hold_key_text(self, text: str) -> None:
        self._key = text
        self._refresh_hint()
        self.set_source(self._src, self._off, self._area)

    def _refresh_hint(self) -> None:
        if self.tools.clone_aligned:
            mode = tr("Hizalı: kaynak imleçle birlikte kayar; kaynak-hedef uzaklığı ilk basışta sabitlenir "
                      "ve sonraki darbelerde de korunur.")
        else:
            mode = tr("Hizalı değil: kaynak seçerken o anki fırça boyutunda KARE bir alan (konum ve içerik) "
                      "sabitlenir. Boyarken hedef bu alanın tekrarlarıyla desen gibi döşenir; fareyi bırakmasanız da "
                      "kayma ya da uzama olmaz, alanın dışından okunmaz. Yalnızca yeni kaynak seçince değişir.")
        self.hint.setText(
            tr("1. {key} tuşunu basılı tutup kopyalanacak (temiz) bölgeye tıklayın: kaynak seçilir, "
               "hiçbir şey çizilmez.\n", key=self._key)
            + tr("2. Tuşu bırakıp hedefe tıklayın ya da sürükleyin: kaynak pikselleri aktarılır.\n\n")
            + f"{mode}\n\n"
            + tr("Boyut yalnızca hedefte boyanan alanı belirler; kaynak noktasını etkilemez. "
                 "[ ve ] boyutu değiştirir."))

    def set_source(self, source, offset, area=None) -> None:
        """source: QPointF | None. offset: QPoint | None (aligned mode: set after the first stroke).
        area: (width, height) in pixels of the fixed source area, if any."""
        self._src, self._off, self._area = source, offset, area
        if source is None:
            self.status.setText(tr("Kaynak: seçilmedi — {key} basılı tutup tıklayın", key=self._key))
            self.status.setStyleSheet("color: #ffb020;")
        else:
            text = tr("Kaynak: x {x}, y {y}", x=int(source.x()), y=int(source.y()))
            if area is not None:
                text += tr("  ·  alan {w}×{h} px", w=area[0], h=area[1])
            self.status.setText(text)
            self.status.setStyleSheet("color: #35e0ff;")


class EyedropperPanel(QWidget):
    def __init__(self, tools: ToolSettings) -> None:
        super().__init__()
        self.tools = tools
        lay = _panel_layout(self, tr("Damlalık"))
        self.swatch = QFrame()
        self.swatch.setFixedHeight(44)
        self.value = QLabel("")
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.swatch)
        lay.addWidget(self.value)
        lay.addWidget(_hint(tr("Görselde bir noktaya tıklayın: o pikselin rengi fırça rengi olur. "
                               "Damlalık seçili kalır; istediğiniz kadar nokta deneyebilirsiniz. "
                               "Basılı tutup sürükleyerek önizleyebilirsiniz.")))
        lay.addStretch(1)
        tools.brushChanged.connect(self.sync)
        self.sync()

    def sync(self) -> None:
        c: QColor = self.tools.brush_color
        self.swatch.setStyleSheet(f"background: {c.name()}; border: 1px solid #50555e; border-radius: 6px;")
        self.value.setText(f"{c.name().upper()}   RGB({c.red()}, {c.green()}, {c.blue()})")


class SidePanel(QStackedWidget):
    """Shows the settings page of the active tool."""

    def __init__(self, tools: ToolSettings) -> None:
        super().__init__()
        self.setObjectName("sidePanel")
        self.setFixedWidth(280)
        self.tools = tools
        self.pages: dict[Tool, QWidget] = {}
        self.add_tool_page(Tool.BRUSH, BrushPanel(tools))
        self.add_tool_page(Tool.ERASER, EraserPanel(tools))
        self.clone_panel = ClonePanel(tools)
        self.add_tool_page(Tool.CLONE, self.clone_panel)
        self.add_tool_page(Tool.EYEDROPPER, EyedropperPanel(tools))
        tools.toolChanged.connect(self.show_tool)
        self.show_tool(tools.tool)

    def add_tool_page(self, tool: Tool, widget: QWidget) -> None:
        widget.setObjectName("sidePanel")
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.pages[tool] = widget
        self.addWidget(widget)

    def show_tool(self, tool: Tool) -> None:
        w = self.pages.get(tool)
        if w is not None:
            self.setCurrentWidget(w)
        self.setToolTip(tr(TOOL_LABELS.get(tool, "")))
