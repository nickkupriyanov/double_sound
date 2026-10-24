"""Пути к ресурсам и данным приложения."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def app_dir() -> Path:
    """Каталог с исходниками или распакованным приложением."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def resource_path(name: str) -> Path:
    """Ресурс из app/resources (в сборке — resources/)."""
    candidates = [
        app_dir() / "resources" / name,
        app_dir() / "app" / "resources" / name,
        Path(sys.executable).resolve().parent / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def data_dir() -> Path:
    """Каталог для кэша и настроек.

    В собранной версии данные лежат рядом с программой — сборка остаётся
    переносимой. Если папка только для чтения, используется системный каталог.
    """
    if getattr(sys, "frozen", False):
        portable = Path(sys.executable).resolve().parent / "data"
        try:
            portable.mkdir(parents=True, exist_ok=True)
            probe = portable / ".write_test"
            probe.write_bytes(b"")
            probe.unlink()
            return portable
        except OSError:
            pass

    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home())
        path = Path(base) / "DoubleSound"
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "DoubleSound"
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / "double-sound"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return data_dir() / "settings.ini"


def default_cache_path() -> Path:
    return data_dir() / "fingerprints.sqlite3"
