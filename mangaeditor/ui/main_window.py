"""Main window: project, page tabs, tools and panels."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
    QTransform,
    QUndoGroup,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QStackedWidget,
    QTabBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from .. import i18n
from ..core.commands import MergePageCommand
from ..i18n import tr
from ..core.export import export_pages, write_page_outputs
from ..core.fonts import FONT_FILTER, FontLoadError, FontManager
from ..core.imageio import INPUT_FILTER, is_supported_input
from ..core.page import PageDocument
from ..core.project import PROJECT_FILE, Project, ProjectError
from ..core.text_data import GEOMETRY_FIELDS, TextData
from . import icons
from . import shortcuts as sc
from .canvas_view import CanvasView
from .dialogs import ExportDialog, NewProjectDialog, WelcomeWidget, default_projects_dir
from .page_scene import PageScene
from .panels import SidePanel
from .shortcuts import ShortcutRegistry
from .shortcuts_dialog import ShortcutsDialog
from .text_panel import TextPanel
from .tools import TOOL_LABELS, Tool, ToolSettings

RECOVERY_INTERVAL_MS = 30_000  # recovery copy interval
AUTOSAVE_INTERVAL_MS = 3 * 60_000  # autosave interval for the project data
MAX_RECENT = 8
DIRTY_MARK = "● "


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        self.settings = settings if settings is not None else QSettings()
        self.setWindowTitle(APP_NAME)
        self.resize(1400, 900)
        self.setAcceptDrops(True)

        self.project: Project | None = None
        self.scenes: dict[str, PageScene] = {}
        self._view_states: dict[str, tuple[QTransform, QPointF]] = {}
        self._current_id: str | None = None
        self._syncing_tabs = False

        # All shortcuts are managed from one place (ui/shortcuts.py).
        self.shortcuts = ShortcutRegistry(self.settings, self)
        self.tools = ToolSettings()
        self._restore_text_defaults()
        self.tools.set_clone_aligned(self.settings.value("clone_aligned", True, type=bool))
        self.tools.cloneModeChanged.connect(self._on_clone_mode_changed)
        self.fonts = FontManager()
        self.undo_group = QUndoGroup(self)

        # --- center: welcome screen | (tabs + canvas + side panel)
        self.canvas = CanvasView(self)
        self.canvas.set_tools(self.tools)
        self.canvas.set_shortcuts(self.shortcuts)
        self.side_panel = SidePanel(self.tools)
        self.text_panel = TextPanel()
        self.side_panel.add_tool_page(Tool.TEXT, self.text_panel)
        self.side_panel.show_tool(self.tools.tool)
        self.text_panel.fieldEdited.connect(self._on_text_field_edited)
        self.text_panel.loadFontRequested.connect(self.load_font_dialog)

        self.tabbar = QTabBar()
        self.tabbar.setMovable(True)
        self.tabbar.setExpanding(False)
        self.tabbar.setUsesScrollButtons(True)
        self.tabbar.setElideMode(Qt.TextElideMode.ElideRight)
        self.tabbar.setDocumentMode(True)
        self.tabbar.setDrawBase(False)
        self.tabbar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabbar.currentChanged.connect(self._on_tab_changed)
        self.tabbar.tabMoved.connect(self._on_tab_moved)
        self.tabbar.customContextMenuRequested.connect(self._tab_context_menu)

        editor = QWidget()
        ev = QVBoxLayout(editor)
        ev.setContentsMargins(0, 0, 0, 0)
        ev.setSpacing(0)
        ev.addWidget(self.tabbar)
        ev.addWidget(self.canvas, 1)
        self.welcome = WelcomeWidget()
        self.welcome.newRequested.connect(self.new_project_dialog)
        self.welcome.openRequested.connect(self.open_project_dialog)
        self.welcome.recentRequested.connect(self.open_project)
        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self.welcome)
        self.center_stack.addWidget(editor)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.center_stack, 1)
        lay.addWidget(self.side_panel)
        self.setCentralWidget(central)

        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_tools_bar()
        self._build_statusbar()
        self.canvas.zoomChanged.connect(self._on_zoom)
        self.canvas.cursorMoved.connect(self._on_cursor)
        self.tools.toolChanged.connect(self._on_tool_changed)
        self.tools.textDefaultsChanged.connect(self._store_text_defaults)
        self.canvas.message.connect(lambda text: self.statusBar().showMessage(text, 7000))
        self.canvas.cloneStateChanged.connect(self.refresh_clone_panel)
        self.shortcuts.changed.connect(self._on_shortcuts_changed)
        self._on_shortcuts_changed()

        self.recovery_timer = QTimer(self)
        self.recovery_timer.setInterval(RECOVERY_INTERVAL_MS)
        self.recovery_timer.timeout.connect(self.write_recovery)
        self.recovery_timer.start()
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(AUTOSAVE_INTERVAL_MS)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start()

        geo = self.settings.value("window/geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self._show_project_ui(False)
        self.refresh_text_panel()

    # ================================================================== setup
    def _build_actions(self) -> None:
        reg = self.shortcuts

        def act(sid: str, text: str, slot=None, tip: str | None = None) -> QAction:
            a = QAction(tr(text), self)
            if slot:
                a.triggered.connect(slot)
            # The shortcut and tooltip come from the shortcut registry.
            reg.bind_action(sid, a, tr(tip or text))
            self.addAction(a)
            return a

        self.act_new = act(sc.FILE_NEW, "Yeni Proje", self.new_project_dialog)
        self.act_open = act(sc.FILE_OPEN, "Aç", self.open_project_dialog, "Proje aç")
        self.act_save = act(sc.FILE_SAVE, "Kaydet", self.save_project, "Projeyi kaydet")
        self.act_close_project = act(sc.FILE_CLOSE, "Projeyi Kapat", self.close_project)
        self.act_add_pages = act(sc.PAGE_ADD, "Sayfa Ekle", self.add_pages_dialog,
                                 "Projeye görsel ekle (PNG, JPG, JPEG, WEBP)")
        self.act_remove_page = act(sc.PAGE_REMOVE, "Sayfayı Kaldır", self.remove_current_page)
        self.act_move_left = act(sc.PAGE_MOVE_LEFT, "Sayfayı Sola Taşı", lambda: self.move_current_page(-1))
        self.act_move_right = act(sc.PAGE_MOVE_RIGHT, "Sayfayı Sağa Taşı", lambda: self.move_current_page(1))
        self.act_set_target = act(sc.PAGE_SET_TARGET, "Kaydetme Hedefini Değiştir…", self.change_output_target_dialog,
                                  "Kaydederken bu sayfanın düzenlenmiş görselinin yazılacağı dosya")
        self.act_export = act(sc.FILE_EXPORT, "Dışa Aktar", self.export_dialog, "Sayfaları PNG/JPG olarak dışa aktar")
        self.act_autosave = QAction(tr("Otomatik Kaydet"), self, checkable=True)
        self.act_autosave.setChecked(self.settings.value("autosave", True, type=bool))
        self.act_autosave.toggled.connect(lambda on: self.settings.setValue("autosave", on))
        self.act_quit = act(sc.FILE_QUIT, "Çıkış", self.close)
        self.act_shortcuts = QAction(tr("Kısayollar…"), self)
        self.act_shortcuts.triggered.connect(self.open_shortcuts_dialog)
        self.addAction(self.act_shortcuts)
        self.act_language = QAction(tr("Dil / Language…"), self)
        self.act_language.triggered.connect(self.open_language_dialog)
        self.addAction(self.act_language)

        self.act_undo = act(sc.EDIT_UNDO, "Geri Al", self.undo)
        self.act_redo = act(sc.EDIT_REDO, "Yinele", self.redo)
        self.act_undo.setEnabled(False)
        self.act_redo.setEnabled(False)
        self.undo_group.canUndoChanged.connect(self.act_undo.setEnabled)
        self.undo_group.canRedoChanged.connect(self.act_redo.setEnabled)
        self.undo_group.undoTextChanged.connect(lambda _t: self._refresh_undo_tips())
        self.undo_group.redoTextChanged.connect(lambda _t: self._refresh_undo_tips())
        self.act_merge = act(sc.PAGE_MERGE, "Sayfayı Birleştir", self.merge_page,
                             "Metinleri ve boyamayı tek katmana birleştir")

        self.act_zoom_out = act(sc.VIEW_ZOOM_OUT, "−", self.canvas.zoom_out, "Uzaklaştır")
        self.act_zoom_in = act(sc.VIEW_ZOOM_IN, "+", self.canvas.zoom_in, "Yakınlaştır")
        self.act_fit = act(sc.VIEW_FIT, "Sığdır", self.canvas.fit_to_window, "Ekrana sığdır")
        self.act_actual = act(sc.VIEW_ACTUAL, "%100", self.canvas.actual_size, "Gerçek boyut")

        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_actions: dict[Tool, QAction] = {}
        specs = (
            (Tool.BRUSH, icons.brush_icon(), sc.TOOL_BRUSH),
            (Tool.ERASER, icons.eraser_icon(), sc.TOOL_ERASER),
            (Tool.CLONE, icons.clone_icon(), sc.TOOL_CLONE),
            (Tool.EYEDROPPER, icons.eyedropper_icon(), sc.TOOL_EYEDROPPER),
            (Tool.TEXT, icons.text_icon(), sc.TOOL_TEXT),
        )
        for tool, icon, sid in specs:
            a = QAction(icon, tr(TOOL_LABELS[tool]), self)
            a.setCheckable(True)
            a.triggered.connect(lambda _c=False, t=tool: self.tools.set_tool(t))
            reg.bind_action(sid, a, tr(TOOL_LABELS[tool]))
            self.tool_group.addAction(a)
            self.addAction(a)
            self.tool_actions[tool] = a
        self.tool_actions[self.tools.tool].setChecked(True)
        self.project_actions = (self.act_save, self.act_close_project, self.act_add_pages, self.act_export)
        self.page_actions = (self.act_remove_page, self.act_move_left, self.act_move_right, self.act_merge,
                             self.act_set_target,
                             self.act_zoom_in, self.act_zoom_out, self.act_fit, self.act_actual)

    def _refresh_undo_tips(self) -> None:
        """Undo/redo tooltips: the last action name plus the current shortcut."""
        for action, sid, verb, text in (
            (self.act_undo, sc.EDIT_UNDO, tr("Geri al"), self.undo_group.undoText()),
            (self.act_redo, sc.EDIT_REDO, tr("Yinele"), self.undo_group.redoText()),
        ):
            keys = self.shortcuts.display(sid) if self.shortcuts.sequences(sid) else ""
            label = f"{verb}: {text}" if text else verb
            action.setToolTip(f"{label} ({keys})" if keys else label)

    def _on_shortcuts_changed(self) -> None:
        self._refresh_undo_tips()
        self.side_panel.clone_panel.set_hold_key_text(self.shortcuts.display(sc.CLONE_SOURCE_HOLD))
        self.canvas._update_cursor()

    def open_shortcuts_dialog(self) -> None:
        self.commit_ui_state()
        dlg = ShortcutsDialog(self.shortcuts, self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)  # new dialog each time, no leaks
        dlg.exec()

    def open_language_dialog(self) -> None:
        """Language choice. The new language is applied after a restart."""
        current = i18n.current()
        box = QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setText("Dil / Language")
        box.setInformativeText(tr("Değişiklik uygulamayı yeniden başlattığınızda geçerli olur."))
        tr_btn = box.addButton("Türkçe", QMessageBox.ButtonRole.AcceptRole)
        en_btn = box.addButton("English", QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("Vazgeç"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        chosen = "tr" if clicked is tr_btn else "en" if clicked is en_btn else None
        if chosen and chosen != current:
            i18n.set_language(chosen, self.settings)
            # The confirmation is written in the language that was just chosen.
            QMessageBox.information(self, APP_NAME, i18n.tr_in(
                chosen, "Dil kaydedildi. Uygulamayı yeniden başlatın."))

    def refresh_clone_panel(self) -> None:
        scene = self.scene_
        patch = scene.clone_patch if scene is not None else None
        self.side_panel.clone_panel.set_source(
            scene.clone_source if scene is not None else None,
            scene.clone_offset if scene is not None else None,
            (patch.width, patch.height) if patch is not None else None)

    def _on_clone_mode_changed(self) -> None:
        """The mode preference is saved. The source POINT is kept; only the aligned mode's
        locked offset is reset (the next stroke starts from the marked source)."""
        self.settings.setValue("clone_aligned", self.tools.clone_aligned)
        self.settings.sync()  # save right away so the preference survives a crash
        for scene in self.scenes.values():
            scene.clone_offset = None
        self.refresh_clone_panel()
        self.canvas.viewport().update()

    def _build_menus(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu(tr("Dosya"))
        m.addAction(self.act_new)
        m.addAction(self.act_open)
        self.recent_menu = m.addMenu(tr("Son Projeler"))
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        m.addSeparator()
        m.addAction(self.act_save)
        m.addAction(self.act_autosave)
        m.addSeparator()
        m.addAction(self.act_add_pages)
        m.addAction(self.act_export)
        m.addSeparator()
        m.addAction(self.act_close_project)
        m.addAction(self.act_quit)
        m = mb.addMenu(tr("Düzen"))
        m.addAction(self.act_undo)
        m.addAction(self.act_redo)
        m.addSeparator()
        m.addAction(self.act_merge)
        m = mb.addMenu(tr("Sayfa"))
        m.addAction(self.act_add_pages)
        m.addAction(self.act_remove_page)
        m.addSeparator()
        m.addAction(self.act_move_left)
        m.addAction(self.act_move_right)
        m.addSeparator()
        m.addAction(self.act_set_target)
        m = mb.addMenu(tr("Görünüm"))
        for a in (self.act_zoom_in, self.act_zoom_out, self.act_fit, self.act_actual):
            m.addAction(a)
        m = mb.addMenu(tr("Ayarlar"))
        m.addAction(self.act_shortcuts)
        m.addAction(self.act_language)

    def _build_toolbar(self) -> None:
        tb = QToolBar(tr("Ana"), self)
        tb.setObjectName("mainToolbar")
        tb.setMovable(False)
        for a in (self.act_open, self.act_save):
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(self.act_undo)
        tb.addAction(self.act_redo)
        tb.addSeparator()
        tb.addAction(self.act_add_pages)
        tb.addAction(self.act_merge)
        tb.addAction(self.act_export)
        tb.addSeparator()
        tb.addAction(self.act_zoom_out)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(52)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tb.addWidget(self.zoom_label)
        tb.addAction(self.act_zoom_in)
        tb.addAction(self.act_fit)
        tb.addAction(self.act_actual)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
        self.main_toolbar = tb

    def _build_tools_bar(self) -> None:
        tb = QToolBar(tr("Araçlar"), self)
        tb.setObjectName("toolsBar")
        tb.setMovable(False)
        tb.setOrientation(Qt.Orientation.Vertical)
        tb.setIconSize(QSize(24, 24))
        for a in self.tool_actions.values():
            tb.addAction(a)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, tb)
        self.tools_toolbar = tb

    def _build_statusbar(self) -> None:
        self.status_size = QLabel("")
        self.status_pos = QLabel("")
        self.statusBar().addPermanentWidget(self.status_pos)
        self.statusBar().addPermanentWidget(self.status_size)

    # ================================================================== helpers
    @property
    def page(self) -> PageDocument | None:
        if self.project is None or self._current_id is None:
            return None
        i = self.project.index_of(self._current_id)
        return self.project.pages[i] if i >= 0 else None

    @property
    def scene_(self) -> PageScene | None:
        return self.scenes.get(self._current_id) if self._current_id else None

    def ask_unsaved(self) -> str:
        """Returns 'save', 'discard' or 'cancel'."""
        B = QMessageBox.StandardButton
        r = QMessageBox.question(
            self, APP_NAME, tr("Projede kaydedilmemiş değişiklikler var. Kaydedilsin mi?"),
            B.Save | B.Discard | B.Cancel, B.Save)
        return {B.Save: "save", B.Discard: "discard"}.get(r, "cancel")

    def ask_recovery(self, root: Path) -> bool:
        B = QMessageBox.StandardButton
        r = QMessageBox.question(
            self, APP_NAME,
            tr("Bu proje beklenmedik şekilde kapanmış görünüyor ve kaydedilmemiş değişiklikler bulundu.\n\n"
               "Kurtarılan değişiklikler geri yüklensin mi?\n"
               "(Hayır seçilirse kurtarma kopyası silinir ve son kaydedilen hâl açılır.)"),
            B.Yes | B.No, B.Yes)
        return r == B.Yes

    def _error(self, text: str) -> None:
        QMessageBox.warning(self, APP_NAME, text)

    def commit_ui_state(self) -> None:
        """Completes in-progress interactions (brush stroke, text editing).
        Called before saving, switching tabs, merging and undo."""
        self.canvas.finish_interaction()
        if self.scene_ is not None:
            self.scene_.finish_editing()

    def _show_project_ui(self, has_project: bool) -> None:
        self.center_stack.setCurrentIndex(1 if has_project else 0)
        for a in self.project_actions:
            a.setEnabled(has_project)
        has_page = has_project and self.page is not None
        for a in self.page_actions:
            a.setEnabled(has_page)
        self.side_panel.setVisible(has_project)
        self.tools_toolbar.setVisible(has_project)
        self.tools_toolbar.setEnabled(has_page)
        if not has_project:
            self.welcome.set_recent(self.recent_projects())
        self._update_title()

    def _update_title(self) -> None:
        if self.project is None:
            self.setWindowTitle(APP_NAME)
            return
        mark = "*" if self.project.needs_save else ""
        page = self.page
        page_part = f" – {page.name}" if page is not None else ""
        self.setWindowTitle(f"{mark}{self.project.name}{page_part} – {APP_NAME}")

    # ================================================================== project
    def new_project_dialog(self, suggested_name: str = "", location: str | Path | None = None) -> bool:
        dlg = NewProjectDialog(self, suggested_name, location or self.settings.value("last_location", None))
        while dlg.exec():
            name, loc = dlg.values()
            try:
                self.create_project(loc, name)
                return True
            except (ProjectError, OSError) as e:
                self._error(str(e))
        return False

    def create_project(self, parent_dir: str | Path, name: str) -> Project:
        if not self.close_project():
            raise ProjectError(tr("Açık proje kapatılamadı."))
        project = Project.create(parent_dir, name)
        self.settings.setValue("last_location", str(Path(parent_dir)))
        self._set_project(project)
        return project

    def open_project_dialog(self) -> None:
        start = str(Path(self.settings.value("last_location", str(default_projects_dir()))))
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Proje Aç"), start, tr("Manga Editör Projesi ({file})", file=PROJECT_FILE))
        if path:
            self.open_project(path)

    def open_project(self, path: str | Path) -> bool:
        root = Path(path)
        if root.is_file():
            root = root.parent
        if self.project is not None and self.project.root.resolve() == root.resolve():
            return True
        if not self.close_project():
            return False
        use_recovery = False
        if Project.has_recovery(root):
            use_recovery = self.ask_recovery(root)
        try:
            project = Project.open(root, use_recovery=use_recovery)
        except ProjectError as e:
            self._error(str(e))
            self._remove_recent(str(root))
            self._show_project_ui(False)
            return False
        if not use_recovery:
            project.discard_recovery()
        self._set_project(project)
        if project.warnings:
            self._error(tr("Proje açıldı, ancak bazı sorunlar var:\n\n") + "\n".join(project.warnings))
        if use_recovery:
            self.statusBar().showMessage(
                tr("Kurtarılan değişiklikler yüklendi. Kalıcı olması için kaydedin (Ctrl+S)."), 10000)
        return True

    def _set_project(self, project: Project) -> None:
        self.project = project
        self.fonts.unload_all()
        _fams, errors = self.fonts.load_dir(project.fonts_dir)
        if errors:
            project.warnings.extend(errors)
        missing = sorted({t.font_family for p in project.pages for t in p.texts
                          if not FontManager.is_available(t.font_family)})
        if missing:
            project.warnings.append(
                tr("Bulunamayan fontlar (yerine benzer font kullanılır): ") + ", ".join(missing))
        for page in project.pages:
            self._attach_page(page)
        project.dirtyChanged.connect(lambda _d: self._update_title())
        project.pagesChanged.connect(self._update_title)
        self._add_recent(str(project.root))
        self.settings.setValue("last_project", str(project.root))
        self._rebuild_tabs()
        self._show_project_ui(True)
        if project.pages:
            self.switch_to_page(0)
        else:
            self._show_page(None)

    def _attach_page(self, page: PageDocument) -> None:
        self.undo_group.addStack(page.undo_stack)
        page.dirtyChanged.connect(lambda _d, pid=page.id: self._refresh_tab_for(pid))

    def close_project(self) -> bool:
        """Asks about unsaved changes. Returns True if the project was closed (or none was open)."""
        if self.project is None:
            return True
        self.commit_ui_state()
        if self.project.needs_save:
            answer = self.ask_unsaved()
            if answer == "cancel":
                return False
            if answer == "save" and not self.save_project():
                return False
            if answer == "discard":
                self.project.discard_recovery()
        project, self.project = self.project, None
        self.canvas.set_page_scene(None, fit=False)
        self._current_id = None
        for page in project.pages:
            self.undo_group.removeStack(page.undo_stack)
        for scene in self.scenes.values():
            scene.deleteLater()
        self.scenes.clear()
        self._view_states.clear()
        self._syncing_tabs = True
        while self.tabbar.count():
            self.tabbar.removeTab(0)
        self._syncing_tabs = False
        self.fonts.unload_all()
        project.deleteLater()
        self._show_project_ui(False)
        self.status_size.setText("")
        return True

    def save_project(self, quiet: bool = False, export_images: bool = True) -> bool:
        """Saves the project. With export_images=True (Ctrl+S, Save on exit), the edited
        image of every changed page is also written to its target file. If an image cannot
        be written, the project data is still saved, the user is informed and False is
        returned (which cancels closing)."""
        if self.project is None:
            return False
        self.commit_ui_state()
        written: list[Path] = []
        out_errors: list[str] = []
        if export_images:
            written, out_errors = write_page_outputs(self.project)
        try:
            self.project.save()  # keep the project data even if an image failed
        except (OSError, ProjectError) as e:
            self._error(tr("Proje kaydedilemedi:\n{e}", e=e))
            return False
        self._refresh_all_tabs()
        self._update_title()
        if quiet:
            msg = tr("Otomatik kaydedildi (görseller Ctrl+S ile güncellenir).")
        elif written:
            msg = tr("Kaydedildi · {n} görsel güncellendi.", n=len(written))
        else:
            msg = tr("Kaydedildi.")
        self.statusBar().showMessage(msg, 6000)
        if out_errors:
            self._error(
                tr("Proje kaydedildi, ancak bazı sayfaların düzenlenmiş görseli yazılamadı:\n\n")
                + "\n".join(out_errors)
                + tr("\n\nBu sayfalar bir sonraki kaydetmede yeniden denenecek. Hedefi değiştirmek için: ")
                + tr("Sayfa > Kaydetme Hedefini Değiştir…"))
            return False
        return True

    def write_recovery(self) -> None:
        if self.project is None or not self.project.is_dirty or self.canvas.is_stroking():
            return
        try:
            self.project.write_recovery()
        except (OSError, ProjectError):
            pass  # the recovery copy is best effort; do not interrupt the work

    def autosave(self) -> None:
        if self.project is None or not self.act_autosave.isChecked() or not self.project.is_dirty:
            return
        if self.canvas.is_stroking() or self.canvas.is_editing_text():
            return  # do not interrupt the user; it is saved on the next tick
        # Autosave never overwrites source images; it only saves the project data.
        self.save_project(quiet=True, export_images=False)

    # ------------------------------------------------------------------ recent projects
    def recent_projects(self) -> list[str]:
        raw = self.settings.value("recent_projects", [])
        if isinstance(raw, str):
            raw = [raw]
        return [p for p in (raw or []) if (Path(p) / PROJECT_FILE).exists()]

    def _add_recent(self, path: str) -> None:
        items = [p for p in self.recent_projects() if Path(p).resolve() != Path(path).resolve()]
        self.settings.setValue("recent_projects", [path] + items[: MAX_RECENT - 1])

    def _remove_recent(self, path: str) -> None:
        self.settings.setValue("recent_projects", [p for p in self.recent_projects() if p != path])

    def _fill_recent_menu(self) -> None:
        self.recent_menu.clear()
        recent = self.recent_projects()
        if not recent:
            a = self.recent_menu.addAction(tr("(boş)"))
            a.setEnabled(False)
        for p in recent:
            self.recent_menu.addAction(f"{Path(p).name}  —  {p}", lambda path=p: self.open_project(path))

    def restore_last_project(self) -> None:
        last = self.settings.value("last_project", "")
        if last and (Path(last) / PROJECT_FILE).exists():
            self.open_project(last)

    # ================================================================== pages
    def add_pages_dialog(self) -> None:
        start = self.settings.value("last_image_dir", "")
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Sayfa Ekle"), start, tr(INPUT_FILTER))
        if paths:
            self.settings.setValue("last_image_dir", str(Path(paths[0]).parent))
            self.add_pages(paths)

    def add_pages(self, paths: list[str | Path]) -> list[PageDocument]:
        paths = [Path(p) for p in paths]
        if self.project is None:
            # No project yet: suggest a new project named after the image folder.
            first = paths[0] if paths else None
            name = first.parent.name if first else ""
            if not self.new_project_dialog(name):
                return []
        assert self.project is not None
        self.commit_ui_state()
        added, errors = self.project.add_images(paths)
        for page in added:
            self._attach_page(page)
        if added:
            self._rebuild_tabs()
            self.switch_to_page(self.project.index_of(added[0].id))
            self._show_project_ui(True)
            self.statusBar().showMessage(tr("{n} sayfa eklendi.", n=len(added)), 5000)
        if errors:
            self._error(tr("Bazı dosyalar eklenemedi:\n\n") + "\n".join(errors))
        return added

    def remove_current_page(self) -> None:
        if self.project is None or self.page is None:
            return
        self.remove_page(self.project.index_of(self.page.id))

    def remove_page(self, index: int, confirm: bool = True) -> None:
        if self.project is None or not (0 <= index < len(self.project.pages)):
            return
        page = self.project.pages[index]
        if confirm:
            B = QMessageBox.StandardButton
            r = QMessageBox.question(
                self, APP_NAME,
                tr("'{name}' sayfası projeden kaldırılsın mı?\n\n", name=page.name)
                + tr("Bu işlem geri alınamaz. Orijinal görsel dosyası proje klasöründe kalır."),
                B.Yes | B.No, B.No)
            if r != B.Yes:
                return
        self.commit_ui_state()
        was_current = page.id == self._current_id
        self.project.remove_page(index)
        self.undo_group.removeStack(page.undo_stack)
        scene = self.scenes.pop(page.id, None)
        if was_current:
            self.canvas.set_page_scene(None, fit=False)
            self._current_id = None
        if scene is not None:
            scene.deleteLater()
        self._view_states.pop(page.id, None)
        self._rebuild_tabs()
        if self.project.pages:
            self.switch_to_page(min(index, len(self.project.pages) - 1))
        else:
            self._show_page(None)

    def move_current_page(self, delta: int) -> None:
        if self.project is None or self.page is None:
            return
        i = self.project.index_of(self.page.id)
        j = i + delta
        if 0 <= j < len(self.project.pages):
            self.project.move_page(i, j)
            self._rebuild_tabs()
            self.switch_to_page(j)

    def change_output_target_dialog(self) -> None:
        page = self.page
        if self.project is None or page is None:
            return
        current = self.project.output_target(page)
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Kaydetme Hedefi"), str(current),
            tr(INPUT_FILTER) + ";;PNG (*.png);;JPG (*.jpg *.jpeg);;WEBP (*.webp)")
        if path:
            self.set_output_target(page, path)

    def set_output_target(self, page: PageDocument, path: str | Path) -> bool:
        """Changes the page's save target (after the safety checks)."""
        assert self.project is not None
        try:
            self.project.set_output_target(page, path)
        except ProjectError as e:
            self._error(tr("Bu hedef kullanılamaz:\n{e}", e=e))
            return False
        self._refresh_tab_for(page.id)
        self.statusBar().showMessage(tr("Kaydetme hedefi: {t}", t=self.project.output_target(page)), 6000)
        return True

    def switch_to_page(self, index: int) -> None:
        if self.project is None or not (0 <= index < len(self.project.pages)):
            return
        if self.tabbar.currentIndex() != index:
            self._syncing_tabs = True
            self.tabbar.setCurrentIndex(index)
            self._syncing_tabs = False
        self._show_page(self.project.pages[index])

    def _show_page(self, page: PageDocument | None) -> None:
        self.commit_ui_state()
        old = self.scene_
        if old is not None and self._current_id is not None:
            center = self.canvas.mapToScene(self.canvas.viewport().rect().center())
            self._view_states[self._current_id] = (self.canvas.transform(), QPointF(center))
        if page is None:
            self._current_id = None
            self.canvas.set_page_scene(None, fit=False)
            self.undo_group.setActiveStack(None)
            self.status_size.setText("")
            self._show_project_ui(self.project is not None)
            return
        try:
            page.ensure_loaded()
        except (ProjectError, OSError) as e:
            self._error(str(e))
            self._current_id = page.id
            self.canvas.set_page_scene(None, fit=False)
            self.undo_group.setActiveStack(page.undo_stack)
            self._show_project_ui(True)
            return
        scene = self.scenes.get(page.id)
        if scene is None:
            scene = PageScene(page)
            scene.textSelectionChanged.connect(self.refresh_text_panel)
            self.scenes[page.id] = scene
        self._current_id = page.id
        state = self._view_states.get(page.id)
        self.canvas.set_page_scene(scene, fit=state is None)
        if state is not None:
            self.canvas.setTransform(state[0])
            self.canvas.centerOn(state[1])
            self.canvas._zoom_updated()
        self.undo_group.setActiveStack(page.undo_stack)
        self.status_size.setText(f"{page.size.width()} × {page.size.height()} px")
        self._show_project_ui(True)
        self.refresh_text_panel()

    # ------------------------------------------------------------------ tabs
    def _tab_text(self, page: PageDocument, index: int) -> str:
        return f"{DIRTY_MARK if page.needs_attention else ''}{index + 1}. {page.name}"

    def _tab_tooltip(self, page: PageDocument) -> str:
        assert self.project is not None
        state = tr("\n(düzenlenmiş görsel henüz yazılmadı – Ctrl+S)") if page.output_stale else ""
        return f"{page.name}\n{tr('Kaydetme hedefi:')} {self.project.output_target(page)}{state}"

    def _rebuild_tabs(self) -> None:
        self._syncing_tabs = True
        try:
            while self.tabbar.count():
                self.tabbar.removeTab(0)
            if self.project is not None:
                for i, page in enumerate(self.project.pages):
                    t = self.tabbar.addTab(self._tab_text(page, i))
                    self.tabbar.setTabData(t, page.id)
                    self.tabbar.setTabToolTip(t, self._tab_tooltip(page))
                if self._current_id is not None:
                    i = self.project.index_of(self._current_id)
                    if i >= 0:
                        self.tabbar.setCurrentIndex(i)
        finally:
            self._syncing_tabs = False

    def _refresh_tab_for(self, page_id: str) -> None:
        if self.project is None:
            return
        i = self.project.index_of(page_id)
        if 0 <= i < self.tabbar.count():
            self.tabbar.setTabText(i, self._tab_text(self.project.pages[i], i))
            self.tabbar.setTabToolTip(i, self._tab_tooltip(self.project.pages[i]))
        self._update_title()

    def _refresh_all_tabs(self) -> None:
        if self.project is None:
            return
        for i, page in enumerate(self.project.pages):
            if i < self.tabbar.count():
                self.tabbar.setTabText(i, self._tab_text(page, i))
                self.tabbar.setTabToolTip(i, self._tab_tooltip(page))

    def _on_tab_changed(self, index: int) -> None:
        if self._syncing_tabs or self.project is None or index < 0:
            return
        self._show_page(self.project.pages[index])

    def _on_tab_moved(self, src: int, dst: int) -> None:
        if self._syncing_tabs or self.project is None:
            return
        self.project.move_page(src, dst)
        self._refresh_all_tabs()  # renumber the tabs

    def _tab_context_menu(self, pos) -> None:
        index = self.tabbar.tabAt(pos)
        if index < 0:
            return
        self.switch_to_page(index)
        m = QMenu(self)
        m.addAction(self.act_move_left)
        m.addAction(self.act_move_right)
        m.addSeparator()
        m.addAction(self.act_set_target)
        m.addAction(self.act_remove_page)
        m.exec(self.tabbar.mapToGlobal(pos))

    # ================================================================== editing
    def undo(self) -> None:
        self.commit_ui_state()
        self.undo_group.undo()

    def redo(self) -> None:
        self.commit_ui_state()
        self.undo_group.redo()

    def merge_page(self) -> None:
        self.commit_ui_state()
        page = self.page
        if page is None or not page.is_loaded:
            return
        if not page.texts:
            self.statusBar().showMessage(tr("Birleştirilecek metin yok."), 4000)
            return
        n = len(page.texts)
        page.undo_stack.push(MergePageCommand(page))
        self.statusBar().showMessage(
            tr("{n} metin boya katmanına birleştirildi. Geri almak için Ctrl+Z.", n=n), 6000)

    # ------------------------------------------------------------------ text panel
    def refresh_text_panel(self) -> None:
        items = self.scene_.selected_text_items() if self.scene_ is not None else []
        data = items[0].data if items else self.tools.text_defaults
        self.text_panel.load(data, len(items))

    def _on_text_field_edited(self, field: str, value) -> None:
        if field not in GEOMETRY_FIELDS:
            # The last used style becomes the default for new texts.
            self.tools.set_text_defaults(self.tools.text_defaults.with_(**{field: value}))
        if self.scene_ is not None:
            self.scene_.apply_style(field, value)

    def _store_text_defaults(self) -> None:
        self.settings.setValue("text_defaults", json.dumps(self.tools.text_defaults.to_dict(), ensure_ascii=False))

    def _restore_text_defaults(self) -> None:
        raw = self.settings.value("text_defaults", "")
        if raw:
            try:
                self.tools.set_text_defaults(TextData.from_dict(json.loads(raw)))
            except (ValueError, TypeError):
                pass

    def load_font_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Font Yükle"), "", tr(FONT_FILTER))
        if paths:
            self.load_fonts(paths)

    def load_fonts(self, paths: list[str | Path]) -> list[str]:
        """Loads fonts (copying them into the project's fonts/ folder when a project is
        open) and applies the first one to the selected text or the defaults."""
        families: list[str] = []
        errors: list[str] = []
        fonts_dir = self.project.fonts_dir if self.project is not None else None
        for p in paths:
            try:
                families.extend(self.fonts.import_font(p, fonts_dir))
            except (FontLoadError, OSError) as e:
                errors.append(str(e))
        if errors:
            self._error("\n".join(errors))
        if families:
            self.statusBar().showMessage(tr("Yüklenen font: ") + ", ".join(families), 6000)
            self._on_text_field_edited("font_family", families[0])
            self.refresh_text_panel()
        return families

    # ================================================================== export
    def export_dialog(self) -> None:
        if self.project is None or not self.project.pages:
            self.statusBar().showMessage(tr("Dışa aktarılacak sayfa yok."), 4000)
            return
        self.commit_ui_state()
        current = self.project.index_of(self._current_id) if self._current_id else 0
        dlg = ExportDialog(self.project.pages, current, Path(self.settings.value(
            "export_dir/" + str(self.project.root), str(self.project.exports_dir))), self)
        if not dlg.exec():
            return
        indices = dlg.selected_indices()
        if not indices:
            self.statusBar().showMessage(tr("Hiç sayfa seçilmedi."), 4000)
            return
        out_dir = Path(dlg.out_edit.text())
        self.settings.setValue("export_dir/" + str(self.project.root), str(out_dir))
        written, errors = self.export(indices, out_dir, dlg.fmt(), dlg.quality.value(), show_progress=True)
        if errors:
            self._error(tr("Bazı sayfalar dışa aktarılamadı:\n\n") + "\n".join(errors))
        if written:
            box = QMessageBox(self)
            box.setWindowTitle(APP_NAME)
            box.setText(tr("{n} sayfa dışa aktarıldı:\n{d}", n=len(written), d=out_dir))
            open_btn = box.addButton(tr("Klasörü Aç"), QMessageBox.ButtonRole.ActionRole)
            box.addButton(tr("Tamam"), QMessageBox.ButtonRole.AcceptRole)
            box.exec()
            if box.clickedButton() is open_btn:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_dir)))

    def export(self, indices: list[int], out_dir: Path, fmt: str, quality: int = 95,
               show_progress: bool = False) -> tuple[list[Path], list[str]]:
        assert self.project is not None
        self.commit_ui_state()
        pages = [(i + 1, self.project.pages[i]) for i in indices]
        progress = None
        if show_progress and len(pages) > 1:
            dlg = QProgressDialog(tr("Dışa aktarılıyor…"), tr("İptal"), 0, len(pages), self)
            dlg.setWindowModality(Qt.WindowModality.WindowModal)
            dlg.setMinimumDuration(300)

            def progress(i, total, name):
                dlg.setValue(i)
                dlg.setLabelText(tr("Dışa aktarılıyor: {name}", name=name) if name else tr("Tamamlandı"))
                return not dlg.wasCanceled()
        return export_pages(pages, out_dir, fmt, quality, progress)

    # ================================================================== events
    def _on_tool_changed(self, tool: Tool) -> None:
        a = self.tool_actions.get(tool)
        if a is not None and not a.isChecked():
            a.setChecked(True)
        if tool == Tool.TEXT:
            self.refresh_text_panel()

    def _on_zoom(self, z: float) -> None:
        self.zoom_label.setText(f"{z * 100:.0f}%")

    def _on_cursor(self, p: QPointF) -> None:
        page = self.page
        if page is None:
            return
        x, y = int(p.x()), int(p.y())
        if 0 <= x < page.size.width() and 0 <= y < page.size.height():
            self.status_pos.setText(f"x {x}, y {y}")
        else:
            self.status_pos.setText("")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        projects = [p for p in paths if p.name == PROJECT_FILE or (p / PROJECT_FILE).exists()]
        if projects:
            self.open_project(projects[0])
        else:
            images = [p for p in paths if is_supported_input(p)]
            if images:
                self.add_pages(images)
            elif paths:
                self.statusBar().showMessage(tr("Desteklenen biçimler: PNG, JPG, JPEG, WEBP"), 5000)
        event.acceptProposedAction()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.close_project():
            event.ignore()
            return
        self.settings.setValue("window/geometry", self.saveGeometry())
        event.accept()

    def changeEvent(self, event) -> None:
        # Release held keys when the window loses focus (Alt+Tab) so they do not get stuck.
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            self.shortcuts.release_all()
        super().changeEvent(event)
