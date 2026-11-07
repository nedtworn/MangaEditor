import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# the offscreen platform does not find the system fonts by itself.
os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from PySide6.QtCore import QCoreApplication, QSettings, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    QCoreApplication.setOrganizationName("MangaEditorTests")
    QCoreApplication.setApplicationName("MangaEditorTests")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    app = QApplication.instance() or QApplication([])
    yield app


def make_manga_image(width=800, height=1200) -> QImage:
    """A fake manga page with a speech bubble and an 'original text'."""
    img = QImage(width, height, QImage.Format.Format_RGB32)
    img.fill(QColor(235, 235, 235))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor(20, 20, 20))
    p.setBrush(QColor(255, 255, 255))
    p.drawEllipse(100, 100, 400, 250)
    f = QFont("Arial")
    f.setPixelSize(40)
    p.setFont(f)
    p.drawText(180, 240, "ORIGINAL")
    p.fillRect(600, 900, 100, 100, QColor(200, 30, 30))  # red square for the eyedropper test
    p.end()
    return img


def make_ttf(path, family: str) -> None:
    """Generates a TTF that is NOT installed on the system (the family name of Arial is changed)."""
    from fontTools.ttLib import TTFont

    f = TTFont(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf"))
    for rec in f["name"].names:
        if rec.nameID in (1, 4, 16):
            rec.string = family
        elif rec.nameID == 6:
            rec.string = family.replace(" ", "")
        elif rec.nameID == 3:
            rec.string = family + " test"
    f.save(str(path))


def make_otf(path, family: str) -> None:
    """Builds a real CFF-based OTF from scratch. 'A' and 'B' are filled boxes:
    it is identified by the pixels drawn with this font."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.t2CharStringPen import T2CharStringPen

    def box(width):
        pen = T2CharStringPen(width, None)
        pen.moveTo((50, 0))
        pen.lineTo((50, 700))
        pen.lineTo((width - 50, 700))
        pen.lineTo((width - 50, 0))
        pen.closePath()
        return pen.getCharString()

    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder([".notdef", "space", "A", "B"])
    fb.setupCharacterMap({32: "space", 65: "A", 66: "B"})
    charstrings = {".notdef": box(500), "space": T2CharStringPen(500, None).getCharString(),
                   "A": box(600), "B": box(600)}
    ps_name = family.replace(" ", "")
    fb.setupCFF(ps_name, {"FullName": family}, charstrings, {})
    fb.setupHorizontalMetrics({".notdef": (500, 50), "space": (500, 0), "A": (600, 50), "B": (600, 50)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": family, "styleName": "Regular", "psName": ps_name})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    fb.save(str(path))


class _FakeMessageBox:
    """In the tests, modal message boxes must not block the test: answer with the default,
    return it and record the shown messages."""

    log: list = []

    @classmethod
    def install(cls, monkeypatch):
        from PySide6.QtWidgets import QMessageBox

        import mangaeditor.ui.main_window as mw

        cls.log = []

        class Fake(QMessageBox):
            @staticmethod
            def question(parent, title, text, buttons=None, default=None):
                cls.log.append(("question", text))
                if "Kaydedilsin" in text:
                    return QMessageBox.StandardButton.Discard
                if "döndürülsün" in text:  # confirmation to reset the shortcuts to their defaults
                    return QMessageBox.StandardButton.Yes
                return default if default is not None else QMessageBox.StandardButton.Yes

            @staticmethod
            def warning(parent, title, text, *a, **k):
                cls.log.append(("warning", text))
                return QMessageBox.StandardButton.Ok

            information = warning

            def exec(self):
                cls.log.append(("box", self.text()))
                return 0

        monkeypatch.setattr(mw, "QMessageBox", Fake)
        import mangaeditor.ui.shortcuts_dialog as sd

        monkeypatch.setattr(sd, "QMessageBox", Fake)
        return cls.log


@pytest.fixture(autouse=True)
def dialogs(monkeypatch):
    return _FakeMessageBox.install(monkeypatch)


def make_settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def open_window(tmp_path, image_paths, size=(1300, 900), settings=None):
    """Window that creates a temporary project and adds the images as pages."""
    from PySide6.QtTest import QTest

    from mangaeditor.ui.main_window import MainWindow

    w = MainWindow(settings=settings or make_settings(tmp_path))
    w.resize(*size)
    w.show()
    QTest.qWaitForWindowExposed(w)
    w.create_project(tmp_path / "projeler", "Test")
    if not isinstance(image_paths, (list, tuple)):
        image_paths = [image_paths]
    w.add_pages(list(image_paths))
    QApplication.processEvents()
    return w


@pytest.fixture
def manga_files(tmp_path, qapp):
    img = make_manga_image()
    files = {}
    for ext, fmt in (("png", "PNG"), ("jpg", "JPG"), ("jpeg", "JPG"), ("webp", "WEBP")):
        path = tmp_path / f"sayfa.{ext}"
        assert img.save(str(path), fmt, 100 if fmt != "PNG" else -1)
        files[ext] = path
    return files
