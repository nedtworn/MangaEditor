"""Central shortcut system: assignment, conflict prevention, saving, defaults,
the Settings → Shortcuts window, and protection while editing text."""
import json
import re
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QSettings, Qt
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtTest import QTest

from mangaeditor.core.commands import AddTextCommand
from mangaeditor.core.text_data import TextData
from mangaeditor.ui import shortcuts as sc
from mangaeditor.ui.main_window import MainWindow
from mangaeditor.ui.shortcuts import SETTINGS_KEY, ShortcutRegistry, event_sequences, parse, portable
from mangaeditor.ui.shortcuts_dialog import ShortcutsDialog, capture_prompt
from mangaeditor.ui.tools import Tool

from conftest import make_settings, open_window

CTRL, SHIFT, ALT = (Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier,
                    Qt.KeyboardModifier.AltModifier)
NM = Qt.KeyboardModifier.NoModifier
L = Qt.MouseButton.LeftButton


def key_event(key, mods=NM, text="", release=False):
    t = QEvent.Type.KeyRelease if release else QEvent.Type.KeyPress
    return QKeyEvent(t, key, mods, text)


def seq(text: str) -> QKeySequence:
    return parse(text)


@pytest.fixture
def window(tmp_path, manga_files):
    w = open_window(tmp_path, manga_files["png"])
    w.canvas.actual_size()
    w.canvas.centerOn(400, 600)
    yield w
    w.project and w.project.discard_recovery()
    w.close()


@pytest.fixture
def reg(tmp_path, qapp):
    return ShortcutRegistry(make_settings(tmp_path))


# =============================================================== olaylardan kombinasyon
@pytest.mark.parametrize("key,mods,text,expected", [
    (Qt.Key.Key_B, NM, "b", "B"),
    (Qt.Key.Key_F, CTRL, "\x06", "Ctrl+F"),
    (Qt.Key.Key_E, SHIFT, "E", "Shift+E"),
    (Qt.Key.Key_S, CTRL | SHIFT, "\x13", "Ctrl+Shift+S"),
    (Qt.Key.Key_1, ALT, "", "Alt+1"),
    (Qt.Key.Key_Z, CTRL | ALT, "", "Ctrl+Alt+Z"),
    (Qt.Key.Key_Z, CTRL | ALT | SHIFT, "", "Ctrl+Alt+Shift+Z"),
    (Qt.Key.Key_Exclam, SHIFT, "!", "!"),  # Shift does not count when it was only used to type a symbol
    (Qt.Key.Key_BracketLeft, CTRL | ALT, "[", "["),  # a character typed with AltGr (Turkish keyboard)
    (Qt.Key.Key_Enter, NM, "\r", "Return"),  # Enter on the numeric keypad
    (Qt.Key.Key_Backtab, SHIFT, "", "Shift+Tab"),
    (Qt.Key.Key_Space, NM, " ", "Space"),
    (Qt.Key.Key_Delete, NM, "", "Del"),
])
def test_event_to_sequence(key, mods, text, expected):
    cands = event_sequences(key_event(key, mods, text))
    assert portable(cands[0]) == expected


def test_modifier_only_events_produce_no_sequence():
    for k in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_AltGr):
        assert event_sequences(key_event(k, CTRL)) == []


def test_altgr_char_also_matches_real_ctrl_alt_binding():
    cands = [portable(c) for c in event_sequences(key_event(Qt.Key.Key_BracketLeft, CTRL | ALT, "["))]
    assert cands == ["[", "Ctrl+Alt+["]


# =============================================================== registry
def test_defaults_are_unique_and_cover_every_action(reg, window):
    seen = {}
    for d in reg.definitions():
        for s in reg.sequences(d.id):
            assert not s.isEmpty()
            assert portable(s) not in seen, (d.id, seen.get(portable(s)))
            seen[portable(s)] = d.id
    # Every 'action' kind is really bound to a QAction, and its shortcuts match the registry
    for d in window.shortcuts.definitions():
        if d.kind == sc.ACTION:
            action, _ = window.shortcuts._actions[d.id]
            assert action.shortcuts() == window.shortcuts.sequences(d.id), d.id


def test_required_default_shortcuts_present(reg):
    want = {"edit.undo": "Ctrl+Z", "edit.redo": "Ctrl+Y", "file.save": "Ctrl+S", "file.open": "Ctrl+O",
            "file.new": "Ctrl+N", "tool.text": "Ctrl+T", "tool.brush": "B", "tool.eraser": "E",
            "tool.eyedropper": "I", "canvas.pan": "Space", "clone.source": "K", "tool.clone": "S"}
    for sid, text in want.items():
        assert portable(reg.sequences(sid)[0]) == text, sid


def test_no_hard_coded_shortcuts_left_in_ui_code():
    """Shortcuts come from one place: no fixed key checks may remain in the canvas and the main window."""
    root = Path(__file__).resolve().parents[1] / "mangaeditor" / "ui"
    for name in ("canvas_view.py", "main_window.py"):
        src = (root / name).read_text(encoding="utf-8")
        # Text-editing keys (Ctrl+A/C/V, Delete, Backspace...) are fixed and are not in the registry;
        # only this set, which is protected by ShortcutOverride, is excluded from the scan.
        src = re.sub(r"_EDIT_CTRL_KEYS = \{.*?\}", "", src, flags=re.S)
        for pat in (r"Key_Space", r"Key_BracketLeft", r"Key_BracketRight", r"Key_Delete", r"Key_Backspace",
                    r"Key_Return", r"Key_Enter", r"Key_K\b", r"setShortcut\(", r'QKeySequence\("'):
            assert not re.search(pat, src), f"{name}: sabit kısayol kalmış: {pat}"


def test_single_key_assignment_applies_to_menu_toolbar_and_tooltip(window):
    reg = window.shortcuts
    assert reg.assign(sc.TOOL_BRUSH, seq("Q")).ok
    assert window.tool_actions[Tool.BRUSH].shortcuts() == [seq("Q")]
    assert "(Q)" in window.tool_actions[Tool.BRUSH].toolTip()
    window.tools.set_tool(Tool.ERASER)
    QTest.keyClick(window, Qt.Key.Key_B)  # the old key no longer does anything
    assert window.tools.tool == Tool.ERASER
    QTest.keyClick(window, Qt.Key.Key_Q)
    assert window.tools.tool == Tool.BRUSH


@pytest.mark.parametrize("sid,text,key,mods,tool", [
    (sc.TOOL_BRUSH, "Ctrl+F", Qt.Key.Key_F, CTRL, Tool.BRUSH),
    (sc.TOOL_ERASER, "Shift+E", Qt.Key.Key_E, SHIFT, Tool.ERASER),
    (sc.TOOL_EYEDROPPER, "Ctrl+Shift+S", Qt.Key.Key_S, CTRL | SHIFT, Tool.EYEDROPPER),
    (sc.TOOL_CLONE, "Alt+1", Qt.Key.Key_1, ALT, Tool.CLONE),
    (sc.TOOL_TEXT, "Ctrl+Alt+Z", Qt.Key.Key_Z, CTRL | ALT, Tool.TEXT),
])
def test_modifier_combinations_assign_and_trigger(window, sid, text, key, mods, tool):
    reg = window.shortcuts
    res = reg.assign(sid, seq(text))
    assert res.ok, res.message
    other = Tool.TEXT if tool != Tool.TEXT else Tool.BRUSH
    window.tools.set_tool(other)
    QTest.keyClick(window, key, mods)
    assert window.tools.tool == tool
    # The same key WITHOUT the modifier does not trigger the action (unless it is another action's default)
    plain = reg.find_conflict(QKeySequence(key))
    if plain is None:
        window.tools.set_tool(other)
        QTest.keyClick(window, key, NM)
        assert window.tools.tool == other


def test_ctrl_a_and_ctrl_alt_z_style_combos_assignable(reg):
    for sid, text in ((sc.TOOL_ERASER, "Ctrl+A"), (sc.TOOL_CLONE, "Ctrl+Alt+Z"), (sc.PAGE_ADD, "Ctrl+Shift+A"),
                      (sc.FILE_QUIT, "Ctrl+Q")):
        assert reg.assign(sid, seq(text)).ok
        assert reg.display(sid).replace(" ", "") != "Atanmadı"


def test_modifier_alone_and_esc_cannot_be_assigned(reg):
    for text in ("Ctrl", "Shift", "Alt", "Meta"):
        assert reg.assign(sc.TOOL_BRUSH, seq(text)).ok is False
    for k in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt):
        res = reg.assign(sc.TOOL_BRUSH, QKeySequence(k))
        assert not res.ok and "tek başına" in res.message
    res = reg.assign(sc.TOOL_BRUSH, QKeySequence(Qt.Key.Key_Escape))
    assert not res.ok and "Esc" in res.message
    assert portable(reg.sequences(sc.TOOL_BRUSH)[0]) == "B"  # none was assigned


def test_hold_keys_must_be_plain_single_keys(reg):
    for text in ("Ctrl+K", "Shift+K", "Alt+Space"):
        res = reg.assign(sc.CLONE_SOURCE_HOLD, seq(text))
        assert not res.ok and "tek tuş" in res.message
    assert reg.assign(sc.CLONE_SOURCE_HOLD, seq("J")).ok


# =============================================================== conflict prevention
def test_same_shortcut_cannot_go_to_two_actions(reg):
    res = reg.assign(sc.TOOL_ERASER, seq("B"))  # B is the brush
    assert not res.ok
    assert res.conflict is not None and res.conflict.id == sc.TOOL_BRUSH
    assert "Fırça" in res.message and "atama yapılmadı" in res.message.lower()
    assert portable(reg.sequences(sc.TOOL_ERASER)[0]) == "E"  # the current shortcut was not lost
    assert portable(reg.sequences(sc.TOOL_BRUSH)[0]) == "B"
    # For every pair: no shortcut is found in two actions
    owners = {}
    for d in reg.definitions():
        for s in reg.sequences(d.id):
            owners.setdefault(portable(s), []).append(d.id)
    assert all(len(v) == 1 for v in owners.values())


@pytest.mark.parametrize("sid,text,owner", [
    (sc.TOOL_ERASER, "K", sc.CLONE_SOURCE_HOLD),  # with a hold key
    (sc.TOOL_CLONE, "]", sc.SIZE_UP),  # with a canvas-local key
    (sc.PAGE_ADD, "Ctrl+S", sc.FILE_SAVE),  # with a menu shortcut
    (sc.PAGE_ADD, "Ctrl+Shift+Z", sc.EDIT_REDO),  # with the second (alternate) shortcut
    (sc.PAN_HOLD, "S", sc.TOOL_CLONE),
    (sc.TEXT_EDIT, "Backspace", sc.TEXT_DELETE),
])
def test_conflicts_detected_across_kinds(reg, sid, text, owner):
    before = reg.sequences(sid)
    res = reg.assign(sid, seq(text))
    assert not res.ok and res.conflict.id == owner
    assert reg.sequences(sid) == before


def test_reassigning_own_shortcut_is_fine_and_swap_needs_two_steps(reg):
    assert reg.assign(sc.TOOL_BRUSH, seq("B")).ok  # its own shortcut: not a conflict
    assert not reg.assign(sc.TOOL_BRUSH, seq("E")).ok
    assert reg.assign(sc.TOOL_ERASER, seq("W")).ok
    assert reg.assign(sc.TOOL_BRUSH, seq("E")).ok  # E is free now
    assert portable(reg.sequences(sc.TOOL_ERASER)[0]) == "W"


def test_freed_default_becomes_available(reg):
    assert reg.assign(sc.TOOL_BRUSH, seq("Q")).ok
    assert reg.assign(sc.TOOL_ERASER, seq("B")).ok  # B is free now


# =============================================================== defaults, persistence
def test_reset_one_and_reset_all(window):
    reg = window.shortcuts
    reg.assign(sc.TOOL_BRUSH, seq("Q"))
    reg.assign(sc.FILE_SAVE, seq("Ctrl+Shift+S"))
    reg.assign(sc.CLONE_SOURCE_HOLD, seq("J"))
    assert not reg.all_default()
    res = reg.reset(sc.TOOL_BRUSH)
    assert res.ok and portable(reg.sequences(sc.TOOL_BRUSH)[0]) == "B" and not reg.is_default(sc.FILE_SAVE)
    reg.reset_all()
    assert reg.all_default()
    assert window.act_save.shortcuts() == [seq("Ctrl+S")]
    assert window.act_redo.shortcuts() == [seq("Ctrl+Y"), seq("Ctrl+Shift+Z")]  # the alternate shortcut is restored too
    assert "(Ctrl+S)" in window.act_save.toolTip()
    window.tools.set_tool(Tool.TEXT)
    QTest.keyClick(window, Qt.Key.Key_B)
    assert window.tools.tool == Tool.BRUSH
    assert not reg._settings.contains(SETTINGS_KEY)  # the record was cleared


def test_reset_one_blocked_when_default_is_taken(reg):
    reg.assign(sc.TOOL_BRUSH, seq("Q"))
    reg.assign(sc.TOOL_ERASER, seq("B"))  # the brush's old default
    res = reg.reset(sc.TOOL_BRUSH)
    assert not res.ok and "Silgi" in res.message
    assert portable(reg.sequences(sc.TOOL_BRUSH)[0]) == "Q"  # was not lost


def test_assignments_persist_across_restart(tmp_path, manga_files):
    settings = make_settings(tmp_path)
    w = open_window(tmp_path, manga_files["png"], settings=settings)
    w.shortcuts.assign(sc.TOOL_BRUSH, seq("Ctrl+F"))
    w.shortcuts.assign(sc.TOOL_ERASER, seq("Shift+E"))
    w.shortcuts.assign(sc.SIZE_UP, seq("."))
    w.shortcuts.assign(sc.CLONE_SOURCE_HOLD, seq("J"))
    w.project.discard_recovery()
    w.close()
    # New session (same settings file)
    fresh = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    w2 = MainWindow(settings=fresh)
    w2.show()
    QTest.qWaitForWindowExposed(w2)
    reg2 = w2.shortcuts
    assert [portable(s) for s in reg2.sequences(sc.TOOL_BRUSH)] == ["Ctrl+F"]
    assert [portable(s) for s in reg2.sequences(sc.SIZE_UP)] == ["."]
    assert [portable(s) for s in reg2.sequences(sc.CLONE_SOURCE_HOLD)] == ["J"]
    assert [portable(s) for s in reg2.sequences(sc.TOOL_CLONE)] == ["S"]  # the untouched ones keep their defaults
    w2.tools.set_tool(Tool.TEXT)
    QTest.keyClick(w2, Qt.Key.Key_F, CTRL)
    assert w2.tools.tool == Tool.BRUSH
    w2.tools.set_tool(Tool.TEXT)
    QTest.keyClick(w2, Qt.Key.Key_E, SHIFT)
    assert w2.tools.tool == Tool.ERASER
    QTest.keyClick(w2, Qt.Key.Key_E)  # the old E no longer selects the eraser
    assert w2.tools.tool == Tool.ERASER  # already the eraser: it did not switch to another tool
    w2.tools.set_tool(Tool.TEXT)
    QTest.keyClick(w2, Qt.Key.Key_E)
    assert w2.tools.tool == Tool.TEXT
    assert "J" in w2.side_panel.clone_panel.hint.text()  # the panel shows the new key
    w2.close()


def test_corrupt_or_conflicting_saved_data_is_ignored(tmp_path, qapp):
    for bad in ("{bozuk json", "[1,2]", json.dumps({"tool.brush": "B"}), json.dumps({"yok.id": ["Q"]}),
                json.dumps({"tool.brush": ["Ctrl"]}), json.dumps({"tool.brush": ["Esc"]}),
                json.dumps({"clone.source": ["Ctrl+K"]})):
        st = QSettings(str(tmp_path / "x.ini"), QSettings.Format.IniFormat)
        st.setValue(SETTINGS_KEY, bad)
        r = ShortcutRegistry(st)
        assert r.all_default(), bad
    # If a hand-edited record assigns the same key to two actions, both return to their defaults
    st = QSettings(str(tmp_path / "y.ini"), QSettings.Format.IniFormat)
    st.setValue(SETTINGS_KEY, json.dumps({"tool.brush": ["Q"], "tool.eraser": ["Q"], "tool.text": ["F"]}))
    r = ShortcutRegistry(st)
    assert portable(r.sequences(sc.TOOL_BRUSH)[0]) == "B" and portable(r.sequences(sc.TOOL_ERASER)[0]) == "E"
    assert portable(r.sequences(sc.TOOL_TEXT)[0]) == "F"  # the valid one is kept
    # A record that conflicts with a default: it returns to the default
    st.setValue(SETTINGS_KEY, json.dumps({"tool.brush": ["E"]}))
    r = ShortcutRegistry(st)
    assert portable(r.sequences(sc.TOOL_BRUSH)[0]) == "B" and portable(r.sequences(sc.TOOL_ERASER)[0]) == "E"


# =============================================================== old fixed keys do not break new assignments
def test_brush_size_keys_follow_assignment(window):
    reg = window.shortcuts
    window.tools.set_tool(Tool.BRUSH)
    window.tools.set_brush_size(40)
    window.canvas.setFocus()
    reg.assign(sc.SIZE_UP, seq("."))
    reg.assign(sc.SIZE_DOWN, seq(","))
    QTest.keyClick(window.canvas, Qt.Key.Key_BracketRight)  # old key
    assert window.tools.brush_size == 40
    QTest.keyClick(window.canvas, Qt.Key.Key_Period)
    assert window.tools.brush_size > 40
    big = window.tools.brush_size
    QTest.keyClick(window.canvas, Qt.Key.Key_Comma)
    assert window.tools.brush_size < big


def test_pan_hold_key_follows_assignment(window):
    view = window.canvas
    window.shortcuts.assign(sc.PAN_HOLD, seq("H"))
    view.setFocus()
    c0 = view.mapToScene(view.viewport().rect().center())

    def drag_with(key):
        QTest.keyPress(view, key)
        QTest.mousePress(view.viewport(), L, NM, QPoint(400, 400))
        QTest.mouseMove(view.viewport(), QPoint(340, 360))
        QTest.mouseRelease(view.viewport(), L, NM, QPoint(340, 360))
        QTest.keyRelease(view, key)

    window.tools.set_tool(Tool.ERASER)  # panning with the old shortcut (Space) must not happen: it would paint
    drag_with(Qt.Key.Key_Space)
    assert abs(view.mapToScene(view.viewport().rect().center()).x() - c0.x()) < 0.5
    drag_with(Qt.Key.Key_H)
    c1 = view.mapToScene(view.viewport().rect().center())
    assert abs((c1.x() - c0.x()) - 60) < 1.5 and abs((c1.y() - c0.y()) - 40) < 1.5


def test_clone_source_key_follows_assignment(window):
    view = window.canvas
    window.shortcuts.assign(sc.CLONE_SOURCE_HOLD, seq("J"))
    window.tools.set_tool(Tool.CLONE)
    view.setFocus()
    p = view.mapFromScene(QPointF(300, 500))
    QTest.keyPress(view, Qt.Key.Key_K)  # old key: must not pick a source
    QTest.mouseClick(view.viewport(), L, NM, p)
    QTest.keyRelease(view, Qt.Key.Key_K)
    assert window.scene_.clone_source is None
    QTest.keyPress(view, Qt.Key.Key_J)
    QTest.mouseClick(view.viewport(), L, NM, p)
    QTest.keyRelease(view, Qt.Key.Key_J)
    assert window.scene_.clone_source is not None
    assert window.page.paint_is_empty()


def send_enter(view):
    from PySide6.QtGui import QEnterEvent
    from PySide6.QtWidgets import QApplication

    pos = QPointF(100, 100)
    QApplication.sendEvent(view, QEnterEvent(pos, pos, view.mapToGlobal(pos.toPoint())))


def test_canvas_takes_focus_on_hover_so_hold_keys_work(window):
    """When the focus is on another widget, the canvas takes the focus when the mouse enters it, so K/Space reach it."""
    view = window.canvas
    window.tools.set_tool(Tool.CLONE)
    window.tabbar.setFocus()
    QTest.qWait(10)
    assert not view.hasFocus()
    send_enter(view)
    assert view.hasFocus()
    QTest.keyPress(view, Qt.Key.Key_K)
    assert window.shortcuts.is_held(sc.CLONE_SOURCE_HOLD)
    QTest.keyRelease(view, Qt.Key.Key_K)
    assert not window.shortcuts.is_held(sc.CLONE_SOURCE_HOLD)


def test_canvas_does_not_steal_focus_from_text_fields(window):
    line = window.text_panel.size_spin.lineEdit()
    window.tools.set_tool(Tool.TEXT)
    line.setFocus()
    QTest.qWait(10)
    assert line.hasFocus()
    send_enter(window.canvas)  # even if the mouse moves over the canvas while the user types a number, the focus stays
    assert line.hasFocus() and not window.canvas.hasFocus()


def test_held_keys_released_when_focus_is_lost(window):
    view = window.canvas
    view.setFocus()
    QTest.keyPress(view, Qt.Key.Key_Space)
    assert view._space_down
    window.tabbar.setFocus()  # focus left while a key was held: no release event arrives
    QTest.qWait(10)
    assert not window.shortcuts.is_held(sc.PAN_HOLD) and not view._space_down


def test_space_while_typing_text_is_a_space_not_pan(window):
    window.tools.set_tool(Tool.TEXT)
    d = make_text(window, "ab")
    window.scene_.start_editing(window.scene_.text_items[d.id])
    window.canvas.setFocus()
    QTest.keyClick(window.canvas, Qt.Key.Key_Space)
    assert window.scene_.editing_item.data.text.endswith("ab ") and not window.canvas._space_down
    QTest.keyClick(window.canvas, Qt.Key.Key_Escape)


def make_text(window, text="Merhaba", x=300, y=500):
    page = window.page
    d = TextData(id=f"t{len(page.texts)}", text=text, x=x, y=y, width=240, height=100, font_size=36)
    page.undo_stack.push(AddTextCommand(page, d))
    return d


def test_text_keys_follow_assignment(window):
    d = make_text(window)
    window.tools.set_tool(Tool.TEXT)
    scene, view = window.scene_, window.canvas
    scene.text_items[d.id].setSelected(True)
    view.setFocus()
    window.shortcuts.assign(sc.TEXT_EDIT, seq("F2"))
    window.shortcuts.assign(sc.TEXT_DELETE, seq("X"))
    QTest.keyClick(view, Qt.Key.Key_Return)  # old key: does not open editing
    assert scene.editing_item is None
    QTest.keyClick(view, Qt.Key.Key_Delete)  # old key: silmez
    QTest.keyClick(view, Qt.Key.Key_Backspace)
    assert window.page.text(d.id) is not None
    QTest.keyClick(view, Qt.Key.Key_F2)
    assert scene.editing_item is not None
    QTest.keyClick(view, Qt.Key.Key_Escape)
    scene.text_items[d.id].setSelected(True)
    QTest.keyClick(view, Qt.Key.Key_X)
    assert window.page.text(d.id) is None  # deleted with the newly assigned key


# =============================================================== protection while editing text
def start_editing(window):
    d = make_text(window, "abc def")
    window.tools.set_tool(Tool.TEXT)
    item = window.scene_.text_items[d.id]
    window.scene_.start_editing(item)
    window.canvas.setFocus()
    return d, item


def finish_editing(window):
    QTest.keyClick(window.canvas, Qt.Key.Key_Escape)
    assert window.scene_.editing_item is None


def test_plain_letter_shortcut_types_instead_of_switching_tool(window):
    window.shortcuts.assign(sc.TOOL_BRUSH, seq("Q"))
    d, item = start_editing(window)
    QTest.keyClick(window.canvas, Qt.Key.Key_Q)
    assert item.data.text.endswith("q") and window.tools.tool == Tool.TEXT
    finish_editing(window)
    QTest.keyClick(window, Qt.Key.Key_Q)  # the assignment works again after the edit ends
    assert window.tools.tool == Tool.BRUSH


def test_ctrl_a_with_assigned_tool_selects_text_instead(window):
    window.shortcuts.assign(sc.TOOL_ERASER, seq("Ctrl+A"))
    d, item = start_editing(window)
    QTest.keyClick(window.canvas, Qt.Key.Key_A, CTRL)
    assert (item.anchor, item.cursor) == (0, len(item.data.text))  # everything was selected
    assert window.tools.tool == Tool.TEXT  # did not switch to the eraser
    QTest.keyClick(window.canvas, Qt.Key.Key_C, CTRL)  # the other text keys also go to the text
    finish_editing(window)
    QTest.keyClick(window, Qt.Key.Key_A, CTRL)
    assert window.tools.tool == Tool.ERASER


def test_shift_letter_shortcut_types_capital(window):
    window.shortcuts.assign(sc.TOOL_CLONE, seq("Shift+E"))
    d, item = start_editing(window)
    QTest.keyClick(window.canvas, "E", SHIFT)  # with a capital 'E' as on a real keyboard
    assert item.data.text.endswith("E") and window.tools.tool == Tool.TEXT
    finish_editing(window)
    QTest.keyClick(window, Qt.Key.Key_E, SHIFT)
    assert window.tools.tool == Tool.CLONE


def test_alt_and_ctrl_alt_shortcuts_do_not_fire_while_editing(window):
    window.shortcuts.assign(sc.TOOL_BRUSH, seq("Alt+1"))
    window.shortcuts.assign(sc.TOOL_ERASER, seq("Ctrl+Alt+Z"))
    d, item = start_editing(window)
    QTest.keyClick(window.canvas, Qt.Key.Key_1, ALT)
    QTest.keyClick(window.canvas, Qt.Key.Key_Z, CTRL | ALT)
    assert window.tools.tool == Tool.TEXT
    finish_editing(window)
    QTest.keyClick(window, Qt.Key.Key_1, ALT)
    assert window.tools.tool == Tool.BRUSH
    window.tools.set_tool(Tool.TEXT)
    QTest.keyClick(window, Qt.Key.Key_Z, CTRL | ALT)
    assert window.tools.tool == Tool.ERASER


def test_file_shortcuts_still_work_while_editing_text(window):
    """While typing text, application shortcuts such as Ctrl+S still work (only the text keys are protected)."""
    window.shortcuts.assign(sc.FILE_SAVE, seq("Ctrl+Shift+S"))
    d, item = start_editing(window)
    QTest.keyClick(window.canvas, Qt.Key.Key_S, CTRL)  # no longer Save: it goes to neither the text nor anything else
    assert window.project.needs_save
    QTest.keyClick(window.canvas, Qt.Key.Key_S, CTRL | SHIFT)
    assert not window.project.needs_save  # yeni atama kaydetti
    assert window.scene_.editing_item is None or window.page.texts  # the typed text was not lost
    assert window.page.text(d.id) is not None


def test_assigned_letter_in_panel_field_does_not_fire(window):
    window.shortcuts.assign(sc.TOOL_BRUSH, seq("Q"))
    window.tools.set_tool(Tool.TEXT)
    line = window.text_panel.size_spin.lineEdit()
    line.setFocus()
    QTest.keyClick(line, Qt.Key.Key_Q)
    assert window.tools.tool == Tool.TEXT


# =============================================================== Settings → Shortcuts window
def test_settings_menu_opens_dialog(window, monkeypatch):
    opened = []
    monkeypatch.setattr(ShortcutsDialog, "exec", lambda self: opened.append(self) or 0)
    menus = {a.text(): a for a in window.menuBar().actions()}
    assert "Ayarlar" in menus
    entries = [a.text() for a in menus["Ayarlar"].menu().actions()]
    assert "Kısayollar…" in entries
    window.act_shortcuts.trigger()
    assert len(opened) == 1 and isinstance(opened[0], ShortcutsDialog)


@pytest.fixture
def dlg(window):
    d = ShortcutsDialog(window.shortcuts, window)
    d.show()
    QTest.qWait(10)
    yield d
    d.close()


def test_dialog_lists_every_action_with_its_shortcut(dlg, window):
    reg = window.shortcuts
    assert set(dlg._buttons) == {d.id for d in reg.definitions()}
    for sid, btn in dlg._buttons.items():
        assert btn.text() == reg.display(sid)
    assert dlg.capture_button(sc.TOOL_BRUSH).text() == "B"
    assert dlg.capture_button(sc.PAGE_ADD).text() == "Atanmadı"
    groups = [dlg.tree.topLevelItem(i).text(0) for i in range(dlg.tree.topLevelItemCount())]
    assert groups == reg.groups() and "Araçlar" in groups and "Metin" in groups


def test_click_enters_capture_mode_visibly_and_single_key_is_assigned(dlg, window):
    btn = dlg.capture_button(sc.TOOL_BRUSH)
    assert not btn.capturing
    QTest.mouseClick(btn, L)
    assert btn.capturing and btn.text() == capture_prompt()
    assert "ffb020" in btn.styleSheet()  # visibly shown
    QTest.keyClick(btn, Qt.Key.Key_Q)
    assert not btn.capturing and btn.text() == "Q" and btn.styleSheet() == ""
    assert portable(window.shortcuts.sequences(sc.TOOL_BRUSH)[0]) == "Q"
    assert "Q" in dlg.status.text()
    assert dlg.reset_button(sc.TOOL_BRUSH).isEnabled()  # reset is enabled on the changed row
    assert not dlg.reset_button(sc.TOOL_ERASER).isEnabled()


def test_dialog_multi_modifier_capture_with_live_preview(dlg, window):
    btn = dlg.capture_button(sc.FILE_SAVE)
    QTest.mouseClick(btn, L)
    QTest.keyPress(btn, Qt.Key.Key_Control)  # a modifier alone cannot be assigned; capturing continues
    assert btn.capturing and btn.text() == "Ctrl + …"
    QTest.keyPress(btn, Qt.Key.Key_Shift, CTRL)
    assert btn.capturing and btn.text() == "Ctrl + Shift + …"
    assert portable(window.shortcuts.sequences(sc.FILE_SAVE)[0]) == "Ctrl+S"  # not changed yet
    QTest.keyClick(btn, Qt.Key.Key_S, CTRL | SHIFT)
    assert not btn.capturing
    assert [portable(s) for s in window.shortcuts.sequences(sc.FILE_SAVE)] == ["Ctrl+Shift+S"]
    assert window.act_save.shortcuts() == [seq("Ctrl+Shift+S")]
    for text, sid, key, mods in (("Ctrl+F", sc.TOOL_BRUSH, Qt.Key.Key_F, CTRL), ("Shift+E", sc.TOOL_ERASER, Qt.Key.Key_E, SHIFT),
                                 ("Alt+1", sc.TOOL_CLONE, Qt.Key.Key_1, ALT), ("Ctrl+Alt+Z", sc.TOOL_TEXT, Qt.Key.Key_Z, CTRL | ALT)):
        b = dlg.capture_button(sid)
        QTest.mouseClick(b, L)
        QTest.keyClick(b, key, mods)
        assert portable(window.shortcuts.sequences(sid)[0]) == text


def test_dialog_esc_cancels_without_changes_and_keeps_dialog_open(dlg, window):
    btn = dlg.capture_button(sc.TOOL_ERASER)
    QTest.mouseClick(btn, L)
    QTest.keyClick(btn, Qt.Key.Key_Escape)
    assert not btn.capturing and btn.text() == "E"
    assert portable(window.shortcuts.sequences(sc.TOOL_ERASER)[0]) == "E"
    assert dlg.isVisible()  # Esc only cancels the assignment, it does not close the window
    assert "iptal" in dlg.status.text().lower()
    # Esc modifier'la birlikte de iptaldir; atanamaz
    QTest.mouseClick(btn, L)
    QTest.keyClick(btn, Qt.Key.Key_Escape, CTRL)
    assert btn.text() == "E" and not btn.capturing


def test_dialog_conflict_blocks_assignment_and_names_the_other_action(dlg, window):
    reg = window.shortcuts
    eraser = dlg.capture_button(sc.TOOL_ERASER)
    QTest.mouseClick(eraser, L)
    QTest.keyClick(eraser, Qt.Key.Key_B)  # B is the brush
    assert portable(reg.sequences(sc.TOOL_ERASER)[0]) == "E" and eraser.text() == "E"
    assert portable(reg.sequences(sc.TOOL_BRUSH)[0]) == "B"
    msg = dlg.status.text()
    assert "Fırça" in msg and "atanmış" in msg and "yapılmadı" in msg.lower()
    assert "ff7b7b" in dlg.status.styleSheet()  # hata rengi
    assert dlg.tree.currentItem() is dlg.row_item(sc.TOOL_BRUSH)  # the conflicting row is marked
    # Still works: B brush, E eraser (while the window is active; the main window's shortcuts are inactive while the shortcut window is open)
    assert window.tool_actions[Tool.BRUSH].shortcuts() == [seq("B")]
    assert window.tool_actions[Tool.ERASER].shortcuts() == [seq("E")]
    dlg.hide()
    window.activateWindow()
    QTest.qWait(30)
    window.tools.set_tool(Tool.TEXT)
    QTest.keyClick(window, Qt.Key.Key_B)
    assert window.tools.tool == Tool.BRUSH
    QTest.keyClick(window, Qt.Key.Key_E)
    assert window.tools.tool == Tool.ERASER
    # A conflict with a modifier and a conflict with a hold key are also blocked
    dlg.show()
    QTest.mouseClick(eraser, L)
    QTest.keyClick(eraser, Qt.Key.Key_S, CTRL)
    assert "Kaydet" in dlg.status.text() and eraser.text() == "E"
    QTest.mouseClick(eraser, L)
    QTest.keyClick(eraser, Qt.Key.Key_K)
    assert "Klon kaynağı" in dlg.status.text() and eraser.text() == "E"


def test_dialog_hold_key_with_modifier_is_rejected(dlg, window):
    btn = dlg.capture_button(sc.CLONE_SOURCE_HOLD)
    QTest.mouseClick(btn, L)
    QTest.keyClick(btn, Qt.Key.Key_K, CTRL)
    assert "tek tuş" in dlg.status.text() and btn.text() == "K"


def test_dialog_reset_one_and_all(dlg, window):
    reg = window.shortcuts
    for sid, key in ((sc.TOOL_BRUSH, Qt.Key.Key_Q), (sc.TOOL_ERASER, Qt.Key.Key_W)):
        b = dlg.capture_button(sid)
        QTest.mouseClick(b, L)
        QTest.keyClick(b, key)
    assert dlg.reset_all_btn.isEnabled()
    QTest.mouseClick(dlg.reset_button(sc.TOOL_BRUSH), L)
    assert dlg.capture_button(sc.TOOL_BRUSH).text() == "B"
    assert dlg.capture_button(sc.TOOL_ERASER).text() == "W"
    QTest.mouseClick(dlg.reset_all_btn, L)  # sahte onay "Evet" der
    assert reg.all_default() and dlg.capture_button(sc.TOOL_ERASER).text() == "E"
    assert not dlg.reset_all_btn.isEnabled()


def test_dialog_changes_persist_to_new_session(tmp_path, manga_files):
    settings = make_settings(tmp_path)
    w = open_window(tmp_path, manga_files["png"], settings=settings)
    d = ShortcutsDialog(w.shortcuts, w)
    d.show()
    b = d.capture_button(sc.EDIT_UNDO)
    QTest.mouseClick(b, L)
    QTest.keyClick(b, Qt.Key.Key_U, CTRL | ALT)
    d.close()
    w.project.discard_recovery()
    w.close()
    w2 = MainWindow(settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    assert [portable(s) for s in w2.shortcuts.sequences(sc.EDIT_UNDO)] == ["Ctrl+Alt+U"]
    assert w2.act_undo.shortcuts() == [seq("Ctrl+Alt+U")]
    d2 = ShortcutsDialog(w2.shortcuts, w2)
    assert d2.capture_button(sc.EDIT_UNDO).text() == "Ctrl+Alt+U"
    w2.close()
