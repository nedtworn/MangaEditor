"""Phase 8: shortcuts and interface behavior."""
from collections import Counter

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest

from mangaeditor.ui.main_window import MainWindow
from mangaeditor.ui.tools import Tool

from conftest import make_settings, open_window


@pytest.fixture
def window(tmp_path, manga_files):
    w = open_window(tmp_path, manga_files["png"])
    yield w
    w.close()


def test_required_shortcuts_exist_and_do_not_conflict(window):
    seqs = Counter()
    for a in window.actions():
        for s in a.shortcuts():
            seqs[s.toString()] += 1
    assert [k for k, n in seqs.items() if n > 1] == []
    required = {"Ctrl+Z": window.act_undo, "Ctrl+Y": window.act_redo, "Ctrl+S": window.act_save,
                "Ctrl+O": window.act_open, "Ctrl+N": window.act_new,
                "Ctrl+T": window.tool_actions[Tool.TEXT], "B": window.tool_actions[Tool.BRUSH],
                "E": window.tool_actions[Tool.ERASER], "I": window.tool_actions[Tool.EYEDROPPER]}
    for key, action in required.items():
        assert QKeySequence(key) in action.shortcuts(), key


def test_typing_in_panel_field_does_not_switch_tools(window):
    window.tools.set_tool(Tool.TEXT)
    spin = window.text_panel.size_spin
    spin.setFocus()
    line = spin.lineEdit()
    QTest.keyClick(line, Qt.Key.Key_B)
    QTest.keyClick(line, Qt.Key.Key_E)
    QTest.keyClick(line, Qt.Key.Key_I)
    assert window.tools.tool == Tool.TEXT


def test_space_types_while_editing_but_pans_otherwise(window):
    view = window.canvas
    window.tools.set_tool(Tool.TEXT)
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     view.mapFromScene(QPointF(400, 600)))
    QTest.keyClicks(view, "a b")
    assert window.scene_.editing_item.data.text == "a b"
    assert not view._space_down
    QTest.keyClick(view, Qt.Key.Key_Escape)
    QTest.keyPress(view, Qt.Key.Key_Space)
    assert view._space_down
    QTest.keyRelease(view, Qt.Key.Key_Space)
    assert not view._space_down


def test_actions_safe_during_text_editing(window):
    """Save / merge / tab switch during editing does not lose what was typed."""
    view = window.canvas
    window.tools.set_tool(Tool.TEXT)
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     view.mapFromScene(QPointF(400, 600)))
    QTest.keyClicks(view, "Kaydedilecek")
    QTest.keyClick(window, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    assert [t.text for t in window.page.texts] == ["Kaydedilecek"]
    assert not window.project.is_dirty
    QTest.keyClick(view, Qt.Key.Key_Return)  # edit again
    QTest.keyClicks(view, "!")
    window.merge_page()
    assert window.page.texts == ()
    window.undo()
    assert [t.text for t in window.page.texts] == ["Kaydedilecek!"]


def test_welcome_screen_without_project(tmp_path, qapp):
    w = MainWindow(settings=make_settings(tmp_path))
    w.show()
    assert w.center_stack.currentWidget() is w.welcome
    assert not w.tools_toolbar.isVisible()
    assert not w.act_save.isEnabled() and not w.act_merge.isEnabled()
    w.close()
