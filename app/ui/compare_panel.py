"""Панель сравнения: обложка, параметры и A/B-прослушивание."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..core.models import AudioFile, DuplicateGroup
from ..core.quality import quality_badge
from ..core.scanner import extract_cover


def _rounded_pixmap(source: QPixmap, size: int, radius: int = 12) -> QPixmap:
    scaled = source.scaled(
        size,
        size,
        Qt.KeepAspectRatioByExpanding,
        Qt.SmoothTransformation,
    )
    if scaled.width() > size or scaled.height() > size:
        x = max(0, (scaled.width() - size) // 2)
        y = max(0, (scaled.height() - size) // 2)
        scaled = scaled.copy(x, y, size, size)
    result = QPixmap(size, size)
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, scaled)
    painter.end()
    return result


class ComparePanel(QFrame):
    COVER_SIZE = 260

    keeper_requested = Signal(str)
    open_folder_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ComparePanel")
        self.setMinimumWidth(300)
        self.setMaximumWidth(460)

        self._group: DuplicateGroup | None = None
        self._file: AudioFile | None = None
        self._covers: dict[str, QPixmap | None] = {}
        self._active_slot = "A"
        self._pending_position = 0
        self._pending_play = False
        self._slider_dragging = False
        self._loading = False

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._audio.setVolume(0.85)
        self._player.setAudioOutput(self._audio)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.playbackStateChanged.connect(self._on_playback_state)
        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)
        self._player.errorOccurred.connect(self._on_error)

        self._build_ui()
        self.clear()

    # ------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setAutoFillBackground(False)

        content = QWidget()
        content.setObjectName("CompareContent")
        scroll.setWidget(content)
        outer.addWidget(scroll)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("Сравнение")
        title.setObjectName("TitleLabel")
        header.addWidget(title)
        header.addStretch(1)
        self.group_label = QLabel("")
        self.group_label.setObjectName("Muted")
        header.addWidget(self.group_label)
        layout.addLayout(header)

        self.cover = QLabel("♪")
        self.cover.setObjectName("Cover")
        self.cover.setFixedSize(self.COVER_SIZE, self.COVER_SIZE)
        self.cover.setAlignment(Qt.AlignCenter)
        cover_wrap = QHBoxLayout()
        cover_wrap.addStretch(1)
        cover_wrap.addWidget(self.cover)
        cover_wrap.addStretch(1)
        layout.addLayout(cover_wrap)

        self.title_label = QLabel("Файл не выбран")
        self.title_label.setObjectName("TitleLabel")
        self.title_label.setWordWrap(True)
        self.title_label.setMaximumHeight(48)
        layout.addWidget(self.title_label)

        self.artist_label = QLabel("Выберите файл в списке слева")
        self.artist_label.setObjectName("ArtistLabel")
        self.artist_label.setWordWrap(True)
        layout.addWidget(self.artist_label)

        self.match_label = QLabel("")
        self.match_label.setObjectName("MatchBadge")
        self.match_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        match_row = QHBoxLayout()
        match_row.addWidget(self.match_label)
        match_row.addStretch(1)
        layout.addLayout(match_row)

        info = QGridLayout()
        info.setHorizontalSpacing(12)
        info.setVerticalSpacing(4)
        self._info_values: dict[str, QLabel] = {}
        rows = [
            ("format", "Формат"),
            ("duration", "Длительность"),
            ("size", "Размер"),
            ("path", "Путь"),
        ]
        for row, (key, caption) in enumerate(rows):
            key_label = QLabel(caption)
            key_label.setObjectName("InfoKey")
            value_label = QLabel("—")
            value_label.setObjectName("InfoValue")
            value_label.setWordWrap(True)
            if key == "path":
                value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                value_label.setMaximumHeight(44)
            self._info_values[key] = value_label
            info.addWidget(key_label, row, 0, Qt.AlignTop)
            info.addWidget(value_label, row, 1)
        info.setColumnStretch(1, 1)
        layout.addLayout(info)

        divider = QFrame()
        divider.setObjectName("Divider")
        layout.addWidget(divider)

        ab_caption = QLabel("A/B ПРОСЛУШИВАНИЕ")
        ab_caption.setObjectName("SectionTitle")
        layout.addWidget(ab_caption)

        self.a_combo = QComboBox()
        self.b_combo = QComboBox()
        for combo in (self.a_combo, self.b_combo):
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            combo.setMinimumContentsLength(14)
        self.a_combo.activated.connect(lambda _index: self._combo_changed("A"))
        self.b_combo.activated.connect(lambda _index: self._combo_changed("B"))

        layout.addLayout(self._slot_row("A", self.a_combo))
        layout.addLayout(self._slot_row("B", self.b_combo))

        ab_buttons = QHBoxLayout()
        ab_buttons.setSpacing(6)
        self.play_a = QPushButton("▶  Слушать A")
        self.play_b = QPushButton("▶  Слушать B")
        self.stop_button = QPushButton("■  Стоп")
        self.stop_button.setObjectName("Ghost")
        for button in (self.play_a, self.play_b):
            button.setObjectName("Small")
            button.setToolTip("Переключение A ↔ B сохраняет позицию воспроизведения")
        self.play_a.clicked.connect(lambda: self._play_slot("A"))
        self.play_b.clicked.connect(lambda: self._play_slot("B"))
        self.stop_button.clicked.connect(self.stop)
        ab_buttons.addWidget(self.play_a)
        ab_buttons.addWidget(self.play_b)
        ab_buttons.addWidget(self.stop_button)
        layout.addLayout(ab_buttons)

        transport = QHBoxLayout()
        transport.setSpacing(8)
        self.play_button = QPushButton("▶")
        self.play_button.setObjectName("IconButton")
        self.play_button.setFixedWidth(40)
        self.play_button.setToolTip("Воспроизвести / пауза (Пробел)")
        self.play_button.clicked.connect(self.toggle_play)
        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderPressed.connect(self._slider_pressed)
        self.position_slider.sliderReleased.connect(self._slider_released)
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setObjectName("Muted")
        self.time_label.setMinimumWidth(76)
        transport.addWidget(self.play_button)
        transport.addWidget(self.position_slider, 1)
        transport.addWidget(self.time_label)
        layout.addLayout(transport)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Muted")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(28)
        layout.addWidget(self.status_label)

        divider2 = QFrame()
        divider2.setObjectName("Divider")
        layout.addWidget(divider2)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.keeper_button = QPushButton("★  Оставить этот файл")
        self.keeper_button.setObjectName("Primary")
        self.keeper_button.clicked.connect(self._request_keeper)
        action_row.addWidget(self.keeper_button, 1)
        self.open_button = QPushButton("Папка")
        self.open_button.setObjectName("Small")
        self.open_button.setToolTip("Открыть папку с файлом")
        self.open_button.clicked.connect(self._open_folder)
        action_row.addWidget(self.open_button)
        layout.addLayout(action_row)

        layout.addStretch(1)

    @staticmethod
    def _slot_row(name: str, combo: QComboBox) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel(name)
        label.setObjectName("Badge")
        label.setFixedWidth(24)
        label.setAlignment(Qt.AlignCenter)
        row.addWidget(label)
        row.addWidget(combo, 1)
        return row

    # --------------------------------------------------------------- public
    def clear(self) -> None:
        self.stop()
        self._group = None
        self._file = None
        self._loading = True
        self.a_combo.clear()
        self.b_combo.clear()
        self._loading = False
        self.title_label.setText("Файл не выбран")
        self.artist_label.setText("Выберите файл в списке слева")
        self.match_label.hide()
        self.group_label.setText("")
        self.keeper_button.setEnabled(False)
        self.keeper_button.setText("★  Оставить этот файл")
        self.open_button.setEnabled(False)
        for widget in (
            self.a_combo,
            self.b_combo,
            self.play_a,
            self.play_b,
            self.stop_button,
            self.play_button,
            self.position_slider,
        ):
            widget.setEnabled(False)
        self._active_slot = "A"
        self._update_slot_buttons()
        for label in self._info_values.values():
            label.setText("—")
        self.cover.setPixmap(QPixmap())
        self.cover.setText("♪")
        self.status_label.clear()
        self.position_slider.setRange(0, 0)
        self.time_label.setText("0:00 / 0:00")

    def set_group(self, group: DuplicateGroup | None, current: AudioFile | None) -> None:
        self._group = group
        self._file = current
        if group is None or current is None:
            self.clear()
            return

        self._loading = True
        files = group.sorted_files()
        self.a_combo.clear()
        self.b_combo.clear()
        for audio in files:
            label = audio.filename
            if audio.is_keeper:
                label = f"★ {label}"
            self.a_combo.addItem(label, audio.path)
            self.b_combo.addItem(label, audio.path)

        a_index = max(0, self.a_combo.findData(current.path))
        self.a_combo.setCurrentIndex(a_index)
        other = next((audio for audio in files if audio.path != current.path), current)
        self.b_combo.setCurrentIndex(max(0, self.b_combo.findData(other.path)))
        self._loading = False

        self.title_label.setText(current.display_title)
        subtitle = current.display_subtitle
        self.artist_label.setText(subtitle or "Без тегов")
        badge = quality_badge(current)
        self.match_label.setText(f"{current.similarity_text}   ·   {badge}")
        self.match_label.show()

        plural = self._plural(len(group.files))
        self.group_label.setText(
            f"Группа {group.index} · {len(group.files)} {plural}"
        )

        format_parts = [current.format_label, current.sample_rate_text]
        if current.bits_per_sample:
            format_parts.append(f"{current.bits_per_sample} бит")
        self._info_values["format"].setText(" · ".join(format_parts))
        self._info_values["duration"].setText(
            f"{current.duration_text} · {current.bitrate_text}"
        )
        self._info_values["size"].setText(current.size_text)
        self._info_values["path"].setText(current.folder)
        self._info_values["path"].setToolTip(current.path)

        self._set_cover(current.path)
        self.keeper_button.setEnabled(not current.is_keeper)
        self.keeper_button.setText(
            "★  Этот файл будет оставлен" if current.is_keeper else "★  Оставить этот файл"
        )
        self.open_button.setEnabled(True)
        for widget in (
            self.a_combo,
            self.b_combo,
            self.play_a,
            self.play_b,
            self.stop_button,
            self.play_button,
            self.position_slider,
        ):
            widget.setEnabled(True)

        # Загружаем текущий файл, но не начинаем играть без команды.
        if self._active_path() != current.path:
            self._load_source(current.path, 0, False)
            self._active_slot = "A"
        self._update_slot_buttons()

    def toggle_play(self) -> None:
        if not self._active_path():
            self._play_slot("A")
            return
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def stop(self) -> None:
        self._player.stop()
        self.position_slider.setValue(0)
        self.time_label.setText("0:00 / 0:00")

    # -------------------------------------------------------------- details
    def _set_cover(self, path: str) -> None:
        if path not in self._covers:
            data = extract_cover(path)
            pixmap = None
            if data:
                raw = QPixmap()
                if raw.loadFromData(data):
                    pixmap = _rounded_pixmap(raw, self.COVER_SIZE)
            self._covers[path] = pixmap
        pixmap = self._covers[path]
        if pixmap is None:
            self.cover.setPixmap(QPixmap())
            self.cover.setText("♪")
        else:
            self.cover.setText("")
            self.cover.setPixmap(pixmap)

    def _request_keeper(self) -> None:
        if self._file is not None:
            self.keeper_requested.emit(self._file.path)

    def _open_folder(self) -> None:
        if self._file is not None:
            self.open_folder_requested.emit(self._file.path)

    # ------------------------------------------------------------- playback
    def _slot_path(self, slot: str) -> str:
        combo = self.a_combo if slot == "A" else self.b_combo
        data = combo.currentData()
        return str(data) if data else ""

    def _active_path(self) -> str:
        data = self._player.source().toLocalFile()
        return data or ""

    def _combo_changed(self, slot: str) -> None:
        if self._loading:
            return
        path = self._slot_path(slot)
        if not path:
            return
        self._active_slot = slot
        self._load_source(path, 0, False)
        self.status_label.setText(f"Выбран файл {slot}: {os.path.basename(path)}")
        self._update_slot_buttons()

    def _play_slot(self, slot: str) -> None:
        path = self._slot_path(slot)
        if not path:
            return
        self._active_slot = slot
        if self._active_path() == path:
            self._player.play()
            self.status_label.setText(f"Играет {slot}: {os.path.basename(path)}")
        else:
            position = self._player.position() if self._active_path() else 0
            self._load_source(path, position, True)
            self.status_label.setText(
                f"Играет {slot}: {os.path.basename(path)} · позиция {self._format_ms(position)}"
            )
        self._update_slot_buttons()

    def _load_source(self, path: str, position_ms: int, play: bool) -> None:
        self._pending_position = max(0, int(position_ms))
        self._pending_play = play
        if path == self._active_path():
            if position_ms > 0:
                self._player.setPosition(position_ms)
            if play:
                self._player.play()
            return
        self._player.setSource(QUrl.fromLocalFile(path))

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status != QMediaPlayer.LoadedMedia:
            return
        duration = self._player.duration()
        position = self._pending_position
        if duration > 0:
            position = min(position, max(0, duration - 500))
        if position > 0:
            self._player.setPosition(position)
        if self._pending_play:
            self._player.play()
        self._pending_position = 0
        self._pending_play = False

    def _on_playback_state(self, state: QMediaPlayer.PlaybackState) -> None:
        playing = state == QMediaPlayer.PlayingState
        self.play_button.setText("⏸" if playing else "▶")
        if playing:
            path = self._active_path()
            if path:
                self.status_label.setText(
                    f"Играет {self._active_slot}: {os.path.basename(path)}"
                )

    def _on_position(self, position: int) -> None:
        if not self._slider_dragging:
            self.position_slider.setValue(position)
        self.time_label.setText(
            f"{self._format_ms(position)} / "
            f"{self._format_ms(self._player.duration())}"
        )

    def _on_duration(self, duration: int) -> None:
        self.position_slider.setRange(0, max(0, duration))
        self.time_label.setText(
            f"{self._format_ms(self._player.position())} / "
            f"{self._format_ms(duration)}"
        )

    def _on_error(self, _error, error_string: str) -> None:
        if error_string:
            self.status_label.setText(
                f"Не удалось воспроизвести: {error_string}. "
                "Попробуйте открыть файл в системном плеере."
            )

    def _slider_pressed(self) -> None:
        self._slider_dragging = True

    def _slider_released(self) -> None:
        self._slider_dragging = False
        self._player.setPosition(self.position_slider.value())

    def _update_slot_buttons(self) -> None:
        active = self._active_slot
        self.play_a.setObjectName("Primary" if active == "A" else "Small")
        self.play_b.setObjectName("Primary" if active == "B" else "Small")
        for button in (self.play_a, self.play_b):
            button.style().unpolish(button)
            button.style().polish(button)

    @staticmethod
    def _plural(count: int) -> str:
        if count % 10 == 1 and count % 100 != 11:
            return "файл"
        if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
            return "файла"
        return "файлов"

    @staticmethod
    def _format_ms(milliseconds: int) -> str:
        total = max(0, int(milliseconds)) // 1000
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
