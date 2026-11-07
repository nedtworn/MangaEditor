"""Image reading and writing helpers."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtGui import QImage, QImageReader

from ..i18n import tr

INPUT_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
INPUT_FILTER = "Görseller (*.png *.jpg *.jpeg *.webp)"  # file dialog filter; translate with i18n.tr at use


class ImageLoadError(Exception):
    pass


def is_supported_input(path: str | os.PathLike) -> bool:
    return Path(path).suffix.lower() in INPUT_EXTENSIONS


def load_image(path: str | os.PathLike) -> QImage:
    """Reads the image; applies the EXIF orientation of JPG files."""
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        raise ImageLoadError(tr("Görsel okunamadı: {path} ({err})", path=path, err=reader.errorString()))
    # One fast, lossless common format for drawing.
    if image.hasAlphaChannel():
        return image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    return image.convertToFormat(QImage.Format.Format_RGB32)


def save_image_atomic(image: QImage, path: str | os.PathLike, fmt: str, quality: int = -1) -> None:
    """Writes to a temporary file first and then moves it into place, so an interrupted write
    never damages the existing file. The temporary file is removed on error."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        if not image.save(str(tmp), fmt, quality):
            raise OSError(tr("Görsel yazılamadı: {path}", path=path))
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
