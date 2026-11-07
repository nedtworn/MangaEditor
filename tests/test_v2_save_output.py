"""Saving (Ctrl+S / Save on exit) also writes the edited image to the target file."""
import hashlib
import json
import os
import shutil
import stat

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest

from mangaeditor.core.commands import AddTextCommand
from mangaeditor.core.compose import compose_page
from mangaeditor.core.project import Project
from mangaeditor.core.stroke import BRUSH, StrokeSession
from mangaeditor.core.text_data import TextData
from mangaeditor.ui.main_window import MainWindow

from conftest import make_manga_image, make_settings, open_window


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rgb32(img: QImage) -> QImage:
    return img.convertToFormat(QImage.Format.Format_RGB32)


def edit(page, color="#ffffff", text="Merhaba"):
    s = StrokeSession(page, BRUSH, 40, QColor(color))
    s.add_point(QPointF(170, 230))
    s.add_point(QPointF(430, 230))
    page.undo_stack.push(s.finish())
    page.undo_stack.push(AddTextCommand(page, TextData(text=text, id=f"t{page.id[-6:]}{len(page.texts)}",
                                                       x=170, y=150, width=260, height=150, font_size=40)))


def mean_abs_diff(a: QImage, b: QImage) -> float:
    a, b = rgb32(a), rgb32(b)
    total = n = 0
    for y in range(0, a.height(), 9):
        for x in range(0, a.width(), 9):
            ca, cb = a.pixelColor(x, y), b.pixelColor(x, y)
            total += abs(ca.red() - cb.red()) + abs(ca.green() - cb.green()) + abs(ca.blue() - cb.blue())
            n += 3
    return total / n


@pytest.fixture
def sources(tmp_path, qapp):
    """Source images in two different folders, plus a neighbor file that is not in the project."""
    a, b = tmp_path / "bolumA", tmp_path / "bolumB"
    a.mkdir()
    b.mkdir()
    files = {
        "a1": a / "001.png",
        "b2": b / "002.jpg",
        "a3": a / "003.webp",
        "neighbor": a / "komsu.png",  # not in the project, must never change
    }
    make_manga_image(800, 1200).save(str(files["a1"]), "PNG")
    make_manga_image(900, 1300).save(str(files["b2"]), "JPG", 95)
    make_manga_image(700, 1000).save(str(files["a3"]), "WEBP", 100)
    make_manga_image(500, 500).save(str(files["neighbor"]), "PNG")
    return files


@pytest.fixture
def window(tmp_path, sources):
    w = open_window(tmp_path, [sources["a1"], sources["b2"], sources["a3"]])
    yield w
    w.project and w.project.discard_recovery()
    w.close()


def test_ctrl_s_writes_edited_image_over_source(window, sources):
    page = window.project.pages[0]
    original_copy = window.project.root / page.original_rel
    original_hash = sha(original_copy)
    window.switch_to_page(0)
    edit(page)
    assert "●" in window.tabbar.tabText(0)
    QTest.keyClick(window, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    written = QImage(str(sources["a1"]))
    assert rgb32(written) == rgb32(compose_page(page))  # PNG is lossless: exactly the edited version
    assert sha(original_copy) == original_hash  # projedeki orijinal korunur
    assert not page.output_stale and not window.project.needs_save
    assert "●" not in window.tabbar.tabText(0)
    assert window.project.output_target(page) == sources["a1"].resolve()


def test_only_changed_pages_written_and_nothing_else_touched(window, sources):
    project = window.project
    p1, p2, p3 = project.pages
    hashes = {k: sha(v) for k, v in sources.items()}
    orig_hashes = {p.id: sha(project.root / p.original_rel) for p in project.pages}
    edit(p1)
    edit(p2, color="#ff0000")
    assert window.save_project()
    assert sha(sources["a1"]) != hashes["a1"]
    assert sha(sources["b2"]) != hashes["b2"]
    assert sha(sources["a3"]) == hashes["a3"]  # the unedited page was not written
    assert sha(sources["neighbor"]) == hashes["neighbor"]  # another file in the same folder
    assert {p.id: sha(project.root / p.original_rel) for p in project.pages} == orig_hashes
    assert mean_abs_diff(QImage(str(sources["b2"])), compose_page(p2)) < 3.0  # JPG, high quality
    # Then only page 3 changes, so only it is written
    h1, h2 = sha(sources["a1"]), sha(sources["b2"])
    edit(p3)
    assert window.save_project()
    assert (sha(sources["a1"]), sha(sources["b2"])) == (h1, h2)
    assert sha(sources["a3"]) != hashes["a3"]
    assert rgb32(QImage(str(sources["a3"]))) == rgb32(compose_page(p3))  # WEBP quality 100 = lossless
    # The written files have the original size
    for key, page in (("a1", p1), ("b2", p2), ("a3", p3)):
        img = QImage(str(sources[key]))
        assert (img.width(), img.height()) == (page.size.width(), page.size.height())
    assert not list(sources["a1"].parent.glob("*.tmp")) and not list(sources["b2"].parent.glob("*.tmp"))


def test_quit_with_save_writes_image(tmp_path, sources, monkeypatch):
    w = open_window(tmp_path, [sources["a1"]])
    page = w.project.pages[0]
    edit(page)
    expected = rgb32(compose_page(page))
    root = w.project.root
    monkeypatch.setattr(w, "ask_unsaved", lambda: "save")
    assert w.close()
    assert rgb32(QImage(str(sources["a1"]))) == expected
    data = json.loads((root / "project.json").read_text(encoding="utf-8"))
    assert data["pages"][0]["output_pending"] is False
    assert data["pages"][0]["texts"]  # proje verisi de kaydedildi


def test_quit_with_discard_does_not_write(tmp_path, sources):
    w = open_window(tmp_path, [sources["a1"]])
    before = sha(sources["a1"])
    edit(w.project.pages[0])
    w.close()  # the test dialog answers "Save"
    assert sha(sources["a1"]) == before


def test_same_source_twice_never_shares_a_target(tmp_path, sources):
    w = open_window(tmp_path, [sources["a1"], sources["a1"]])
    p1, p2 = w.project.pages
    t1, t2 = w.project.output_target(p1), w.project.output_target(p2)
    assert t1 == sources["a1"].resolve()
    assert t2.parent == w.project.exports_dir and t1 != t2
    edit(p1, color="#ff0000")
    edit(p2, color="#0000ff")
    assert w.save_project()
    assert rgb32(QImage(str(t1))) == rgb32(compose_page(p1))
    assert rgb32(QImage(str(t2))) == rgb32(compose_page(p2))
    w.project.discard_recovery()
    w.close()


def test_unsafe_targets_are_rejected(window, sources, dialogs):
    project = window.project
    p1, p2, _ = project.pages
    bad = [
        project.root / p1.original_rel,          # the protected original copy
        project.root / p2.original_rel,          # the original of another page
        project.root / "pages" / "x.png",        # paint layers
        project.root / "fonts" / "x.png",
        project.root / "ust.png",                # project root
        sources["b2"],                           # the target of another page
        sources["a1"].with_suffix(".bmp"),       # unsupported format
        sources["a1"].parent / "yok" / "x.png",  # folder that does not exist
    ]
    for target in bad:
        assert not window.set_output_target(p1, target), target
    assert project.output_target(p1) == sources["a1"].resolve()  # did not change
    assert sum(1 for k, t in dialogs if k == "warning" and "kullanılamaz" in t) == len(bad)
    # A valid new target is accepted and is written to on save; the old source no longer changes
    new_target = sources["a1"].parent / "001_tr.png"
    before = sha(sources["a1"])
    assert window.set_output_target(p1, new_target)
    edit(p1)
    assert window.save_project()
    assert rgb32(QImage(str(new_target))) == rgb32(compose_page(p1))
    assert sha(sources["a1"]) == before
    assert window.set_output_target(project.pages[2], project.exports_dir / "ozel.png")  # exports/ serbest


def test_write_failure_keeps_project_data_and_retries(window, sources, dialogs):
    project = window.project
    page = project.pages[0]
    before = sha(sources["a1"])
    os.chmod(sources["a1"], stat.S_IREAD)  # salt okunur
    try:
        edit(page, text="Kaybolmamalı")
        assert window.save_project() is False
        assert any(k == "warning" and "yazılamadı" in t for k, t in dialogs)
        assert sha(sources["a1"]) == before  # was not damaged
        assert not list(sources["a1"].parent.glob("*.tmp"))
        data = json.loads((project.root / "project.json").read_text(encoding="utf-8"))
        assert data["pages"][0]["texts"][0]["text"] == "Kaybolmamalı"  # project data was saved
        assert data["pages"][0]["output_pending"] is True  # yeniden denenecek
        assert page.output_stale and "●" in window.tabbar.tabText(0)
    finally:
        os.chmod(sources["a1"], stat.S_IWRITE | stat.S_IREAD)
    assert window.save_project()  # retries once the permission is fixed
    assert rgb32(QImage(str(sources["a1"]))) == rgb32(compose_page(page))
    assert not page.output_stale


def test_pending_output_survives_restart(tmp_path, sources):
    settings = make_settings(tmp_path)
    w = open_window(tmp_path, [sources["a1"]], settings=settings)
    root = w.project.root
    edit(w.project.pages[0])
    shutil.rmtree(sources["a1"].parent)  # the target folder no longer exists
    assert w.save_project() is False
    w.close()
    sources["a1"].parent.mkdir()
    w2 = MainWindow(settings=settings)
    w2.open_project(root)
    page = w2.project.pages[0]
    assert page.output_stale and w2.project.needs_save
    assert w2.save_project()
    page.ensure_loaded()
    assert rgb32(QImage(str(sources["a1"]))) == rgb32(compose_page(page))
    w2.close()


def test_autosave_does_not_overwrite_sources_but_keeps_marker(window, sources, dialogs):
    before = sha(sources["a1"])
    edit(window.project.pages[0])
    window.act_autosave.setChecked(True)
    window.autosave()
    assert not window.project.is_dirty  # project data was saved
    assert sha(sources["a1"]) == before  # the source image is not written by autosave
    assert window.project.needs_save and "●" in window.tabbar.tabText(0)
    window.close()  # an image is unwritten, so closing asks again
    assert any(k == "question" and "Kaydedilsin" in t for k, t in dialogs)


def test_undo_after_save_rewrites_on_next_save(window, sources):
    page = window.project.pages[0]
    window.switch_to_page(0)
    edit(page)
    assert window.save_project()
    window.undo()
    window.undo()  # both edits were undone
    assert page.output_stale
    assert window.save_project()
    assert rgb32(QImage(str(sources["a1"]))) == rgb32(compose_page(page))
    assert rgb32(compose_page(page)) == rgb32(page.original)


def test_legacy_project_without_output_uses_exports(tmp_path, sources, qapp):
    w = open_window(tmp_path, [sources["a1"]])
    root = w.project.root
    w.save_project()
    w.close()
    data = json.loads((root / "project.json").read_text(encoding="utf-8"))
    for p in data["pages"]:
        p.pop("output")
        p.pop("output_pending")
    (root / "project.json").write_text(json.dumps(data), encoding="utf-8")
    before = sha(sources["a1"])
    project = Project.open(root)
    page = project.pages[0]
    assert project.output_target(page) == project.exports_dir / "001.png"
    page.ensure_loaded()
    edit(page)
    from mangaeditor.core.export import write_page_outputs
    written, errors = write_page_outputs(project)
    assert errors == [] and written == [project.exports_dir / "001.png"]
    assert sha(sources["a1"]) == before


def test_manual_export_still_works_elsewhere(window, tmp_path):
    edit(window.project.pages[1])
    written, errors = window.export([0, 1], tmp_path / "baska_yer", "PNG")
    assert errors == [] and [p.name for p in written] == ["001_001.png", "002_002.png"]
