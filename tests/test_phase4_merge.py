"""Phase 4: Merge Page (text + paint → one raster layer)."""
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from mangaeditor.core.commands import AddTextCommand, MergePageCommand
from mangaeditor.core.compose import compose_page
from mangaeditor.core.page import PageDocument
from mangaeditor.core.stroke import BRUSH, ERASER, StrokeSession
from mangaeditor.core.text_data import TextData
from mangaeditor.ui.main_window import MainWindow
from mangaeditor.ui.tools import Tool

from conftest import make_manga_image, open_window


def max_diff(a, b):
    assert a.size() == b.size()
    worst = 0
    for y in range(0, a.height(), 3):
        for x in range(0, a.width(), 3):
            ca, cb = a.pixelColor(x, y), b.pixelColor(x, y)
            worst = max(worst, abs(ca.red() - cb.red()), abs(ca.green() - cb.green()), abs(ca.blue() - cb.blue()))
    return worst


def stroke(page, mode, pts, size=30, color=QColor(255, 255, 255)):
    s = StrokeSession(page, mode, size, color)
    for p in pts:
        s.add_point(QPointF(*p))
    page.undo_stack.push(s.finish())


@pytest.fixture
def page(qapp):
    p = PageDocument.from_image(make_manga_image(), name="p")
    stroke(p, BRUSH, [(170, 230), (430, 230)], size=40)  # clean up the original text
    texts = [
        TextData(id="a", text="Bu bir\nmanga", x=170, y=150, width=260, height=150, font_size=36, color="#ff102030"),
        TextData(id="b", text="GÜM!", x=380, y=550, width=300, height=150, font_size=90, rotation=-20,
                 color="#ffd02020", stroke_enabled=True, stroke_width=6, shadow_enabled=True,
                 shadow_color="#80000000"),
    ]
    for t in texts:
        p.undo_stack.push(AddTextCommand(p, t))
    return p


def test_merge_produces_identical_image(page):
    original = page.original.copy()
    before = compose_page(page)
    page.undo_stack.push(MergePageCommand(page))
    assert page.texts == ()  # the texts are no longer separate objects
    after = compose_page(page)
    assert max_diff(before, after) <= 2  # the look is preserved exactly
    assert page.original == original  # the original image did not change
    # The text pixels are now in the paint layer
    assert page.paint.pixelColor(300, 225).alpha() == 255


def test_paint_and_erase_on_merged_text(page):
    page.undo_stack.push(MergePageCommand(page))
    # brush over the area of the 'GÜM!' text
    stroke(page, BRUSH, [(430, 625), (630, 625)], size=60, color=QColor(0, 200, 0))
    assert compose_page(page).pixelColor(530, 625) == QColor(0, 200, 0)
    # The eraser also removes the merged text: the original underneath is revealed
    stroke(page, ERASER, [(200, 225), (400, 225)], size=20)
    assert compose_page(page).pixelColor(300, 225) == page.original.pixelColor(300, 225)


def test_merge_undo_redo(page):
    before = compose_page(page)
    paint_before = page.paint.copy()
    page.undo_stack.push(MergePageCommand(page))
    stroke(page, BRUSH, [(430, 625), (630, 625)], size=60, color=QColor(0, 200, 0))
    page.undo_stack.undo()  # brush
    page.undo_stack.undo()  # merge
    assert [t.id for t in page.texts] == ["a", "b"]  # the texts are editable again
    assert page.paint == paint_before
    assert max_diff(before, compose_page(page)) == 0
    page.undo_stack.redo()
    assert page.texts == ()
    assert max_diff(before, compose_page(page)) <= 2


# ---------------------------------------------------------------- interface
def test_merge_via_ui_then_brush_over_text_and_ctrl_z(qapp, manga_files, tmp_path):
    w = open_window(tmp_path, manga_files["png"])
    w.canvas.actual_size()
    w.canvas.centerOn(400, 500)
    page = w.page
    page.undo_stack.push(AddTextCommand(page, TextData(id="t", text="METIN", x=250, y=450, width=300,
                                                       height=100, font_size=60)))
    w.tools.set_tool(Tool.TEXT)
    w.scene_.text_items["t"].setSelected(True)
    w.act_merge.trigger()
    assert page.texts == () and not w.scene_.text_items
    # Paint over the text with the brush (it works directly now that there is no text object)
    QTest.keyClick(w, Qt.Key.Key_B)
    w.tools.set_brush_color(QColor(0, 0, 255))
    v = w.canvas
    a, b = v.mapFromScene(QPointF(260, 500)), v.mapFromScene(QPointF(540, 500))
    QTest.mousePress(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
    QTest.mouseMove(v.viewport(), QPoint((a.x() + b.x()) // 2, a.y()))
    QTest.mouseRelease(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
    assert page.paint.pixelColor(400, 500) == QColor(0, 0, 255)
    QTest.keyClick(w, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)  # undo the brush
    QTest.keyClick(w, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)  # undo the merge
    assert [t.id for t in page.texts] == ["t"]
    assert "t" in w.scene_.text_items
    w.close()


def test_merge_without_texts_is_noop(qapp, manga_files, tmp_path):
    w = open_window(tmp_path, manga_files["png"])
    w.act_merge.trigger()
    assert w.page.undo_stack.count() == 0
    w.close()
