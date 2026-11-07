"""Eyedropper: only a single pixel; no sampling size setting; the tool stays
selected after a color is picked."""
import inspect

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QSlider, QSpinBox

from mangaeditor.core import compose
from mangaeditor.core.compose import sample_color
from mangaeditor.core.page import PageDocument
from mangaeditor.ui.tools import Tool, ToolSettings

from conftest import open_window


def rgb(c: QColor):
    return (c.red(), c.green(), c.blue())


@pytest.fixture
def gradient_page(qapp):
    """A page whose every pixel color can be computed from its position."""
    img = QImage(100, 80, QImage.Format.Format_RGB32)
    for y in range(80):
        for x in range(100):
            img.setPixelColor(x, y, QColor((x * 7 + y) % 256, (y * 5) % 256, (x * 3 + y * 11) % 256))
    return PageDocument.from_image(img, "grad")


def test_samples_exactly_the_pixel_under_cursor(gradient_page):
    for x, y in ((0, 0), (37, 21), (99, 79), (50.9, 40.2), (12.5, 3.5)):
        c = sample_color(gradient_page, QPointF(x, y))
        assert rgb(c) == rgb(gradient_page.original.pixelColor(int(x), int(y)))
    # The neighboring pixel is not mixed in: two side-by-side pixels have different colors
    assert rgb(sample_color(gradient_page, QPointF(40.5, 30.5))) != rgb(sample_color(gradient_page, QPointF(41.5, 30.5)))


def test_outside_image_returns_none(gradient_page):
    for p in ((-0.5, 10), (-3, 10), (100, 10), (10, 80), (10, -0.1)):
        assert sample_color(gradient_page, QPointF(*p)) is None


def test_sampling_size_feature_is_removed(qapp):
    assert list(inspect.signature(sample_color).parameters) == ["page", "point", "include_texts"]
    assert not hasattr(compose, "sample_rect")
    tools = ToolSettings()
    for name in ("eyedropper_size", "set_eyedropper_size", "eyedropperChanged", "MAX_SAMPLE"):
        assert not hasattr(tools, name) and not hasattr(ToolSettings, name), name


@pytest.fixture
def window(tmp_path, manga_files):
    w = open_window(tmp_path, manga_files["png"])
    w.canvas.actual_size()
    w.canvas.centerOn(500, 700)
    yield w
    w.close()


def click(view, x, y, mods=Qt.KeyboardModifier.NoModifier):
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, mods, view.mapFromScene(QPointF(x, y)))


def test_panel_has_no_size_controls(window):
    panel = window.side_panel.pages[Tool.EYEDROPPER]
    assert panel.findChildren(QSlider) == [] and panel.findChildren(QSpinBox) == []


def test_stays_active_after_multiple_picks(window):
    view = window.canvas
    QTest.keyClick(window, Qt.Key.Key_I)
    assert window.tools.tool == Tool.EYEDROPPER
    click(view, 650, 950)  # red square
    assert rgb(window.tools.brush_color) == (200, 30, 30)
    assert window.tools.tool == Tool.EYEDROPPER
    click(view, 300, 200)  # inside the bubble (white)
    assert rgb(window.tools.brush_color) == (255, 255, 255)
    click(view, 50, 600)  # arka plan grisi
    assert rgb(window.tools.brush_color) == (235, 235, 235)
    assert window.tools.tool == Tool.EYEDROPPER  # the same tool unless the user changes it
    QTest.keyClick(window, Qt.Key.Key_B)
    assert window.tools.tool == Tool.BRUSH


def test_single_pixel_on_canvas_at_edge_of_colored_square(window):
    """No blending on the edge of the red square (600..699, 900..999).
    At 4x zoom a view pixel is 0.25 image pixels: sub-pixel precision."""
    view = window.canvas
    window.tools.set_tool(Tool.EYEDROPPER)
    view.set_zoom(4.0)
    view.centerOn(600, 950)
    QTest.qWait(10)
    click(view, 600.5, 950.5)  # the first column of the square
    assert rgb(window.tools.brush_color) == (200, 30, 30)
    click(view, 599.5, 950.5)  # hemen solu: arka plan
    assert rgb(window.tools.brush_color) == (235, 235, 235)
    click(view, 600.5, 950.5)
    assert rgb(window.tools.brush_color) == (200, 30, 30)


def test_drag_preview_keeps_tool_and_updates_color(window):
    view = window.canvas
    window.tools.set_tool(Tool.EYEDROPPER)
    vp = view.viewport()
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, view.mapFromScene(QPointF(50, 600)))
    QTest.mouseMove(vp, view.mapFromScene(QPointF(650, 950)))
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       view.mapFromScene(QPointF(650, 950)))
    assert rgb(window.tools.brush_color) == (200, 30, 30)
    assert window.tools.tool == Tool.EYEDROPPER


def test_alt_click_with_brush_picks_and_keeps_brush(window):
    window.tools.set_tool(Tool.BRUSH)
    click(window.canvas, 650, 950, Qt.KeyboardModifier.AltModifier)
    assert rgb(window.tools.brush_color) == (200, 30, 30)
    assert window.tools.tool == Tool.BRUSH
    assert window.page.undo_stack.count() == 0  # renk almak boyama yapmaz
