"""Clone stamp: with real mouse / keyboard events (source picking, painting, zoom/pan,
undo, saving and reopening, visual feedback)."""
import hashlib

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest

from mangaeditor.core.compose import compose_page
from mangaeditor.ui.main_window import MainWindow
from mangaeditor.ui.tools import Tool

from conftest import make_settings, open_window

L = Qt.MouseButton.LeftButton
NM = Qt.KeyboardModifier.NoModifier


def make_pattern_png(path, w=800, h=600):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    for y in range(h):
        for x in range(w):
            img.setPixelColor(x, y, QColor((x * 5 + y * 3) % 256, (x * 11 + y * 7) % 256, (x * 3 + y * 13) % 256))
    assert img.save(str(path), "PNG")
    return path


@pytest.fixture
def pattern_png(tmp_path, qapp):
    (tmp_path / "kaynak").mkdir()
    return make_pattern_png(tmp_path / "kaynak" / "pattern.png")


@pytest.fixture
def window(tmp_path, pattern_png):
    w = open_window(tmp_path, pattern_png)
    w.canvas.actual_size()
    w.canvas.centerOn(400, 300)
    QTest.qWait(10)
    w.tools.set_tool(Tool.CLONE)
    yield w
    w.project and w.project.discard_recovery()
    w.close()


def rgb(c: QColor):
    return (c.red(), c.green(), c.blue())


def vp(view, x, y) -> QPoint:
    return view.mapFromScene(QPointF(x, y))


def sp(view, p: QPoint) -> QPointF:
    return view.scene_pos(QPointF(p))


def select_source(window, view_pos: QPoint):
    """Hold K and left-click (picks the source)."""
    view = window.canvas
    QTest.keyPress(view, Qt.Key.Key_K)
    QTest.mouseClick(view.viewport(), L, NM, view_pos)
    QTest.keyRelease(view, Qt.Key.Key_K)


def drag(view, points, steps=6):
    v = view.viewport()
    QTest.mousePress(v, L, NM, points[0])
    cur = points[0]
    for nxt in points[1:]:
        for i in range(1, steps + 1):
            QTest.mouseMove(v, QPoint(round(cur.x() + (nxt.x() - cur.x()) * i / steps),
                                      round(cur.y() + (nxt.y() - cur.y()) * i / steps)))
        cur = nxt
    QTest.mouseRelease(v, L, NM, points[-1])


def assert_cloned_at(page, scene_pt: QPointF, offset: QPoint):
    x, y = int(scene_pt.x()), int(scene_pt.y())
    d = page.paint.pixelColor(x, y)
    assert d.alpha() == 255, (x, y)
    assert rgb(d) == rgb(page.original.pixelColor(x + offset.x(), y + offset.y())), (x, y)


# ------------------------------------------------------------------ tool and panel
def test_clone_tool_in_toolbar_and_shortcut(window):
    assert Tool.CLONE in window.tool_actions
    assert window.tool_actions[Tool.CLONE] in window.tools_toolbar.actions()
    window.tools.set_tool(Tool.BRUSH)
    QTest.keyClick(window, Qt.Key.Key_S)
    assert window.tools.tool == Tool.CLONE and window.tool_actions[Tool.CLONE].isChecked()
    panel = window.side_panel.clone_panel
    assert window.side_panel.currentWidget() is panel
    assert "seçilmedi" in panel.status.text()


def test_brush_size_for_clone_is_independent_and_cursor_circle_matches(window):
    window.tools.set_brush_size(12)
    window.tools.set_eraser_size(34)
    panel = window.side_panel.clone_panel
    panel.size.spin.setValue(60)
    assert window.tools.clone_size == 60
    assert (window.tools.brush_size, window.tools.eraser_size) == (12, 34)
    assert window.canvas._brush_radius() == 30  # cursor circle = clone size / 2
    window.canvas.setFocus()
    QTest.keyClick(window.canvas, Qt.Key.Key_BracketRight)
    assert window.tools.clone_size > 60
    QTest.keyClick(window.canvas, Qt.Key.Key_BracketLeft)
    QTest.keyClick(window.canvas, Qt.Key.Key_BracketLeft)
    assert window.tools.clone_size < 60
    assert (window.tools.brush_size, window.tools.eraser_size) == (12, 34)


# ------------------------------------------------------------------ source selection
def test_cannot_paint_without_source(window):
    view, page = window.canvas, window.page
    assert window.scene_.clone_source is None
    drag(view, [vp(view, 300, 300), vp(view, 450, 320)])
    QTest.mouseClick(view.viewport(), L, NM, vp(view, 500, 400))
    assert page.paint_is_empty() and page.undo_stack.count() == 0
    assert not page.is_dirty
    assert "kaynak" in window.statusBar().currentMessage().lower()  # the user is told why


def test_k_click_sets_source_and_paints_nothing(window):
    view, page = window.canvas, window.page
    window.tools.set_clone_size(40)
    select_source(window, vp(view, 500, 200))
    src = window.scene_.clone_source
    expected = sp(view, vp(view, 500, 200))
    assert src is not None and abs(src.x() - expected.x()) < 0.01 and abs(src.y() - expected.y()) < 0.01
    assert window.scene_.clone_offset is None  # the relationship is fixed at the first stroke
    assert page.paint_is_empty() and page.undo_stack.count() == 0 and not page.is_dirty
    assert "seçildi" in window.statusBar().currentMessage()
    text = window.side_panel.clone_panel.status.text()
    assert "x 500" in text and "y 200" in text


def test_k_drag_does_not_paint_either(window):
    view, page = window.canvas, window.page
    QTest.keyPress(view, Qt.Key.Key_K)
    drag(view, [vp(view, 300, 300), vp(view, 500, 320)])
    QTest.keyRelease(view, Qt.Key.Key_K)
    assert page.paint_is_empty() and page.undo_stack.count() == 0
    assert window.scene_.clone_source is not None  # only the source was picked


def test_source_outside_image_is_rejected(window):
    view = window.canvas
    view.set_zoom(0.5)
    view.centerOn(400, 300)
    select_source(window, vp(view, -60, 300))  # left of the image (empty scene area)
    assert window.scene_.clone_source is None
    assert "içinde" in window.statusBar().currentMessage()


def test_normal_click_after_releasing_k_paints_and_new_source_resets_offset(window):
    view, page = window.canvas, window.page
    select_source(window, vp(view, 500, 200))
    QTest.mouseClick(view.viewport(), L, NM, vp(view, 200, 400))  # K released: now it paints
    assert page.undo_stack.count() == 1
    assert window.scene_.clone_offset is not None
    select_source(window, vp(view, 600, 100))
    assert window.scene_.clone_offset is None  # new source = new relationship
    assert page.undo_stack.count() == 1  # picking a source does not create an undo record


def test_source_is_per_page(tmp_path, pattern_png, qapp):
    other = make_pattern_png(tmp_path / "kaynak" / "diger.png", 600, 400)
    w = open_window(tmp_path, [pattern_png, other])
    w.tools.set_tool(Tool.CLONE)
    w.switch_to_page(0)
    w.canvas.actual_size()
    select_source(w, w.canvas.mapFromScene(QPointF(300, 200)))
    assert w.scene_.clone_source is not None
    w.switch_to_page(1)
    assert w.scene_.clone_source is None  # another page's source is not valid on this page
    assert "seçilmedi" in w.side_panel.clone_panel.status.text()
    w.switch_to_page(0)
    assert w.scene_.clone_source is not None and "x 300" in w.side_panel.clone_panel.status.text()
    w.project.discard_recovery()
    w.close()


# ------------------------------------------------------------------ klonlama
def test_drag_transfers_source_pixels_exactly(window):
    view, page = window.canvas, window.page
    window.tools.set_clone_size(30)
    select_source(window, vp(view, 500, 150))
    t1, t2, t3 = vp(view, 200, 400), vp(view, 320, 430), vp(view, 330, 520)
    drag(view, [t1, t2, t3])
    off = window.scene_.clone_offset
    s, a = window.scene_.clone_source, sp(view, t1)
    assert abs(off.x() - (s.x() - a.x())) <= 0.5 and abs(off.y() - (s.y() - a.y())) <= 0.5
    for (p, q) in ((t1, t2), (t2, t3)):
        for i in range(0, 11):  # continuous along the line
            f = i / 10
            assert_cloned_at(page, sp(view, QPoint(round(p.x() + (q.x() - p.x()) * f),
                                                   round(p.y() + (q.y() - p.y()) * f))), off)
    # Nothing was painted far from the cursor
    assert page.paint.pixelColor(700, 100).alpha() == 0 and page.paint.pixelColor(100, 550).alpha() == 0
    assert page.undo_stack.count() == 1  # one drag = one undo step


def test_relationship_kept_during_drag_and_across_strokes(window):
    view, page = window.canvas, window.page
    select_source(window, vp(view, 500, 150))
    drag(view, [vp(view, 200, 300), vp(view, 260, 320)])
    off = QPoint(window.scene_.clone_offset)
    drag(view, [vp(view, 150, 450), vp(view, 250, 470)])  # second stroke, at a different place
    assert window.scene_.clone_offset == off  # aligned: the relationship is kept between strokes too
    assert_cloned_at(page, sp(view, vp(view, 150, 450)), off)
    assert_cloned_at(page, sp(view, vp(view, 250, 470)), off)
    assert page.undo_stack.count() == 2


@pytest.mark.parametrize("size", [8, 25, 70])
def test_brush_sizes_on_canvas(window, size):
    view, page = window.canvas, window.page
    window.tools.set_clone_size(size)
    select_source(window, vp(view, 600, 100))
    QTest.mouseClick(view.viewport(), L, NM, vp(view, 300, 400))
    xs = [x for x in range(800) for y in (400,) if page.paint.pixelColor(x, y).alpha() >= 128]
    assert abs((max(xs) - min(xs) + 1) - size) <= 3  # the thickness matches the brush size


@pytest.mark.parametrize("zoom", [0.5, 1.0, 2.0, 4.0])
def test_coordinates_correct_at_any_zoom(window, zoom):
    view, page = window.canvas, window.page
    window.tools.set_clone_size(24)
    view.set_zoom(zoom)
    view.centerOn(400, 300)
    QTest.qWait(10)
    assert view.zoom() == pytest.approx(zoom)
    vS, vT1, vT2 = vp(view, 520, 180), vp(view, 300, 330), vp(view, 360, 330)
    select_source(window, vS)
    S = window.scene_.clone_source
    assert abs(S.x() - 520) <= 1 / zoom + 1 and abs(S.y() - 180) <= 1 / zoom + 1  # the clicked image point
    drag(view, [vT1, vT2], steps=10)
    off = window.scene_.clone_offset
    T1 = sp(view, vT1)
    # The pixel painted on the target is the pixel of the source that was clicked
    assert abs(T1.x() + off.x() - S.x()) <= 0.5 and abs(T1.y() + off.y() - S.y()) <= 0.5
    assert_cloned_at(page, T1, off)
    assert_cloned_at(page, sp(view, vT2), off)
    assert rgb(page.paint.pixelColor(int(T1.x()), int(T1.y()))) == rgb(page.original.pixelColor(int(S.x()), int(S.y())))
    # Painting happens under the cursor, not elsewhere
    far = QPointF(T1.x() + 120, T1.y() + 120)
    assert page.paint.pixelColor(int(far.x()), int(far.y())).alpha() == 0


def test_pan_between_source_and_paint_keeps_coordinates(window):
    view, page = window.canvas, window.page
    window.tools.set_clone_size(24)
    view.set_zoom(2.0)
    view.centerOn(400, 300)
    QTest.qWait(10)
    select_source(window, vp(view, 450, 250))
    S = QPointF(window.scene_.clone_source)
    # Pan the page with Space + drag
    z0 = view.zoom()
    c0 = view.mapToScene(view.viewport().rect().center())
    QTest.keyPress(view, Qt.Key.Key_Space)
    QTest.mousePress(view.viewport(), L, NM, QPoint(500, 400))
    QTest.mouseMove(view.viewport(), QPoint(380, 330))
    QTest.mouseRelease(view.viewport(), L, NM, QPoint(380, 330))
    QTest.keyRelease(view, Qt.Key.Key_Space)
    c1 = view.mapToScene(view.viewport().rect().center())
    assert view.zoom() == z0 and abs((c1.x() - c0.x()) - 60) <= 1.5 and abs((c1.y() - c0.y()) - 35) <= 1.5
    assert window.page.paint_is_empty() and page.undo_stack.count() == 0  # panning did not paint
    assert window.scene_.clone_source == S  # the source is fixed to the page, not the screen
    vT = vp(view, 430, 300)
    drag(view, [vT, vp(view, 470, 310)])
    T = sp(view, vT)
    off = window.scene_.clone_offset
    assert abs(T.x() + off.x() - S.x()) <= 0.5 and abs(T.y() + off.y() - S.y()) <= 0.5  # still the same source point
    assert_cloned_at(page, T, off)
    assert rgb(page.paint.pixelColor(int(T.x()), int(T.y()))) == rgb(page.original.pixelColor(int(S.x()), int(S.y())))


def test_stays_safe_near_image_borders_and_with_source_off_page(window):
    view, page = window.canvas, window.page
    window.tools.set_clone_size(60)
    view.set_zoom(0.5)
    view.centerOn(400, 300)
    QTest.qWait(10)
    select_source(window, vp(view, 780, 20))  # source near the top-right corner
    drag(view, [vp(view, 10, 580), vp(view, 120, 590), vp(view, -30, 640)])  # at the bottom-left edge; it also overflows outside
    assert page.paint.size() == page.original.size()
    window.undo()
    assert page.paint_is_empty()


# ------------------------------------------------------------------ geri al / yinele, kaydet
def test_undo_redo_via_shortcuts(window):
    view, page = window.canvas, window.page
    select_source(window, vp(view, 500, 150))
    drag(view, [vp(view, 200, 300), vp(view, 300, 320), vp(view, 320, 400)])
    after = page.paint.copy()
    assert not page.paint_is_empty()
    QTest.keyClick(window, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert page.paint_is_empty() and not page.is_dirty
    QTest.keyClick(window, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
    assert page.paint == after
    assert window.act_undo.toolTip().startswith("Geri al: Klonlama")


def test_brush_and_eraser_unaffected_by_clone(window):
    view, page = window.canvas, window.page
    select_source(window, vp(view, 500, 150))
    drag(view, [vp(view, 200, 300), vp(view, 300, 320)])
    clone_state = page.paint.copy()
    QTest.keyClick(window, Qt.Key.Key_B)
    window.tools.set_brush_color(QColor(0, 0, 255))
    window.tools.set_brush_size(20)
    drag(view, [vp(view, 400, 500), vp(view, 500, 500)])
    assert page.paint.pixelColor(450, 500) == QColor(0, 0, 255)
    QTest.keyClick(window, Qt.Key.Key_E)
    drag(view, [vp(view, 410, 500), vp(view, 490, 500)])
    assert page.paint.pixelColor(450, 500).alpha() == 0
    # The cloned area was not changed by the brush/eraser
    cs = window.scene_.clone_offset
    assert_cloned_at(page, sp(view, vp(view, 250, 310)), cs)
    assert page.undo_stack.count() == 3
    for _ in range(2):
        window.undo()
    assert page.paint == clone_state


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_clone_survives_save_and_reopen_and_safety_rules_hold(tmp_path, pattern_png, qapp):
    settings = make_settings(tmp_path)
    w = open_window(tmp_path, pattern_png, settings=settings)
    w.canvas.actual_size()
    w.canvas.centerOn(400, 300)
    w.tools.set_tool(Tool.CLONE)
    w.tools.set_clone_size(34)
    view = w.canvas
    root = w.project.root
    original_copy = root / w.page.original_rel
    h_copy, h_source = sha(original_copy), sha(pattern_png)
    select_source(w, vp(view, 550, 120))
    drag(view, [vp(view, 150, 350), vp(view, 280, 380), vp(view, 300, 480)])
    expected_paint = w.page.paint.copy()
    expected_image = compose_page(w.page)
    assert w.save_project()
    # Ctrl+S writes the edited image to the source file; the original copy in the project is kept
    assert QImage(str(pattern_png)).convertToFormat(QImage.Format.Format_RGB32) == \
        expected_image.convertToFormat(QImage.Format.Format_RGB32)
    assert sha(original_copy) == h_copy and sha(pattern_png) != h_source
    assert (root / "pages").exists() and list((root / "pages").glob("*.png"))
    w.close()

    w2 = MainWindow(settings=settings)
    w2.resize(1300, 900)
    w2.show()
    assert w2.open_project(root)
    page = w2.project.pages[0]
    page.ensure_loaded()
    assert page.paint == expected_paint  # the cloned pixels are the same after reopening
    assert compose_page(page) == expected_image
    assert not w2.project.is_dirty
    # In a reopened project a clone cannot be undone (no history), but a new clone works and can be undone
    w2.canvas.actual_size()
    w2.tools.set_tool(Tool.CLONE)
    select_source(w2, w2.canvas.mapFromScene(QPointF(600, 100)))
    drag(w2.canvas, [w2.canvas.mapFromScene(QPointF(100, 100)), w2.canvas.mapFromScene(QPointF(160, 120))])
    assert page.paint != expected_paint
    w2.undo()
    assert page.paint == expected_paint
    w2.project.discard_recovery()
    w2.close()


# ------------------------------------------------------------------ visual feedback
def count_color(img: QImage, pred, base: QImage | None = None, region=None) -> int:
    """Number of pixels that satisfy pred. If base is given, only pixels that DIFFER from base
    are counted (i.e. the drawn marker; the pattern's own colors are not counted). region=(x0,y0,x1,y1)."""
    x0, y0, x1, y1 = region or (0, 0, img.width(), img.height())
    n = 0
    for y in range(max(0, y0), min(img.height(), y1)):
        for x in range(max(0, x0), min(img.width(), x1)):
            c = img.pixelColor(x, y)
            if pred(c) and (base is None or base.pixelColor(x, y) != c):
                n += 1
    return n


def cyan(c):
    return c.blue() > 200 and c.green() > 170 and c.red() < 110


def orange(c):
    return c.red() > 220 and 130 < c.green() < 210 and c.blue() < 90


def hover_at(window, x, y):
    view = window.canvas
    p = vp(view, x, y)
    QTest.mouseMove(view.viewport(), p)
    QTest.mouseMove(view.viewport(), p + QPoint(1, 0))
    QTest.mouseMove(view.viewport(), p)
    QTest.qWait(20)


def test_source_marker_and_k_mode_are_visible(window):
    view = window.canvas
    window.tools.set_clone_size(50)
    hover_at(window, 300, 300)
    idle = view.viewport().grab().toImage()
    hover_at(window, 301, 301)
    assert count_color(view.viewport().grab().toImage(), cyan, base=idle,
                       region=(0, 0, 980, 804)) < 8  # no cyan marker without a source (only the cursor circle moves)

    select_source(window, vp(view, 560, 160))
    QTest.qWait(500)  # let the short 'ping' animation finish
    hover_at(window, 300, 300)
    with_source = view.viewport().grab().toImage()
    assert count_color(with_source, cyan, base=idle) > 40  # source marker (cyan cross + circle)

    # When painting starts, the source moves with the cursor (at cursor + offset)
    drag(view, [vp(view, 300, 300), vp(view, 330, 300)])
    hover_at(window, 250, 420)
    off = window.scene_.clone_offset
    assert off is not None
    img = view.viewport().grab().toImage()
    mx = view.mapFromScene(QPointF(250 + off.x(), 420 + off.y()))
    assert 30 <= mx.x() < img.width() - 30 and 30 <= mx.y() < img.height() - 30
    region = (mx.x() - 30, mx.y() - 30, mx.x() + 30, mx.y() + 30)
    assert count_color(img, cyan, base=idle, region=region) > 15  # the marker is right there

    # Orange 'pick source mode' cross + hand cursor while K is held
    before_k = view.viewport().grab().toImage()
    QTest.keyPress(view, Qt.Key.Key_K)
    QTest.qWait(20)
    assert count_color(view.viewport().grab().toImage(), orange, base=before_k) > 10
    assert view.viewport().cursor().shape() == Qt.CursorShape.PointingHandCursor
    QTest.keyRelease(view, Qt.Key.Key_K)
    assert view.viewport().cursor().shape() == Qt.CursorShape.CrossCursor


def test_brush_circle_preview_shows_for_clone(window):
    """Circle at the cursor showing the clone size (diameter): radius = size / 2."""
    view = window.canvas
    window.tools.set_clone_size(80)
    hover_at(window, 700, 500)
    elsewhere = view.viewport().grab().toImage()  # daire uzakta
    hover_at(window, 400, 300)
    img = view.viewport().grab().toImage()
    c = view.mapFromScene(QPointF(400, 300))

    def diff_in_annulus(image, r0, r1) -> int:
        n = 0
        for y in range(c.y() - r1, c.y() + r1 + 1):
            for x in range(c.x() - r1, c.x() + r1 + 1):
                if r0 <= ((x - c.x()) ** 2 + (y - c.y()) ** 2) ** 0.5 <= r1 \
                        and image.pixelColor(x, y) != elsewhere.pixelColor(x, y):
                    n += 1
        return n

    assert diff_in_annulus(img, 38, 42) > 150  # a ring is drawn around radius 40 (circumference ≈ 250 px)
    assert diff_in_annulus(img, 5, 30) == 0  # the inside of the circle is clean
    assert diff_in_annulus(img, 48, 70) == 0  # the outside is clean

    window.tools.set_clone_size(40)  # when the size changes the circle shrinks too: radius 20
    hover_at(window, 400, 300)
    smaller = view.viewport().grab().toImage()
    assert diff_in_annulus(smaller, 18, 22) > 80
    assert diff_in_annulus(smaller, 30, 60) == 0
