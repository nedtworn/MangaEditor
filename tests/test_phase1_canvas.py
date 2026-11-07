"""Phase 1: opening images, canvas, zoom and pan."""
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest

from mangaeditor.core.imageio import ImageLoadError, load_image
from mangaeditor.ui.main_window import MainWindow  # noqa: F401

from conftest import open_window


@pytest.mark.parametrize("ext", ["png", "jpg", "jpeg", "webp"])
def test_load_supported_formats(manga_files, ext):
    img = load_image(manga_files[ext])
    assert (img.width(), img.height()) == (800, 1200)


def test_load_invalid_file(tmp_path, qapp):
    bad = tmp_path / "bozuk.png"
    bad.write_bytes(b"not an image")
    with pytest.raises(ImageLoadError):
        load_image(bad)


@pytest.fixture
def window(qapp, manga_files, tmp_path):
    w = open_window(tmp_path, manga_files["png"], (1200, 800))
    qapp.processEvents()
    yield w
    w.close()


def test_open_image_centers_and_fits(window):
    view = window.canvas
    view.fit_to_window()
    vp = view.viewport().rect()
    # The whole image must be visible and centered.
    top_left = view.mapFromScene(QPointF(0, 0))
    bottom_right = view.mapFromScene(QPointF(800, 1200))
    assert vp.contains(top_left) and vp.contains(bottom_right)
    cx = (top_left.x() + bottom_right.x()) / 2
    cy = (top_left.y() + bottom_right.y()) / 2
    assert abs(cx - vp.center().x()) <= 2
    assert abs(cy - vp.center().y()) <= 2


def test_actual_size_and_zoom_buttons(window):
    view = window.canvas
    view.actual_size()
    assert view.zoom() == pytest.approx(1.0)
    assert window.zoom_label.text() == "100%"
    view.zoom_in()
    assert view.zoom() == pytest.approx(1.2)
    view.zoom_out()
    view.zoom_out()
    assert view.zoom() == pytest.approx(1 / 1.2)


def test_wheel_zoom_keeps_point_under_mouse(window, qapp):
    view = window.canvas
    view.actual_size()
    pos = QPointF(300, 250)
    before = view.mapToScene(pos.toPoint())
    ev = QWheelEvent(pos, view.viewport().mapToGlobal(pos), QPoint(0, 0), QPoint(0, 120),
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    qapp.sendEvent(view.viewport(), ev)
    assert view.zoom() == pytest.approx(1.2)
    after = view.mapToScene(pos.toPoint())
    assert abs(after.x() - before.x()) < 2 and abs(after.y() - before.y()) < 2


def test_space_drag_pans(window, qapp):
    view = window.canvas
    view.actual_size()
    view.setFocus()
    start_center = view.mapToScene(view.viewport().rect().center())
    QTest.keyPress(view, Qt.Key.Key_Space)
    vp = view.viewport()
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(400, 400))
    QTest.mouseMove(vp, QPoint(300, 350))
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(300, 350))
    QTest.keyRelease(view, Qt.Key.Key_Space)
    end_center = view.mapToScene(view.viewport().rect().center())
    # When the mouse moves left/up, the image must move with it.
    assert end_center.x() - start_center.x() == pytest.approx(100, abs=2)
    assert end_center.y() - start_center.y() == pytest.approx(50, abs=2)
    assert not view.is_panning()
