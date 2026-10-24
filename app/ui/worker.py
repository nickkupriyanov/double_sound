"""Фоновое сканирование с сигналами Qt."""

from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from ..core.engine import ScanCancelled, ScanEngine
from ..core.models import ScanOptions


class ScanWorker(QObject):
    progress = Signal(str, int, int, str)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, options: ScanOptions, cache_path: str | Path):
        super().__init__()
        self._options = options
        self._cache_path = cache_path
        self._cancel = threading.Event()
        self._last_emit = 0.0

    def cancel(self) -> None:
        """Вызывается из GUI-потока; потокобезопасно."""
        self._cancel.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    def _emit_progress(self, stage: str, done: int, total: int, current: str) -> None:
        now = time.monotonic()
        # Не заваливаем GUI сигналами на каждый файл.
        if done >= total or now - self._last_emit > 0.06:
            self._last_emit = now
            self.progress.emit(stage, done, total, current)

    @Slot()
    def run(self) -> None:
        engine = None
        try:
            engine = ScanEngine(self._options, self._cache_path)
            result = engine.scan(self._emit_progress, self._cancel)
            if self._cancel.is_set():
                self.cancelled.emit()
            else:
                self.finished.emit(result)
        except ScanCancelled:
            self.cancelled.emit()
        except Exception:  # noqa: BLE001 - показываем пользователю
            self.failed.emit(traceback.format_exc())
        finally:
            if engine is not None:
                try:
                    engine.close()
                except Exception:
                    pass
