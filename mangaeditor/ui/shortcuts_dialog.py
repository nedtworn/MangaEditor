"""Settings → Shortcuts window.

Each action shows its shortcut as a button. Clicking the button enters "capture" mode
(orange border, "Press a key combination…"); the pressed combination is then assigned
with ShortcutRegistry.assign. On a conflict nothing is assigned: the message names the
conflicting action and the existing shortcut stays as it was.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from .shortcuts import ShortcutRegistry, is_modifier_key, sequence_from_event

ROW_HEIGHT = 32

_IDLE_STYLE = ""
_CAPTURE_STYLE = ("QPushButton { background: #3a2f12; color: #ffd27a; border: 2px solid #ffb020;"
                  " border-radius: 5px; font-weight: 600; }")


def capture_prompt() -> str:
    return tr("Tuş kombinasyonuna basın…  (Esc: iptal)")


class ShortcutCaptureButton(QPushButton):
    """Button that waits for a key combination after it is clicked."""

    captured = Signal(object)  # QKeySequence
    cancelled = Signal()

    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self._capturing = False
        self._idle_text = text
        self.setAutoDefault(False)
        self.setDefault(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumWidth(190)
        self.clicked.connect(self.start_capture)

    @property
    def capturing(self) -> bool:
        return self._capturing

    def set_display(self, text: str) -> None:
        self._idle_text = text
        if not self._capturing:
            self.setText(text)

    def start_capture(self) -> None:
        if self._capturing:
            return
        self._capturing = True
        self.setText(capture_prompt())
        self.setStyleSheet(_CAPTURE_STYLE)
        self.setFocus(Qt.FocusReason.MouseFocusReason)

    def _end_capture(self) -> None:
        self._capturing = False
        self.setText(self._idle_text)
        self.setStyleSheet(_IDLE_STYLE)

    def cancel_capture(self) -> None:
        if self._capturing:
            self._end_capture()
            self.cancelled.emit()

    @staticmethod
    def _modifier_preview(mods: Qt.KeyboardModifier) -> str:
        parts = []
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if mods & Qt.KeyboardModifier.MetaModifier:
            parts.append("Meta")
        return " + ".join(parts + ["…"]) if parts else capture_prompt()

    def event(self, ev: QEvent) -> bool:
        # While capturing, application shortcuts (such as Ctrl+S) must not fire: the key comes to us.
        if self._capturing and ev.type() == QEvent.Type.ShortcutOverride:
            ev.accept()
            return True
        return super().event(ev)

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        if not self._capturing:
            super().keyPressEvent(ev)
            return
        ev.accept()
        if ev.isAutoRepeat():
            return
        if ev.key() == Qt.Key.Key_Escape:
            self.cancel_capture()
            return
        if is_modifier_key(ev.key()):
            # A modifier alone cannot be assigned; show the modifiers being held.
            self.setText(self._modifier_preview(ev.modifiers() | _mod_of(ev.key())))
            return
        seq = sequence_from_event(ev)
        if seq is None:
            return
        self._end_capture()
        self.captured.emit(seq)

    def keyReleaseEvent(self, ev: QKeyEvent) -> None:
        if not self._capturing:
            super().keyReleaseEvent(ev)
            return
        ev.accept()
        if is_modifier_key(ev.key()) and not ev.isAutoRepeat():
            self.setText(self._modifier_preview(ev.modifiers() & ~_mod_of(ev.key())))

    def focusOutEvent(self, ev) -> None:
        self.cancel_capture()  # clicking elsewhere ends capture without changing the assignment
        super().focusOutEvent(ev)


def _mod_of(key: int) -> Qt.KeyboardModifier:
    return {
        Qt.Key.Key_Control: Qt.KeyboardModifier.ControlModifier,
        Qt.Key.Key_Alt: Qt.KeyboardModifier.AltModifier,
        Qt.Key.Key_AltGr: Qt.KeyboardModifier.AltModifier,
        Qt.Key.Key_Shift: Qt.KeyboardModifier.ShiftModifier,
        Qt.Key.Key_Meta: Qt.KeyboardModifier.MetaModifier,
    }.get(Qt.Key(key), Qt.KeyboardModifier.NoModifier)


class ShortcutsDialog(QDialog):
    def __init__(self, registry: ShortcutRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.registry = registry
        self.setWindowTitle(tr("Kısayollar"))
        self.resize(620, 640)
        lay = QVBoxLayout(self)

        intro = QLabel(tr("Değiştirmek istediğiniz işlemin kısayoluna tıklayın, ardından yeni tuş "
                          "kombinasyonuna basın (Ctrl, Alt, Shift ile birlikte olabilir). Esc iptal eder."))
        intro.setWordWrap(True)
        intro.setObjectName("hint")
        lay.addWidget(intro)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels([tr("İşlem"), tr("Kısayol"), ""])
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(12)
        self.tree.setUniformRowHeights(False)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        h = self.tree.header()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.tree, 1)

        self._buttons: dict[str, ShortcutCaptureButton] = {}
        self._reset_buttons: dict[str, QPushButton] = {}
        self._items: dict[str, QTreeWidgetItem] = {}
        bold = QFont(self.font())
        bold.setBold(True)
        for group in registry.groups():
            top = QTreeWidgetItem([tr(group)])
            top.setFont(0, bold)
            top.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tree.addTopLevelItem(top)
            top.setExpanded(True)
            for d in registry.definitions():
                if d.group != group:
                    continue
                item = QTreeWidgetItem([tr(d.label)])
                item.setSizeHint(0, QSize(0, ROW_HEIGHT))  # keep the buttons from being clipped
                top.addChild(item)
                self._items[d.id] = item
                btn = ShortcutCaptureButton()
                btn.setFixedHeight(ROW_HEIGHT - 6)
                btn.captured.connect(lambda seq, sid=d.id: self._on_captured(sid, seq))
                btn.cancelled.connect(lambda sid=d.id: self._set_status(tr("Atama iptal edildi."), "info"))
                self.tree.setItemWidget(item, 1, btn)
                self._buttons[d.id] = btn
                rb = QPushButton("↺")
                rb.setToolTip(tr("Bu işlemin kısayolunu varsayılana döndür"))
                rb.setFixedSize(30, ROW_HEIGHT - 6)
                rb.setAutoDefault(False)
                rb.clicked.connect(lambda _c=False, sid=d.id: self._on_reset_one(sid))
                self.tree.setItemWidget(item, 2, rb)
                self._reset_buttons[d.id] = rb

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(40)
        lay.addWidget(self.status)
        note = QLabel(tr("Basılı tutma tuşları (Space, K) tek tuş olmalıdır. Metin düzenlenirken Ctrl+A/C/X/V/Z/Y, "
                         "ok, Home/End gibi yazı düzenleme tuşları sabittir ve her zaman metne gider."))
        note.setWordWrap(True)
        note.setObjectName("hint")
        lay.addWidget(note)

        row = QHBoxLayout()
        self.reset_all_btn = QPushButton(tr("Varsayılanlara Dön"))
        self.reset_all_btn.setAutoDefault(False)
        self.reset_all_btn.clicked.connect(self._on_reset_all)
        close = QPushButton(tr("Kapat"))
        close.setObjectName("primary")
        close.clicked.connect(self.accept)
        row.addWidget(self.reset_all_btn)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)

        registry.changed.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------------ access (tests and other code)
    def capture_button(self, sid: str) -> ShortcutCaptureButton:
        return self._buttons[sid]

    def reset_button(self, sid: str) -> QPushButton:
        return self._reset_buttons[sid]

    def row_item(self, sid: str) -> QTreeWidgetItem:
        return self._items[sid]

    # ------------------------------------------------------------------ state
    def refresh(self) -> None:
        for sid, btn in self._buttons.items():
            btn.set_display(self.registry.display(sid))
            custom = not self.registry.is_default(sid)
            self._reset_buttons[sid].setEnabled(custom)
            f = QFont(self._items[sid].font(0))
            f.setBold(custom)  # changed shortcuts are shown in bold
            self._items[sid].setFont(0, f)
        self.reset_all_btn.setEnabled(not self.registry.all_default())

    def _set_status(self, text: str, kind: str) -> None:
        color = {"error": "#ff7b7b", "ok": "#7bd88f", "info": "#9ea3ab"}[kind]
        self.status.setStyleSheet(f"color: {color};")
        self.status.setText(text)

    def _on_captured(self, sid: str, seq: QKeySequence) -> None:
        d = self.registry.definition(sid)
        result = self.registry.assign(sid, seq)
        self.refresh()
        if result.ok:
            self._set_status(tr("“{label}” kısayolu: {keys}", label=tr(d.label),
                                keys=self.registry.display(sid)), "ok")
            return
        self._set_status(result.message, "error")
        if result.conflict is not None:  # show the conflicting action
            item = self._items[result.conflict.id]
            self.tree.setCurrentItem(item)
            self.tree.scrollToItem(item)

    def _on_reset_one(self, sid: str) -> None:
        result = self.registry.reset(sid)
        self.refresh()
        if result.ok:
            self._set_status(tr("“{label}” varsayılana döndü: {keys}",
                                label=tr(self.registry.definition(sid).label),
                                keys=self.registry.display(sid)), "ok")
        else:
            self._set_status(result.message, "error")

    def _on_reset_all(self) -> None:
        B = QMessageBox.StandardButton
        r = QMessageBox.question(self, tr("Kısayollar"),
                                 tr("Tüm kısayollar varsayılan değerlerine döndürülsün mü?"),
                                 B.Yes | B.No, B.No)
        if r == B.Yes:
            self.registry.reset_all()
            self.refresh()
            self._set_status(tr("Tüm kısayollar varsayılana döndü."), "ok")
