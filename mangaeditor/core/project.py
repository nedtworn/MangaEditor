"""Folder-based project.

    MangaProject/
      project.json     – page order, texts, page information
      originals/       – original images copied into the project (never modified)
      pages/           – paint layer of each page (<page-id>.png, transparent PNG)
      fonts/           – TTF/OTF fonts added to the project
      exports/         – exported images (default target)
      .recovery/       – recovery copy of unsaved changes

All writes go to a temporary file first and are then moved into place, so an interrupted
save never corrupts the existing project.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from ..i18n import tr
from .imageio import ImageLoadError, is_supported_input, load_image, save_image_atomic
from .page import PageDocument
from .text_data import TextData

PROJECT_FILE = "project.json"
RECOVERY_FILE = "recovery.json"
FORMAT_ID = "manga-editor-project"
FORMAT_VERSION = 1
SUBDIRS = ("originals", "pages", "fonts", "exports")
RECOVERY_DIR = ".recovery"
# Formats an edited image can be saved in (extension → Qt format name)
OUTPUT_FORMATS = {".png": "PNG", ".jpg": "JPG", ".jpeg": "JPG", ".webp": "WEBP"}
# Places inside the project where an output image is NEVER written
PROTECTED_DIRS = ("originals", "pages", "fonts", RECOVERY_DIR)


class ProjectError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _safe_stem(stem: str) -> str:
    stem = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", stem).strip(" .")
    return stem[:80] or "sayfa"  # fallback file name ("page")


def _norm(p: Path) -> str:
    return os.path.normcase(os.path.abspath(p))


def _is_within(path: Path, folder: Path) -> bool:
    try:
        Path(os.path.abspath(path)).relative_to(Path(os.path.abspath(folder)))
        return True
    except ValueError:
        return False


class Project(QObject):
    pagesChanged = Signal()  # page added / removed / reordered
    dirtyChanged = Signal(bool)

    def __init__(self, root: Path, name: str) -> None:
        super().__init__()
        self.root = Path(root)
        self.name = name
        self.pages: list[PageDocument] = []
        self.created = _now()
        self.warnings: list[str] = []  # warnings shown to the user when the project opens
        self._structure_dirty = False
        self._last_dirty = False

    # ------------------------------------------------------------------ paths
    @property
    def project_file(self) -> Path:
        return self.root / PROJECT_FILE

    @property
    def originals_dir(self) -> Path:
        return self.root / "originals"

    @property
    def pages_dir(self) -> Path:
        return self.root / "pages"

    @property
    def fonts_dir(self) -> Path:
        return self.root / "fonts"

    @property
    def exports_dir(self) -> Path:
        return self.root / "exports"

    @property
    def recovery_dir(self) -> Path:
        return self.root / RECOVERY_DIR

    # ------------------------------------------------------------------ create / open
    @classmethod
    def create(cls, parent_dir: str | Path, name: str) -> "Project":
        name = name.strip()
        if not name:
            raise ProjectError(tr("Proje adı boş olamaz."))
        root = Path(parent_dir) / _safe_stem(name)
        if (root / PROJECT_FILE).exists():
            raise ProjectError(tr("Bu klasörde zaten bir proje var: {root}", root=root))
        if root.exists() and any(root.iterdir()):
            raise ProjectError(tr("Klasör boş değil: {root}", root=root))
        root.mkdir(parents=True, exist_ok=True)
        project = cls(root, name)
        for d in SUBDIRS:
            (root / d).mkdir(exist_ok=True)
        project.save()
        return project

    @staticmethod
    def has_recovery(root: str | Path) -> bool:
        return (Path(root) / RECOVERY_DIR / RECOVERY_FILE).exists()

    @classmethod
    def open(cls, root: str | Path, use_recovery: bool = False) -> "Project":
        root = Path(root)
        if root.is_file():
            root = root.parent
        source = root / RECOVERY_DIR / RECOVERY_FILE if use_recovery else root / PROJECT_FILE
        if not source.exists():
            raise ProjectError(tr("Proje dosyası bulunamadı: {source}", source=source))
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise ProjectError(tr("Proje dosyası okunamadı: {e}", e=e)) from e
        if raw.get("format") != FORMAT_ID:
            raise ProjectError(tr("Bu dosya bir Manga Editör projesi değil."))
        if int(raw.get("version", 0)) > FORMAT_VERSION:
            raise ProjectError(tr("Proje, uygulamanın daha yeni bir sürümüyle kaydedilmiş."))
        project = cls(root, str(raw.get("name") or root.name))
        project.created = raw.get("created", project.created)
        for d in SUBDIRS:
            (root / d).mkdir(exist_ok=True)
        seen: set[str] = set()
        for entry in raw.get("pages", []):
            try:
                page = project._page_from_entry(entry)
            except (KeyError, TypeError, ValueError) as e:
                project.warnings.append(tr("Bozuk sayfa kaydı atlandı: {e}", e=e))
                continue
            if page.id in seen:
                project.warnings.append(tr("Yinelenen sayfa atlandı: {name}", name=page.name))
                continue
            seen.add(page.id)
            if not (root / page.original_rel).exists():
                project.warnings.append(tr("Orijinal görsel eksik: {p}", p=page.original_rel))
            project.pages.append(page)
        if use_recovery:
            # Everything restored from recovery counts as unsaved; the project file is not
            # changed until the user saves.
            project._structure_dirty = True
            for page in project.pages:
                page.mark_dirty(paint_too=bool(page.paint_rel and page.paint_rel.startswith(RECOVERY_DIR)))
        project._last_dirty = project.is_dirty
        return project

    def _page_from_entry(self, entry: dict[str, Any]) -> PageDocument:
        from PySide6.QtCore import QSize

        texts = [TextData.from_dict(t) for t in entry.get("texts", [])]
        page = PageDocument(
            name=str(entry.get("name", "")),
            page_id=str(entry["id"]),
            original_rel=str(entry["original"]),
            paint_rel=entry.get("paint") or None,
            size=QSize(int(entry.get("width", 0)), int(entry.get("height", 0))),
            texts=texts,
            loader=self._load_page_images,
        )
        page.output_path = entry.get("output") or None
        page.output_stale = bool(entry.get("output_pending", False))
        self._watch_page(page)
        return page

    def _load_page_images(self, page: PageDocument) -> tuple[QImage, QImage | None]:
        try:
            original = load_image(self.root / page.original_rel)
        except ImageLoadError as e:
            raise ProjectError(tr("'{name}' sayfasının orijinal görseli açılamadı.\n{e}",
                                  name=page.name, e=e)) from e
        paint = None
        if page.paint_rel:
            path = self.root / page.paint_rel
            img = QImage(str(path))
            if img.isNull():
                # Do not silently treat the paint layer as empty: warn the user.
                raise ProjectError(tr("'{name}' sayfasının düzenleme katmanı okunamadı: {path}",
                                      name=page.name, path=path))
            paint = img
        return original, paint

    def _watch_page(self, page: PageDocument) -> None:
        page.dirtyChanged.connect(lambda _d: self._emit_dirty())

    # ------------------------------------------------------------------ pages
    def add_images(self, paths: Iterable[str | Path]) -> tuple[list[PageDocument], list[str]]:
        """COPIES the images into the project and adds them as pages.
        Returns (added pages, error messages)."""
        added: list[PageDocument] = []
        errors: list[str] = []
        self.originals_dir.mkdir(parents=True, exist_ok=True)
        for src in paths:
            src = Path(src)
            if not is_supported_input(src):
                errors.append(tr("Desteklenmeyen dosya: {name} (PNG, JPG, JPEG, WEBP)", name=src.name))
                continue
            try:
                image = load_image(src)  # validate first so a broken file never enters the project
            except ImageLoadError as e:
                errors.append(str(e))
                continue
            target = self._unique_original_name(src)
            try:
                shutil.copy2(src, target)
            except OSError as e:
                errors.append(tr("Kopyalanamadı: {name} ({e})", name=src.name, e=e))
                continue
            page = PageDocument(
                name=src.stem,
                original_rel=target.relative_to(self.root).as_posix(),
                size=image.size(),
                loader=self._load_page_images,
            )
            page.attach_images(image, None)
            # When saved, the edited version is written over the source file (the original is
            # kept under originals/). If the same source is added twice, the second page must not
            # write to the same file: it uses the default target under exports/.
            source = str(src.resolve())
            if src.suffix.lower() in OUTPUT_FORMATS and not self._target_taken(Path(source), None, added):
                page.output_path = source
            self._watch_page(page)
            self.pages.append(page)
            added.append(page)
        if added:
            self._structure_dirty = True
            self.pagesChanged.emit()
            self._emit_dirty()
        return added, errors

    def _unique_original_name(self, src: Path) -> Path:
        n = len(self.pages) + 1
        stem, ext = _safe_stem(src.stem), src.suffix.lower()
        while True:
            candidate = self.originals_dir / f"{n:03d}_{stem}{ext}"
            if not candidate.exists():
                return candidate
            n += 1

    def remove_page(self, index: int) -> PageDocument:
        """Removes the page from the project. Files stay on disk (no data loss)."""
        page = self.pages.pop(index)
        self._structure_dirty = True
        self.pagesChanged.emit()
        self._emit_dirty()
        return page

    def move_page(self, src: int, dst: int) -> None:
        if src == dst or not (0 <= src < len(self.pages)) or not (0 <= dst < len(self.pages)):
            return
        page = self.pages.pop(src)
        self.pages.insert(dst, page)
        self._structure_dirty = True
        self.pagesChanged.emit()
        self._emit_dirty()

    def index_of(self, page_id: str) -> int:
        for i, p in enumerate(self.pages):
            if p.id == page_id:
                return i
        return -1

    # ------------------------------------------------------------------ output images
    def _resolve(self, stored: str) -> Path:
        p = Path(stored)
        return p if p.is_absolute() else self.root / p

    def default_output_target(self, page: PageDocument) -> Path:
        ext = Path(page.original_rel).suffix.lower()
        ext = ext if ext in OUTPUT_FORMATS else ".png"
        base = _safe_stem(page.name)
        same_name = [p for p in self.pages if p is not page and _safe_stem(p.name) == base and not p.output_path]
        if same_name:
            base = f"{base}_{page.id[-6:]}"
        return self.exports_dir / f"{base}{ext}"

    def output_target(self, page: PageDocument) -> Path:
        """The file the page's edited image is written to when saving."""
        return self._resolve(page.output_path) if page.output_path else self.default_output_target(page)

    def _target_taken(self, target: Path, page: PageDocument | None, extra: Iterable[PageDocument] = ()) -> bool:
        key = _norm(target)
        for other in list(self.pages) + list(extra):
            if other is not page and _norm(self.output_target(other)) == key:
                return True
        return False

    def check_output_target(self, page: PageDocument, target: Path | None = None) -> str | None:
        """Write-safety check. Returns None when it is safe, otherwise an explanation."""
        target = self.output_target(page) if target is None else Path(target)
        fmt = OUTPUT_FORMATS.get(target.suffix.lower())
        if fmt is None:
            return tr("Desteklenmeyen kaydetme biçimi: {name} (PNG, JPG, JPEG, WEBP)", name=target.name)
        resolved = Path(os.path.abspath(target))
        root = Path(os.path.abspath(self.root))
        if _is_within(resolved, root):
            rel = resolved.relative_to(root)
            if not rel.parts or rel.parts[0] in PROTECTED_DIRS or len(rel.parts) == 1:
                return tr("Proje dosyalarının üzerine yazılamaz: {p} (yalnızca exports/ kullanılabilir)",
                          p=rel.as_posix())
        if self._target_taken(resolved, page):
            return tr("Başka bir sayfa da aynı dosyaya kaydediyor: {p}", p=resolved)
        if resolved.exists() and resolved.is_dir():
            return tr("Hedef bir klasör: {p}", p=resolved)
        if not _is_within(resolved, self.exports_dir) and not resolved.parent.is_dir():
            return tr("Hedef klasör bulunamadı: {p}", p=resolved.parent)
        return None

    def set_output_target(self, page: PageDocument, target: str | Path) -> None:
        """Changes the page's save target; raises ProjectError if the target is not safe."""
        target = Path(os.path.abspath(target))
        error = self.check_output_target(page, target)
        if error:
            raise ProjectError(error)
        root = Path(os.path.abspath(self.root))
        page.output_path = target.relative_to(root).as_posix() if _is_within(target, root) else str(target)
        page.output_stale = True  # written to the new target on the next save
        self._structure_dirty = True
        page.dirtyChanged.emit(page.is_dirty)
        self._emit_dirty()

    @property
    def has_pending_outputs(self) -> bool:
        return any(p.output_stale for p in self.pages)

    @property
    def needs_save(self) -> bool:
        """Is there unsaved data or an image not written yet? (asked when closing)"""
        return self.is_dirty or self.has_pending_outputs

    # ------------------------------------------------------------------ dirty state
    @property
    def is_dirty(self) -> bool:
        return self._structure_dirty or any(p.is_dirty for p in self.pages)

    def _emit_dirty(self) -> None:
        d = self.is_dirty
        if d != self._last_dirty:
            self._last_dirty = d
            self.dirtyChanged.emit(d)

    # ------------------------------------------------------------------ save
    def _page_entry(self, page: PageDocument, paint_rel: str | None) -> dict[str, Any]:
        return {
            "id": page.id,
            "name": page.name,
            "original": page.original_rel,
            "paint": paint_rel,
            "width": page.size.width(),
            "height": page.size.height(),
            "texts": [t.to_dict() for t in page.texts],
            "output": page.output_path,
            "output_pending": page.output_stale,
        }

    def _document(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "format": FORMAT_ID,
            "version": FORMAT_VERSION,
            "name": self.name,
            "created": self.created,
            "modified": _now(),
            "pages": entries,
        }

    def save(self) -> None:
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        entries = []
        for page in self.pages:
            in_recovery = bool(page.paint_rel and page.paint_rel.startswith(RECOVERY_DIR))
            if in_recovery:
                page.ensure_loaded()  # move the recovered layer to its permanent place before the copy is deleted
            if page.paint_needs_save or in_recovery:
                if page.paint_is_empty():
                    page.paint_rel = None
                else:
                    rel = f"pages/{page.id}.png"
                    assert page.paint is not None
                    save_image_atomic(page.paint, self.root / rel, "PNG")
                    page.paint_rel = rel
            entries.append(self._page_entry(page, page.paint_rel))
        _write_json_atomic(self.project_file, self._document(entries))
        for page in self.pages:
            page.mark_saved()
        self._structure_dirty = False
        self.discard_recovery()
        self._emit_dirty()

    # ------------------------------------------------------------------ recovery
    def write_recovery(self) -> None:
        """Writes a copy of the unsaved changes under .recovery/.
        The real project files are not touched."""
        rec_pages = self.recovery_dir / "pages"
        rec_pages.mkdir(parents=True, exist_ok=True)
        entries = []
        keep: set[str] = set()
        for page in self.pages:
            paint_rel = page.paint_rel
            if page.is_loaded and page.paint_needs_save:
                rel = f"{RECOVERY_DIR}/pages/{page.id}.png"
                assert page.paint is not None
                save_image_atomic(page.paint, self.root / rel, "PNG")
                paint_rel = rel
            if paint_rel and paint_rel.startswith(RECOVERY_DIR):
                keep.add(Path(paint_rel).name)
            entries.append(self._page_entry(page, paint_rel))
        _write_json_atomic(self.recovery_dir / RECOVERY_FILE, self._document(entries))
        for f in rec_pages.glob("*.png"):
            if f.name not in keep:
                f.unlink(missing_ok=True)

    def discard_recovery(self) -> None:
        if self.recovery_dir.exists():
            shutil.rmtree(self.recovery_dir, ignore_errors=True)
