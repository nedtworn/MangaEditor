"""Small, reusable settings widgets."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from ..i18n import tr
from PySide6.QtWidgets import (
    QColorDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QPushButton,
    QSlider,
    QSpinBox,
    QWidget,
)


class ColorButton(QPushButton):
    """Button that shows a color and opens the color picker when clicked."""

    colorChanged = Signal(QColor)

    def __init__(self, color: QColor | None = None, alpha: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._alpha = alpha
        self._color = QColor(color) if color is not None else QColor(0, 0, 0)
        self.setFixedHeight(28)
        self.setMinimumWidth(80)
        self.clicked.connect(self._pick)
        self._refresh()

    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor, emit: bool = False) -> None:
        color = QColor(color)
        if color == self._color:
            return
        self._color = color
        self._refresh()
        if emit:
            self.colorChanged.emit(QColor(color))

    def _refresh(self) -> None:
        c = self._color
        text_color = "#000000" if c.lightnessF() > 0.55 or c.alphaF() < 0.4 else "#ffffff"
        label = c.name(QColor.NameFormat.HexArgb if self._alpha and c.alpha() < 255 else QColor.NameFormat.HexRgb)
        self.setText(label.upper())
        self.setStyleSheet(
            f"QPushButton {{ background: rgba({c.red()},{c.green()},{c.blue()},{c.alpha()});"
            f" color: {text_color}; border: 1px solid #50555e; border-radius: 5px; }}"
        )

    def _pick(self) -> None:
        opts = QColorDialog.ColorDialogOption(0)
        if self._alpha:
            opts |= QColorDialog.ColorDialogOption.ShowAlphaChannel
        c = QColorDialog.getColor(self._color, self.window(), tr("Renk Seç"), opts)
        if c.isValid():
            self.set_color(c, emit=True)


class SliderSpin(QWidget):
    """Slider with a spin box (integer value)."""

    valueChanged = Signal(int)

    def __init__(self, minimum: int, maximum: int, value: int, suffix: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.spin = QSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setSuffix(suffix)
        self.spin.setFixedWidth(72)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.spin)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)
        self.set_value(value)

    def value(self) -> int:
        return self.spin.value()

    def set_value(self, v: int) -> None:
        for w in (self.slider, self.spin):
            w.blockSignals(True)
            w.setValue(int(v))
            w.blockSignals(False)

    def _from_slider(self, v: int) -> None:
        self.spin.blockSignals(True)
        self.spin.setValue(v)
        self.spin.blockSignals(False)
        self.valueChanged.emit(v)

    def _from_spin(self, v: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(v)
        self.slider.blockSignals(False)
        self.valueChanged.emit(v)


def double_spin(minimum: float, maximum: float, value: float, step: float = 0.1, decimals: int = 1,
                suffix: str = "") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(minimum, maximum)
    s.setSingleStep(step)
    s.setDecimals(decimals)
    s.setValue(value)
    s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    return s
