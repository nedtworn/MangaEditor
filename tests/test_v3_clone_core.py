"""Clone stamp core (no UI): exact pixel copies, continuous strokes, sizes,
boundaries and undo."""
import math

import pytest
from PySide6.QtCore import QPoint, QPointF
from PySide6.QtGui import QColor, QImage

from mangaeditor.core.clone import CloneSession, offset_between
from mangaeditor.core.page import PageDocument
from mangaeditor.core.stroke import BRUSH, StrokeSession


def pattern(w=400, h=300) -> QImage:
    """Every neighboring pixel has a different color, so a wrong shift is noticed at once."""
    img = QImage(w, h, QImage.Format.Format_RGB32)
    for y in range(h):
        for x in range(w):
            img.setPixelColor(x, y, QColor((x * 5 + y * 3) % 256, (x * 11 + y * 7) % 256, (x * 3 + y * 13) % 256))
    return img


@pytest.fixture
def page(qapp):
    return PageDocument.from_image(pattern(), "p")


def rgb(c: QColor):
    return (c.red(), c.green(), c.blue())


def dist_to_segment(px, py, a, b) -> float:
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def run(page, offset, size, pts, push=True):
    s = CloneSession(page, offset, size)
    for p in pts:
        s.add_point(QPointF(*p))
    cmd = s.finish()
    if cmd is not None and push:
        page.undo_stack.push(cmd)
    return cmd


def painted_count(page) -> int:
    img = page.paint
    return sum(1 for y in range(img.height()) for x in range(img.width()) if img.pixelColor(x, y).alpha() > 0)


def test_offset_between_rounds_to_nearest():
    assert offset_between(QPointF(10.4, 20.6), QPointF(0, 0)) == QPoint(10, 21)
    assert offset_between(QPointF(5, 5), QPointF(8.5, 2.5)) == QPoint(-3, 3)  # .5 rounds up
    assert offset_between(QPointF(0, 0), QPointF(0.2, 0.2)) == QPoint(0, 0)


def test_pixels_are_exact_copies_of_the_source(page):
    original = page.original.copy()
    off = QPoint(120, 40)
    a, b, size = (100, 100), (180, 100), 21
    run(page, off, size, [a, b])
    r = size / 2
    inside = outside = 0
    for y in range(page.size.height()):
        for x in range(page.size.width()):
            d = dist_to_segment(x + 0.5, y + 0.5, a, b)
            c = page.paint.pixelColor(x, y)
            if d <= r - 1.5:
                inside += 1
                assert c.alpha() == 255, (x, y)
                assert rgb(c) == rgb(original.pixelColor(x + off.x(), y + off.y())), (x, y)  # birebir
            elif d >= r + 2.5:
                outside += 1
                assert c.alpha() == 0, (x, y)
    assert inside > 1000 and outside > 50000
    assert page.original == original  # the original image never changes


@pytest.mark.parametrize("size", [3, 10, 31, 80])
def test_brush_size_controls_width(page, size):
    run(page, QPoint(100, 0), size, [(200, 150)])  # a single click = a circle
    xs, ys, n = [], [], 0
    for y in range(page.size.height()):
        for x in range(page.size.width()):
            if page.paint.pixelColor(x, y).alpha() >= 128:  # semi-transparent edge pixels are not counted
                xs.append(x)
                ys.append(y)
                n += 1
    assert max(xs) - min(xs) + 1 <= size + 3 and max(ys) - min(ys) + 1 <= size + 3
    assert max(xs) - min(xs) + 1 >= size - 1
    area = math.pi * (size / 2) ** 2
    if size >= 10:
        assert area * 0.8 <= n <= area * 1.35 + 4
    else:  # with a very small brush, anti-aliasing and the pixel grid change the area noticeably
        assert 3 <= n <= size * size + 4


@pytest.mark.parametrize("pts", [
    [(40, 50), (300, 50)],  # one long jump (260 px between mouse events)
    [(40, 40), (120, 40), (120, 140), (40, 140), (40, 40)],  # angular path
    [(20, 250), (60, 120), (140, 260), (230, 90), (360, 200)],  # irregular zigzag
])
def test_stroke_is_continuous_without_gaps(page, pts):
    size = 14
    run(page, QPoint(0, 0), size, pts)  # offset 0: source = target → the alpha density shows the line
    for (a, b) in zip(pts, pts[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(2, int(L * 2))
        for i in range(n + 1):
            x = a[0] + (b[0] - a[0]) * i / n
            y = a[1] + (b[1] - a[1]) * i / n
            assert page.paint.pixelColor(int(x), int(y)).alpha() == 255, (x, y)  # kopukluk yok


def test_source_is_the_view_before_the_stroke_no_feedback(page):
    """If the target overlaps the source, the stroke does not copy its own output again:
    the result is the view at the start of the stroke, shifted."""
    before = page.original.copy()
    off = QPoint(10, 0)
    run(page, off, 20, [(50, 150), (200, 150)])
    for x in range(60, 190, 3):
        for y in range(145, 156):
            c = page.paint.pixelColor(x, y)
            assert c.alpha() == 255
            assert rgb(c) == rgb(before.pixelColor(x + 10, y)), (x, y)  # (x+20, y) would have smeared it


def test_source_includes_existing_paint(page):
    # Paint the source area red first; the clone carries the visible (original + paint) state.
    s = StrokeSession(page, BRUSH, 40, QColor(255, 0, 0))
    s.add_point(QPointF(250, 100))
    page.undo_stack.push(s.finish())
    run(page, QPoint(150, 0), 12, [(100, 100)])  # hedef (100,100) ← kaynak (250,100)
    assert rgb(page.paint.pixelColor(100, 100)) == (255, 0, 0)
    assert page.paint.pixelColor(100, 100).alpha() == 255


def test_source_outside_image_is_skipped_safely(page):
    assert run(page, QPoint(-5000, 0), 20, [(100, 100), (200, 100)]) is None  # everything outside
    assert painted_count(page) == 0
    assert page.undo_stack.count() == 0

    # Partly outside: target pixels whose source has x < 0 stay empty, the others are copied.
    off = QPoint(-100, 0)
    run(page, off, 16, [(30, 150), (180, 150)])
    assert page.paint.pixelColor(50, 150).alpha() == 0  # source x = -50 → outside the image
    assert page.paint.pixelColor(150, 150).alpha() == 255  # kaynak x = 50
    assert rgb(page.paint.pixelColor(150, 150)) == rgb(page.original.pixelColor(50, 150))


def test_destination_outside_image_is_clipped_safely(page):
    size_before = page.paint.size()
    run(page, QPoint(0, 0), 40, [(-50, -50), (10, 10), (200, 150), (450, 330), (900, 900)])
    assert page.paint.size() == size_before  # the layer did not grow or overflow
    assert page.paint.pixelColor(0, 0).alpha() == 255  # the corner was painted
    assert page.paint.pixelColor(399, 299).alpha() == 255
    # A click that is entirely outside does nothing
    p2 = PageDocument.from_image(pattern(), "q")
    assert run(p2, QPoint(0, 0), 10, [(-100, -100), (-80, -90)]) is None
    assert painted_count(p2) == 0


def test_undo_redo_restores_exactly(page):
    base = page.paint.copy()
    run(page, QPoint(60, 20), 25, [(100, 100), (160, 130), (200, 100)])
    after = page.paint.copy()
    assert after != base and page.is_dirty and page.undo_stack.count() == 1
    page.undo_stack.undo()
    assert page.paint == base and not page.is_dirty
    page.undo_stack.redo()
    assert page.paint == after
    assert page.undo_stack.undoText() == "Klonlama"


def test_cancel_restores_layer(page):
    base = page.paint.copy()
    s = CloneSession(page, QPoint(50, 0), 20)
    s.add_point(QPointF(100, 100))
    s.add_point(QPointF(150, 100))
    assert page.paint != base
    s.cancel()
    assert page.paint == base
    assert s.finish() is None
