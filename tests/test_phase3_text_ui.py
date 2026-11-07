"""Phase 3b: text tool (with real mouse/keyboard events) and external fonts."""
import pytest
from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtTest import QTest

from mangaeditor.core.compose import compose_page
from mangaeditor.core.fonts import FontLoadError, FontManager
from mangaeditor.core.text_layout import TextLayout
from mangaeditor.ui.main_window import MainWindow  # noqa: F401
from mangaeditor.ui.tools import Tool

from conftest import make_otf, make_ttf, open_window

L = Qt.MouseButton.LeftButton
NM = Qt.KeyboardModifier.NoModifier


@pytest.fixture
def window(qapp, manga_files, tmp_path):
    w = open_window(tmp_path, manga_files["png"], (1300, 900))
    w.canvas.actual_size()
    w.canvas.centerOn(400, 500)
    w.tools.set_text_defaults(w.tools.text_defaults.with_(font_family="Arial", font_size=32))
    qapp.processEvents()
    yield w
    w.close()


def type_unicode(widget, text):
    """QTest.keyClicks crashes on non-ASCII characters, so send the Turkish characters
    as text key events, the way a real keyboard produces them."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication

    for ch in text:
        for t in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(widget, QKeyEvent(t, 0, NM, ch))


def vpos(view, x, y) -> QPoint:
    return view.mapFromScene(QPointF(x, y))


def drag(view, a: QPoint, b: QPoint, steps=8, mods=NM):
    vp = view.viewport()
    QTest.mousePress(vp, L, mods, a)
    for i in range(1, steps + 1):
        QTest.mouseMove(vp, QPoint(round(a.x() + (b.x() - a.x()) * i / steps),
                                   round(a.y() + (b.y() - a.y()) * i / steps)))
    QTest.mouseRelease(vp, L, mods, b)


def create_text(window, x, y, typed_lines):
    view = window.canvas
    QTest.keyClick(window, Qt.Key.Key_T, Qt.KeyboardModifier.ControlModifier)
    assert window.tools.tool == Tool.TEXT
    QTest.mouseClick(view.viewport(), L, NM, vpos(view, x, y))
    scene = window.scene_
    assert scene.editing_item is not None and scene.editing_item.pending_new
    for i, line in enumerate(typed_lines):
        if i:
            QTest.keyClick(view, Qt.Key.Key_Return)
        if line.isascii():
            QTest.keyClicks(view, line)  # goes through the shortcut path (a tool shortcut must not fire)
        else:
            type_unicode(view, line)
    QTest.keyClick(view, Qt.Key.Key_Escape)
    assert scene.editing_item is None
    return window.page.texts[-1]


def test_create_text_by_typing_and_shortcuts_do_not_fire(window):
    data = create_text(window, 300, 600, ["Bu bir", "manga"])
    assert data.text == "Bu bir\nmanga"
    assert window.tools.tool == Tool.TEXT  # typing 'b', 'i', 'e' did not change the tool
    # Turkish characters
    view = window.canvas
    item = window.scene_.text_items[data.id]
    QTest.keyClick(view, Qt.Key.Key_Return)  # edit the selected text
    assert window.scene_.editing_item is item
    QTest.keyClick(view, Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier)
    type_unicode(view, " şğüöçıİ")
    QTest.keyClick(view, Qt.Key.Key_Escape)
    assert window.page.text(data.id).text == "Bu bir\nmanga şğüöçıİ"


def test_text_creation_undo_redo(window):
    data = create_text(window, 300, 600, ["Merhaba"])
    assert len(window.page.texts) == 1
    QTest.keyClick(window, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert len(window.page.texts) == 0 and not window.scene_.text_items
    QTest.keyClick(window, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
    assert window.page.text(data.id).text == "Merhaba"


def test_empty_new_text_leaves_nothing(window):
    view = window.canvas
    window.tools.set_tool(Tool.TEXT)
    QTest.mouseClick(view.viewport(), L, NM, vpos(view, 300, 600))
    QTest.keyClick(view, Qt.Key.Key_Escape)
    assert window.page.texts == () and not window.scene_.text_items
    assert not window.act_undo.isEnabled()


def test_editing_backspace_and_inline_undo(window):
    data = create_text(window, 300, 600, ["Merhaba dünya"])
    view = window.canvas
    QTest.keyClick(view, Qt.Key.Key_Return)
    QTest.keyClick(view, Qt.Key.Key_Backspace, Qt.KeyboardModifier.ControlModifier)  # kelime sil
    assert window.scene_.editing_item.data.text == "Merhaba "
    QTest.keyClick(view, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)  # undo inside the edit
    assert window.scene_.editing_item.data.text == "Merhaba dünya"
    QTest.keyClick(view, Qt.Key.Key_Escape)
    assert window.page.text(data.id).text == "Merhaba dünya"


def handle_view_pos(window, item, name) -> QPoint:
    return window.canvas.mapFromScene(item.mapToScene(item.handle_points()[name]))


def test_resize_keeps_manual_breaks_and_reflows_auto(window):
    data = create_text(window, 400, 500, ["Bu bir", "manga"])
    item = window.scene_.text_items[data.id]
    assert item.isSelected()
    drag(window.canvas, handle_view_pos(window, item, "e"), handle_view_pos(window, item, "e") + QPoint(250, 0))
    new = window.page.text(data.id)
    assert new.width > data.width + 200
    lay = TextLayout(new)
    assert [lay.line_text(i) for i in range(len(lay.lines))] == ["Bu bir", "manga"]  # manuel korunur

    # Long automatically wrapped text: widening it reduces the number of lines.
    long = create_text(window, 400, 900, ["Bu oldukça uzun bir manga cümlesidir"])
    item2 = window.scene_.text_items[long.id]
    before_lines = len(TextLayout(window.page.text(long.id)).lines)
    assert before_lines >= 2
    drag(window.canvas, handle_view_pos(window, item2, "e"), handle_view_pos(window, item2, "e") + QPoint(400, 0))
    after = window.page.text(long.id)
    assert len(TextLayout(after).lines) < before_lines
    assert "\n" not in after.text


def test_move_and_rotate_text(window):
    data = create_text(window, 400, 500, ["Taşı"])
    item = window.scene_.text_items[data.id]
    center = window.canvas.mapFromScene(QPointF(data.x + data.width / 2, data.y + data.height / 2))
    drag(window.canvas, center, center + QPoint(60, 40))
    moved = window.page.text(data.id)
    assert moved.x == pytest.approx(data.x + 60, abs=1.5)
    assert moved.y == pytest.approx(data.y + 40, abs=1.5)
    # drag the rotation handle to the right of the center → about 90°
    rot = handle_view_pos(window, item, "rot")
    c = window.canvas.mapFromScene(QPointF(moved.x + moved.width / 2, moved.y + moved.height / 2))
    drag(window.canvas, rot, c + QPoint(150, 0))
    rotated = window.page.text(data.id)
    assert rotated.rotation == pytest.approx(90, abs=3)
    # each interaction is one undo step
    window.undo()
    assert window.page.text(data.id).rotation == 0
    window.undo()
    assert window.page.text(data.id).x == pytest.approx(data.x)


def test_brush_does_not_touch_texts(window):
    data = create_text(window, 400, 500, ["Yazı"])
    QTest.keyClick(window, Qt.Key.Key_B)
    assert window.tools.tool == Tool.BRUSH
    view = window.canvas
    drag(view, vpos(view, data.x - 20, data.y + data.height / 2),
         vpos(view, data.x + data.width + 20, data.y + data.height / 2))
    assert window.page.text(data.id) == data  # the text was not moved or changed
    assert window.page.paint.pixelColor(int(data.x + data.width / 2), int(data.y + data.height / 2)).alpha() == 255


def test_panel_changes_selected_text_and_defaults(window):
    data = create_text(window, 400, 500, ["Stil"])
    panel = window.text_panel
    panel.size_spin.setValue(48)
    panel.stroke_box.setChecked(True)
    panel.bold_btn.setChecked(True)
    panel.h_group.buttons()[0].click()  # Sol
    t = window.page.text(data.id)
    assert (t.font_size, t.stroke_enabled, t.bold, t.align_h) == (48, True, True, "left")
    assert window.tools.text_defaults.font_size == 48  # the next texts start with the same style
    # consecutive changes made with a slider merge into one step
    count = window.page.undo_stack.count()
    panel.size_spin.setValue(50)
    panel.size_spin.setValue(52)
    assert window.page.undo_stack.count() == count + 1
    window.undo()
    assert window.page.text(data.id).font_size == 48


def test_external_ttf_and_otf_fonts(window, tmp_path):
    ttf, otf = tmp_path / "MangaTestTTF.ttf", tmp_path / "MangaTestOTF.otf"
    make_ttf(ttf, "Manga Test TTF")
    make_otf(otf, "Manga Test OTF")
    assert "Manga Test TTF" not in QFontDatabase.families()
    assert "Manga Test OTF" not in QFontDatabase.families()
    fams_t = window.fonts.import_font(ttf, None)
    fams_o = window.fonts.import_font(otf, None)
    assert fams_t == ["Manga Test TTF"] and fams_o == ["Manga Test OTF"]
    assert "Manga Test OTF" in QFontDatabase.families()

    data = create_text(window, 400, 500, ["AB"])
    window._on_text_field_edited("font_family", "Manga Test OTF")
    t = window.page.text(data.id)
    assert t.font_family == "Manga Test OTF"
    # The 'A' and 'B' in the OTF are filled boxes: the bounding box of the dark pixels is almost
    # completely filled. Arial 'AB' is made of thin lines, so its fill ratio is low.
    def fill_ratio(text_data):
        window.page.replace_text(text_data)
        r = QRect(int(text_data.x), int(text_data.y), int(text_data.width), int(text_data.height))
        img = compose_page(window.page, r)
        dark = [(x, y) for y in range(img.height()) for x in range(img.width())
                if img.pixelColor(x, y).lightness() < 60]
        xs, ys = [p[0] for p in dark], [p[1] for p in dark]
        bbox_area = (max(xs) - min(xs) + 1) * (max(ys) - min(ys) + 1)
        return len(dark) / bbox_area
    assert fill_ratio(t) > 0.75
    assert fill_ratio(t.with_(font_family="Arial")) < 0.5


def test_invalid_font_rejected(qapp, tmp_path):
    fm = FontManager()
    bad = tmp_path / "bozuk.ttf"
    bad.write_bytes(b"\x00\x01garbage")
    with pytest.raises(FontLoadError):
        fm.load_file(bad)
    with pytest.raises(FontLoadError):
        fm.load_file(tmp_path / "x.woff")
