"""Phase 6: project save / load, recovery, autosave, recent projects."""
import hashlib
import json

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtTest import QTest

from mangaeditor.core.commands import AddTextCommand, MergePageCommand
from mangaeditor.core.compose import compose_page
from mangaeditor.core.project import Project, ProjectError
from mangaeditor.core.stroke import BRUSH, ERASER, StrokeSession
from mangaeditor.core.text_data import TextData
from mangaeditor.ui.main_window import MainWindow

from conftest import make_manga_image, make_settings, make_ttf, open_window


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stroke(page, mode, pts, color="#ffffff", size=30):
    s = StrokeSession(page, mode, size, QColor(color), 0.8)
    for p in pts:
        s.add_point(QPointF(*p))
    page.undo_stack.push(s.finish())


@pytest.fixture
def images(tmp_path, qapp):
    out = []
    for i in range(2):
        p = tmp_path / "kaynak" / f"s{i + 1}.png"
        p.parent.mkdir(exist_ok=True)
        make_manga_image().save(str(p))
        out.append(p)
    return out


def new_window(tmp_path):
    w = MainWindow(settings=make_settings(tmp_path))
    w.resize(1300, 900)
    w.show()
    QTest.qWaitForWindowExposed(w)
    return w


def build_edited_project(tmp_path, images):
    w = open_window(tmp_path, images)
    ttf = tmp_path / "MangaRoundTrip.ttf"
    make_ttf(ttf, "Manga RoundTrip")
    p1, p2 = w.project.pages
    w.switch_to_page(0)
    assert w.load_fonts([ttf]) == ["Manga RoundTrip"]
    stroke(p1, BRUSH, [(170, 230), (430, 230)])
    stroke(p1, ERASER, [(250, 230), (300, 230)], size=10)
    t1 = TextData(id="t1", text="Bu bir\nmanga sayfası", x=150, y=140, width=300, height=180, rotation=12.5,
                  font_family="Manga RoundTrip", font_size=40, bold=True, italic=True, color="#ff112233",
                  align_h="left", align_v="bottom", line_spacing=1.3, letter_spacing=2.5,
                  stroke_enabled=True, stroke_width=4, stroke_color="#ffeeeeee",
                  shadow_enabled=True, shadow_color="#80000000", shadow_dx=-2, shadow_dy=5,
                  bg_enabled=True, bg_color="#c0ffffff", bg_radius=9)
    p1.undo_stack.push(AddTextCommand(p1, t1))
    w.switch_to_page(1)
    p2.undo_stack.push(AddTextCommand(p2, TextData(id="t2", text="Birleşik", x=300, y=500, font_size=50)))
    p2.undo_stack.push(MergePageCommand(p2))
    p2.undo_stack.push(AddTextCommand(p2, TextData(id="t3", text="Sonradan", x=100, y=800)))
    expected = {
        "order": [p.id for p in w.project.pages],
        "texts": {p.id: p.texts for p in w.project.pages},
        "images": {p.id: compose_page(p) for p in w.project.pages},
        "paint": {p.id: p.paint.copy() for p in w.project.pages},
    }
    return w, expected


def test_save_close_reopen_keeps_everything(tmp_path, images):
    w, exp = build_edited_project(tmp_path, images)
    root = w.project.root
    originals = {p: sha(root / p.original_rel) for p in w.project.pages}
    assert w.save_project()
    assert not w.project.is_dirty
    assert "●" not in w.tabbar.tabText(0)
    for page, h in originals.items():
        assert sha(root / page.original_rel) == h  # originals did not change
    assert (root / "fonts" / "MangaRoundTrip.ttf").exists()  # font was copied into the project
    data = json.loads((root / "project.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in data["pages"]] == exp["order"]
    assert w.close()

    # The application closed; the font was also removed from memory
    assert "Manga RoundTrip" not in QFontDatabase.families()
    w2 = new_window(tmp_path)
    assert w2.open_project(root)
    assert "Manga RoundTrip" in QFontDatabase.families()  # the project font was loaded again
    assert [p.id for p in w2.project.pages] == exp["order"]
    for page in w2.project.pages:
        assert page.texts == exp["texts"][page.id]
        page.ensure_loaded()
        assert page.paint == exp["paint"][page.id]
        assert compose_page(page) == exp["images"][page.id]
    assert not w2.project.is_dirty
    # The merged page has no text object; the one added later exists
    assert [t.id for t in w2.project.pages[1].texts] == ["t3"]
    w2.close()


def test_unsaved_changes_prompt_on_close(tmp_path, images, dialogs):
    w = open_window(tmp_path, images)
    stroke(w.page, BRUSH, [(10, 10)])
    assert w.project.is_dirty
    w.close()
    assert any(k == "question" and "Kaydedilsin" in t for k, t in dialogs)


def test_cancel_close_keeps_window(tmp_path, images, monkeypatch):
    w = open_window(tmp_path, images)
    stroke(w.page, BRUSH, [(10, 10)])
    monkeypatch.setattr(w, "ask_unsaved", lambda: "cancel")
    assert not w.close()
    assert w.project is not None
    monkeypatch.setattr(w, "ask_unsaved", lambda: "save")
    assert w.close()
    reopened = Project.open(tmp_path / "projeler" / "Test")
    reopened.pages[0].ensure_loaded()
    assert reopened.pages[0].paint.pixelColor(10, 10).alpha() > 0


def test_crash_recovery(tmp_path, images):
    w, exp = build_edited_project(tmp_path, images)
    root = w.project.root
    w.write_recovery()
    assert Project.has_recovery(root)
    # Beklenmedik kapanma: proje kaydedilmeden pencere yok olur.
    w.project = None
    w.close()
    # Nothing was saved: there are no pages in the project file; everything must come from the recovery.
    assert json.loads((root / "project.json").read_text(encoding="utf-8"))["pages"] == []

    w2 = new_window(tmp_path)
    assert w2.open_project(root)  # sahte diyalog "Evet, kurtar" der
    assert w2.project.is_dirty
    for page in w2.project.pages:
        assert page.texts == exp["texts"][page.id]
    assert w2.save_project()
    assert not Project.has_recovery(root)
    w2.close()
    w3 = new_window(tmp_path)
    w3.open_project(root)
    for page in w3.project.pages:
        page.ensure_loaded()
        assert compose_page(page) == exp["images"][page.id]
    w3.close()


def test_declining_recovery_discards_it(tmp_path, images, monkeypatch):
    w, _ = build_edited_project(tmp_path, images)
    root = w.project.root
    w.write_recovery()
    w.project = None
    w.close()
    w2 = new_window(tmp_path)
    monkeypatch.setattr(w2, "ask_recovery", lambda root: False)
    w2.open_project(root)
    assert not Project.has_recovery(root)
    assert all(p.texts == () for p in w2.project.pages)
    w2.close()


def test_autosave(tmp_path, images):
    w = open_window(tmp_path, images)
    stroke(w.page, BRUSH, [(10, 10)])
    w.act_autosave.setChecked(True)
    w.autosave()
    assert not w.project.is_dirty
    stroke(w.page, BRUSH, [(20, 20)])
    w.act_autosave.setChecked(False)
    w.autosave()
    assert w.project.is_dirty  # it does not save while turned off
    w.project.discard_recovery()
    w.close()


def test_last_project_remembered(tmp_path, images):
    settings = make_settings(tmp_path)
    w = open_window(tmp_path, images, settings=settings)
    root = w.project.root
    w.save_project()
    w.close()
    w2 = MainWindow(settings=settings)
    assert str(root) in w2.recent_projects()
    w2.restore_last_project()
    assert w2.project is not None and w2.project.root == root
    w2.close()


def test_open_invalid_project(tmp_path, qapp):
    (tmp_path / "bos").mkdir()
    with pytest.raises(ProjectError):
        Project.open(tmp_path / "bos")
    (tmp_path / "bozuk").mkdir()
    (tmp_path / "bozuk" / "project.json").write_text("{bozuk json", encoding="utf-8")
    with pytest.raises(ProjectError):
        Project.open(tmp_path / "bozuk")


def test_missing_original_warns_but_opens(tmp_path, images, dialogs):
    w = open_window(tmp_path, images)
    root = w.project.root
    w.save_project()
    missing = root / w.project.pages[1].original_rel
    w.close()
    missing.unlink()
    w2 = new_window(tmp_path)
    assert w2.open_project(root)
    assert any(k == "warning" and "eksik" in t for k, t in dialogs)
    w2.switch_to_page(0)
    assert w2.scene_ is not None  # the healthy page works
    w2.close()


def test_project_folder_structure(tmp_path, qapp):
    p = Project.create(tmp_path, "Bölüm 12")
    for d in ("originals", "pages", "fonts", "exports"):
        assert (p.root / d).is_dir()
    assert (p.root / "project.json").exists()
    with pytest.raises(ProjectError):
        Project.create(tmp_path, "Bölüm 12")  # does not overwrite
