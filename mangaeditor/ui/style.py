"""Dark, simple theme."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#4c8dff"

STYLESHEET = f"""
QMainWindow, QWidget {{ font-size: 13px; }}
QToolBar {{ background: #24272d; border: none; spacing: 4px; padding: 4px; }}
QToolBar#toolsBar {{ border-right: 1px solid #1a1c20; padding: 6px 4px; }}
QToolBar QToolButton {{
    background: transparent; border: 1px solid transparent; border-radius: 6px;
    padding: 5px 9px; color: #d7dae0;
}}
QToolBar QToolButton:hover {{ background: #30343b; }}
QToolBar QToolButton:checked {{ background: #2f4f86; border-color: {ACCENT}; }}
QToolBar QToolButton:disabled {{ color: #6b7079; }}
QToolBar#toolsBar QToolButton {{ padding: 6px; }}
QTabBar {{ background: #24272d; }}
QTabBar::tab {{
    background: #2a2d33; color: #b8bcc4; padding: 6px 14px; border: none;
    border-right: 1px solid #1d1f23; min-width: 60px;
}}
QTabBar::tab:selected {{ background: #1b1d21; color: #ffffff; }}
QTabBar::tab:hover:!selected {{ background: #32363d; }}
QWidget#sidePanel {{ background: #24272d; border-left: 1px solid #1a1c20; }}
QLabel#panelTitle {{ font-size: 14px; font-weight: 600; color: #ffffff; padding-bottom: 4px; }}
QLabel#hint {{ color: #8b9099; }}
QGroupBox {{ border: 1px solid #353941; border-radius: 6px; margin-top: 10px; padding-top: 6px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #c9ccd2; }}
QPushButton {{
    background: #31353c; border: 1px solid #3c4048; border-radius: 5px; padding: 5px 10px; color: #e2e4e8;
}}
QPushButton:hover {{ background: #3a3f47; }}
QPushButton:checked {{ background: #2f4f86; border-color: {ACCENT}; }}
QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; color: white; font-weight: 600; }}
QStatusBar {{ background: #24272d; color: #9ea3ab; }}
QStatusBar::item {{ border: none; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    base = QColor("#1f2125")
    window = QColor("#24272d")
    text = QColor("#e2e4e8")
    pal.setColor(QPalette.ColorRole.Window, window)
    pal.setColor(QPalette.ColorRole.WindowText, text)
    pal.setColor(QPalette.ColorRole.Base, base)
    pal.setColor(QPalette.ColorRole.AlternateBase, window)
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#30343b"))
    pal.setColor(QPalette.ColorRole.ToolTipText, text)
    pal.setColor(QPalette.ColorRole.Text, text)
    pal.setColor(QPalette.ColorRole.Button, QColor("#31353c"))
    pal.setColor(QPalette.ColorRole.ButtonText, text)
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor("#7d828b"))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor("#6b7079"))
    app.setPalette(pal)
    app.setStyleSheet(STYLESHEET)
