"""Undoable operations. Each command goes only onto the undo stack of its own page."""
from __future__ import annotations

import time

from PySide6.QtCore import QRect
from PySide6.QtGui import QImage, QUndoCommand

from ..i18n import tr
from .page import PageDocument
from .text_data import TextData


class StrokeCommand(QUndoCommand):
    """Brush / eraser stroke. Keeps only the before and after images of the affected rectangle
    (not a full layer copy), which is memory-friendly."""

    def __init__(self, page: PageDocument, rect: QRect, before: QImage, after: QImage, label: str) -> None:
        super().__init__(tr(label))  # labels are source strings; shown in the active language
        self.page = page
        self.rect = QRect(rect)
        self.before = before
        self.after = after
        self._applied = True  # the stroke is already drawn on the layer

    def redo(self) -> None:
        if self._applied:
            self._applied = False
            return
        self.page.write_paint_region(self.rect, self.after)

    def undo(self) -> None:
        self.page.write_paint_region(self.rect, self.before)


class AddTextCommand(QUndoCommand):
    def __init__(self, page: PageDocument, data: TextData, index: int | None = None, label: str = "Metin ekle") -> None:
        super().__init__(tr(label))
        self.page = page
        self.data = data
        self.index = index

    def redo(self) -> None:
        self.page.insert_text(self.data, self.index)

    def undo(self) -> None:
        self.page.remove_text(self.data.id)


class RemoveTextCommand(QUndoCommand):
    def __init__(self, page: PageDocument, text_id: str, label: str = "Metni sil") -> None:
        super().__init__(tr(label))
        self.page = page
        self.index = page.text_index(text_id)
        data = page.text(text_id)
        if data is None:
            raise KeyError(text_id)
        self.data = data

    def redo(self) -> None:
        self.page.remove_text(self.data.id)

    def undo(self) -> None:
        self.page.insert_text(self.data, self.index)


class ChangeTextCommand(QUndoCommand):
    """Change of a text's content / style / position. Consecutive changes to the same field
    (e.g. dragging a slider) merge into one undo step."""

    MERGE_ID = 0x7E47
    MERGE_WINDOW_S = 1.5

    def __init__(self, page: PageDocument, before: TextData, after: TextData, label: str,
                 merge_key: str | None = None) -> None:
        super().__init__(tr(label))
        assert before.id == after.id
        self.page = page
        self.before = before
        self.after = after
        self.merge_key = merge_key
        self.stamp = time.monotonic()

    def id(self) -> int:
        return self.MERGE_ID if self.merge_key else -1

    def mergeWith(self, other: QUndoCommand) -> bool:
        if not isinstance(other, ChangeTextCommand):
            return False
        if other.merge_key != self.merge_key or other.after.id != self.after.id:
            return False
        if other.stamp - self.stamp > self.MERGE_WINDOW_S:
            return False
        self.after = other.after
        self.stamp = other.stamp
        return True

    def redo(self) -> None:
        self.page.replace_text(self.after)

    def undo(self) -> None:
        self.page.replace_text(self.before)


class MergePageCommand(QUndoCommand):
    """Merge page: stamps all texts into the paint layer and removes the text objects.
    The original image is not touched. Undoable."""

    def __init__(self, page: PageDocument, label: str = "Sayfayı birleştir") -> None:
        super().__init__(tr(label))
        self.page = page
        self.texts = page.texts
        self.before: QImage | None = None
        self.after: QImage | None = None

    def redo(self) -> None:
        from PySide6.QtGui import QPainter

        from .compose import draw_texts

        page = self.page
        assert page.paint is not None
        if self.after is None:
            self.before = page.paint.copy()
            merged = page.paint.copy()
            p = QPainter(merged)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            draw_texts(p, self.texts)
            p.end()
            self.after = merged
        page.set_texts([])
        page.replace_paint(self.after.copy())

    def undo(self) -> None:
        assert self.before is not None
        self.page.replace_paint(self.before.copy())
        self.page.set_texts(self.texts)
