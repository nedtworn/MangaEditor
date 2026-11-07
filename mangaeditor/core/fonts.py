"""External font (TTF/OTF) management.

Fonts added to a project are copied into the project's fonts/ folder, so the same fonts
load when the project is opened on another computer.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QFontDatabase

from ..i18n import tr

FONT_EXTENSIONS = (".ttf", ".otf")
FONT_FILTER = "Font dosyaları (*.ttf *.otf)"  # file dialog filter; translate with i18n.tr at use


class FontLoadError(Exception):
    pass


class FontManager(QObject):
    fontsChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._loaded: dict[str, tuple[int, list[str]]] = {}  # yol -> (id, aileler)

    @property
    def loaded_families(self) -> list[str]:
        seen: list[str] = []
        for _id, fams in self._loaded.values():
            for f in fams:
                if f not in seen:
                    seen.append(f)
        return seen

    def load_file(self, path: str | Path) -> list[str]:
        path = Path(path).resolve()
        if path.suffix.lower() not in FONT_EXTENSIONS:
            raise FontLoadError(tr("Desteklenmeyen font türü: {name} (yalnızca TTF/OTF)", name=path.name))
        key = str(path).lower()
        if key in self._loaded:
            return list(self._loaded[key][1])
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            raise FontLoadError(tr("Font yüklenemedi: {name}", name=path.name))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if not families:
            QFontDatabase.removeApplicationFont(font_id)
            raise FontLoadError(tr("Font ailesi okunamadı: {name}", name=path.name))
        self._loaded[key] = (font_id, list(families))
        self.fontsChanged.emit()
        return list(families)

    def import_font(self, source: str | Path, fonts_dir: str | Path | None) -> list[str]:
        """Copies the font (if given) into the project's fonts/ folder and loads it."""
        source = Path(source)
        if fonts_dir is None:
            return self.load_file(source)
        fonts_dir = Path(fonts_dir)
        fonts_dir.mkdir(parents=True, exist_ok=True)
        target = fonts_dir / source.name
        if target.resolve() != source.resolve():
            if target.exists() and target.read_bytes() != source.read_bytes():
                stem, ext = source.stem, source.suffix
                n = 2
                while (fonts_dir / f"{stem}_{n}{ext}").exists():
                    n += 1
                target = fonts_dir / f"{stem}_{n}{ext}"
            if not target.exists():
                # Validate first, then copy: a broken file must not enter the project.
                families = self.load_file(source)
                shutil.copy2(source, target)
                self._rekey(source, target)
                return families
        return self.load_file(target)

    def _rekey(self, old: Path, new: Path) -> None:
        k_old, k_new = str(old.resolve()).lower(), str(new.resolve()).lower()
        if k_old in self._loaded:
            self._loaded[k_new] = self._loaded.pop(k_old)

    def load_dir(self, fonts_dir: str | Path) -> tuple[list[str], list[str]]:
        """Loads all fonts in the folder. Returns (families, error messages)."""
        fams: list[str] = []
        errors: list[str] = []
        d = Path(fonts_dir)
        if not d.is_dir():
            return fams, errors
        for p in sorted(d.iterdir()):
            if p.suffix.lower() in FONT_EXTENSIONS:
                try:
                    fams.extend(self.load_file(p))
                except FontLoadError as e:
                    errors.append(str(e))
        return fams, errors

    def unload_all(self) -> None:
        for font_id, _ in self._loaded.values():
            QFontDatabase.removeApplicationFont(font_id)
        if self._loaded:
            self._loaded.clear()
            self.fontsChanged.emit()

    @staticmethod
    def is_available(family: str) -> bool:
        return family in QFontDatabase.families()
