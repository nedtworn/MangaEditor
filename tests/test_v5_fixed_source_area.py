"""Non-aligned mode: a FIXED square source area, tiled onto the target like a PATTERN.

Rule: target pixel q <- corner + ((q - corner) mod side)
The grid is fixed to the image; the cursor, releasing or not releasing the mouse, and the stroke order do not change it.

In the test image every pixel's color encodes its own (x, y) coordinate, so for every target pixel
the exact source coordinate it was copied from can be determined.
"""
import pytest
from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest

from mangaeditor.core.clone import PatternCloneSession, SourcePatch
from mangaeditor.core.compose import compose_page
from mangaeditor.core.page import PageDocument
from mangaeditor.ui.main_window import MainWindow
from mangaeditor.ui.tools import Tool

from conftest import make_settings, open_window

L = Qt.MouseButton.LeftButton
NM = Qt.KeyboardModifier.NoModifier
W, H = 800, 600


# ------------------------------------------------------------------ coordinate-encoded image
def encode(x, y) -> QColor:
    return QColor(x & 255, y & 255, (x >> 8) | ((y >> 8) << 4))


def decode(c: QColor) -> tuple[int, int]:
    return c.red() + (c.blue() & 15) * 256, c.green() + (c.blue() >> 4) * 256


def coded_image(w=W, h=H) -> QImage:
    img = QImage(w, h, QImage.Format.Format_RGB32)
    for y in range(h):
        for x in range(w):
            img.setPixelColor(x, y, encode(x, y))
    return img


def painted(page_or_image, since: QImage | None = None):
    img = page_or_image if isinstance(page_or_image, QImage) else page_or_image.paint
    out = []
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() > 0 and (since is None or since.pixelColor(x, y) != c):
                out.append((x, y, c))
    return out


def assert_tiled_from(patch: SourcePatch, pixels) -> int:
    """Every painted pixel: fully opaque, from the square area, and exactly following the tiling rule."""
    assert pixels, "hiçbir şey boyanmadı"
    b = patch.bounds
    for x, y, c in pixels:
        assert c.alpha() == 255, f"({x},{y}) kısmi/karışık piksel"
        src = decode(c)
        assert b.contains(*src), f"({x},{y}) alan DIŞINDAN {src} örneklenmiş"
        assert src == patch.source_of(x, y), f"({x},{y}) desen kuralına uymuyor: {src} != {patch.source_of(x, y)}"
    return len(pixels)


# ------------------------------------------------------------------ fixture'lar
@pytest.fixture
def coded_png(tmp_path, qapp):
    d = tmp_path / "kaynak"
    d.mkdir()
    p = d / "kodlu.png"
    assert coded_image().save(str(p), "PNG")
    return p


@pytest.fixture
def win(tmp_path, coded_png):
    w = open_window(tmp_path, coded_png)
    w.canvas.actual_size()
    w.canvas.centerOn(400, 300)
    QTest.qWait(10)
    w.tools.set_tool(Tool.CLONE)
    w.tools.set_clone_aligned(False)
    yield w
    w.project and w.project.discard_recovery()
    w.close()


def vp(view, x, y) -> QPoint:
    return view.mapFromScene(QPointF(x, y))


def sp(view, p: QPoint) -> QPointF:
    return view.scene_pos(QPointF(p))


def pick_source(win, x, y, size=None) -> SourcePatch:
    view = win.canvas
    if size is not None:
        win.tools.set_clone_size(size)
    QTest.keyPress(view, Qt.Key.Key_K)
    QTest.mouseClick(view.viewport(), L, NM, vp(view, x, y))
    QTest.keyRelease(view, Qt.Key.Key_K)
    patch = win.scene_.clone_patch
    assert patch is not None
    return patch


def drag(view, scene_pts, steps=6):
    v = view.viewport()
    pts = [vp(view, x, y) for x, y in scene_pts]
    QTest.mousePress(v, L, NM, pts[0])
    cur = pts[0]
    for nxt in pts[1:]:
        for i in range(1, steps + 1):
            QTest.mouseMove(v, QPoint(round(cur.x() + (nxt.x() - cur.x()) * i / steps),
                                      round(cur.y() + (nxt.y() - cur.y()) * i / steps)))
        cur = nxt
    QTest.mouseRelease(v, L, NM, pts[-1])


# =================================================================== core (no UI)
def test_patch_is_a_square_of_the_brush_size_centered_on_the_click(qapp):
    page = PageDocument.from_image(coded_image(), "p")
    p = SourcePatch.capture(page, QPointF(400.4, 300.6), 50)
    assert (p.width, p.height) == (50, 50)
    assert abs(p.bounds.center().x() + 0.5 - 400.4) <= 1 and abs(p.bounds.center().y() + 0.5 - 300.6) <= 1
    for y in range(p.height):  # content = the image at the moment of selection, exactly
        for x in range(p.width):
            assert decode(p.image.pixelColor(x, y)) == (p.origin.x() + x, p.origin.y() + y)
    edge = SourcePatch.capture(page, QPointF(5, 590), 60)  # clipped at the image edge
    assert edge.bounds == QRect(0, 560, 35, 40) and page.rect.contains(edge.bounds)


def test_tiled_fill_follows_the_rule_exactly(qapp):
    page = PageDocument.from_image(coded_image(), "p")
    p = SourcePatch.capture(page, QPointF(600, 150), 30)
    rect = QRect(17, 333, 140, 95)
    img = p.tiled(rect)
    for y in range(rect.height()):
        for x in range(rect.width()):
            assert decode(img.pixelColor(x, y)) == p.source_of(rect.x() + x, rect.y() + y)


def test_core_session_only_tiles_area_pixels(qapp):
    page = PageDocument.from_image(coded_image(), "p")
    patch = SourcePatch.capture(page, QPointF(600, 150), 40)
    s = PatternCloneSession(page, patch, 120)  # target brush 3 times larger than the area
    for p in [(100, 400), (300, 420), (320, 550), (60, 520), (500, 300), (610, 160)]:  # also passes over the source
        s.add_point(QPointF(*p))
    page.undo_stack.push(s.finish())
    assert assert_tiled_from(patch, painted(page)) > 30000


# =================================================================== painting without releasing = same place
def test_continuous_drag_equals_separate_clicks(win):
    """The user's requirement: painting without releasing the mouse at all gives the SAME result, pixel
    by pixel, as clicking the same path one at a time, because every target pixel always gets the same source pixel."""
    view, page = win.canvas, win.page
    patch = pick_source(win, 560, 140, size=50)
    win.tools.set_clone_size(40)
    path = [(100, 300), (180, 310), (260, 300), (340, 320), (420, 300), (500, 330)]
    drag(view, path, steps=8)  # one continuous drag
    continuous = page.paint.copy()
    assert_tiled_from(patch, painted(page))
    win.undo()
    assert page.paint_is_empty()
    for x in range(100, 501, 4):  # the same path with separate clicks
        y = 300 + (20 if 300 < x < 360 else 0) + (30 if x > 460 else 0)
        QTest.mouseClick(view.viewport(), L, NM, vp(view, x, y))
    clicks = page.paint
    both = 0
    for y in range(260, 380):
        for x in range(60, 540):
            a, b = continuous.pixelColor(x, y), clicks.pixelColor(x, y)
            if a.alpha() and b.alpha():
                assert a == b, (x, y)  # same target pixel = same value
                both += 1
    assert both > 5000


def test_mouse_motion_never_moves_the_sampling(win):
    view, page = win.canvas, win.page
    patch = pick_source(win, 560, 140, size=60)
    win.tools.set_clone_size(60)
    v = view.viewport()
    path = [(120, 300), (180, 320), (260, 360), (300, 450), (220, 520), (130, 470), (125, 305)]  # also passes over itself
    QTest.mousePress(v, L, NM, vp(view, *path[0]))
    prev = page.paint.copy()
    for p in path[1:]:
        QTest.mouseMove(v, vp(view, *p))
        assert_tiled_from(patch, painted(page, since=prev))  # her harekette eklenen her piksel kurala uyar
        overwritten = [(x, y) for x, y, _ in painted(prev) if prev.pixelColor(x, y) != page.paint.pixelColor(x, y)]
        assert overwritten == []  # a place passed again does NOT change: no shifting or stretching
        prev = page.paint.copy()
        assert win.scene_.clone_patch is patch
    QTest.mouseRelease(v, L, NM, vp(view, *path[-1]))
    assert page.undo_stack.count() == 1  # one drag = one undo step


def test_pattern_repeats_side_by_side(win):
    view, page = win.canvas, win.page
    patch = pick_source(win, 560, 140, size=40)
    win.tools.set_clone_size(180)
    drag(view, [(150, 400), (450, 400)])
    w, h = patch.width, patch.height
    checked = 0
    for y in range(340, 460, 7):
        for x in range(160, 400, 7):
            a, b, c = page.paint.pixelColor(x, y), page.paint.pixelColor(x + w, y), page.paint.pixelColor(x, y + h)
            if a.alpha() and b.alpha():
                assert a == b  # horizontally, the same at an interval of w
                checked += 1
            if a.alpha() and c.alpha():
                assert a == c  # vertically, the same at an interval of h
    assert checked > 100


# =================================================================== nothing outside the area, separate strokes, size
def test_pixels_outside_area_are_never_sampled(win):
    view, page = win.canvas, win.page
    patch = pick_source(win, 560, 140, size=50)
    for size in (50, 200, 12, 90):
        win.tools.set_clone_size(size)
        drag(view, [(60, 300), (420, 330), (430, 560), (120, 500)], steps=3)
    drag(view, [(500, 100), (640, 180), (790, 20)])  # over the source area and to the page edge
    n = assert_tiled_from(patch, painted(page))
    assert n > 40000
    srcs = {decode(c) for _, _, c in painted(page)}
    assert max(s[0] for s in srcs) - min(s[0] for s in srcs) + 1 <= 50
    assert max(s[1] for s in srcs) - min(s[1] for s in srcs) + 1 <= 50


def test_separate_overlapping_strokes_have_no_seams(win):
    view, page = win.canvas, win.page
    patch = pick_source(win, 560, 140, size=50)
    win.tools.set_clone_size(70)
    drag(view, [(100, 300), (300, 310)])
    first = page.paint.copy()
    drag(view, [(200, 260), (220, 420)])  # second stroke over the first one
    drag(view, [(700, 450), (520, 420)])
    for x, y, _ in painted(first):  # the pixels of the first stroke did not change when passed over
        assert page.paint.pixelColor(x, y) == first.pixelColor(x, y), (x, y)
    assert_tiled_from(patch, painted(page))
    assert page.undo_stack.count() == 3 and win.scene_.clone_patch is patch


def test_50px_area_with_200px_brush_fills_200px_only_from_the_50px_area(win):
    view, page = win.canvas, win.page
    patch = pick_source(win, 560, 140, size=50)
    win.side_panel.clone_panel.size.spin.setValue(200)
    assert win.scene_.clone_patch is patch and (patch.width, patch.height) == (50, 50)  # the area did not grow
    T = vp(view, 300, 380)
    QTest.mouseClick(view.viewport(), L, NM, T)
    t = sp(view, T)
    px = painted(page)
    assert_tiled_from(patch, px)
    row = [x for x, y, _ in px if y == int(t.y())]
    assert abs((max(row) - min(row) + 1) - 200) <= 2  # target 200 px, only by repeating the 50 px area
    assert len({decode(c) for _, _, c in px}) <= 50 * 50


def test_200px_area_with_50px_brush(win):
    view, page = win.canvas, win.page
    patch = pick_source(win, 400, 160, size=200)
    win.tools.set_clone_size(50)
    drag(view, [(150, 430), (300, 450)])
    assert_tiled_from(patch, painted(page))


# =================================================================== content, new source, mode
def test_area_content_is_frozen_at_selection(win):
    view, page = win.canvas, win.page
    patch = pick_source(win, 560, 140, size=50)
    QTest.keyClick(win, Qt.Key.Key_B)
    win.tools.set_brush_color(QColor(255, 0, 0))
    win.tools.set_brush_size(80)
    drag(view, [(540, 140), (580, 140)])  # paint the source area red
    assert page.paint.pixelColor(560, 140) == QColor(255, 0, 0)
    QTest.keyClick(win, Qt.Key.Key_S)
    assert win.tools.tool == Tool.CLONE and win.scene_.clone_patch is patch
    before = page.paint.copy()
    drag(view, [(150, 400), (250, 420)])
    new = painted(page, since=before)
    assert all(c != QColor(255, 0, 0) for _, _, c in new)  # the red added later was not copied
    assert_tiled_from(patch, new)


def test_new_k_click_replaces_the_area(win):
    view, page = win.canvas, win.page
    a1 = pick_source(win, 600, 120, size=50)
    drag(view, [(100, 300), (200, 310)])
    before = page.paint.copy()
    a2 = pick_source(win, 150, 520, size=30)
    assert a2 is not a1 and win.scene_.clone_patch is a2 and (a2.width, a2.height) == (30, 30)
    drag(view, [(400, 300), (520, 330)])
    new = painted(page, since=before)
    assert_tiled_from(a2, new)
    assert not any(a1.bounds.contains(*decode(c)) for _, _, c in new)  # the old area was dropped
    assert "alan 30×30 px" in win.side_panel.clone_panel.status.text()


def test_brush_size_change_and_mode_switch_keep_the_area(win):
    view = win.canvas
    patch = pick_source(win, 560, 140, size=50)
    status = win.side_panel.clone_panel.status.text()
    assert "alan 50×50 px" in status
    for size in (10, 200, 77):
        win.tools.set_clone_size(size)
        assert win.scene_.clone_patch is patch
    assert win.side_panel.clone_panel.status.text() == status
    win.tools.set_clone_aligned(True)
    win.tools.set_clone_aligned(False)
    assert win.scene_.clone_patch is patch
    drag(view, [(150, 400), (250, 420)])
    assert_tiled_from(patch, painted(win.page))


# =================================================================== zoom ve pan
@pytest.mark.parametrize("zoom", [0.5, 1.0, 2.0, 4.0])
def test_area_in_image_coordinates_at_any_zoom(win, zoom):
    view, page = win.canvas, win.page
    view.set_zoom(zoom)
    view.centerOn(400, 300)
    QTest.qWait(10)
    patch = pick_source(win, 480, 220, size=40)
    c = patch.bounds
    assert abs(c.x() + 20 - 480) <= 1 / zoom + 1 and abs(c.y() + 20 - 220) <= 1 / zoom + 1
    assert (patch.width, patch.height) == (40, 40)  # image pixels, not screen pixels
    win.tools.set_clone_size(70)
    drag(view, [(380, 300), (430, 330), (360, 360)], steps=8)
    assert_tiled_from(patch, painted(page))


def test_area_survives_pan(win):
    view, page = win.canvas, win.page
    view.set_zoom(2.0)
    view.centerOn(400, 300)
    QTest.qWait(10)
    patch = pick_source(win, 450, 250, size=40)
    b = QRect(patch.bounds)
    sv0 = view.mapFromScene(QPointF(b.topLeft()))
    QTest.keyPress(view, Qt.Key.Key_Space)
    QTest.mousePress(view.viewport(), L, NM, QPoint(500, 400))
    QTest.mouseMove(view.viewport(), QPoint(420, 350))
    QTest.mouseRelease(view.viewport(), L, NM, QPoint(420, 350))
    QTest.keyRelease(view, Qt.Key.Key_Space)
    sv1 = view.mapFromScene(QPointF(b.topLeft()))
    assert (sv1.x() - sv0.x(), sv1.y() - sv0.y()) == (-80, -50)
    assert win.scene_.clone_patch is patch and patch.bounds == b
    assert page.paint_is_empty()
    drag(view, [(330, 360), (380, 370)])
    assert_tiled_from(patch, painted(page))


def test_area_clipped_at_image_edge(win):
    view, page = win.canvas, win.page
    patch = pick_source(win, 4, 3, size=60)
    assert patch.bounds.left() == 0 and patch.bounds.top() == 0 and patch.width < 60 and patch.height < 60
    drag(view, [(300, 300), (400, 320)])
    assert_tiled_from(patch, painted(page))  # the clipped square is also tiled without gaps


# =================================================================== indicator
def cyan(c):
    return c.blue() > 200 and c.green() > 170 and c.red() < 110


def orange(c):
    return c.red() > 220 and 130 < c.green() < 210 and c.blue() < 90


def diff_bbox(img, base, pred):
    xs, ys = [], []
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if pred(c) and base.pixelColor(x, y) != c:
                xs.append(x)
                ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def hover(win, x, y):
    v = win.canvas.viewport()
    p = vp(win.canvas, x, y)
    QTest.mouseMove(v, p)
    QTest.mouseMove(v, p + QPoint(1, 0))
    QTest.mouseMove(v, p)
    QTest.qWait(30)


def indicator_bbox(win, at=(250, 450)):
    view, scene = win.canvas, win.scene_
    src, patch = QPointF(scene.clone_source), scene.clone_patch
    scene.clone_source, scene.clone_patch = None, None
    hover(win, *at)
    base = view.viewport().grab().toImage()
    scene.clone_source, scene.clone_patch = src, patch
    hover(win, *at)
    return diff_bbox(view.viewport().grab().toImage(), base, cyan)


def test_indicator_is_the_real_square_area(win):
    view = win.canvas
    patch = pick_source(win, 500, 200, size=80)
    QTest.qWait(500)
    bb = indicator_bbox(win)
    tl = view.mapFromScene(QPointF(patch.bounds.topLeft()))
    assert abs(bb[0] - tl.x()) <= 2 and abs(bb[1] - tl.y()) <= 2
    assert abs((bb[2] - bb[0]) - 80) <= 3 and abs((bb[3] - bb[1]) - 80) <= 3  # 80×80 square
    for size in (10, 250):
        win.tools.set_clone_size(size)
        assert indicator_bbox(win) == pytest.approx(bb, abs=1)  # does not change with the brush size
    for at in ((150, 300), (650, 500)):
        assert indicator_bbox(win, at) == pytest.approx(bb, abs=1)  # does not shift with the cursor


def test_k_held_previews_the_square_that_would_be_captured(win):
    view = win.canvas
    win.tools.set_clone_size(120)
    hover(win, 400, 300)
    base = view.viewport().grab().toImage()
    QTest.keyPress(view, Qt.Key.Key_K)
    QTest.qWait(20)
    bb = diff_bbox(view.viewport().grab().toImage(), base, orange)
    QTest.keyRelease(view, Qt.Key.Key_K)
    assert bb is not None and abs((bb[2] - bb[0]) - 120) <= 4 and abs((bb[3] - bb[1]) - 120) <= 4


# =================================================================== geri al, kaydet
def test_undo_redo_and_save_reopen(tmp_path, coded_png):
    settings = make_settings(tmp_path)
    w = open_window(tmp_path, coded_png, settings=settings)
    w.canvas.actual_size()
    w.canvas.centerOn(400, 300)
    w.tools.set_tool(Tool.CLONE)
    w.tools.set_clone_aligned(False)
    view, page = w.canvas, w.page
    patch = pick_source(w, 560, 140, size=50)
    drag(view, [(100, 300), (200, 320), (260, 400)])
    first = page.paint.copy()
    w.tools.set_clone_size(150)
    drag(view, [(300, 480), (420, 500)])
    both = page.paint.copy()
    assert page.undo_stack.count() == 2
    w.undo()
    assert page.paint == first
    w.undo()
    assert page.paint_is_empty()
    w.redo()
    w.redo()
    assert page.paint == both
    assert_tiled_from(patch, painted(page))
    image = compose_page(page)
    root = w.project.root
    assert w.save_project()
    w.close()
    w2 = MainWindow(settings=settings)
    w2.resize(1300, 900)
    w2.show()
    assert w2.open_project(root)
    p2 = w2.project.pages[0]
    p2.ensure_loaded()
    assert p2.paint == both and compose_page(p2) == image
    assert w2.tools.clone_aligned is False
    w2.project.discard_recovery()
    w2.close()
