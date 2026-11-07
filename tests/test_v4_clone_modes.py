"""Clone stamp: Aligned / Non-aligned modes and the independence of the source from the brush size.

Rule: source = (a point in image coordinates, source-target offset). The brush size only
sets only the painted area on the target; it does not change the source point, the offset or the source marker.
"""
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from mangaeditor.core.clone import offset_between
from mangaeditor.core.compose import compose_page
from mangaeditor.ui.canvas_view import CLONE_MARK_ARM
from mangaeditor.ui.main_window import MainWindow
from mangaeditor.ui.tools import Tool

from conftest import make_settings, open_window
from test_v3_clone_ui import (  # noqa: F401  (fixtures and helpers)
    L,
    NM,
    assert_cloned_at,
    count_color,
    cyan,
    drag,
    hover_at,
    pattern_png,
    rgb,
    select_source,
    sp,
    vp,
    window,
)

MODES = [pytest.param(True, id="hizali"), pytest.param(False, id="hizali_degil")]
# v5: the non-aligned mode now paints from a FIXED source area (test_v5_fixed_source_area.py). The tests below
# that use this list assumed the old "sampling moves with the cursor" behavior, so they run only
# in aligned mode; the non-aligned behavior is tested with real pixels in the new file.
ALIGNED_ONLY = [pytest.param(True, id="hizali")]


def set_mode(window, aligned: bool):
    window.tools.set_clone_aligned(aligned)


def expected_offset(window, view_pos: QPoint) -> QPoint:
    """The expected offset from the 'source point' when a stroke starts at the point T."""
    return offset_between(window.scene_.clone_source, sp(window.canvas, view_pos))


def painted_mask(page):
    img = page.paint
    return [(x, y) for y in range(img.height()) for x in range(img.width()) if img.pixelColor(x, y).alpha() == 255]


def cyan_bbox(img, base, region=None):
    x0, y0, x1, y1 = region or (0, 0, img.width(), img.height())
    xs, ys = [], []
    for y in range(max(0, y0), min(img.height(), y1)):
        for x in range(max(0, x0), min(img.width(), x1)):
            c = img.pixelColor(x, y)
            if cyan(c) and base.pixelColor(x, y) != c:
                xs.append(x)
                ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def marker_bbox(window, hover_scene):
    """Only the box covered by the source marker (turquoise): the difference between images
    with and without a source at the same cursor position."""
    view, scene = window.canvas, window.scene_
    src = QPointF(scene.clone_source)
    scene.clone_source = None
    hover_at(window, *hover_scene)
    base = view.viewport().grab().toImage()
    scene.clone_source = src
    hover_at(window, *hover_scene)
    img = view.viewport().grab().toImage()
    return cyan_bbox(img, base), img, base


def center(b):
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


# =============================================================== interface: mode selection
def test_panel_has_two_modes_aligned_by_default(window):
    panel = window.side_panel.clone_panel
    assert window.tools.clone_aligned is True
    assert panel.mode_aligned.text() == "Hizalı" and panel.mode_free.text() == "Hizalı Değil"
    assert panel.mode_aligned.isChecked() and not panel.mode_free.isChecked()
    QTest.mouseClick(panel.mode_free, L)
    assert window.tools.clone_aligned is False and panel.mode_free.isChecked() and not panel.mode_aligned.isChecked()
    QTest.mouseClick(panel.mode_aligned, L)
    assert window.tools.clone_aligned is True and panel.mode_aligned.isChecked()
    from PySide6.QtWidgets import QRadioButton
    assert len(panel.findChildren(QRadioButton)) == 2  # simple: only two options


def test_mode_preference_persists_between_sessions(tmp_path, pattern_png):
    settings = make_settings(tmp_path)
    w = open_window(tmp_path, pattern_png, settings=settings)
    w.tools.set_tool(Tool.CLONE)  # the panel is only shown while the clone tool is selected
    QTest.mouseClick(w.side_panel.clone_panel.mode_free, L)
    assert w.tools.clone_aligned is False
    w.project.discard_recovery()
    w.close()
    w2 = MainWindow(settings=make_settings(tmp_path))  # new session: reads from the settings file
    assert w2.tools.clone_aligned is False
    p2 = w2.side_panel.clone_panel
    assert p2.mode_free.isChecked() and not p2.mode_aligned.isChecked()
    w2.tools.set_tool(Tool.CLONE)
    QTest.mouseClick(p2.mode_aligned, L)
    assert w2.tools.clone_aligned is True
    w2.close()
    w3 = MainWindow(settings=make_settings(tmp_path))
    assert w3.tools.clone_aligned is True
    w3.close()


def test_switching_mode_keeps_the_source_point(window):
    view = window.canvas
    select_source(window, vp(view, 500, 150))
    S = QPointF(window.scene_.clone_source)
    drag(view, [vp(view, 200, 300), vp(view, 260, 320)])
    assert window.scene_.clone_offset is not None  # aligned: the offset is fixed
    text = window.side_panel.clone_panel.status.text()
    set_mode(window, False)
    assert window.scene_.clone_source == S and window.side_panel.clone_panel.status.text() == text
    assert window.scene_.clone_offset is None  # only the fixed offset is reset
    set_mode(window, True)
    assert window.scene_.clone_source == S  # the source point was not lost
    T = vp(view, 150, 450)
    drag(view, [T, vp(view, 200, 460)])
    # After a mode change, the first stroke starts from the marked source
    assert_cloned_at(window.page, sp(view, T), window.scene_.clone_offset)
    off = window.scene_.clone_offset
    assert abs(sp(view, T).x() + off.x() - S.x()) <= 0.5 and abs(sp(view, T).y() + off.y() - S.y()) <= 0.5


# =============================================================== Aligned mode (current behavior)
def test_aligned_keeps_distance_and_marker_follows_cursor(window):
    view, page = window.canvas, window.page
    set_mode(window, True)
    select_source(window, vp(view, 560, 120))
    T1, T2 = vp(view, 200, 330), vp(view, 120, 460)
    drag(view, [T1, vp(view, 260, 340)])
    off = QPoint(window.scene_.clone_offset)
    drag(view, [T2, vp(view, 190, 470)])  # second stroke at a different place
    QTest.qWait(500)  # let the short 'ping' animation of the source pick finish (so it does not disturb the measurement)
    assert window.scene_.clone_offset == off  # the distance is kept
    assert_cloned_at(page, sp(view, T2), off)  # the second stroke comes from the kept relationship, not from the SOURCE POINT
    S = window.scene_.clone_source
    assert rgb(page.paint.pixelColor(int(sp(view, T2).x()), int(sp(view, T2).y()))) != \
        rgb(page.original.pixelColor(int(S.x()), int(S.y())))
    # The marker moves with the cursor + offset position
    for hover in ((250, 480), (330, 520)):
        bb, _, _ = marker_bbox(window, hover)
        assert bb is not None
        cx, cy = center(bb)
        ex = view.mapFromScene(QPointF(hover[0] + off.x(), hover[1] + off.y()))
        assert abs(cx - ex.x()) <= 3 and abs(cy - ex.y()) <= 3


def test_aligned_new_source_resets_relationship(window):
    view = window.canvas
    select_source(window, vp(view, 560, 120))
    drag(view, [vp(view, 200, 330), vp(view, 260, 340)])
    assert window.scene_.clone_offset is not None
    select_source(window, vp(view, 100, 100))
    assert window.scene_.clone_offset is None
    T = vp(view, 400, 400)
    drag(view, [T, vp(view, 450, 410)])
    S = window.scene_.clone_source
    off = window.scene_.clone_offset
    assert abs(sp(view, T).x() + off.x() - S.x()) <= 0.5  # started from the new source


# =============================================================== Non-aligned mode
@pytest.mark.parametrize("aligned", ALIGNED_ONLY)
def test_source_changes_only_with_a_new_source_selection(window, aligned):
    view, page = window.canvas, window.page
    set_mode(window, aligned)
    select_source(window, vp(view, 560, 120))
    S1 = QPointF(window.scene_.clone_source)
    for pts in ([vp(view, 200, 330), vp(view, 250, 340)], [vp(view, 300, 450), vp(view, 360, 460)]):
        drag(view, pts)
        assert window.scene_.clone_source == S1
    QTest.mouseMove(view.viewport(), vp(view, 500, 500))
    set_mode(window, not aligned)
    set_mode(window, aligned)
    assert window.scene_.clone_source == S1
    select_source(window, vp(view, 90, 520))
    S2 = QPointF(window.scene_.clone_source)
    assert S2 != S1
    T = vp(view, 400, 250)
    drag(view, [T, vp(view, 440, 260)])
    off = offset_between(S2, sp(view, T))
    assert_cloned_at(page, sp(view, T), off)  # copied from the new source
    assert window.scene_.clone_source == S2


def test_nonaligned_marker_stays_at_the_fixed_coordinate(window):
    view = window.canvas
    set_mode(window, False)
    select_source(window, vp(view, 560, 120))
    QTest.qWait(500)
    S = QPointF(window.scene_.clone_source)
    sv = view.mapFromScene(S)
    for hover in ((200, 400), (330, 500), (150, 250)):
        bb, _, _ = marker_bbox(window, hover)
        assert bb is not None
        cx, cy = center(bb)
        assert abs(cx - sv.x()) <= 3 and abs(cy - sv.y()) <= 3  # her zaman sabit koordinatta
        hv = view.mapFromScene(QPointF(*hover))
        assert not (abs(cx - hv.x()) < 20 and abs(cy - hv.y()) < 20)  # does not move with the cursor
    # Also fixed during and after the stroke
    v = view.viewport()
    QTest.mousePress(v, L, NM, vp(view, 200, 400))
    QTest.mouseMove(v, vp(view, 260, 420))
    QTest.mouseMove(v, vp(view, 300, 430))
    mid, _, _ = marker_bbox(window, (300, 430))  # while the stroke is in progress
    cx, cy = center(mid)
    assert abs(cx - sv.x()) <= 3 and abs(cy - sv.y()) <= 3
    QTest.mouseRelease(v, L, NM, vp(view, 300, 430))
    after, _, _ = marker_bbox(window, (420, 300))
    cx, cy = center(after)
    assert abs(cx - sv.x()) <= 3 and abs(cy - sv.y()) <= 3


def test_nonaligned_without_source_does_not_paint(window):
    view, page = window.canvas, window.page
    set_mode(window, False)
    drag(view, [vp(view, 300, 300), vp(view, 400, 320)])
    assert page.paint_is_empty() and page.undo_stack.count() == 0
    assert "kaynak" in window.statusBar().currentMessage().lower()


# =============================================================== source ↔ brush size independence
@pytest.mark.parametrize("aligned", ALIGNED_ONLY)
@pytest.mark.parametrize("size_source,size_paint", [(20, 100), (100, 20)], ids=["20-sonra-100", "100-sonra-20"])
def test_source_is_independent_of_brush_size(window, aligned, size_source, size_paint):
    view, page = window.canvas, window.page
    panel = window.side_panel.clone_panel
    set_mode(window, aligned)
    panel.size.spin.setValue(size_source)
    assert window.tools.clone_size == size_source
    select_source(window, vp(view, 560, 130))
    QTest.qWait(500)
    S = QPointF(window.scene_.clone_source)
    status = panel.status.text()
    bb_before, _, _ = marker_bbox(window, (300, 400))

    panel.size.spin.setValue(size_paint)  # change the size
    assert window.tools.clone_size == size_paint
    assert window.scene_.clone_source == S  # the source coordinate did not change (exactly)
    assert panel.status.text() == status
    assert window.scene_.clone_offset is None
    bb_after, _, _ = marker_bbox(window, (300, 400))
    # Source marker: same position and size; it is not scaled by the brush size
    assert center(bb_after) == pytest.approx(center(bb_before), abs=1)
    w0, h0 = bb_before[2] - bb_before[0], bb_before[3] - bb_before[1]
    w1, h1 = bb_after[2] - bb_after[0], bb_after[3] - bb_after[1]
    assert (w1, h1) == pytest.approx((w0, h0), abs=1)
    assert max(w0, h0, w1, h1) <= 2 * CLONE_MARK_ARM + 6  # fixed screen size (≈28 px), much smaller than a 100 px brush

    # Painting on the target: the painted area = the new size; every copied pixel is offset from the source point
    T = vp(view, 300, 400)
    QTest.mouseClick(view.viewport(), L, NM, T)
    t = sp(view, T)
    off = offset_between(S, t)
    assert abs(t.x() + off.x() - S.x()) <= 0.5 and abs(t.y() + off.y() - S.y()) <= 0.5
    tx, ty = int(t.x()), int(t.y())
    row = [x for x in range(page.size.width()) if page.paint.pixelColor(x, ty).alpha() >= 128]
    assert abs((max(row) - min(row) + 1) - size_paint) <= 3  # target = brush size
    pts = painted_mask(page)
    assert pts
    r_in = size_paint / 2 - 2.5
    for x, y in pts:  # no pixel was scaled or resampled
        got = page.paint.pixelColor(x, y)
        want = page.original.pixelColor(x + off.x(), y + off.y())
        tol = 0 if ((x + 0.5 - t.x()) ** 2 + (y + 0.5 - t.y()) ** 2) ** 0.5 <= r_in else 2  # kenar: anti-alias
        assert all(abs(a - b) <= tol for a, b in zip(rgb(got), rgb(want))), (x, y)
    # The center region contains the same source pixels in both sizes
    small = min(size_source, size_paint)
    for dx in range(-(small // 2) + 3, small // 2 - 2, 3):
        assert rgb(page.paint.pixelColor(tx + dx, ty)) == rgb(page.original.pixelColor(tx + dx + off.x(), ty + off.y()))


@pytest.mark.parametrize("aligned", MODES)
def test_same_source_relationship_for_any_brush_size(window, aligned):
    """The same source and target point give the SAME source offset with different brush sizes."""
    view, page = window.canvas, window.page
    set_mode(window, aligned)
    select_source(window, vp(view, 560, 130))
    S = window.scene_.clone_source
    T = vp(view, 300, 400)
    offsets = []
    for size in (10, 40, 150):
        window.tools.set_clone_size(size)
        window.scene_.clone_offset = None  # in aligned mode the relationship is rebuilt on every try
        QTest.mouseClick(view.viewport(), L, NM, T)
        off = window.scene_.clone_offset if aligned else offset_between(S, sp(view, T))
        offsets.append(QPoint(off))
        assert window.scene_.clone_source == S
        window.undo()
    assert offsets[0] == offsets[1] == offsets[2]


def test_aligned_resize_between_strokes_keeps_relationship(window):
    view, page = window.canvas, window.page
    window.tools.set_clone_size(20)
    select_source(window, vp(view, 560, 130))
    drag(view, [vp(view, 200, 330), vp(view, 240, 340)])
    off = QPoint(window.scene_.clone_offset)
    S = QPointF(window.scene_.clone_source)
    window.tools.set_clone_size(100)
    assert window.scene_.clone_offset == off and window.scene_.clone_source == S
    T = vp(view, 120, 470)
    QTest.mouseClick(view.viewport(), L, NM, T)
    assert window.scene_.clone_offset == off
    assert_cloned_at(page, sp(view, T), off)


# =============================================================== zoom, pan, koordinatlar
@pytest.mark.parametrize("aligned", ALIGNED_ONLY)
@pytest.mark.parametrize("zoom", [0.5, 1.0, 2.0, 4.0])
def test_coordinates_in_image_space_at_all_zoom_levels(window, aligned, zoom):
    view, page = window.canvas, window.page
    set_mode(window, aligned)
    window.tools.set_clone_size(24)
    view.set_zoom(zoom)
    view.centerOn(400, 300)
    QTest.qWait(10)
    vS = vp(view, 520, 180)
    select_source(window, vS)
    S = window.scene_.clone_source
    assert abs(S.x() - 520) <= 1 / zoom + 1 and abs(S.y() - 180) <= 1 / zoom + 1  # image coordinate
    vT1, vT2 = vp(view, 300, 330), vp(view, 380, 340)
    drag(view, [vT1, vT2], steps=10)
    off = offset_between(S, sp(view, vT1))
    assert_cloned_at(page, sp(view, vT1), off)
    assert_cloned_at(page, sp(view, vT2), off)
    T1 = sp(view, vT1)
    assert rgb(page.paint.pixelColor(int(T1.x()), int(T1.y()))) == rgb(page.original.pixelColor(int(S.x()), int(S.y()))) \
        or (abs(T1.x() + off.x() - S.x()) <= 0.5)
    assert window.scene_.clone_source == S


@pytest.mark.parametrize("aligned", ALIGNED_ONLY)
def test_pan_keeps_source_in_image_space(window, aligned):
    view, page = window.canvas, window.page
    set_mode(window, aligned)
    window.tools.set_clone_size(24)
    view.set_zoom(2.0)
    view.centerOn(400, 300)
    QTest.qWait(10)
    select_source(window, vp(view, 450, 250))
    QTest.qWait(500)
    S = QPointF(window.scene_.clone_source)
    drag(view, [vp(view, 410, 300), vp(view, 440, 305)])
    off1 = offset_between(S, sp(view, vp(view, 410, 300)))
    sv_before = view.mapFromScene(S)
    # Pan with Space + drag
    QTest.keyPress(view, Qt.Key.Key_Space)
    QTest.mousePress(view.viewport(), L, NM, QPoint(500, 400))
    QTest.mouseMove(view.viewport(), QPoint(420, 350))
    QTest.mouseRelease(view.viewport(), L, NM, QPoint(420, 350))
    QTest.keyRelease(view, Qt.Key.Key_Space)
    sv_after = view.mapFromScene(S)
    assert (sv_after.x() - sv_before.x(), sv_after.y() - sv_before.y()) == (-80, -50)  # screen shift = the pan
    assert window.scene_.clone_source == S  # the source is tied to the image, not the screen
    assert page.undo_stack.count() == 1  # panning did not paint
    # Second stroke: at a place where the source does not fall into the area painted by the first stroke (398..452 × 288..317)
    T2 = vp(view, 300, 400)
    drag(view, [T2, vp(view, 340, 405)])
    t2 = sp(view, T2)
    off = off1 if aligned else offset_between(S, t2)
    assert_cloned_at(page, t2, off)
    if aligned:
        assert window.scene_.clone_offset == off1  # the panning did not break the relationship
    else:
        assert abs(t2.x() + off.x() - S.x()) <= 0.5 and abs(t2.y() + off.y() - S.y()) <= 0.5  # again started from S
        bb, _, _ = marker_bbox(window, (300, 400))
        cx, cy = center(bb)
        assert abs(cx - sv_after.x()) <= 3 and abs(cy - sv_after.y()) <= 3  # the marker is at the image's point S


# =============================================================== continuity, undo, saving
@pytest.mark.parametrize("aligned", MODES)
def test_drag_is_continuous_in_both_modes(window, aligned):
    view, page = window.canvas, window.page
    set_mode(window, aligned)
    window.tools.set_clone_size(14)
    select_source(window, vp(view, 300, 100))  # along the path the source also stays inside the image
    pts = [vp(view, 100, 300), vp(view, 340, 300), vp(view, 340, 450), vp(view, 120, 520)]  # big jumps
    drag(view, pts, steps=2)
    for a, b in zip(pts, pts[1:]):
        for i in range(0, 21):
            f = i / 20
            sx, sy = sp(view, QPoint(round(a.x() + (b.x() - a.x()) * f), round(a.y() + (b.y() - a.y()) * f))).toTuple()
            assert page.paint.pixelColor(int(sx), int(sy)).alpha() == 255, (sx, sy)


@pytest.mark.parametrize("aligned", MODES)
def test_undo_redo_one_step_per_stroke(window, aligned):
    view, page = window.canvas, window.page
    set_mode(window, aligned)
    select_source(window, vp(view, 560, 130))
    drag(view, [vp(view, 200, 330), vp(view, 260, 340), vp(view, 300, 400), vp(view, 340, 380)])
    assert page.undo_stack.count() == 1
    first = page.paint.copy()
    drag(view, [vp(view, 150, 470), vp(view, 230, 480)])
    assert page.undo_stack.count() == 2
    both = page.paint.copy()
    window.undo()
    assert page.paint == first
    window.undo()
    assert page.paint_is_empty() and not page.is_dirty
    window.redo()
    assert page.paint == first
    window.redo()
    assert page.paint == both
    assert window.act_undo.toolTip().startswith("Geri al: Klonlama")


@pytest.mark.parametrize("aligned", MODES)
def test_save_and_reopen_keep_cloned_pixels(tmp_path, pattern_png, aligned):
    settings = make_settings(tmp_path)
    w = open_window(tmp_path, pattern_png, settings=settings)
    w.canvas.actual_size()
    w.canvas.centerOn(400, 300)
    w.tools.set_tool(Tool.CLONE)
    set_mode(w, aligned)
    view = w.canvas
    root = w.project.root
    select_source(w, vp(view, 560, 130))
    w.tools.set_clone_size(30)
    drag(view, [vp(view, 150, 350), vp(view, 280, 380)])
    w.tools.set_clone_size(90)
    drag(view, [vp(view, 150, 480), vp(view, 300, 490)])
    expected_paint = w.page.paint.copy()
    expected_image = compose_page(w.page)
    assert w.save_project()
    w.close()
    w2 = MainWindow(settings=settings)
    w2.resize(1300, 900)
    w2.show()
    assert w2.open_project(root)
    page = w2.project.pages[0]
    page.ensure_loaded()
    assert page.paint == expected_paint and compose_page(page) == expected_image
    assert w2.tools.clone_aligned is aligned  # mod tercihi de korundu
    assert not w2.project.is_dirty
    w2.project.discard_recovery()
    w2.close()
