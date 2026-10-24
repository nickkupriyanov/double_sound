"""Главное окно Double Sound."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import (
    QStandardPaths,
    Qt,
    QThread,
    QUrl,
)
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QDesktopServices,
    QIcon,
    QKeySequence,
    QPalette,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.models import (
    FORMAT_FILTER_LABELS,
    FORMAT_FILTERS,
    AudioFile,
    DuplicateGroup,
    ScanOptions,
    ScanResult,
    human_size,
    plural_ru,
)
from ..core.paths import default_cache_path, resource_path
from ..core.report import default_report_name, write_report
from ..settings_store import app_settings
from .compare_panel import ComparePanel
from .settings_dialog import SettingsDialog
from .styles import apply_theme, theme_colors
from .worker import ScanWorker

APP_TITLE = "Double Sound — поиск дубликатов музыки"
KIND_LABELS = {
    "exact": "точные копии",
    "acoustic": "по звучанию",
    "mixed": "смешанная группа",
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = app_settings()
        self._theme = str(self.settings.value("theme", "light") or "light")
        self._colors = theme_colors(self._theme)
        self._threshold = self._get_float("threshold", 0.12)
        self._groups: list[DuplicateGroup] = []
        self._last_result: ScanResult | None = None
        self._group_items: dict[int, QTreeWidgetItem] = {}
        self._child_items: dict[str, QTreeWidgetItem] = {}
        self._group_by_path: dict[str, DuplicateGroup] = {}
        self._scanning = False
        self._close_when_done = False
        self._warned_no_fpcalc = False
        self._thread: QThread | None = None
        self._worker: ScanWorker | None = None
        self._scan_started = 0.0
        self._warnings: list[str] = []
        self._errors: list[str] = []

        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(1080, 640)
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(
                max(1080, min(1380, available.width() - 80)),
                max(640, min(860, available.height() - 80)),
            )
        else:
            self.resize(1380, 860)
        self.setAcceptDrops(True)

        icon_path = resource_path("icon.svg")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._build_ui()
        self._restore_settings()
        apply_theme(QApplication.instance(), self._theme)
        self._colors = theme_colors(self._theme)
        self._apply_tree_palette()
        self._apply_windows_titlebar()
        self._install_shortcuts()
        self._update_folders_state()
        self._update_summary()
        self._show_placeholder(
            "Начните с выбора папок",
            "Добавьте папки с музыкой и нажмите «Сканировать». "
            "Программа найдёт точные копии и одну и ту же песню "
            "в разных форматах или битрейтах.",
        )

    # ------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_topbar())

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(16, 14, 16, 14)
        content_layout.setSpacing(0)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(10)
        self.splitter.addWidget(self._build_side_panel())
        self.splitter.addWidget(self._build_results_panel())
        self.compare_panel = ComparePanel()
        self.compare_panel.keeper_requested.connect(self._keeper_requested)
        self.compare_panel.open_folder_requested.connect(self._reveal_path)
        self.splitter.addWidget(self.compare_panel)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)
        self.splitter.setSizes([300, 760, 370])
        content_layout.addWidget(self.splitter)
        outer.addWidget(content, 1)

        self._build_statusbar()

    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(12)

        icon_label = QLabel()
        icon_label.setFixedSize(38, 38)
        icon_path = resource_path("icon.svg")
        pixmap = QPixmap(str(icon_path)) if icon_path.exists() else QPixmap()
        if not pixmap.isNull():
            icon_label.setPixmap(
                pixmap.scaled(38, 38, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            icon_label.setText("♪")
            icon_label.setStyleSheet("font-size: 28px; color: #2F6FED;")
        layout.addWidget(icon_label)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        app_title = QLabel("Double Sound")
        app_title.setObjectName("AppTitle")
        app_subtitle = QLabel("Поиск дубликатов музыки по звучанию")
        app_subtitle.setObjectName("AppSubtitle")
        titles.addWidget(app_title)
        titles.addWidget(app_subtitle)
        layout.addLayout(titles)
        layout.addStretch(1)

        self.add_folder_button = QPushButton("+  Добавить папки")
        self.add_folder_button.setToolTip("Добавить папку с музыкой (Ctrl+O)")
        self.add_folder_button.clicked.connect(self._choose_folder)
        layout.addWidget(self.add_folder_button)

        self.scan_button = QPushButton("Сканировать")
        self.scan_button.setObjectName("Primary")
        self.scan_button.setMinimumWidth(132)
        self.scan_button.setToolTip("Начать поиск дубликатов (F5)")
        self.scan_button.clicked.connect(self._start_scan)
        layout.addWidget(self.scan_button)

        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.setObjectName("Danger")
        self.cancel_button.setToolTip("Остановить сканирование (Esc)")
        self.cancel_button.clicked.connect(self._cancel_scan)
        self.cancel_button.hide()
        layout.addWidget(self.cancel_button)

        self.settings_button = QPushButton("Настройки")
        self.settings_button.clicked.connect(self._open_settings)
        layout.addWidget(self.settings_button)
        return bar

    def _build_side_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Card")
        panel.setMinimumWidth(250)
        panel.setMaximumWidth(340)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)

        header = QHBoxLayout()
        title = QLabel("ПАПКИ ДЛЯ ПОИСКА")
        title.setObjectName("SectionTitle")
        self.folder_count_label = QLabel("0")
        self.folder_count_label.setObjectName("Muted")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.folder_count_label)
        layout.addLayout(header)

        self.folders_list = QListWidget()
        self.folders_list.setObjectName("Folders")
        self.folders_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.folders_list.setTextElideMode(Qt.ElideMiddle)
        self.folders_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.folders_list.setWordWrap(False)
        self.folders_list.setMinimumHeight(130)
        self.folders_list.setMaximumHeight(230)
        self.folders_list.setToolTip(
            "Перетащите папки в окно программы или нажмите «+ Добавить»"
        )
        self.folders_list.itemDoubleClicked.connect(
            lambda item: self._reveal_path(str(item.data(Qt.UserRole)))
        )
        self.folders_list.itemSelectionChanged.connect(self._update_folder_buttons)
        layout.addWidget(self.folders_list)

        folder_buttons = QHBoxLayout()
        folder_buttons.setSpacing(6)
        self.folder_add_button = QPushButton("+  Добавить")
        self.folder_add_button.clicked.connect(self._choose_folder)
        self.folder_remove_button = QPushButton("−")
        self.folder_remove_button.setObjectName("IconButton")
        self.folder_remove_button.setFixedWidth(38)
        self.folder_remove_button.setToolTip("Удалить выбранные папки из списка")
        self.folder_remove_button.clicked.connect(self._remove_folders)
        folder_buttons.addWidget(self.folder_add_button)
        folder_buttons.addWidget(self.folder_remove_button)
        layout.addLayout(folder_buttons)

        divider = QFrame()
        divider.setObjectName("Divider")
        layout.addWidget(divider)

        params_title = QLabel("ПАРАМЕТРЫ ПОИСКА")
        params_title.setObjectName("SectionTitle")
        layout.addWidget(params_title)

        threshold_row = QHBoxLayout()
        threshold_caption = QLabel("Схожесть файлов")
        threshold_caption.setObjectName("Muted")
        self.threshold_value_label = QLabel("88 %")
        self.threshold_value_label.setObjectName("InfoValue")
        threshold_row.addWidget(threshold_caption)
        threshold_row.addStretch(1)
        threshold_row.addWidget(self.threshold_value_label)
        layout.addLayout(threshold_row)

        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(70, 99)
        self.threshold_slider.setToolTip(
            "Чем выше значение, тем строже поиск. 85–92 % — оптимально."
        )
        self.threshold_slider.valueChanged.connect(self._threshold_changed)
        layout.addWidget(self.threshold_slider)

        duration_row = QHBoxLayout()
        duration_caption = QLabel("Мин. длительность")
        duration_caption.setObjectName("Muted")
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 3600)
        self.duration_spin.setSuffix(" с")
        self.duration_spin.setFixedWidth(92)
        self.duration_spin.valueChanged.connect(self._duration_changed)
        duration_row.addWidget(duration_caption)
        duration_row.addStretch(1)
        duration_row.addWidget(self.duration_spin)
        layout.addLayout(duration_row)

        self.acoustic_check = QCheckBox("Сравнивать по звучанию")
        self.acoustic_check.setToolTip(
            "Находить одну песню в MP3, FLAC, WAV и других форматах. "
            "Если выключить — только точные копии файлов."
        )
        self.acoustic_check.toggled.connect(self._acoustic_changed)
        layout.addWidget(self.acoustic_check)

        hint = QLabel(
            "Поиск по звучанию использует отпечатки Chromaprint. "
            "Параметры применяются при следующем сканировании."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        return panel

    def _build_results_panel(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        card.setMinimumWidth(480)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 14, 16, 8)
        header_layout.setSpacing(10)
        title = QLabel("Результаты")
        title.setObjectName("TitleLabel")
        self.stats_label = QLabel("Результатов пока нет")
        self.stats_label.setObjectName("StatLabel")
        header_layout.addWidget(title)
        header_layout.addWidget(self.stats_label)
        header_layout.addStretch(1)
        self.mark_button = QPushButton("Отметить дубликаты")
        self.mark_button.setObjectName("Ghost")
        self.mark_button.setToolTip("Отметить все копии, кроме выбранных «оставить»")
        self.mark_button.clicked.connect(self._mark_duplicates)
        self.clear_marks_button = QPushButton("Снять отметки")
        self.clear_marks_button.setObjectName("Ghost")
        self.clear_marks_button.clicked.connect(self._clear_marks)
        header_layout.addWidget(self.mark_button)
        header_layout.addWidget(self.clear_marks_button)
        layout.addWidget(header)

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 0, 16, 10)
        toolbar_layout.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("Search")
        self.search_edit.setPlaceholderText("Поиск по названию, исполнителю или пути…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)
        self.format_combo = QComboBox()
        for key, label in FORMAT_FILTER_LABELS.items():
            self.format_combo.addItem(label, key)
        self.format_combo.setFixedWidth(146)
        self.format_combo.setToolTip("Показывать только выбранный формат")
        self.format_combo.currentIndexChanged.connect(self._apply_filter)
        toolbar_layout.addWidget(self.search_edit, 1)
        toolbar_layout.addWidget(self.format_combo)
        layout.addWidget(toolbar)

        self.results_stack = QStackedWidget()
        self.results_stack.addWidget(self._build_placeholder())
        self.tree = self._build_tree()
        self.results_stack.addWidget(self.tree)
        layout.addWidget(self.results_stack, 1)

        divider = QFrame()
        divider.setObjectName("Divider")
        layout.addWidget(divider)

        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(16, 10, 16, 13)
        footer_layout.setSpacing(10)
        self.summary_label = QLabel("Ничего не отмечено")
        self.summary_label.setObjectName("SummaryLabel")
        footer_layout.addWidget(self.summary_label)
        footer_layout.addStretch(1)
        self.export_button = QPushButton("Экспорт отчёта")
        self.export_button.setToolTip("Сохранить отчёт в CSV для Excel")
        self.export_button.clicked.connect(self._export_report)
        footer_layout.addWidget(self.export_button)
        self.delete_button = QPushButton("Удалить в корзину")
        self.delete_button.setObjectName("Danger")
        self.delete_button.setEnabled(False)
        self.delete_button.setToolTip("Отправить отмеченные файлы в корзину")
        self.delete_button.clicked.connect(self._delete_marked)
        footer_layout.addWidget(self.delete_button)
        layout.addWidget(footer)
        return card

    def _build_placeholder(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.addStretch(1)
        icon_row = QHBoxLayout()
        icon_row.addStretch(1)
        icon = QLabel("♪")
        icon.setObjectName("PlaceholderIcon")
        icon.setFixedSize(76, 76)
        icon.setAlignment(Qt.AlignCenter)
        icon_row.addWidget(icon)
        icon_row.addStretch(1)
        layout.addLayout(icon_row)
        layout.addSpacing(12)
        self.placeholder_title = QLabel("Начните с выбора папок")
        self.placeholder_title.setObjectName("PlaceholderTitle")
        self.placeholder_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.placeholder_title)
        self.placeholder_text = QLabel("")
        self.placeholder_text.setObjectName("PlaceholderText")
        self.placeholder_text.setAlignment(Qt.AlignCenter)
        self.placeholder_text.setWordWrap(True)
        self.placeholder_text.setMaximumWidth(460)
        text_row = QHBoxLayout()
        text_row.addStretch(1)
        text_row.addWidget(self.placeholder_text)
        text_row.addStretch(1)
        layout.addLayout(text_row)
        layout.addStretch(2)
        return page

    def _build_tree(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setObjectName("Results")
        tree.setColumnCount(7)
        tree.setHeaderLabels(
            ["Файл", "★", "Формат", "Битрейт", "Время", "Размер", "Совпадение"]
        )
        tree.setIndentation(16)
        tree.setRootIsDecorated(True)
        tree.setUniformRowHeights(True)
        tree.setAlternatingRowColors(True)
        tree.setSelectionMode(QAbstractItemView.SingleSelection)
        tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tree.setContextMenuPolicy(Qt.CustomContextMenu)
        tree.setSortingEnabled(False)
        tree.setAnimated(True)
        tree.setWordWrap(False)

        header = tree.header()
        header.setStretchLastSection(False)
        header.setHighlightSections(False)
        modes = [
            QHeaderView.Stretch,
            QHeaderView.Fixed,
            QHeaderView.Fixed,
            QHeaderView.Fixed,
            QHeaderView.Fixed,
            QHeaderView.Fixed,
            QHeaderView.Fixed,
        ]
        for column, mode in enumerate(modes):
            header.setSectionResizeMode(column, mode)
        widths = [300, 34, 66, 88, 70, 82, 128]
        for column, width in enumerate(widths):
            tree.setColumnWidth(column, width)

        tree.currentItemChanged.connect(self._current_item_changed)
        tree.itemChanged.connect(self._item_changed)
        tree.itemClicked.connect(self._item_clicked)
        tree.itemDoubleClicked.connect(self._item_double_clicked)
        tree.customContextMenuRequested.connect(self._show_context_menu)
        return tree

    def _build_statusbar(self) -> None:
        status = self.statusBar()
        status.setSizeGripEnabled(True)
        self.status_label = QLabel("Готово")
        self.status_label.setObjectName("Muted")
        status.addWidget(self.status_label, 1)
        self.messages_button = QPushButton("Сообщения")
        self.messages_button.setObjectName("Ghost")
        self.messages_button.setToolTip("Предупреждения и пропущенные файлы")
        self.messages_button.clicked.connect(self._show_messages)
        self.messages_button.hide()
        status.addPermanentWidget(self.messages_button)
        self.stage_label = QLabel("")
        self.stage_label.setObjectName("StageLabel")
        status.addPermanentWidget(self.stage_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(150)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        status.addPermanentWidget(self.progress_bar)

    def _install_shortcuts(self) -> None:
        add_shortcut = QShortcut(QKeySequence("Ctrl+O"), self)
        add_shortcut.activated.connect(self._choose_folder)
        scan_shortcut = QShortcut(QKeySequence("F5"), self)
        scan_shortcut.activated.connect(self._start_scan)
        cancel_shortcut = QShortcut(QKeySequence("Esc"), self)
        cancel_shortcut.activated.connect(self._cancel_scan)
        play_shortcut = QShortcut(QKeySequence(Qt.Key_Space), self.tree)
        play_shortcut.setContext(Qt.WidgetShortcut)
        play_shortcut.activated.connect(self.compare_panel.toggle_play)

    # -------------------------------------------------------------- settings
    def _get_float(self, key: str, default: float) -> float:
        try:
            return float(self.settings.value(key, default))
        except (TypeError, ValueError):
            return default

    def _get_int(self, key: str, default: int) -> int:
        try:
            return int(self.settings.value(key, default))
        except (TypeError, ValueError):
            return default

    def _get_bool(self, key: str, default: bool) -> bool:
        value = self.settings.value(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _restore_settings(self) -> None:
        stored = self.settings.value("folders", [])
        if isinstance(stored, str):
            stored = [stored] if stored else []
        for path in stored or []:
            if os.path.isdir(str(path)):
                self._add_folder_item(str(path), save=False)

        threshold_similarity = int(round((1.0 - self._threshold) * 100))
        self.threshold_slider.blockSignals(True)
        self.threshold_slider.setValue(max(70, min(99, threshold_similarity)))
        self.threshold_slider.blockSignals(False)
        self.threshold_value_label.setText(f"{self.threshold_slider.value()} %")

        self.duration_spin.blockSignals(True)
        self.duration_spin.setValue(self._get_int("min_duration", 10))
        self.duration_spin.blockSignals(False)

        self.acoustic_check.blockSignals(True)
        self.acoustic_check.setChecked(self._get_bool("use_acoustic", True))
        self.acoustic_check.blockSignals(False)

        format_key = str(self.settings.value("format_filter", "all") or "all")
        index = self.format_combo.findData(format_key)
        if index >= 0:
            self.format_combo.blockSignals(True)
            self.format_combo.setCurrentIndex(index)
            self.format_combo.blockSignals(False)

        geometry = self.settings.value("window/geometry")
        if geometry is not None:
            try:
                self.restoreGeometry(geometry)
            except Exception:
                pass

        self._update_folder_count()

    def _current_values(self) -> dict:
        return {
            "threshold": round(1.0 - self.threshold_slider.value() / 100.0, 4),
            "min_duration": self.duration_spin.value(),
            "fingerprint_length": self._get_int("fingerprint_length", 120),
            "workers": self._get_int(
                "workers", max(1, min(8, os.cpu_count() or 4))
            ),
            "theme": self._theme,
            "use_acoustic": self.acoustic_check.isChecked(),
        }

    def _current_options(self) -> ScanOptions:
        values = self._current_values()
        return ScanOptions(
            folders=self._folder_paths(),
            threshold=float(values["threshold"]),
            min_duration=float(values["min_duration"]),
            fingerprint_length=int(values["fingerprint_length"]),
            workers=max(1, int(values["workers"])),
            use_acoustic=bool(values["use_acoustic"]),
        )

    def _threshold_changed(self, value: int) -> None:
        self._threshold = round(1.0 - value / 100.0, 4)
        self.threshold_value_label.setText(f"{value} %")
        self.settings.setValue("threshold", self._threshold)

    def _duration_changed(self, value: int) -> None:
        self.settings.setValue("min_duration", value)

    def _acoustic_changed(self, checked: bool) -> None:
        self.settings.setValue("use_acoustic", checked)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._current_values(), default_cache_path(), self)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        for key, value in values.items():
            self.settings.setValue(key, value)
        old_theme = self._theme
        self._theme = str(values["theme"])
        if self._theme != old_theme:
            apply_theme(QApplication.instance(), self._theme)
            self._colors = theme_colors(self._theme)
            self._apply_tree_palette()
            self._apply_windows_titlebar()
            self._refresh_theme_colors()

        self.threshold_slider.blockSignals(True)
        self.threshold_slider.setValue(
            max(70, min(99, int(round((1.0 - values["threshold"]) * 100))))
        )
        self.threshold_slider.blockSignals(False)
        self.threshold_value_label.setText(f"{self.threshold_slider.value()} %")
        self._threshold = float(values["threshold"])

        self.duration_spin.blockSignals(True)
        self.duration_spin.setValue(int(values["min_duration"]))
        self.duration_spin.blockSignals(False)

        self.acoustic_check.blockSignals(True)
        self.acoustic_check.setChecked(bool(values["use_acoustic"]))
        self.acoustic_check.blockSignals(False)

        self.status_label.setText("Настройки сохранены")

    # --------------------------------------------------------------- folders
    def _folder_paths(self) -> list[str]:
        paths = []
        for row in range(self.folders_list.count()):
            item = self.folders_list.item(row)
            paths.append(str(item.data(Qt.UserRole)))
        return paths

    def _choose_folder(self) -> None:
        if self._scanning:
            return
        start_dir = str(
            self.settings.value("last_folder", "")
            or QStandardPaths.writableLocation(QStandardPaths.MusicLocation)
            or str(Path.home())
        )
        folder = QFileDialog.getExistingDirectory(
            self, "Добавить папку с музыкой", start_dir
        )
        if folder:
            self.settings.setValue("last_folder", folder)
            self._add_folder_item(folder)

    def _add_folder_item(self, path: str, save: bool = True) -> None:
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isdir(path):
            return
        existing = {value.lower() for value in self._folder_paths()}
        if path.lower() in existing:
            return
        item = QListWidgetItem(path)
        item.setData(Qt.UserRole, path)
        item.setToolTip(path)
        self.folders_list.addItem(item)
        if save:
            self._save_folders()
        self._update_folder_count()

    def _remove_folders(self) -> None:
        if self._scanning:
            return
        selected = self.folders_list.selectedItems()
        if not selected:
            return
        for item in selected:
            row = self.folders_list.row(item)
            self.folders_list.takeItem(row)
        self._save_folders()
        self._update_folder_count()

    def _save_folders(self) -> None:
        self.settings.setValue("folders", self._folder_paths())

    def _update_folders_state(self) -> None:
        has_folders = bool(self._folder_paths())
        self.scan_button.setEnabled(has_folders and not self._scanning)
        self._update_folder_buttons()
        self._update_folder_count()

    def _update_folder_buttons(self) -> None:
        has_selection = bool(self.folders_list.selectedItems())
        self.folder_remove_button.setEnabled(has_selection and not self._scanning)

    def _update_folder_count(self) -> None:
        count = self.folders_list.count()
        text = f"{count} {plural_ru(count, 'папка', 'папки', 'папок')}"
        self.folder_count_label.setText(text)
        self._update_folders_state_safe()

    def _update_folders_state_safe(self) -> None:
        if self._scanning:
            return
        self.scan_button.setEnabled(self.folders_list.count() > 0)

    # ------------------------------------------------------------------ scan
    def _start_scan(self) -> None:
        if self._scanning or (self._thread is not None and self._thread.isRunning()):
            return
        if not self._folder_paths():
            QMessageBox.information(
                self,
                "Нет папок",
                "Сначала добавьте хотя бы одну папку с музыкой.",
            )
            return

        options = self._current_options()
        self._groups = []
        self._last_result = None
        self._warnings = []
        self._errors = []
        self._group_items.clear()
        self._child_items.clear()
        self._group_by_path.clear()
        self.tree.clear()
        self.compare_panel.clear()
        self._update_summary()
        self.stats_label.setText("Идёт сканирование…")
        self.messages_button.hide()
        self._show_placeholder(
            "Сканирование…",
            "Программа анализирует файлы и сравнивает их отпечатки. "
            "Прогресс отображается в строке состояния.",
        )
        self._set_scanning(True)
        self._scan_started = time.monotonic()
        self.status_label.setText("Подготовка к сканированию…")
        self.stage_label.setText("")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.show()

        self._thread = QThread(self)
        self._worker = ScanWorker(options, default_cache_path())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.failed.connect(self._on_scan_failed)
        self._worker.cancelled.connect(self._on_scan_cancelled)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.cancelled.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._thread_done)
        self._thread.start()

    def _set_scanning(self, scanning: bool) -> None:
        self._scanning = scanning
        self.scan_button.setEnabled(not scanning and bool(self._folder_paths()))
        self.scan_button.setText("Сканирование…" if scanning else "Сканировать")
        self.cancel_button.setVisible(scanning)
        self.cancel_button.setEnabled(scanning)
        self.add_folder_button.setEnabled(not scanning)
        self.settings_button.setEnabled(not scanning)
        self.folder_add_button.setEnabled(not scanning)
        self.folder_remove_button.setEnabled(
            not scanning and bool(self.folders_list.selectedItems())
        )
        self.folders_list.setEnabled(not scanning)
        self.threshold_slider.setEnabled(not scanning)
        self.duration_spin.setEnabled(not scanning)
        self.acoustic_check.setEnabled(not scanning)
        self.mark_button.setEnabled(not scanning)
        self.clear_marks_button.setEnabled(not scanning)
        if scanning:
            self.delete_button.setEnabled(False)
        else:
            self._update_summary()

    def _cancel_scan(self) -> None:
        if not self._scanning or self._worker is None:
            return
        self._worker.cancel()
        self.cancel_button.setEnabled(False)
        self.status_label.setText("Останавливаем сканирование…")

    def _on_progress(self, stage: str, done: int, total: int, current: str) -> None:
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(min(done, total))
            self.stage_label.setText(f"{stage} · {done}/{total}")
        else:
            self.progress_bar.setRange(0, 0)
            self.stage_label.setText(stage)
        if current:
            elided = self.status_label.fontMetrics().elidedText(
                current, Qt.ElideMiddle, 420
            )
            self.status_label.setText(elided)

    def _on_scan_finished(self, result: ScanResult) -> None:
        self._finish_scan_ui()
        self._last_result = result
        self._groups = result.groups
        self._warnings = list(result.stats.warnings)
        self._errors = list(result.stats.errors)
        elapsed = result.stats.elapsed

        if result.stats.scanned == 0:
            self._show_placeholder(
                "Аудиофайлы не найдены",
                "В выбранных папках нет файлов поддерживаемых форматов. "
                "Поддерживаются MP3, FLAC, WAV, M4A, AAC, OGG, OPUS, WMA, AIFF, APE.",
            )
            self.stats_label.setText("Файлы не найдены")
            self.status_label.setText("Сканирование завершено: аудиофайлы не найдены")
        elif not result.groups:
            self.stats_label.setText("Дубликаты не найдены")
            self._show_placeholder(
                "Дубликаты не найдены",
                f"Проверено файлов: {result.stats.analyzed}. "
                "Попробуйте понизить минимальную схожесть в настройках.",
            )
            self.status_label.setText(
                f"Готово за {elapsed:.1f} с · проверено {result.stats.analyzed} "
                f"{plural_ru(result.stats.analyzed, 'файл', 'файла', 'файлов')}"
            )
        else:
            self._render_groups()
            self._update_stats_label()
            self.status_label.setText(
                f"Готово за {elapsed:.1f} с · проверено {result.stats.analyzed} "
                f"{plural_ru(result.stats.analyzed, 'файл', 'файла', 'файлов')} · "
                f"найдено групп: {len(result.groups)}"
            )

        self._update_messages_button()
        if result.stats.warnings and not self._warned_no_fpcalc:
            if any("fpcalc" in warning for warning in result.stats.warnings):
                self._warned_no_fpcalc = True
                QMessageBox.information(
                    self,
                    "Поиск по звучанию недоступен",
                    "Не найден fpcalc — компонент Chromaprint для сравнения "
                    "аудиоотпечатков.\n\n"
                    "Будут найдены только точные копии файлов. "
                    "Положите fpcalc.exe в папку программы и запустите "
                    "сканирование снова.",
                )

    def _on_scan_failed(self, traceback_text: str) -> None:
        self._finish_scan_ui()
        self._show_placeholder(
            "Не удалось завершить сканирование",
            "Подробности ошибки — в диалоговом окне. "
            "Попробуйте повторить сканирование.",
        )
        self.stats_label.setText("Ошибка сканирования")
        self.status_label.setText("Ошибка сканирования")
        short = traceback_text.strip().splitlines()[-1] if traceback_text.strip() else ""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("Ошибка сканирования")
        box.setText("Во время сканирования произошла ошибка.")
        box.setInformativeText(short)
        box.setDetailedText(traceback_text)
        box.exec()

    def _on_scan_cancelled(self) -> None:
        self._finish_scan_ui()
        self._show_placeholder(
            "Сканирование отменено",
            "Результаты предыдущего поиска не сохранялись. "
            "Запустите сканирование снова, когда будете готовы.",
        )
        self.stats_label.setText("Сканирование отменено")
        self.status_label.setText("Сканирование отменено")

    def _finish_scan_ui(self) -> None:
        self._set_scanning(False)
        self.progress_bar.hide()
        self.stage_label.clear()
        self._update_folder_buttons()

    def _thread_done(self) -> None:
        self._thread = None
        self._worker = None
        if self._close_when_done:
            self.close()

    # ------------------------------------------------------------- rendering
    def _render_groups(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        self._group_items.clear()
        self._child_items.clear()
        self._group_by_path.clear()

        expand_all = len(self._groups) <= 20
        for order, group in enumerate(self._groups):
            group_item = QTreeWidgetItem(self.tree)
            group_item.setFirstColumnSpanned(True)
            group_item.setFlags(Qt.ItemIsEnabled)
            group_item.setData(0, Qt.UserRole, group)
            group_item.setText(0, self._group_text(group))
            font = group_item.font(0)
            font.setBold(True)
            group_item.setFont(0, font)
            group_item.setBackground(0, QBrush(QColor(self._colors["group"])))
            group_item.setForeground(0, QBrush(QColor(self._colors["text"])))
            group_item.setToolTip(
                0,
                f"{len(group.files)} "
                f"{plural_ru(len(group.files), 'файл', 'файла', 'файлов')} · "
                f"можно освободить {human_size(group.reclaimable)}",
            )
            self._group_items[id(group)] = group_item

            for audio in group.sorted_files():
                child = QTreeWidgetItem(group_item)
                child.setData(0, Qt.UserRole, audio)
                child.setData(0, Qt.UserRole + 1, group)
                child.setFlags(
                    Qt.ItemIsEnabled
                    | Qt.ItemIsSelectable
                    | Qt.ItemIsUserCheckable
                )
                child.setCheckState(0, Qt.Unchecked)
                child.setText(0, audio.filename)
                child.setToolTip(0, audio.path)
                child.setText(1, "★" if audio.is_keeper else "☆")
                child.setToolTip(
                    1,
                    "Файл будет оставлен" if audio.is_keeper else "Оставить этот файл",
                )
                child.setText(2, audio.format_label)
                child.setText(3, audio.bitrate_text)
                child.setText(4, audio.duration_text)
                child.setText(5, audio.size_text)
                child.setText(6, audio.similarity_text)
                child.setToolTip(6, audio.path)
                for column in (1, 3, 4, 5, 6):
                    child.setTextAlignment(
                        column, int(Qt.AlignHCenter | Qt.AlignVCenter)
                    )
                self._apply_row_style(child)
                self._child_items[audio.path] = child
                self._group_by_path[audio.path] = group

            group_item.setExpanded(expand_all or order < 4)

        self.tree.blockSignals(False)
        self.results_stack.setCurrentIndex(1)
        self._apply_filter()
        self._update_summary()

        first_group = self.tree.topLevelItem(0)
        if first_group is not None and first_group.childCount() > 0:
            self.tree.setCurrentItem(first_group.child(0))
        else:
            self.compare_panel.clear()

    def _group_text(self, group: DuplicateGroup) -> str:
        count = len(group.files)
        return (
            f"{group.title}    ·    {count} "
            f"{plural_ru(count, 'файл', 'файла', 'файлов')}    ·    "
            f"{KIND_LABELS.get(group.kind, group.kind)}    ·    "
            f"можно освободить {human_size(group.reclaimable)}"
        )

    def _apply_row_style(self, item: QTreeWidgetItem) -> None:
        audio = item.data(0, Qt.UserRole)
        if not isinstance(audio, AudioFile):
            return
        checked = item.checkState(0) == Qt.Checked
        if checked:
            item.setBackground(0, QBrush(QColor(self._colors["danger_soft"])))
        else:
            item.setBackground(0, QBrush(QColor(0, 0, 0, 0)))
        star = item.font(1)
        star.setBold(audio.is_keeper)
        item.setFont(1, star)
        item.setForeground(
            1,
            QBrush(
                QColor(
                    self._colors["success"]
                    if audio.is_keeper
                    else self._colors["muted"]
                )
            ),
        )
        item.setForeground(
            6,
            QBrush(
                QColor(
                    self._colors["accent"]
                    if audio.match_type == "exact"
                    else self._colors["text"]
                )
            ),
        )

    def _refresh_group(self, group: DuplicateGroup) -> None:
        group_item = self._group_items.get(id(group))
        if group_item is None:
            return
        group_item.setText(0, self._group_text(group))
        group_item.setToolTip(
            0,
            f"{len(group.files)} "
            f"{plural_ru(len(group.files), 'файл', 'файла', 'файлов')} · "
            f"можно освободить {human_size(group.reclaimable)}",
        )
        for audio in group.files:
            child = self._child_items.get(audio.path)
            if child is None:
                continue
            child.setText(1, "★" if audio.is_keeper else "☆")
            child.setToolTip(
                1,
                "Файл будет оставлен" if audio.is_keeper else "Оставить этот файл",
            )
            self._apply_row_style(child)

    def _refresh_theme_colors(self) -> None:
        for group in self._groups:
            group_item = self._group_items.get(id(group))
            if group_item is not None:
                group_item.setBackground(0, QBrush(QColor(self._colors["group"])))
                group_item.setForeground(0, QBrush(QColor(self._colors["text"])))
            for audio in group.files:
                child = self._child_items.get(audio.path)
                if child is not None:
                    self._apply_row_style(child)

    def _apply_windows_titlebar(self) -> None:
        """Тёмный заголовок окна Windows в тёмной теме."""
        if os.name != "nt":
            return
        try:
            import ctypes

            value = ctypes.c_int(1 if self._theme == "dark" else 0)
            handle = int(self.winId())
            for attribute in (20, 19):
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    handle,
                    attribute,
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )
                if result == 0:
                    break
        except Exception:
            pass

    def _apply_tree_palette(self) -> None:
        """QSS не всегда красит viewport дерева — задаём фон явно."""
        palette = self.tree.viewport().palette()
        palette.setColor(QPalette.Base, QColor(self._colors["panel"]))
        palette.setColor(QPalette.AlternateBase, QColor(self._colors["panel_alt"]))
        palette.setColor(QPalette.Text, QColor(self._colors["text"]))
        palette.setColor(QPalette.Highlight, QColor(self._colors["selection"]))
        palette.setColor(QPalette.HighlightedText, QColor(self._colors["text"]))
        self.tree.viewport().setPalette(palette)
        self.tree.viewport().setAutoFillBackground(True)
        self.tree.viewport().setStyleSheet(
            f"background-color: {self._colors['panel']};"
        )
        # Запасной вариант: если viewport окажется прозрачным, под ним
        # должен быть фон панели, а не белый фон страницы.
        stack_palette = self.results_stack.palette()
        stack_palette.setColor(QPalette.Window, QColor(self._colors["panel"]))
        self.results_stack.setPalette(stack_palette)
        self.results_stack.setAutoFillBackground(True)
        self.tree.setStyleSheet(
            f"QTreeWidget {{ background: {self._colors['panel']}; "
            f"alternate-background-color: {self._colors['panel_alt']}; }}"
        )

    def _update_stats_label(self) -> None:
        if not self._groups:
            self.stats_label.setText("Дубликаты не найдены")
            return
        duplicate_files = sum(len(group.files) for group in self._groups)
        reclaimable = sum(group.reclaimable for group in self._groups)
        self.stats_label.setText(
            f"{len(self._groups)} "
            f"{plural_ru(len(self._groups), 'группа', 'группы', 'групп')} · "
            f"{duplicate_files} "
            f"{plural_ru(duplicate_files, 'файл', 'файла', 'файлов')} · "
            f"можно освободить {human_size(reclaimable)}"
        )

    def _apply_filter(self) -> None:
        if not hasattr(self, "tree"):
            return
        query = self.search_edit.text().strip().lower()
        filter_key = self.format_combo.currentData() or "all"
        allowed = FORMAT_FILTERS.get(str(filter_key))
        for row in range(self.tree.topLevelItemCount()):
            group_item = self.tree.topLevelItem(row)
            group = group_item.data(0, Qt.UserRole)
            title_match = bool(
                query and isinstance(group, DuplicateGroup) and query in group.title.lower()
            )
            any_visible = False
            for index in range(group_item.childCount()):
                child = group_item.child(index)
                audio = child.data(0, Qt.UserRole)
                if not isinstance(audio, AudioFile):
                    continue
                format_ok = allowed is None or audio.suffix in allowed
                text_ok = (
                    not query
                    or title_match
                    or query
                    in (audio.filename + " " + audio.display_title + " " + audio.path).lower()
                )
                visible = format_ok and text_ok
                child.setHidden(not visible)
                any_visible = any_visible or visible
            group_item.setHidden(not any_visible)
            if query and any_visible:
                group_item.setExpanded(True)

    def _show_placeholder(self, title: str, text: str) -> None:
        self.placeholder_title.setText(title)
        self.placeholder_text.setText(text)
        self.results_stack.setCurrentIndex(0)

    # -------------------------------------------------------------- selection
    def _current_item_changed(
        self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None
    ) -> None:
        if current is None:
            self.compare_panel.clear()
            return
        audio = current.data(0, Qt.UserRole)
        group = current.data(0, Qt.UserRole + 1)
        if isinstance(audio, AudioFile) and isinstance(group, DuplicateGroup):
            current.parent().setExpanded(True)
            self.compare_panel.set_group(group, audio)

    def _item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        audio = item.data(0, Qt.UserRole)
        if not isinstance(audio, AudioFile):
            return
        self._apply_row_style(item)
        self._update_summary()

    def _item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 1:
            return
        audio = item.data(0, Qt.UserRole)
        group = item.data(0, Qt.UserRole + 1)
        if isinstance(audio, AudioFile) and isinstance(group, DuplicateGroup):
            self._set_keeper(group, audio)

    def _item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        audio = item.data(0, Qt.UserRole)
        if isinstance(audio, AudioFile):
            self.tree.setCurrentItem(item)
            self.compare_panel.toggle_play()

    def _keeper_requested(self, path: str) -> None:
        group = self._group_by_path.get(path)
        audio = next((f for f in group.files if f.path == path), None) if group else None
        if group is not None and audio is not None:
            self._set_keeper(group, audio)

    def _set_keeper(self, group: DuplicateGroup, audio: AudioFile) -> None:
        if group.keeper is audio:
            return
        group.keeper = audio
        for member in group.files:
            member.is_keeper = member is audio
        keeper_item = self._child_items.get(audio.path)
        if keeper_item is not None and keeper_item.checkState(0) == Qt.Checked:
            # Файл, который решили оставить, не должен остаться отмеченным.
            self.tree.blockSignals(True)
            keeper_item.setCheckState(0, Qt.Unchecked)
            self.tree.blockSignals(False)
        self._refresh_group(group)
        self._update_summary()
        self._update_stats_label()
        current = self.tree.currentItem()
        if current is not None:
            current_audio = current.data(0, Qt.UserRole)
            current_group = current.data(0, Qt.UserRole + 1)
            if isinstance(current_audio, AudioFile) and current_group is group:
                self.compare_panel.set_group(group, current_audio)

    # ------------------------------------------------------------- selection
    def _checked_paths(self) -> set[str]:
        checked: set[str] = set()
        for path, item in self._child_items.items():
            if item.checkState(0) == Qt.Checked:
                checked.add(path)
        return checked

    def _size_for_paths(self, paths: set[str]) -> int:
        total = 0
        for path in paths:
            group = self._group_by_path.get(path)
            if group:
                audio = next((f for f in group.files if f.path == path), None)
                if audio:
                    total += audio.size
        return total

    def _checked_size(self) -> int:
        return self._size_for_paths(self._checked_paths())

    def _update_summary(self) -> None:
        if not hasattr(self, "summary_label"):
            return
        checked = self._checked_paths()
        count = len(checked)
        if count == 0:
            self.summary_label.setText("Ничего не отмечено")
            self.delete_button.setEnabled(False)
        else:
            self.summary_label.setText(
                f"Отмечено: {count} {plural_ru(count, 'файл', 'файла', 'файлов')} · "
                f"{human_size(self._checked_size())}"
            )
            self.delete_button.setEnabled(not self._scanning)

    def _mark_duplicates(self) -> None:
        if not self._groups:
            return
        self.tree.blockSignals(True)
        for group in self._groups:
            for audio in group.files:
                if group.keeper is not None and audio.path == group.keeper.path:
                    continue
                item = self._child_items.get(audio.path)
                if item is not None:
                    item.setCheckState(0, Qt.Checked)
                    self._apply_row_style(item)
        self.tree.blockSignals(False)
        self._update_summary()

    def _clear_marks(self) -> None:
        self.tree.blockSignals(True)
        for item in self._child_items.values():
            item.setCheckState(0, Qt.Unchecked)
            self._apply_row_style(item)
        self.tree.blockSignals(False)
        self._update_summary()

    # --------------------------------------------------------------- actions
    def _show_context_menu(self, position) -> None:
        item = self.tree.itemAt(position)
        if item is None:
            return
        menu = QMenu(self)
        audio = item.data(0, Qt.UserRole)
        group = item.data(0, Qt.UserRole + 1)
        if isinstance(audio, AudioFile) and isinstance(group, DuplicateGroup):
            play_action = QAction("Воспроизвести / пауза", self)
            play_action.triggered.connect(
                lambda: (self.tree.setCurrentItem(item), self.compare_panel.toggle_play())
            )
            menu.addAction(play_action)
            keeper_action = QAction("Оставить этот файл", self)
            keeper_action.setEnabled(group.keeper is not audio)
            keeper_action.triggered.connect(lambda: self._set_keeper(group, audio))
            menu.addAction(keeper_action)
            checked = item.checkState(0) == Qt.Checked
            mark_action = QAction(
                "Снять отметку" if checked else "Отметить к удалению", self
            )
            mark_action.triggered.connect(
                lambda: item.setCheckState(
                    0, Qt.Unchecked if checked else Qt.Checked
                )
            )
            menu.addAction(mark_action)
            menu.addSeparator()
            folder_action = QAction("Открыть папку с файлом", self)
            folder_action.triggered.connect(lambda: self._reveal_path(audio.path))
            menu.addAction(folder_action)
            open_action = QAction("Открыть в системном плеере", self)
            open_action.triggered.connect(
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(audio.path))
            )
            menu.addAction(open_action)
            copy_action = QAction("Скопировать путь", self)
            copy_action.triggered.connect(
                lambda: QApplication.clipboard().setText(audio.path)
            )
            menu.addAction(copy_action)
        elif isinstance(group, DuplicateGroup):
            toggle_action = QAction(
                "Свернуть" if item.isExpanded() else "Развернуть", self
            )
            toggle_action.triggered.connect(
                lambda: item.setExpanded(not item.isExpanded())
            )
            menu.addAction(toggle_action)
            mark_group = QAction("Отметить дубликаты в группе", self)
            mark_group.triggered.connect(lambda: self._mark_group(group))
            menu.addAction(mark_group)
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _mark_group(self, group: DuplicateGroup) -> None:
        self.tree.blockSignals(True)
        for audio in group.files:
            if group.keeper is not None and audio.path == group.keeper.path:
                continue
            item = self._child_items.get(audio.path)
            if item is not None:
                item.setCheckState(0, Qt.Checked)
                self._apply_row_style(item)
        self.tree.blockSignals(False)
        self._update_summary()

    def _delete_marked(self) -> None:
        checked = self._checked_paths()
        if not checked:
            return
        by_group: dict[int, list[str]] = {}
        for path in checked:
            group = self._group_by_path.get(path)
            if group is not None:
                by_group.setdefault(id(group), []).append(path)
        for group in self._groups:
            paths = by_group.get(id(group), [])
            if paths and len(paths) == len(group.files):
                QMessageBox.warning(
                    self,
                    "Нельзя удалить все файлы группы",
                    f"В группе «{group.title}» отмечены все файлы. "
                    "Оставьте хотя бы один файл, иначе песня пропадёт из коллекции.",
                )
                return

        size = self._checked_size()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Удалить в корзину?")
        box.setText(
            f"Отправить {len(checked)} "
            f"{plural_ru(len(checked), 'файл', 'файла', 'файлов')} "
            f"({human_size(size)}) в корзину?"
        )
        box.setInformativeText(
            "Файлы можно будет восстановить из корзины. "
            "Кэш анализа обновится при следующем сканировании."
        )
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        box.button(QMessageBox.Yes).setText("В корзину")
        box.button(QMessageBox.No).setText("Отмена")
        if box.exec() != QMessageBox.Yes:
            return

        try:
            from send2trash import send2trash
        except ImportError:
            QMessageBox.critical(
                self,
                "Не установлен send2trash",
                "Установите пакет send2trash: pip install send2trash",
            )
            return

        deleted: set[str] = set()
        failed: list[str] = []
        for path in sorted(checked):
            try:
                send2trash(path)
                deleted.add(path)
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{path}: {exc}")

        deleted_size = 0
        if deleted:
            # Размер нужно посчитать до удаления записей из групп.
            deleted_size = self._size_for_paths(deleted)
            self._remove_deleted(deleted)
            try:
                from ..core.cache import Cache

                with Cache(default_cache_path()) as cache:
                    cache.delete(sorted(deleted))
            except Exception:
                pass

        if failed:
            QMessageBox.warning(
                self,
                "Часть файлов не удалена",
                f"Не удалось отправить в корзину: {len(failed)}.\n\n"
                + "\n".join(failed[:10]),
            )

        if deleted:
            self.status_label.setText(
                f"В корзину отправлено: {len(deleted)} "
                f"{plural_ru(len(deleted), 'файл', 'файла', 'файлов')} · "
                f"{human_size(deleted_size)}"
            )
        else:
            self.status_label.setText("Файлы не были удалены")
        self._render_after_change()

    def _remove_deleted(self, deleted: set[str]) -> None:
        from ..core.quality import rank_group

        remaining_groups: list[DuplicateGroup] = []
        for group in self._groups:
            group.files = [f for f in group.files if f.path not in deleted]
            if len(group.files) < 2:
                continue
            if group.keeper is None or group.keeper.path in deleted:
                group.keeper = rank_group(group.files)
            else:
                rank_group(group.files)
                for audio in group.files:
                    audio.is_keeper = audio is group.keeper
            remaining_groups.append(group)
        self._groups = remaining_groups
        for index, group in enumerate(self._groups, start=1):
            group.index = index

        if self._last_result is not None:
            self._last_result.groups = self._groups
            stats = self._last_result.stats
            stats.groups = len(self._groups)
            stats.duplicate_files = sum(len(g.files) for g in self._groups)
            stats.exact_groups = sum(1 for g in self._groups if g.kind == "exact")
            stats.acoustic_groups = sum(1 for g in self._groups if g.kind != "exact")
            stats.reclaimable = sum(g.reclaimable for g in self._groups)

    def _render_after_change(self) -> None:
        self.compare_panel.clear()
        if self._groups:
            self._render_groups()
            self._update_stats_label()
        else:
            self.tree.clear()
            self._child_items.clear()
            self._group_items.clear()
            self._group_by_path.clear()
            self.stats_label.setText("Дубликаты не найдены")
            self._show_placeholder(
                "Дубликаты больше не найдены",
                "Все лишние копии удалены. Можно выбрать другие папки "
                "или изменить параметры поиска.",
            )
            self._update_summary()

    def _export_report(self) -> None:
        if not self._groups:
            QMessageBox.information(
                self,
                "Нечего экспортировать",
                "Сначала найдите дубликаты.",
            )
            return
        documents = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        default_path = os.path.join(documents or str(Path.home()), default_report_name())
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Сохранить отчёт",
            default_path,
            "CSV (*.csv)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            write_report(path, self._groups, self._checked_paths())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить отчёт: {exc}")
            return
        self.status_label.setText(f"Отчёт сохранён: {path}")
        QMessageBox.information(
            self,
            "Отчёт сохранён",
            f"Файл отчёта:\n{path}\n\nЕго можно открыть в Excel.",
        )

    def _reveal_path(self, path: str) -> None:
        if not path:
            return
        path = os.path.abspath(path)
        try:
            if os.name == "nt":
                if os.path.isfile(path):
                    subprocess.Popen(
                        ["explorer", f"/select,{os.path.normpath(path)}"],
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                else:
                    os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                if os.path.isfile(path):
                    subprocess.Popen(["open", "-R", path])
                else:
                    subprocess.Popen(["open", path])
            else:
                target = path if os.path.isdir(path) else os.path.dirname(path)
                QDesktopServices.openUrl(QUrl.fromLocalFile(target))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть папку: {exc}")

    def _update_messages_button(self) -> None:
        total = len(self._warnings) + len(self._errors)
        if total:
            self.messages_button.setText(
                f"Сообщения · {total}"
            )
            self.messages_button.show()
        else:
            self.messages_button.hide()

    def _show_messages(self) -> None:
        if not (self._warnings or self._errors):
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning if self._errors else QMessageBox.Information)
        box.setWindowTitle("Сообщения сканирования")
        box.setText(
            f"Предупреждений: {len(self._warnings)} · "
            f"Ошибок: {len(self._errors)}"
        )
        details = []
        if self._warnings:
            details.append("Предупреждения:\n" + "\n".join(self._warnings))
        if self._errors:
            details.append("Пропущенные файлы:\n" + "\n".join(self._errors))
        box.setDetailedText("\n\n".join(details))
        box.exec()

    # ------------------------------------------------------------------ drag
    def dragEnterEvent(self, event) -> None:
        if self._scanning:
            return
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and os.path.isdir(url.toLocalFile()):
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event) -> None:
        if self._scanning:
            return
        added = False
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            if os.path.isdir(path):
                self._add_folder_item(path)
                added = True
        if added:
            event.acceptProposedAction()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_windows_titlebar()

    # ----------------------------------------------------------------- close
    def closeEvent(self, event) -> None:
        thread_running = self._thread is not None and self._thread.isRunning()
        if self._scanning or thread_running:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle("Идёт сканирование")
            box.setText("Сканирование ещё не завершено. Выйти?")
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            box.setDefaultButton(QMessageBox.No)
            if box.exec() != QMessageBox.Yes:
                event.ignore()
                return
            self._close_when_done = True
            if self._scanning:
                self._cancel_scan()
            event.ignore()
            return

        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("format_filter", self.format_combo.currentData())
        self.settings.setValue("folders", self._folder_paths())
        self.settings.setValue("theme", self._theme)
        self.compare_panel.stop()
        super().closeEvent(event)
