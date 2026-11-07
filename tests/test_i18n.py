"""Interface language: every user-visible string has an English translation, placeholders
match, the English interface really is English, and the choice is saved."""
import ast
import re
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QAbstractButton, QLabel, QMenu

from mangaeditor import i18n
from mangaeditor.translations import EN
from mangaeditor.ui.main_window import MainWindow

from conftest import make_settings

ROOT = Path(__file__).resolve().parents[1]
TURKISH_LETTERS = re.compile(r"[çğıöşüÇĞİÖŞÜ]")


def tr_keys_in_code() -> dict[str, str]:
    """Literal source strings passed to tr() / tr_in(), and the other translated strings
    (tool names, shortcut labels) that are shown through a variable."""
    found: dict[str, str] = {}

    def add(node, where):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value:
            found.setdefault(node.value, where)

    for path in (ROOT / "mangaeditor").rglob("*.py"):
        if path.name == "translations.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
            if name == "tr" and node.args:
                add(node.args[0], f"{path.name}:{node.lineno}")
            elif name == "tr_in" and len(node.args) > 1:
                add(node.args[1], f"{path.name}:{node.lineno}")
            elif name == "act":  # main_window's act(sid, text, slot, tip): literal text and tip
                for index in (1, 3):
                    if len(node.args) > index:
                        add(node.args[index], f"{path.name}:{node.lineno}")
    from mangaeditor.ui.shortcuts import DEFINITIONS
    from mangaeditor.ui.tools import TOOL_LABELS

    for label in TOOL_LABELS.values():
        found.setdefault(label, "tools.TOOL_LABELS")
    for d in DEFINITIONS:
        found.setdefault(d.label, "shortcuts.DEFINITIONS")
        found.setdefault(d.group, "shortcuts.DEFINITIONS")
    return found


@pytest.fixture
def english():
    previous = i18n.current()
    i18n.force("en")
    yield
    i18n.force(previous)


def test_every_source_string_has_an_english_translation():
    missing = {k: w for k, w in tr_keys_in_code().items() if k not in EN}
    assert missing == {}, f"strings without an English translation: {missing}"


def test_translations_keep_the_same_placeholders():
    def fields(s):
        return sorted(re.findall(r"\{(\w+)\}", s))

    bad = {k: v for k, v in EN.items() if fields(k) != fields(v)}
    assert bad == {}


def test_no_stale_translations():
    """Keys that no longer exist in the code are removed, so the table stays accurate."""
    used = set(tr_keys_in_code())
    stale = [k for k in EN if k not in used]
    assert stale == [], f"unused translations: {stale}"


def test_tr_switches_language():
    assert i18n.tr_in("tr", "Kaydet") == "Kaydet"
    assert i18n.tr_in("en", "Kaydet") == "Save"
    previous = i18n.current()
    try:
        i18n.force("en")
        assert i18n.tr("Dosya") == "File"
        assert i18n.tr("Yakınlaştır") == "Zoom In"
        i18n.force("tr")
        assert i18n.tr("Dosya") == "Dosya"
    finally:
        i18n.force(previous)


def test_placeholders_are_filled_in_both_languages():
    previous = i18n.current()
    try:
        i18n.force("en")
        assert i18n.tr("{n} sayfa eklendi.", n=3) == "3 page(s) added."
        i18n.force("tr")
        assert i18n.tr("{n} sayfa eklendi.", n=3) == "3 sayfa eklendi."
    finally:
        i18n.force(previous)


def test_unknown_text_falls_back_to_source():
    previous = i18n.current()
    try:
        i18n.force("en")
        assert i18n.tr("Bu metin hiç çevrilmedi.") == "Bu metin hiç çevrilmedi."
    finally:
        i18n.force(previous)


def test_language_choice_is_saved_and_restored(tmp_path):
    settings = make_settings(tmp_path)
    assert i18n.saved_language(settings) is None
    i18n.set_language("en", settings)
    assert i18n.saved_language(settings) == "en"
    previous = i18n.current()
    try:
        assert i18n.init(settings) == "en"
        i18n.set_language("tr", settings)
        assert i18n.init(settings) == "tr"
    finally:
        i18n.force(previous)
    with pytest.raises(ValueError):
        i18n.set_language("de", settings)


def test_detect_language_maps_turkish_locale_and_others(monkeypatch):
    from PySide6.QtCore import QLocale

    monkeypatch.setattr(QLocale, "system", staticmethod(lambda: QLocale("tr_TR")))
    assert i18n.detect_language() == "tr"
    monkeypatch.setattr(QLocale, "system", staticmethod(lambda: QLocale("de_DE")))
    assert i18n.detect_language() == "en"


def _texts(widget):
    out = []
    for w in [widget, *widget.findChildren(QAbstractButton), *widget.findChildren(QLabel)]:
        if isinstance(w, (QAbstractButton, QLabel)):
            out.append(w.text())
    for m in widget.findChildren(QMenu):
        out.append(m.title())
    for a in widget.actions():
        out.append(a.text())
    menu = widget.menuBar()
    out.extend(a.text() for a in menu.actions())
    return [t for t in out if t]


def test_english_window_has_no_turkish_visible_text(qapp, tmp_path, manga_files):
    previous = i18n.current()
    i18n.force("en")
    w = None
    try:
        w = MainWindow(settings=make_settings(tmp_path))
        w.show()
        visible = _texts(w)
        for t in w.findChildren(QLabel):
            visible.append(t.text())
        # The brand name "Manga Editör" is not translated; everything else must be.
        turkish = [t for t in visible if TURKISH_LETTERS.search(t.replace("Manga Editör", ""))]
        assert turkish == [], f"Turkish text in the English interface: {turkish}"
        menus = [a.text() for a in w.menuBar().actions()]
        for english_name in ("File", "Edit", "Page", "View", "Settings"):
            assert english_name in menus, menus
        file_menu = next(m for m in w.menuBar().findChildren(QMenu) if m.title() == "File")
        file_items = [a.text() for a in file_menu.actions()]
        assert "Save" in file_items and "Open" in file_items and "New Project" in file_items, file_items
    finally:
        if w is not None:
            w.close()
        i18n.force(previous)


def test_turkish_window_keeps_turkish_menu_titles(qapp, tmp_path):
    previous = i18n.current()
    i18n.force("tr")
    try:
        w = MainWindow(settings=make_settings(tmp_path))
        menus = [a.text() for a in w.menuBar().actions()]
        assert {"Dosya", "Düzen", "Sayfa", "Görünüm", "Ayarlar"} <= set(menus)
        w.close()
    finally:
        i18n.force(previous)
