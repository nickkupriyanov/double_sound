"""Точка входа приложения."""

from __future__ import annotations

import ctypes
import os
import sys

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from . import __version__
from .core.paths import resource_path
from .settings_store import app_settings
from .ui.main_window import MainWindow
from .ui.styles import apply_theme


def _set_windows_app_id() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "DoubleSound.DoubleSound.1"
        )
    except Exception:
        pass


def main() -> int:
    _set_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName("DoubleSound")
    app.setApplicationDisplayName("Double Sound")
    app.setOrganizationName("DoubleSound")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")

    font = QFont(app.font())
    font.setPointSize(10)
    if os.name == "nt":
        font.setFamily("Segoe UI")
    app.setFont(font)

    icon_path = resource_path("icon.svg")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    settings = app_settings()
    theme = str(settings.value("theme", "light") or "light")
    apply_theme(app, theme)

    window = MainWindow()
    window.show()
    return app.exec()
