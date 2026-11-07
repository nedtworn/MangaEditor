"""Phase 7: batch export (PNG/JPG)."""
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage

from mangaeditor.core.commands import AddTextCommand
from mangaeditor.core.compose import compose_page
from mangaeditor.core.stroke import BRUSH, StrokeSession
from mangaeditor.core.text_data import TextData

from conftest import make_manga_image, open_window


@pytest.fixture
def window(tmp_path, qapp):
    paths = []
    for i, (w, h) in enumerate(((800, 1200), (1000, 1400), (700, 1000))):
        p = tmp_path / "src" / f"p{i}.png"
        p.parent.mkdir(exist_ok=True)
        make_manga_image(w, h).save(str(p))
        paths.append(p)
    w = open_window(tmp_path, paths)
    for i, page in enumerate(w.project.pages):
        s = StrokeSession(page, BRUSH, 40, QColor(255, 255, 255))
        s.add_point(QPointF(170, 230))
        s.add_point(QPointF(430, 230))
        page.undo_stack.push(s.finish())
        page.undo_stack.push(AddTextCommand(page, TextData(
            id=f"t{i}", text=f"SAYFA {i + 1}", x=150, y=170, width=300, height=120, font_size=48,
            color="#ff0000c0", stroke_enabled=True, stroke_width=3, rotation=5)))
    # Save so that page 3 can be released from memory as if it had never been opened.
    w.save_project()
    yield w
    w.close()


def test_batch_export_png_matches_canvas(window, tmp_path):
    out = tmp_path / "out_png"
    written, errors = window.export([0, 1, 2], out, "PNG")
    assert errors == []
    assert [p.name for p in written] == ["001_p0.png", "002_p1.png", "003_p2.png"]
    for path, page in zip(written, window.project.pages):
        img = QImage(str(path))
        assert (img.width(), img.height()) == (page.size.width(), page.size.height())  # no scaling
        expected = compose_page(page).convertToFormat(QImage.Format.Format_RGB32)
        assert img.convertToFormat(QImage.Format.Format_RGB32) == expected  # PNG is lossless, exact
        # Text and paint are really merged: the original text is erased, the new text is blue
        blue = [img.pixelColor(x, y) for y in range(170, 290, 2) for x in range(150, 450, 2)]
        assert sum(1 for c in blue if c.blue() > 150 and c.red() < 80) > 50


def test_export_jpg_quality_and_subset(window, tmp_path):
    out = tmp_path / "out_jpg"
    written, errors = window.export([1], out, "JPG", quality=95)
    assert errors == [] and [p.name for p in written] == ["002_p1.jpg"]
    img = QImage(str(written[0]))
    ref = compose_page(window.project.pages[1])
    # Lossy but high quality: the average pixel difference must be small
    total, n = 0, 0
    for y in range(0, img.height(), 7):
        for x in range(0, img.width(), 7):
            a, b = img.pixelColor(x, y), ref.pixelColor(x, y)
            total += abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue())
            n += 3
    assert total / n < 3.0
    low = window.export([1], tmp_path / "low", "JPG", quality=50)[0][0]
    assert low.stat().st_size < written[0].stat().st_size


def test_export_unloaded_page_and_does_not_keep_it(window, tmp_path):
    page = window.project.pages[2]
    # Release the page from memory (the never-opened page scenario)
    page.undo_stack.clear()
    page.unload()
    assert not page.is_loaded
    written, errors = window.export([2], tmp_path / "o", "PNG")
    assert errors == [] and len(written) == 1
    assert not page.is_loaded  # a batch export does not inflate the memory
    img = QImage(str(written[0]))
    assert img.pixelColor(300, 230) == QColor(255, 255, 255) or img.pixelColor(300, 230).blue() > 150


def test_export_never_touches_project_files(window, tmp_path):
    root = window.project.root
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and "exports" not in p.parts}
    window.export([0, 1, 2], root / "exports", "PNG")
    after = {p: p.read_bytes() for p in root.rglob("*") if p.is_file() and "exports" not in p.parts}
    assert before == after
    assert len(list((root / "exports").iterdir())) == 3
