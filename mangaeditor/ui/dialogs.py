"""Dialogs and the welcome screen."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.export import DEFAULT_JPG_QUALITY
from ..core.page import PageDocument
from ..i18n import tr


def default_projects_dir() -> Path:
    docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    return Path(docs or Path.home()) / "Manga Editör Projeleri"


class NewProjectDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, name: str = "", location: str | Path | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Yeni Proje"))
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit(name or tr("Yeni Bölüm"))
        self.name_edit.selectAll()
        loc_row = QHBoxLayout()
        self.loc_edit = QLineEdit(str(location or default_projects_dir()))
        browse = QPushButton(tr("Gözat…"))
        browse.clicked.connect(self._browse)
        loc_row.addWidget(self.loc_edit, 1)
        loc_row.addWidget(browse)
        form.addRow(tr("Proje adı"), self.name_edit)
        form.addRow(tr("Konum"), loc_row)
        lay.addLayout(form)
        self.preview = QLabel()
        self.preview.setObjectName("hint")
        self.preview.setWordWrap(True)
        lay.addWidget(self.preview)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Oluştur"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Vazgeç"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.name_edit.textChanged.connect(self._update_preview)
        self.loc_edit.textChanged.connect(self._update_preview)
        self._update_preview()

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Proje konumu"), self.loc_edit.text())
        if d:
            self.loc_edit.setText(d)

    def _update_preview(self) -> None:
        self.preview.setText(tr("Proje klasörü: {p}", p=Path(self.loc_edit.text()) / self.name_edit.text().strip()))

    def values(self) -> tuple[str, str]:
        return self.name_edit.text().strip(), self.loc_edit.text().strip()


class ExportDialog(QDialog):
    """Batch export: page selection, format, JPG quality and target folder."""

    def __init__(self, pages: list[PageDocument], current_index: int, out_dir: Path,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Dışa Aktar"))
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("Sayfalar")))
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for i, p in enumerate(pages):
            it = QListWidgetItem(f"{i + 1:03d}  {p.name}")
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked)
            it.setData(Qt.ItemDataRole.UserRole, i)
            self.list.addItem(it)
        lay.addWidget(self.list, 1)
        sel_row = QHBoxLayout()
        for text, fn in ((tr("Tümü"), lambda: self._check(lambda i: True)),
                         (tr("Hiçbiri"), lambda: self._check(lambda i: False)),
                         (tr("Yalnızca açık sayfa"), lambda: self._check(lambda i: i == current_index))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            sel_row.addWidget(b)
        sel_row.addStretch(1)
        lay.addLayout(sel_row)

        form = QFormLayout()
        fmt_row = QHBoxLayout()
        self.png = QRadioButton(tr("PNG (kayıpsız)"))
        self.jpg = QRadioButton("JPG")
        self.png.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.png)
        grp.addButton(self.jpg)
        fmt_row.addWidget(self.png)
        fmt_row.addWidget(self.jpg)
        fmt_row.addStretch(1)
        form.addRow(tr("Biçim"), fmt_row)
        self.quality = QSpinBox()
        self.quality.setRange(50, 100)
        self.quality.setValue(DEFAULT_JPG_QUALITY)
        self.quality.setSuffix(" %")
        self.quality.setEnabled(False)
        self.jpg.toggled.connect(self.quality.setEnabled)
        form.addRow(tr("JPG kalitesi"), self.quality)
        out_row = QHBoxLayout()
        self.out_edit = QLineEdit(str(out_dir))
        browse = QPushButton(tr("Gözat…"))
        browse.clicked.connect(self._browse)
        out_row.addWidget(self.out_edit, 1)
        out_row.addWidget(browse)
        form.addRow(tr("Klasör"), out_row)
        lay.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Dışa Aktar"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Vazgeç"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _check(self, pred) -> None:
        for r in range(self.list.count()):
            it = self.list.item(r)
            it.setCheckState(Qt.CheckState.Checked if pred(r) else Qt.CheckState.Unchecked)

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("Dışa aktarma klasörü"), self.out_edit.text())
        if d:
            self.out_edit.setText(d)

    def selected_indices(self) -> list[int]:
        return [self.list.item(r).data(Qt.ItemDataRole.UserRole) for r in range(self.list.count())
                if self.list.item(r).checkState() == Qt.CheckState.Checked]

    def fmt(self) -> str:
        return "JPG" if self.jpg.isChecked() else "PNG"


class WelcomeWidget(QWidget):
    """Shown while no project is open."""

    newRequested = Signal()
    openRequested = Signal()
    recentRequested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: #1b1d21;")
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        box = QWidget()
        box.setFixedWidth(420)
        lay = QVBoxLayout(box)
        title = QLabel("Manga Editör")
        title.setStyleSheet("font-size: 26px; font-weight: 600; color: white;")
        lay.addWidget(title)
        sub = QLabel(tr("Yeni bir proje oluşturun veya mevcut bir projeyi açın.\n"
                        "Görselleri pencereye sürükleyip bırakarak da başlayabilirsiniz."))
        sub.setObjectName("hint")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        row = QHBoxLayout()
        new_btn = QPushButton(tr("Yeni Proje") + "  (Ctrl+N)")
        new_btn.setObjectName("primary")
        open_btn = QPushButton(tr("Proje Aç") + "  (Ctrl+O)")
        new_btn.clicked.connect(self.newRequested.emit)
        open_btn.clicked.connect(self.openRequested.emit)
        row.addWidget(new_btn)
        row.addWidget(open_btn)
        lay.addLayout(row)
        self.recent_title = QLabel(tr("Son projeler"))
        self.recent_title.setStyleSheet("margin-top: 18px; color: #c9ccd2;")
        lay.addWidget(self.recent_title)
        self.recent = QListWidget()
        self.recent.setStyleSheet("QListWidget { background: #24272d; border: 1px solid #353941; border-radius: 6px; }"
                                  "QListWidget::item { padding: 6px; }")
        self.recent.itemActivated.connect(lambda it: self.recentRequested.emit(it.data(Qt.ItemDataRole.UserRole)))
        self.recent.itemClicked.connect(lambda it: self.recentRequested.emit(it.data(Qt.ItemDataRole.UserRole)))
        lay.addWidget(self.recent)
        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(box)
        h.addStretch(1)
        outer.addLayout(h)
        outer.addStretch(2)

    def set_recent(self, paths: list[str]) -> None:
        self.recent.clear()
        for p in paths:
            it = QListWidgetItem(f"{Path(p).name}\n{p}")
            it.setData(Qt.ItemDataRole.UserRole, p)
            self.recent.addItem(it)
        visible = bool(paths)
        self.recent.setVisible(visible)
        self.recent_title.setVisible(visible)
