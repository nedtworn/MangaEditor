"""Phase 2: brush, eraser and eyedropper (core logic and the UI with real mouse events)."""
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from mangaeditor.core.compose import compose_page, sample_color
from mangaeditor.core.page import PageDocument
from mangaeditor.core.stroke import BRUSH, ERASER, StrokeSession
from mangaeditor.ui.main_window import MainWindow  # noqa: F401
from mangaeditor.ui.tools import Tool

from conftest import make_manga_image, open_window


@pytest.fixture
def page(qapp):
    return PageDocument.from_image(make_manga_image(), name="test")


def rgb(c: QColor):
    return (c.red(), c.green(), c.blue())


def stroke(page, mode, points, size=20, color=QColor(255, 255, 255), opacity=1.0):
    s = StrokeSession(page, mode, size, color, opacity)
    for p in points:
        s.add_point(QPointF(*p))
    cmd = s.finish()
    if cmd is not None:
        page.undo_stack.push(cmd)
    return cmd


def test_brush_paints_real_pixels(page):
    original_before = page.original.copy()
    assert page.paint.pixelColor(300, 230).alpha() == 0
    stroke(page, BRUSH, [(150, 230), (450, 230)], size=30)
    c = page.paint.pixelColor(300, 230)
    assert c.alpha() == 255 and rgb(c) == (255, 255, 255)
    assert page.paint.pixelColor(300, 400).alpha() == 0  # outside the stroke nothing changed
    assert rgb(compose_page(page).pixelColor(300, 230)) == (255, 255, 255)
    assert page.original == original_before  # the original never changes


def test_brush_opacity_does_not_accumulate(page):
    # A semi-transparent stroke that crosses itself: the intersection must not get darker.
    stroke(page, BRUSH, [(100, 600), (300, 600), (300, 700), (200, 500)], size=20,
           color=QColor(0, 0, 0), opacity=0.5)
    a_single = page.paint.pixelColor(150, 600).alpha()
    a_cross = page.paint.pixelColor(250, 600).alpha()  # the line (200,500)->(300,700) crosses it
    assert a_single == pytest.approx(128, abs=2)
    assert a_cross == a_single


def test_eraser_removes_paint_and_reveals_original(page):
    stroke(page, BRUSH, [(150, 230), (450, 230)], size=30, color=QColor(0, 0, 255))
    stroke(page, ERASER, [(250, 230), (350, 230)], size=40)
    assert page.paint.pixelColor(300, 230).alpha() == 0
    assert page.paint.pixelColor(170, 230).alpha() == 255
    assert rgb(compose_page(page).pixelColor(300, 230)) == rgb(page.original.pixelColor(300, 230))


def test_stroke_undo_redo(page):
    stroke(page, BRUSH, [(10, 10), (100, 100)], size=10, color=QColor(255, 0, 0))
    assert page.paint.pixelColor(50, 50).alpha() == 255
    assert page.is_dirty
    page.undo_stack.undo()
    assert page.paint.pixelColor(50, 50).alpha() == 0
    page.undo_stack.redo()
    assert rgb(page.paint.pixelColor(50, 50)) == (255, 0, 0)
    page.undo_stack.undo()
    assert not page.is_dirty


def test_eyedropper_samples_visible_pixel(page):
    assert rgb(sample_color(page, QPointF(650, 950))) == (200, 30, 30)
    stroke(page, BRUSH, [(650, 950)], size=10, color=QColor(10, 200, 10))
    assert rgb(sample_color(page, QPointF(650, 950))) == (10, 200, 10)
    assert sample_color(page, QPointF(-5, 10)) is None


# ---------------------------------------------------------------- interface
@pytest.fixture
def window(qapp, manga_files, tmp_path):
    w = open_window(tmp_path, manga_files["png"], (1200, 900))
    w.canvas.actual_size()
    w.canvas.centerOn(400, 600)
    qapp.processEvents()
    yield w
    w.close()


def drag(view, a: QPointF, b: QPointF, steps=10):
    vp = view.viewport()
    pa = view.mapFromScene(a)
    pb = view.mapFromScene(b)
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pa)
    for i in range(1, steps + 1):
        t = i / steps
        QTest.mouseMove(vp, QPoint(round(pa.x() + (pb.x() - pa.x()) * t), round(pa.y() + (pb.y() - pa.y()) * t)))
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pb)


def test_ui_brush_eraser_eyedropper_with_mouse(window):
    view, page = window.canvas, window.page
    window.tools.set_brush_size(20)
    QTest.keyClick(window, Qt.Key.Key_B)
    assert window.tools.tool == Tool.BRUSH
    drag(view, QPointF(200, 400), QPointF(500, 400))
    assert page.paint.pixelColor(350, 400).alpha() == 255
    assert window.act_undo.isEnabled()

    QTest.keyClick(window, Qt.Key.Key_E)
    assert window.tools.tool == Tool.ERASER
    drag(view, QPointF(300, 400), QPointF(400, 400))
    assert page.paint.pixelColor(350, 400).alpha() == 0
    assert page.paint.pixelColor(220, 400).alpha() == 255

    QTest.keyClick(window, Qt.Key.Key_I)
    assert window.tools.tool == Tool.EYEDROPPER
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     view.mapFromScene(QPointF(650, 950)))
    assert rgb(window.tools.brush_color) == (200, 30, 30)
    assert window.tools.tool == Tool.EYEDROPPER  # the eyedropper stays selected after picking a color

    window.act_undo.trigger()  # silgiyi geri al
    assert page.paint.pixelColor(350, 400).alpha() == 255
    window.act_redo.trigger()
    assert page.paint.pixelColor(350, 400).alpha() == 0


def test_bracket_keys_change_size(window):
    window.tools.set_tool(Tool.BRUSH)
    window.tools.set_brush_size(20)
    window.canvas.setFocus()
    QTest.keyClick(window.canvas, Qt.Key.Key_BracketRight)
    assert window.tools.brush_size > 20
    QTest.keyClick(window.canvas, Qt.Key.Key_BracketLeft)
    QTest.keyClick(window.canvas, Qt.Key.Key_BracketLeft)
    assert window.tools.brush_size < 20
