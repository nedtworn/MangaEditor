"""Application entry point."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication

from . import APP_NAME, ORG_NAME, i18n
from .ui.main_window import MainWindow
from .ui.style import apply_theme


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    # Choose the interface language (saved choice, otherwise the Windows language) before any
    # window is created, so every label is built in that language.
    i18n.init(QSettings())
    apply_theme(app)
    window = MainWindow()
    window.show()
    # If a project path was given on the command line, open it; otherwise open the last one.
    target = next((a for a in argv[1:] if Path(a).exists()), None)
    if target:
        QTimer.singleShot(0, lambda: window.open_project(target))
    else:
        QTimer.singleShot(0, window.restore_last_project)
    return app.exec()
