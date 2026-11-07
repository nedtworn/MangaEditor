"""Exporting pages as PNG / JPG.

The image is produced by the same compose_page() as on the canvas; texts and paint are
merged at the original resolution (no scaling).
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from PySide6.QtGui import QColor, QImage

from ..i18n import tr
from .compose import compose_page
from .imageio import save_image_atomic
from .page import PageDocument
from .project import OUTPUT_FORMATS, Project, _safe_stem

FORMATS = {"PNG": "png", "JPG": "jpg"}
DEFAULT_JPG_QUALITY = 95


def export_filename(index: int, page: PageDocument, fmt: str) -> str:
    return f"{index:03d}_{_safe_stem(page.name)}.{FORMATS[fmt]}"


def render_for_export(page: PageDocument, fmt: str) -> QImage:
    page.ensure_loaded()
    assert page.original is not None
    if fmt == "JPG":
        # JPG has no transparency: transparent areas become white.
        img = compose_page(page, background=QColor(255, 255, 255))
        return img.convertToFormat(QImage.Format.Format_RGB32)
    img = compose_page(page)
    # An opaque original plus the layers above it gives an opaque result; do not write a needless alpha channel.
    fmt_out = QImage.Format.Format_ARGB32 if page.original.hasAlphaChannel() else QImage.Format.Format_RGB32
    return img.convertToFormat(fmt_out)


def export_pages(
    pages: Sequence[tuple[int, PageDocument]],
    out_dir: str | Path,
    fmt: str = "PNG",
    quality: int = DEFAULT_JPG_QUALITY,
    progress: Callable[[int, int, str], bool] | None = None,
) -> tuple[list[Path], list[str]]:
    """pages: (1-based position in the project, page) pairs.
    If progress(i, total, name) returns False, the operation stops.
    Returns (written files, error messages)."""
    fmt = fmt.upper()
    if fmt not in FORMATS:
        raise ValueError(tr("Desteklenmeyen biçim: {fmt}", fmt=fmt))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    errors: list[str] = []
    total = len(pages)
    for i, (index, page) in enumerate(pages):
        if progress is not None and progress(i, total, page.name) is False:
            break
        was_loaded = page.is_loaded
        try:
            page.ensure_loaded()
            img = render_for_export(page, fmt)
            path = out_dir / export_filename(index, page, fmt)
            save_image_atomic(img, path, fmt, quality if fmt == "JPG" else -1)
            written.append(path)
        except Exception as e:  # one page's error must not stop the others
            errors.append(f"{page.name}: {e}")
        finally:
            if not was_loaded:
                page.unload()  # do not inflate memory during a batch export
    if progress is not None:
        progress(total, total, "")
    return written, errors


def write_page_outputs(project: Project) -> tuple[list[Path], list[str]]:
    """On save: writes the edited image of every page changed since its last write to its
    own target file (over the source image).

    Every target passes a safety check before it is written (project files, another page's
    target, a missing folder). A failed page stays 'pending' and is retried on the next save.
    Returns (written files, error messages)."""
    written: list[Path] = []
    errors: list[str] = []
    for page in project.pages:
        if not page.output_stale:
            continue
        target = project.output_target(page)
        problem = project.check_output_target(page, target)
        if problem:
            errors.append(f"{page.name}: {problem}")
            continue
        fmt = OUTPUT_FORMATS[target.suffix.lower()]
        was_loaded = page.is_loaded
        try:
            img = render_for_export(page, "JPG" if fmt == "JPG" else "PNG")
            quality = {"JPG": DEFAULT_JPG_QUALITY, "WEBP": 100}.get(fmt, -1)  # WEBP 100 = lossless
            save_image_atomic(img, target, fmt, quality)
        except Exception as e:  # one page's error must not stop the others or the project save
            errors.append(f"{page.name}: {target}\n  {e}")
            continue
        finally:
            if not was_loaded:
                page.unload()
        page.output_stale = False
        written.append(target)
    return written, errors
