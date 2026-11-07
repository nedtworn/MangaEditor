"""Phase 5: multiple pages (tabs, independence, add / remove / reorder)."""
import hashlib

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from mangaeditor.core.commands import AddTextCommand
from mangaeditor.core.stroke import BRUSH, StrokeSession
from mangaeditor.core.text_data import TextData

from conftest import make_manga_image, open_window


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def three_images(tmp_path, qapp):
    paths = []
    for i, (w, h, fmt, ext) in enumerate(((800, 1200, "PNG", "png"), (1000, 1500, "JPG", "jpg"),
                                          (640, 960, "WEBP", "webp"))):
        p = tmp_path / "kaynak" / f"bolum1_{i + 1}.{ext}"
        p.parent.mkdir(exist_ok=True)
        assert make_manga_image(w, h).save(str(p), fmt, 95 if fmt != "PNG" else -1)
        paths.append(p)
    return paths


@pytest.fixture
def window(tmp_path, three_images):
    w = open_window(tmp_path, three_images)
    yield w
    w.close()


def paint(page, x, y, color):
    s = StrokeSession(page, BRUSH, 30, QColor(color))
    s.add_point(QPointF(x, y))
    page.undo_stack.push(s.finish())


def test_pages_added_as_tabs_and_copied(window, three_images):
    project = window.project
    assert [p.name for p in project.pages] == ["bolum1_1", "bolum1_2", "bolum1_3"]
    assert window.tabbar.count() == 3
    assert "bolum1_1" in window.tabbar.tabText(0)
    for src, page in zip(three_images, project.pages):
        copied = project.root / page.original_rel
        assert copied.parent == project.originals_dir
        assert sha(copied) == sha(src)  # birebir kopya
    # Different resolutions
    assert [(p.size.width(), p.size.height()) for p in project.pages] == [(800, 1200), (1000, 1500), (640, 960)]


def test_pages_are_independent(window):
    p1, p2, _ = window.project.pages
    window.switch_to_page(0)
    paint(p1, 100, 100, "#ff0000")
    window.page.undo_stack.push(AddTextCommand(p1, TextData(id="t1", text="Sayfa 1", x=50, y=50)))
    window.switch_to_page(1)
    assert window.page is p2
    assert p2.paint.pixelColor(100, 100).alpha() == 0
    assert p2.texts == ()
    assert not window.act_undo.isEnabled()  # page 2's undo history is empty
    paint(p2, 200, 200, "#00ff00")
    window.undo()  # only affects page 2
    assert p2.paint.pixelColor(200, 200).alpha() == 0
    assert p1.paint.pixelColor(100, 100) == QColor(255, 0, 0)
    assert [t.id for t in p1.texts] == ["t1"]
    window.switch_to_page(0)
    assert "t1" in window.scene_.text_items
    window.undo()
    assert p1.texts == () and p2.texts == ()


def test_dirty_marker_on_tabs(window):
    window.switch_to_page(1)
    assert "●" not in window.tabbar.tabText(1)
    paint(window.page, 10, 10, "#000000")
    assert "●" in window.tabbar.tabText(1)
    assert "●" not in window.tabbar.tabText(0)
    assert window.windowTitle().startswith("*")


def test_reorder_by_tab_drag_and_menu(window):
    ids = [p.id for p in window.project.pages]
    window.tabbar.moveTab(0, 2)  # the same signal as dragging and dropping
    assert [p.id for p in window.project.pages] == [ids[1], ids[2], ids[0]]
    assert window.tabbar.tabText(0).endswith("1. bolum1_2")
    window.switch_to_page(2)
    window.move_current_page(-1)
    assert [p.id for p in window.project.pages] == [ids[1], ids[0], ids[2]]
    assert window.page.id == ids[0]
    assert window.project.is_dirty


def test_remove_page(window, dialogs):
    p2 = window.project.pages[1]
    original = window.project.root / p2.original_rel
    window.switch_to_page(1)
    window.remove_current_page()
    assert any("kaldırılsın" in t for k, t in dialogs if k == "question")
    # Default answer "No": the page must not be removed
    assert len(window.project.pages) == 3
    window.remove_page(1, confirm=False)
    assert len(window.project.pages) == 2 and window.tabbar.count() == 2
    assert p2 not in window.project.pages
    assert original.exists()  # the file is left on disk
    assert window.page is window.project.pages[1]


def test_view_state_per_page(window):
    window.switch_to_page(0)
    window.canvas.actual_size()
    window.canvas.zoom_in()
    z0 = window.canvas.zoom()
    window.switch_to_page(1)
    assert window.canvas.zoom() != pytest.approx(z0)  # the new page is fitted to the screen
    window.switch_to_page(0)
    assert window.canvas.zoom() == pytest.approx(z0)


def test_add_pages_rejects_bad_files(window, tmp_path, dialogs):
    bad = tmp_path / "bozuk.png"
    bad.write_bytes(b"xx")
    txt = tmp_path / "not.txt"
    txt.write_text("x")
    added = window.add_pages([bad, txt])
    assert added == []
    assert len(window.project.pages) == 3
    assert any(k == "warning" and "eklenemedi" in t for k, t in dialogs)
