"""Scene of one page: original image + paint layer + text items."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene

from ..core.commands import AddTextCommand, ChangeTextCommand, RemoveTextCommand
from ..core.page import PageDocument
from ..i18n import tr
from ..core.text_data import TextData
from .paint_item import PaintLayerItem
from .text_item import TextItemView

Z_ORIGINAL = 0
Z_PAINT = 1
Z_TEXT_BASE = 10


class PageScene(QGraphicsScene):
    editingChanged = Signal(bool)
    textSelectionChanged = Signal()  # the selection or the data of the selected text changed

    def __init__(self, page: PageDocument) -> None:
        super().__init__()
        page.ensure_loaded()
        self.page = page
        self.view_scale = 1.0
        self.texts_interactive = False
        # Clone stamp: source point and the offset (fixed after the first stroke). Per page.
        self.clone_source: QPointF | None = None
        self.clone_offset: QPoint | None = None
        # Non-aligned mode: source area fixed at K+click (position + content), see core.clone.SourcePatch
        self.clone_patch = None
        self.editing_item: TextItemView | None = None
        self.text_items: dict[str, TextItemView] = {}

        assert page.original is not None
        self.original_item = QGraphicsPixmapItem(QPixmap.fromImage(page.original))
        self.original_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.original_item.setZValue(Z_ORIGINAL)
        self.original_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.addItem(self.original_item)

        self.paint_item = PaintLayerItem(page)
        self.paint_item.setZValue(Z_PAINT)
        self.addItem(self.paint_item)

        # Leave a margin around the image so the canvas can be panned freely
        # while working near the edges.
        w, h = page.size.width(), page.size.height()
        margin = max(w, h)
        self.setSceneRect(QRectF(-margin, -margin, w + 2 * margin, h + 2 * margin))
        self.setBackgroundBrush(QColor("#1b1d21"))

        for t in page.texts:
            self._create_item(t)
        self._restack()
        page.textAdded.connect(self._on_text_added)
        page.textRemoved.connect(self._on_text_removed)
        page.textChanged.connect(self._on_text_changed)
        page.textsReset.connect(self._on_texts_reset)
        self.selectionChanged.connect(self.textSelectionChanged)

    @property
    def image_rect(self) -> QRectF:
        return QRectF(self.page.rect)

    def set_view_scale(self, scale: float) -> None:
        self.view_scale = scale
        for item in self.text_items.values():
            item.view_scale_changed()

    # ------------------------------------------------------------------ items
    def _create_item(self, data: TextData) -> TextItemView:
        item = TextItemView(self, data)
        item.set_interactive(self.texts_interactive)
        self.text_items[data.id] = item
        self.addItem(item)
        return item

    def _restack(self) -> None:
        for i, t in enumerate(self.page.texts):
            item = self.text_items.get(t.id)
            if item is not None:
                item.setZValue(Z_TEXT_BASE + i)
        for item in self.text_items.values():
            if item.pending_new:
                item.setZValue(Z_TEXT_BASE + len(self.text_items) + 1)

    def _on_text_added(self, text_id: str) -> None:
        data = self.page.text(text_id)
        assert data is not None
        item = self.text_items.get(text_id)
        if item is None:
            self._create_item(data)
        else:
            item.pending_new = False
            item.set_data(data)
        self._restack()

    def _on_text_removed(self, text_id: str) -> None:
        item = self.text_items.pop(text_id, None)
        if item is None:
            return
        if item is self.editing_item:
            self.editing_item = None
            item.end_edit()
            self.editingChanged.emit(False)
        self.removeItem(item)
        item.deleteLater()
        self._restack()

    def _on_text_changed(self, text_id: str) -> None:
        item = self.text_items.get(text_id)
        data = self.page.text(text_id)
        if item is None or data is None:
            return
        item.set_data(data)
        if item.isSelected() or item is self.editing_item:
            self.textSelectionChanged.emit()

    def _on_texts_reset(self) -> None:
        if self.editing_item is not None:
            self.editing_item.end_edit()
            self.editing_item = None
            self.editingChanged.emit(False)
        for item in list(self.text_items.values()):
            self.removeItem(item)
            item.deleteLater()
        self.text_items.clear()
        for t in self.page.texts:
            self._create_item(t)
        self._restack()
        self.textSelectionChanged.emit()

    def set_texts_interactive(self, on: bool) -> None:
        """Texts only react to the mouse while the text tool is selected; the brush
        and the eraser work freely on the layer under the texts."""
        if not on:
            self.finish_editing()
            self.clearSelection()
        self.texts_interactive = on
        for item in self.text_items.values():
            item.set_interactive(on)

    def selected_text_items(self) -> list[TextItemView]:
        items = [i for i in self.selectedItems() if isinstance(i, TextItemView)]
        if self.editing_item is not None and self.editing_item not in items:
            items.append(self.editing_item)
        return items

    # ------------------------------------------------------------------ editing
    def new_text(self, data: TextData) -> TextItemView:
        """Creates a new text box and starts editing it at once. The text is added to the page
        (undoable) when editing ends with non-empty content."""
        self.finish_editing()
        item = self._create_item(data)
        item.pending_new = True
        self._restack()
        self.start_editing(item, 0)
        return item

    def start_editing(self, item: TextItemView, cursor: int | None = None) -> None:
        if self.editing_item is item:
            return
        self.finish_editing()
        self.clearSelection()
        item.setSelected(True)
        item.begin_edit(cursor)
        self.editing_item = item
        self.editingChanged.emit(True)
        self.textSelectionChanged.emit()

    def finish_editing(self) -> None:
        item = self.editing_item
        if item is None:
            return
        self.editing_item = None
        base = item.edit_base
        final = item.data
        item.end_edit()
        stack = self.page.undo_stack
        if item.pending_new:
            if final.text.strip():
                stack.push(AddTextCommand(self.page, final))
            else:  # empty new box: remove it without leaving a trace
                self.text_items.pop(final.id, None)
                self.removeItem(item)
                item.deleteLater()
        elif not final.text.strip():
            current = self.page.text(final.id)
            if current is not None:
                stack.push(RemoveTextCommand(self.page, final.id))
        elif base is not None and final != self.page.text(final.id):
            stack.push(ChangeTextCommand(self.page, self.page.text(final.id) or base, final, tr("Metni düzenle")))
        self.editingChanged.emit(False)
        self.textSelectionChanged.emit()

    def commit_pending_text(self) -> None:
        """Commits the text typed so far to the page (editing stays open)."""
        item = self.editing_item
        if item is None or item.pending_new:
            return
        current = self.page.text(item.text_id)
        if current is not None and current.text != item.data.text:
            self.page.undo_stack.push(ChangeTextCommand(self.page, current, current.with_(text=item.data.text),
                                                        tr("Metni düzenle")))
            item.edit_base = self.page.text(item.text_id)

    def commit_text_change(self, item: TextItemView, before: TextData, after: TextData, label: str) -> None:
        if item.pending_new:
            return  # the final state is saved when it is added to the page
        current = self.page.text(item.text_id)
        if current is None:
            return
        self.page.undo_stack.push(ChangeTextCommand(self.page, current, after, label))

    def apply_style(self, field: str, value: Any) -> bool:
        """Applies one style field to the selected texts. Returns True if something was applied."""
        items = self.selected_text_items()
        if not items:
            return False
        stack = self.page.undo_stack
        multi = len([i for i in items if not i.pending_new]) > 1
        if multi:
            stack.beginMacro(tr("Metin stili"))
        for item in items:
            if item.pending_new:
                item.set_data(item.data.with_(**{field: value}))
                continue
            if item.editing:
                self.commit_pending_text()
            before = self.page.text(item.text_id)
            if before is None:
                continue
            after = before.with_(**{field: value})
            if after != before:
                stack.push(ChangeTextCommand(self.page, before, after, tr("Metin stili"),
                                             merge_key=None if multi else field))
            if item.editing:
                item.edit_base = self.page.text(item.text_id)
        if multi:
            stack.endMacro()
        self.textSelectionChanged.emit()
        return True

    def delete_selected_texts(self) -> int:
        self.finish_editing()
        ids = [i.text_id for i in self.selected_text_items() if self.page.text(i.text_id) is not None]
        if not ids:
            return 0
        stack = self.page.undo_stack
        stack.beginMacro(tr("Metni sil") if len(ids) == 1 else tr("{n} metni sil", n=len(ids)))
        for tid in ids:
            stack.push(RemoveTextCommand(self.page, tid))
        stack.endMacro()
        return len(ids)
