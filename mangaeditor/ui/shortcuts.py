"""Central keyboard shortcut management.

ALL shortcuts of the application (menus, tools, canvas and text actions) are defined and
assigned here. No other code checks fixed keys.

Three kinds of shortcut exist:
  action  – Bound to a QAction; Qt's shortcut mechanism triggers it (menus, tools,
            save/open, ...).
  local   – A single key press on the canvas (grow/shrink size, delete/edit text).
            Matched with registry.matches(...) while the canvas has focus.
  hold    – A key held down (Space to pan, K to pick a clone source). The canvas reports
            its key events with registry.note_key_press/release; registry.is_held(...)
            answers "is it down?".

Rules:
  * The same key combination cannot be assigned to two actions (of any kind).
  * Ctrl/Shift/Alt/Meta alone cannot be assigned; Esc is the cancel key and cannot be assigned.
  * Hold keys are single keys without modifiers.
  * User assignments are stored in QSettings; corrupt or conflicting records are ignored.

The labels (``label`` and ``group``) are Turkish source strings; they are translated for
display with ``i18n.tr``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import QKeyCombination, QObject, QSettings, Qt, Signal
from PySide6.QtGui import QAction, QKeyEvent, QKeySequence

from ..i18n import tr

ACTION, LOCAL, HOLD = "action", "local", "hold"

# --- action identifiers (code never checks raw keys; it uses these identifiers)
FILE_NEW, FILE_OPEN, FILE_SAVE, FILE_EXPORT = "file.new", "file.open", "file.save", "file.export"
FILE_CLOSE, FILE_QUIT = "file.close", "file.quit"
EDIT_UNDO, EDIT_REDO, PAGE_MERGE = "edit.undo", "edit.redo", "page.merge"
PAGE_ADD, PAGE_REMOVE = "page.add", "page.remove"
PAGE_MOVE_LEFT, PAGE_MOVE_RIGHT, PAGE_SET_TARGET = "page.move_left", "page.move_right", "page.set_target"
VIEW_ZOOM_IN, VIEW_ZOOM_OUT, VIEW_FIT, VIEW_ACTUAL = "view.zoom_in", "view.zoom_out", "view.fit", "view.actual"
TOOL_BRUSH, TOOL_ERASER, TOOL_CLONE = "tool.brush", "tool.eraser", "tool.clone"
TOOL_EYEDROPPER, TOOL_TEXT = "tool.eyedropper", "tool.text"
SIZE_UP, SIZE_DOWN = "tool.size_up", "tool.size_down"
PAN_HOLD, CLONE_SOURCE_HOLD = "canvas.pan", "clone.source"
TEXT_EDIT, TEXT_DELETE = "text.edit", "text.delete"


@dataclass(frozen=True)
class ShortcutDef:
    id: str
    label: str  # Turkish source string (translated for display)
    group: str  # Turkish source string (translated for display)
    defaults: tuple[str, ...] = ()
    kind: str = ACTION


DEFINITIONS: tuple[ShortcutDef, ...] = (
    ShortcutDef(FILE_NEW, "Yeni Proje", "Dosya", ("Ctrl+N",)),
    ShortcutDef(FILE_OPEN, "Proje Aç", "Dosya", ("Ctrl+O",)),
    ShortcutDef(FILE_SAVE, "Kaydet", "Dosya", ("Ctrl+S",)),
    ShortcutDef(FILE_EXPORT, "Dışa Aktar", "Dosya", ("Ctrl+E",)),
    ShortcutDef(FILE_CLOSE, "Projeyi Kapat", "Dosya"),
    ShortcutDef(FILE_QUIT, "Çıkış", "Dosya"),
    ShortcutDef(EDIT_UNDO, "Geri Al", "Düzen", ("Ctrl+Z",)),
    ShortcutDef(EDIT_REDO, "Yinele", "Düzen", ("Ctrl+Y", "Ctrl+Shift+Z")),
    ShortcutDef(PAGE_MERGE, "Sayfayı Birleştir", "Düzen", ("Ctrl+M",)),
    ShortcutDef(PAGE_ADD, "Sayfa Ekle", "Sayfa"),
    ShortcutDef(PAGE_REMOVE, "Sayfayı Kaldır", "Sayfa"),
    ShortcutDef(PAGE_MOVE_LEFT, "Sayfayı Sola Taşı", "Sayfa"),
    ShortcutDef(PAGE_MOVE_RIGHT, "Sayfayı Sağa Taşı", "Sayfa"),
    ShortcutDef(PAGE_SET_TARGET, "Kaydetme Hedefini Değiştir", "Sayfa"),
    ShortcutDef(VIEW_ZOOM_IN, "Yakınlaştır", "Görünüm", ("Ctrl++",)),
    ShortcutDef(VIEW_ZOOM_OUT, "Uzaklaştır", "Görünüm", ("Ctrl+-",)),
    ShortcutDef(VIEW_FIT, "Ekrana Sığdır", "Görünüm", ("Ctrl+0",)),
    ShortcutDef(VIEW_ACTUAL, "Gerçek Boyut (%100)", "Görünüm", ("Ctrl+1",)),
    ShortcutDef(TOOL_BRUSH, "Fırça", "Araçlar", ("B",)),
    ShortcutDef(TOOL_ERASER, "Silgi", "Araçlar", ("E",)),
    ShortcutDef(TOOL_CLONE, "Klonlama", "Araçlar", ("S",)),
    ShortcutDef(TOOL_EYEDROPPER, "Damlalık", "Araçlar", ("I",)),
    ShortcutDef(TOOL_TEXT, "Metin", "Araçlar", ("Ctrl+T",)),
    ShortcutDef(SIZE_UP, "Fırça / silgi / klon boyutunu büyüt", "Araçlar", ("]",), LOCAL),
    ShortcutDef(SIZE_DOWN, "Fırça / silgi / klon boyutunu küçült", "Araçlar", ("[",), LOCAL),
    ShortcutDef(PAN_HOLD, "Tuvali kaydır (basılı tut + sürükle)", "Tuval", ("Space",), HOLD),
    ShortcutDef(CLONE_SOURCE_HOLD, "Klon kaynağı seç (basılı tut + tıkla)", "Tuval", ("K",), HOLD),
    ShortcutDef(TEXT_EDIT, "Seçili metni düzenle", "Metin", ("Return",), LOCAL),
    ShortcutDef(TEXT_DELETE, "Seçili metni sil", "Metin", ("Del", "Backspace"), LOCAL),
)

_MODIFIER_KEYS = {
    Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_AltGr,
    Qt.Key.Key_Super_L, Qt.Key.Key_Super_R, Qt.Key.Key_Hyper_L, Qt.Key.Key_Hyper_R,
    Qt.Key.Key_CapsLock, Qt.Key.Key_NumLock, Qt.Key.Key_ScrollLock, Qt.Key.Key_Mode_switch,
}
_MODS = (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
         | Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.MetaModifier)
_CTRL, _ALT = Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.AltModifier
_SHIFT, _META = Qt.KeyboardModifier.ShiftModifier, Qt.KeyboardModifier.MetaModifier
SETTINGS_KEY = "shortcuts/overrides"


def is_modifier_key(key: int) -> bool:
    """Keys that cannot be assigned alone: modifiers and the 'unknown' key."""
    return key in (0, int(Qt.Key.Key_unknown)) or Qt.Key(key) in _MODIFIER_KEYS


def _combo(mods, key) -> QKeySequence:
    return QKeySequence(QKeyCombination(mods, Qt.Key(key)))


def _printable_symbol(text: str) -> bool:
    return bool(text) and text[0].isprintable() and not text[0].isalnum() and not text[0].isspace()


def event_sequences(event: QKeyEvent) -> list[QKeySequence]:
    """Key combinations an key event can represent (most likely first).

    * Shift is ignored when it was only used to type a symbol (Shift+1 = '!' is recorded as
      '!' and not 'Shift+!', as in Qt's QKeySequenceEdit).
    * On Windows, AltGr is reported as Ctrl+Alt: if it produces a SYMBOL (on a Turkish keyboard
      AltGr+8 = '[', AltGr+E = '€') the character itself is used. Ctrl+Alt combinations that
      produce letters or digits (Ctrl+Alt+Z) are real combinations.
    * Enter on the numeric keypad behaves like Return.
    """
    key = event.key()
    if is_modifier_key(key):
        return []
    mods = event.modifiers() & _MODS
    text = event.text()
    if key == Qt.Key.Key_Enter:
        key = Qt.Key.Key_Return
    if key == Qt.Key.Key_Backtab:
        key, mods = Qt.Key.Key_Tab, mods | _SHIFT
    candidates: list[QKeySequence] = []
    base = mods
    if (mods & _CTRL) and (mods & _ALT) and _printable_symbol(text):
        base = mods & ~(_CTRL | _ALT)  # a symbol typed with AltGr
    if (base & _SHIFT) and _printable_symbol(text):
        base = base & ~_SHIFT
    candidates.append(_combo(base, key))
    raw = mods
    if (raw & _SHIFT) and _printable_symbol(text) and base == mods:
        raw = raw & ~_SHIFT
    if raw != base:
        candidates.append(_combo(raw, key))  # may still be a real Ctrl+Alt+<key> assignment
    return candidates


def sequence_from_event(event: QKeyEvent) -> QKeySequence | None:
    """One combination for recording a shortcut (a lone modifier key → None)."""
    c = event_sequences(event)
    return c[0] if c else None


def portable(seq: QKeySequence) -> str:
    return seq.toString(QKeySequence.SequenceFormat.PortableText)


def native(seq: QKeySequence) -> str:
    return seq.toString(QKeySequence.SequenceFormat.NativeText)


def parse(text: str) -> QKeySequence:
    return QKeySequence.fromString(text, QKeySequence.SequenceFormat.PortableText)


@dataclass
class AssignResult:
    ok: bool
    message: str = ""
    conflict: ShortcutDef | None = None


class ShortcutRegistry(QObject):
    changed = Signal()  # any assignment changed
    holdChanged = Signal(str, bool)  # (action id, is it held down)

    def __init__(self, settings: QSettings | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._defs: dict[str, ShortcutDef] = {d.id: d for d in DEFINITIONS}
        self._bindings: dict[str, list[QKeySequence]] = {d.id: [parse(s) for s in d.defaults] for d in DEFINITIONS}
        self._actions: dict[str, tuple[QAction, str]] = {}
        self._held: dict[str, int] = {}  # action -> key code of the key holding it
        self._settings = settings
        self._load()
        self.changed.connect(self._refresh_actions)

    # ------------------------------------------------------------------ definitions
    def definitions(self) -> tuple[ShortcutDef, ...]:
        return DEFINITIONS

    def definition(self, sid: str) -> ShortcutDef:
        return self._defs[sid]

    def groups(self) -> list[str]:
        """Group names (Turkish source strings, in definition order)."""
        seen: list[str] = []
        for d in DEFINITIONS:
            if d.group not in seen:
                seen.append(d.group)
        return seen

    # ------------------------------------------------------------------ queries
    def sequences(self, sid: str) -> list[QKeySequence]:
        return list(self._bindings[sid])

    def display(self, sid: str) -> str:
        seqs = self._bindings[sid]
        return ", ".join(native(s) for s in seqs) if seqs else tr("Atanmadı")

    def is_default(self, sid: str) -> bool:
        return [portable(s) for s in self._bindings[sid]] == list(self._defs[sid].defaults)

    def all_default(self) -> bool:
        return all(self.is_default(d.id) for d in DEFINITIONS)

    def find_conflict(self, seq: QKeySequence, exclude_id: str | None = None) -> ShortcutDef | None:
        for d in DEFINITIONS:
            if d.id != exclude_id and any(seq == s for s in self._bindings[d.id]):
                return d
        return None

    def matches(self, sid: str, event: QKeyEvent) -> bool:
        seqs = self._bindings[sid]
        return bool(seqs) and any(c == s for c in event_sequences(event) for s in seqs)

    # ------------------------------------------------------------------ assignment
    def validate(self, sid: str, seq: QKeySequence) -> str | None:
        """Rules other than conflicts. Returns None when there is no problem."""
        if seq.isEmpty() or seq.count() != 1:
            return tr("Tek bir tuş kombinasyonu girin.")
        combo = seq[0]
        key = combo.key()
        if is_modifier_key(key.value if hasattr(key, "value") else int(key)):
            return tr("Ctrl, Shift veya Alt tek başına atanamaz; yanına bir tuş ekleyin.")
        if key == Qt.Key.Key_Escape:
            return tr("Esc iptal tuşudur, bir işleme atanamaz.")
        if self._defs[sid].kind == HOLD and combo.keyboardModifiers() != Qt.KeyboardModifier.NoModifier:
            return tr("Basılı tutma tuşları tek tuş olmalıdır (Ctrl/Alt/Shift ile birlikte olamaz).")
        return None

    def assign(self, sid: str, seq: QKeySequence) -> AssignResult:
        """Assigns the new combination. If it is invalid or conflicting, NOTHING changes."""
        problem = self.validate(sid, seq)
        if problem:
            return AssignResult(False, problem)
        other = self.find_conflict(seq, exclude_id=sid)
        if other is not None:
            return AssignResult(
                False,
                tr("“{seq}” zaten “{label}” işlemine atanmış. Atama yapılmadı.",
                   seq=native(seq), label=tr(other.label)),
                other)
        if self._bindings[sid] == [seq]:
            return AssignResult(True)
        self._bindings[sid] = [seq]
        self._save()
        self.changed.emit()
        return AssignResult(True)

    def reset(self, sid: str) -> AssignResult:
        """Resets one action to its default. Does not reset if the default is used by another action."""
        defaults = [parse(s) for s in self._defs[sid].defaults]
        for s in defaults:
            other = self.find_conflict(s, exclude_id=sid)
            if other is not None:
                return AssignResult(
                    False,
                    tr("Varsayılan “{seq}” şu an “{label}” işleminde kullanılıyor.",
                       seq=native(s), label=tr(other.label)),
                    other)
        self._bindings[sid] = defaults
        self._save()
        self.changed.emit()
        return AssignResult(True)

    def reset_all(self) -> None:
        for d in DEFINITIONS:
            self._bindings[d.id] = [parse(s) for s in d.defaults]
        self._save()
        self.changed.emit()

    # ------------------------------------------------------------------ QAction binding
    def bind_action(self, sid: str, action: QAction, tooltip: str | None = None) -> None:
        """Takes the action's shortcuts from this registry and updates them on change."""
        self._actions[sid] = (action, tooltip if tooltip is not None else action.text().replace("&", ""))
        self._apply(sid)

    def _apply(self, sid: str) -> None:
        entry = self._actions.get(sid)
        if entry is None:
            return
        action, base = entry
        action.setShortcuts(self._bindings[sid])
        action.setToolTip(f"{base} ({self.display(sid)})" if self._bindings[sid] else base)

    def _refresh_actions(self) -> None:
        for sid in self._actions:
            self._apply(sid)

    # ------------------------------------------------------------------ holding keys
    def is_held(self, sid: str) -> bool:
        return sid in self._held

    def note_key_press(self, ev: QKeyEvent) -> None:
        """Report every key press that reaches the canvas, so hold keys can be tracked.
        (No application-wide event filter: forwarding every event to Python is wasteful.)"""
        if not ev.isAutoRepeat():
            self._on_press(ev)

    def note_key_release(self, ev: QKeyEvent) -> None:
        if not ev.isAutoRepeat():
            self._on_release(ev)  # never consume the event: only observe it

    def _on_press(self, ev: QKeyEvent) -> None:
        if ev.modifiers() & (_CTRL | _ALT | _META):
            return
        for d in DEFINITIONS:
            if d.kind == HOLD and d.id not in self._held and self.matches(d.id, ev):
                self._held[d.id] = ev.key()
                self.holdChanged.emit(d.id, True)

    def _on_release(self, ev: QKeyEvent) -> None:
        for sid in [s for s, k in self._held.items() if k == ev.key()]:
            del self._held[sid]
            self.holdChanged.emit(sid, False)

    def release_all(self) -> None:
        for sid in list(self._held):
            del self._held[sid]
            self.holdChanged.emit(sid, False)

    # ------------------------------------------------------------------ persistence
    def _save(self) -> None:
        if self._settings is None:
            return
        overrides = {d.id: [portable(s) for s in self._bindings[d.id]]
                     for d in DEFINITIONS if not self.is_default(d.id)}
        if overrides:
            self._settings.setValue(SETTINGS_KEY, json.dumps(overrides, ensure_ascii=False))
        else:
            self._settings.remove(SETTINGS_KEY)
        self._settings.sync()

    def _load(self) -> None:
        if self._settings is None:
            return
        raw = self._settings.value(SETTINGS_KEY, "")
        try:
            data = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return
        if not isinstance(data, dict):
            return
        overridden: set[str] = set()
        for sid, values in data.items():
            if sid not in self._defs or not isinstance(values, list) or len(values) != 1 \
                    or not isinstance(values[0], str):
                continue
            seq = parse(values[0])
            if self.validate(sid, seq) is not None:
                continue
            self._bindings[sid] = [seq]
            overridden.add(sid)
        self._drop_conflicts(overridden)

    def _drop_conflicts(self, overridden: Iterable[str]) -> None:
        """Hand-edited records must not leave one key on two actions:
        conflicting assignments return to their defaults."""
        overridden = set(overridden)
        while True:
            owners: dict[str, list[str]] = {}
            for d in DEFINITIONS:
                for s in self._bindings[d.id]:
                    owners.setdefault(portable(s), []).append(d.id)
            dup = [ids for ids in owners.values() if len(set(ids)) > 1]
            if not dup:
                return
            changed = False
            for ids in dup:
                for sid in set(ids) & overridden:
                    self._bindings[sid] = [parse(s) for s in self._defs[sid].defaults]
                    overridden.discard(sid)
                    changed = True
            if not changed:
                return
