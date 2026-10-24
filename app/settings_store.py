"""Единая точка хранения пользовательских настроек."""

from __future__ import annotations

from PySide6.QtCore import QSettings

from .core.paths import settings_path


def app_settings() -> QSettings:
    """Настройки в settings.ini рядом с данными приложения.

    Ini-формат выбран специально: в портативной сборке настройки лежат рядом
    с программой, а не в реестре Windows.
    """
    return QSettings(str(settings_path()), QSettings.IniFormat)
