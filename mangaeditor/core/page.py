"""Document of one manga page.

Layers (bottom to top):
  1. original – the original image copied into the project. It is NEVER modified.
  2. paint    – transparent paint layer (the brush, eraser and clone work here;
                "Merge page" flattens the texts into it).
  3. texts    – editable text objects.

Every page has its own undo stack; an action on one page does not affect another page.
"""
from __future__ import annotations

import uuid
from typing import Callable, Iterable, Optional

from PySide6.QtCore import QObject, QRect, QSize, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QUndoStack

from ..i18n import tr
from .text_data import TextData

PAINT_FORMAT = QImage.Format.Format_ARGB32_Premultiplied


def new_page_id() -> str:
    return f"page_{uuid.uuid4().hex[:10]}"


def blank_layer(size: QSize) -> QImage:
    img = QImage(size, PAINT_FORMAT)
    img.fill(QColor(0, 0, 0, 0))
    return img


# Loader: returns (original, paint | None).
PageLoader = Callable[["PageDocument"], tuple[QImage, Optional[QImage]]]


class PageDocument(QObject):
    paintChanged = Signal(QRect)
    textAdded = Signal(str)
    textRemoved = Signal(str)
    textChanged = Signal(str)
    textsReset = Signal()
    dirtyChanged = Signal(bool)

    def __init__(
        self,
        name: str = "",
        page_id: str | None = None,
        original_rel: str = "",
        paint_rel: str | None = None,
        size: QSize | None = None,
        texts: Iterable[TextData] = (),
        loader: PageLoader | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.id = page_id or new_page_id()
        self.name = name
        self.original_rel = original_rel  # path relative to the project root
        self.paint_rel = paint_rel
        self._size = QSize(size) if size is not None else QSize()
        self._texts: list[TextData] = list(texts)
        self._loader = loader
        self.original: QImage | None = None
        self.paint: QImage | None = None
        self.paint_revision = 0
        self.saved_paint_revision = 0
        self._force_dirty = False
        # Target of the edited image written on save (absolute path, or relative to the
        # project root; None = default name inside the project's exports/ folder).
        self.output_path: str | None = None
        # Has the page changed since the last successful image write? It is saved, so a
        # failed write is retried on the next save.
        self.output_stale = False
        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(self._on_clean_changed)
        self.undo_stack.indexChanged.connect(self._on_index_changed)

    # ------------------------------------------------------------------ creation
    @classmethod
    def from_image(cls, image: QImage, name: str = "", original_rel: str = "") -> "PageDocument":
        page = cls(name=name, original_rel=original_rel, size=image.size())
        page.attach_images(image, None)
        return page

    def attach_images(self, original: QImage, paint: QImage | None) -> None:
        if original.isNull():
            raise ValueError(tr("Orijinal görsel boş"))
        self.original = original
        self._size = original.size()
        if paint is None or paint.isNull():
            self.paint = blank_layer(self._size)
        else:
            if paint.size() != self._size:
                # Unexpected case: align the layer to the original size without losing data.
                fixed = blank_layer(self._size)
                p = QPainter(fixed)
                p.drawImage(0, 0, paint)
                p.end()
                paint = fixed
            self.paint = paint.convertToFormat(PAINT_FORMAT)

    @property
    def is_loaded(self) -> bool:
        return self.original is not None

    def ensure_loaded(self) -> None:
        if self.is_loaded:
            return
        if self._loader is None:
            raise RuntimeError(tr("Sayfa yüklenemiyor: {name}", name=self.name))
        original, paint = self._loader(self)
        self.attach_images(original, paint)

    def can_unload(self) -> bool:
        return self.is_loaded and not self.is_dirty and self.undo_stack.count() == 0 and self._loader is not None

    def unload(self) -> None:
        """Releases the images from memory (only if the page was never edited)."""
        if self.can_unload():
            self.original = None
            self.paint = None

    @property
    def size(self) -> QSize:
        return QSize(self._size)

    @property
    def rect(self) -> QRect:
        return QRect(0, 0, self._size.width(), self._size.height())

    # ------------------------------------------------------------------ dirty state
    @property
    def is_dirty(self) -> bool:
        return self._force_dirty or not self.undo_stack.isClean()

    def _on_clean_changed(self, clean: bool) -> None:
        # Do not query the stack itself: this can also run while the stack is being deleted on close.
        self.dirtyChanged.emit(self._force_dirty or not clean)

    def _on_index_changed(self, _index: int) -> None:
        # Every edit / undo / redo makes the output image stale.
        if not self.output_stale:
            self.output_stale = True
            try:
                self.dirtyChanged.emit(self.is_dirty)
            except RuntimeError:
                pass  # called while the stack is being deleted on close

    @property
    def needs_attention(self) -> bool:
        """Is there unsaved data OR an edited image that has not been written yet?"""
        return self.is_dirty or self.output_stale

    @property
    def paint_needs_save(self) -> bool:
        return self.is_loaded and self.paint_revision != self.saved_paint_revision

    def mark_saved(self) -> None:
        was = self.is_dirty
        self._force_dirty = False
        self.saved_paint_revision = self.paint_revision
        self.undo_stack.setClean()
        if was:
            self.dirtyChanged.emit(False)

    def mark_dirty(self, paint_too: bool = False) -> None:
        """For changes that are not on the undo stack (e.g. recovery)."""
        self._force_dirty = True
        if paint_too:
            self.saved_paint_revision = -1
        self.dirtyChanged.emit(True)

    # ------------------------------------------------------------------ texts
    @property
    def texts(self) -> tuple[TextData, ...]:
        return tuple(self._texts)

    def text(self, text_id: str) -> TextData | None:
        for t in self._texts:
            if t.id == text_id:
                return t
        return None

    def text_index(self, text_id: str) -> int:
        for i, t in enumerate(self._texts):
            if t.id == text_id:
                return i
        return -1

    def insert_text(self, data: TextData, index: int | None = None) -> None:
        if self.text_index(data.id) >= 0:
            raise ValueError(tr("Metin zaten var: {id}", id=data.id))
        if index is None or index < 0 or index > len(self._texts):
            index = len(self._texts)
        self._texts.insert(index, data)
        self.textAdded.emit(data.id)

    def remove_text(self, text_id: str) -> tuple[int, TextData]:
        i = self.text_index(text_id)
        if i < 0:
            raise KeyError(text_id)
        data = self._texts.pop(i)
        self.textRemoved.emit(text_id)
        return i, data

    def replace_text(self, data: TextData) -> None:
        i = self.text_index(data.id)
        if i < 0:
            raise KeyError(data.id)
        if self._texts[i] == data:
            return
        self._texts[i] = data
        self.textChanged.emit(data.id)

    def set_texts(self, texts: Iterable[TextData]) -> None:
        self._texts = list(texts)
        self.textsReset.emit()

    # ------------------------------------------------------------------ paint layer
    def notify_paint_changed(self, rect: QRect) -> None:
        self.paint_revision += 1
        self.paintChanged.emit(QRect(rect))

    def write_paint_region(self, rect: QRect, image: QImage) -> None:
        """Replaces the rect region with image exactly (used by undo / redo)."""
        assert self.paint is not None
        p = QPainter(self.paint)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.drawImage(rect.topLeft(), image)
        p.end()
        self.notify_paint_changed(rect)

    def replace_paint(self, image: QImage) -> None:
        assert image.size() == self._size
        self.paint = image.convertToFormat(PAINT_FORMAT)
        self.notify_paint_changed(self.rect)

    def paint_is_empty(self) -> bool:
        """Is the paint layer completely transparent? (so that no needless file is written on save)"""
        if self.paint is None:
            return True
        # A transparent pixel in premultiplied format is 4 zero bytes; bytes.strip runs at C speed.
        img = self.paint
        data = bytes(img.constBits())[: img.bytesPerLine() * img.height()]
        return not data.strip(b"\x00")
