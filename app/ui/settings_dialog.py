"""Диалог настроек."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core.cache import Cache
from ..core.fingerprint import find_fpcalc
from ..core.models import human_size


class SettingsDialog(QDialog):
    def __init__(self, values: dict, cache_path: str | Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setModal(True)
        self.setMinimumWidth(460)
        self._cache_path = Path(cache_path)
        self._values = dict(values)
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("Настройки поиска")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)

        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(70, 99)
        self.threshold_label = QLabel("88 %")
        self.threshold_label.setMinimumWidth(54)
        self.threshold_slider.valueChanged.connect(
            lambda value: self.threshold_label.setText(f"{value} %")
        )
        threshold_row = QHBoxLayout()
        threshold_row.addWidget(self.threshold_slider, 1)
        threshold_row.addWidget(self.threshold_label)
        threshold_wrap = QWidget()
        threshold_wrap.setLayout(threshold_row)
        form.addRow("Минимальная схожесть", threshold_wrap)

        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 3600)
        self.duration_spin.setSuffix(" с")
        form.addRow("Минимальная длительность", self.duration_spin)

        self.length_combo = QComboBox()
        for seconds in (60, 90, 120, 180, 240):
            self.length_combo.addItem(f"{seconds} секунд", seconds)
        form.addRow("Анализировать фрагмент", self.length_combo)

        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 32)
        form.addRow("Потоков анализа", self.workers_spin)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Светлая", "light")
        self.theme_combo.addItem("Тёмная", "dark")
        form.addRow("Тема оформления", self.theme_combo)

        self.acoustic_check = QCheckBox("Искать одну песню в разном качестве")
        form.addRow("", self.acoustic_check)

        layout.addLayout(form)

        hint = QLabel(
            "Чем выше минимальная схожесть, тем строже поиск. "
            "Значения 85–92 % подходят для большинства коллекций. "
            "Параметры применяются при следующем сканировании."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        divider = QFrame()
        divider.setObjectName("Divider")
        layout.addWidget(divider)

        cache_title = QLabel("КЭШ АНАЛИЗА")
        cache_title.setObjectName("SectionTitle")
        layout.addWidget(cache_title)

        cache_row = QHBoxLayout()
        self.cache_label = QLabel("—")
        self.cache_label.setObjectName("Muted")
        self.clear_cache_button = QPushButton("Очистить кэш")
        self.clear_cache_button.setObjectName("Small")
        self.clear_cache_button.clicked.connect(self._clear_cache)
        cache_row.addWidget(self.cache_label, 1)
        cache_row.addWidget(self.clear_cache_button)
        layout.addLayout(cache_row)

        self.fpcalc_label = QLabel("")
        self.fpcalc_label.setObjectName("Muted")
        self.fpcalc_label.setWordWrap(True)
        layout.addWidget(self.fpcalc_label)

        layout.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("Сохранить")
        buttons.button(QDialogButtonBox.Ok).setObjectName("Primary")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_values(self) -> None:
        values = self._values
        similarity = int(round((1.0 - float(values.get("threshold", 0.12))) * 100))
        self.threshold_slider.setValue(max(70, min(99, similarity)))
        self.threshold_label.setText(f"{self.threshold_slider.value()} %")
        self.duration_spin.setValue(int(values.get("min_duration", 10)))
        index = self.length_combo.findData(int(values.get("fingerprint_length", 120)))
        self.length_combo.setCurrentIndex(max(0, index))
        self.workers_spin.setValue(int(values.get("workers", 4)))
        theme_index = self.theme_combo.findData(values.get("theme", "light"))
        self.theme_combo.setCurrentIndex(max(0, theme_index))
        self.acoustic_check.setChecked(bool(values.get("use_acoustic", True)))
        self._update_cache_label()
        self._update_fpcalc_label()

    def _update_cache_label(self) -> None:
        try:
            with Cache(self._cache_path) as cache:
                count, size = cache.stats()
            self.cache_label.setText(
                f"{count} записей · {human_size(size)} исходных файлов"
            )
        except Exception:
            self.cache_label.setText("Кэш недоступен")

    def _update_fpcalc_label(self) -> None:
        path = find_fpcalc()
        if path:
            self.fpcalc_label.setText(f"fpcalc: {path}")
        else:
            self.fpcalc_label.setText(
                "fpcalc не найден — поиск по звучанию недоступен. "
                "Файл fpcalc.exe должен лежать в папке программы."
            )

    def _clear_cache(self) -> None:
        answer = QMessageBox.question(
            self,
            "Очистить кэш?",
            "Кэш ускоряет повторное сканирование. После очистки отпечатки "
            "и хеши будут рассчитаны заново. Продолжить?",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            with Cache(self._cache_path) as cache:
                cache.clear()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Ошибка", f"Не удалось очистить кэш: {exc}")
        self._update_cache_label()

    def values(self) -> dict:
        similarity = self.threshold_slider.value()
        return {
            "threshold": round(1.0 - similarity / 100.0, 4),
            "min_duration": self.duration_spin.value(),
            "fingerprint_length": int(self.length_combo.currentData()),
            "workers": self.workers_spin.value(),
            "theme": self.theme_combo.currentData(),
            "use_acoustic": self.acoustic_check.isChecked(),
        }
