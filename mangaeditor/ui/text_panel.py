"""Text tool panel. Edits the selected text if there is one, otherwise the default
style of new texts."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QFontComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.text_data import TextData
from ..i18n import tr
from .widgets import ColorButton, double_spin


def _color_str(c: QColor) -> str:
    return c.name(QColor.NameFormat.HexArgb)


class TextPanel(QScrollArea):
    fieldEdited = Signal(str, object)  # field name, new value
    loadFontRequested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("sidePanel")
        self.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        self.title = QLabel(tr("Metin"))
        self.title.setObjectName("panelTitle")
        lay.addWidget(self.title)
        self.mode_hint = QLabel("")
        self.mode_hint.setObjectName("hint")
        self.mode_hint.setWordWrap(True)
        lay.addWidget(self.mode_hint)
        self._loading = False

        # --- font
        font_box = QGroupBox(tr("Yazı tipi"))
        fl = QVBoxLayout(font_box)
        self.font_combo = QFontComboBox()
        self.font_combo.setMaxVisibleItems(16)
        fl.addWidget(self.font_combo)
        self.load_font_btn = QPushButton(tr("Font Yükle (TTF/OTF)…"))
        fl.addWidget(self.load_font_btn)
        row = QHBoxLayout()
        self.size_spin = QSpinBox()
        self.size_spin.setRange(4, 600)
        self.size_spin.setSuffix(" px")
        self.size_spin.setKeyboardTracking(False)
        # The button letters are translated too ("K" = Kalın / Bold, "İ" = İtalik / Italic).
        self.bold_btn = self._toggle(tr("K"), tr("Kalın"))
        f = self.bold_btn.font()
        f.setBold(True)
        self.bold_btn.setFont(f)
        self.italic_btn = self._toggle(tr("İ"), tr("İtalik"))
        f = self.italic_btn.font()
        f.setItalic(True)
        self.italic_btn.setFont(f)
        row.addWidget(self.size_spin, 1)
        row.addWidget(self.bold_btn)
        row.addWidget(self.italic_btn)
        fl.addLayout(row)
        cform = QFormLayout()
        self.color_btn = ColorButton(alpha=True)
        cform.addRow(tr("Renk"), self.color_btn)
        fl.addLayout(cform)
        lay.addWidget(font_box)

        # --- alignment and spacing
        align_box = QGroupBox(tr("Hizalama ve aralık"))
        al = QFormLayout(align_box)
        self.h_group, h_row = self._segmented((("left", tr("Sol")), ("center", tr("Orta")), ("right", tr("Sağ"))))
        self.v_group, v_row = self._segmented((("top", tr("Üst")), ("middle", tr("Orta")), ("bottom", tr("Alt"))))
        al.addRow(tr("Yatay"), h_row)
        al.addRow(tr("Dikey"), v_row)
        self.line_spin = double_spin(0.5, 4.0, 1.0, 0.05, 2, " ×")
        self.letter_spin = double_spin(-20.0, 100.0, 0.0, 0.5, 1, " px")
        self.rot_spin = double_spin(-180.0, 180.0, 0.0, 1.0, 1, "°")
        self.rot_spin.setWrapping(True)
        al.addRow(tr("Satır aralığı"), self.line_spin)
        al.addRow(tr("Harf aralığı"), self.letter_spin)
        al.addRow(tr("Döndürme"), self.rot_spin)
        lay.addWidget(align_box)

        # --- outline
        self.stroke_box = QGroupBox(tr("Dış çizgi"))
        self.stroke_box.setCheckable(True)
        sl = QFormLayout(self.stroke_box)
        self.stroke_width = double_spin(0.5, 60.0, 3.0, 0.5, 1, " px")
        self.stroke_color = ColorButton(alpha=True)
        sl.addRow(tr("Kalınlık"), self.stroke_width)
        sl.addRow(tr("Renk"), self.stroke_color)
        lay.addWidget(self.stroke_box)

        # --- shadow
        self.shadow_box = QGroupBox(tr("Gölge"))
        self.shadow_box.setCheckable(True)
        shl = QFormLayout(self.shadow_box)
        self.shadow_color = ColorButton(alpha=True)
        self.shadow_dx = double_spin(-100.0, 100.0, 3.0, 1.0, 1, " px")
        self.shadow_dy = double_spin(-100.0, 100.0, 3.0, 1.0, 1, " px")
        shl.addRow(tr("Renk"), self.shadow_color)
        shl.addRow(tr("Yatay kayma"), self.shadow_dx)
        shl.addRow(tr("Dikey kayma"), self.shadow_dy)
        lay.addWidget(self.shadow_box)

        # --- background
        self.bg_box = QGroupBox(tr("Arka plan"))
        self.bg_box.setCheckable(True)
        bl = QFormLayout(self.bg_box)
        self.bg_color = ColorButton(alpha=True)
        self.bg_radius = double_spin(0.0, 500.0, 0.0, 1.0, 0, " px")
        bl.addRow(tr("Renk"), self.bg_color)
        bl.addRow(tr("Köşe yuvarlama"), self.bg_radius)
        lay.addWidget(self.bg_box)

        hint = QLabel(tr("Boş alana tıkla: yeni metin · Sürükle: kutu çiz\n"
                         "Çift tıkla / Enter: düzenle · Esc: bitir\n"
                         "Enter (düzenlerken): satır sonu · Delete: sil"))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addStretch(1)
        self._connect()

    # ------------------------------------------------------------------ setup
    @staticmethod
    def _toggle(text: str, tip: str) -> QPushButton:
        b = QPushButton(text)
        b.setCheckable(True)
        b.setToolTip(tip)
        b.setFixedWidth(34)
        return b

    @staticmethod
    def _segmented(options) -> tuple[QButtonGroup, QWidget]:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        group = QButtonGroup(w)
        group.setExclusive(True)
        for value, label in options:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setProperty("value", value)
            group.addButton(b)
            row.addWidget(b)
        return group, w

    def _emit(self, field: str, value: Any) -> None:
        if not self._loading:
            self.fieldEdited.emit(field, value)

    def _connect(self) -> None:
        self.font_combo.currentFontChanged.connect(lambda f: self._emit("font_family", f.family()))
        self.load_font_btn.clicked.connect(self.loadFontRequested.emit)
        self.size_spin.valueChanged.connect(lambda v: self._emit("font_size", int(v)))
        self.bold_btn.toggled.connect(lambda v: self._emit("bold", bool(v)))
        self.italic_btn.toggled.connect(lambda v: self._emit("italic", bool(v)))
        self.color_btn.colorChanged.connect(lambda c: self._emit("color", _color_str(c)))
        self.h_group.buttonClicked.connect(lambda b: self._emit("align_h", b.property("value")))
        self.v_group.buttonClicked.connect(lambda b: self._emit("align_v", b.property("value")))
        self.line_spin.valueChanged.connect(lambda v: self._emit("line_spacing", float(v)))
        self.letter_spin.valueChanged.connect(lambda v: self._emit("letter_spacing", float(v)))
        self.rot_spin.valueChanged.connect(lambda v: self._emit("rotation", float(v)))
        self.stroke_box.toggled.connect(lambda v: self._emit("stroke_enabled", bool(v)))
        self.stroke_width.valueChanged.connect(lambda v: self._emit("stroke_width", float(v)))
        self.stroke_color.colorChanged.connect(lambda c: self._emit("stroke_color", _color_str(c)))
        self.shadow_box.toggled.connect(lambda v: self._emit("shadow_enabled", bool(v)))
        self.shadow_color.colorChanged.connect(lambda c: self._emit("shadow_color", _color_str(c)))
        self.shadow_dx.valueChanged.connect(lambda v: self._emit("shadow_dx", float(v)))
        self.shadow_dy.valueChanged.connect(lambda v: self._emit("shadow_dy", float(v)))
        self.bg_box.toggled.connect(lambda v: self._emit("bg_enabled", bool(v)))
        self.bg_color.colorChanged.connect(lambda c: self._emit("bg_color", _color_str(c)))
        self.bg_radius.valueChanged.connect(lambda v: self._emit("bg_radius", float(v)))

    # ------------------------------------------------------------------ loading
    def load(self, data: TextData, selected_count: int) -> None:
        """Fills the panel with the values of the given data (without emitting signals)."""
        self._loading = True
        try:
            if selected_count == 0:
                self.mode_hint.setText(tr("Yeni metinlerin varsayılan stili"))
            elif selected_count == 1:
                self.mode_hint.setText(tr("Seçili metin"))
            else:
                self.mode_hint.setText(tr("{n} metin seçili – değişiklik hepsine uygulanır", n=selected_count))
            self.rot_spin.setEnabled(selected_count > 0)
            self.font_combo.setCurrentFont(QFont(data.font_family))
            self.size_spin.setValue(int(data.font_size))
            self.bold_btn.setChecked(data.bold)
            self.italic_btn.setChecked(data.italic)
            self.color_btn.set_color(QColor(data.color))
            for group, value in ((self.h_group, data.align_h), (self.v_group, data.align_v)):
                for b in group.buttons():
                    b.setChecked(b.property("value") == value)
            self.line_spin.setValue(data.line_spacing)
            self.letter_spin.setValue(data.letter_spacing)
            self.rot_spin.setValue(data.rotation)
            self.stroke_box.setChecked(data.stroke_enabled)
            self.stroke_width.setValue(data.stroke_width)
            self.stroke_color.set_color(QColor(data.stroke_color))
            self.shadow_box.setChecked(data.shadow_enabled)
            self.shadow_color.set_color(QColor(data.shadow_color))
            self.shadow_dx.setValue(data.shadow_dx)
            self.shadow_dy.setValue(data.shadow_dy)
            self.bg_box.setChecked(data.bg_enabled)
            self.bg_color.set_color(QColor(data.bg_color))
            self.bg_radius.setValue(data.bg_radius)
        finally:
            self._loading = False
