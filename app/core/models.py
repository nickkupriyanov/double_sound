"""Модели данных приложения."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

# Расширения, которые умеет читать fpcalc / mutagen.
AUDIO_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".mp3",
        ".flac",
        ".wav",
        ".m4a",
        ".aac",
        ".ogg",
        ".oga",
        ".opus",
        ".wma",
        ".aiff",
        ".aif",
        ".ape",
        ".wv",
        ".alac",
    }
)

LOSSLESS_EXTENSIONS: frozenset[str] = frozenset(
    {".flac", ".wav", ".aiff", ".aif", ".ape", ".wv", ".alac"}
)

# Группы форматов для фильтра в интерфейсе: ключ -> расширения (None = все).
FORMAT_FILTERS: dict[str, frozenset[str] | None] = {
    "all": None,
    "mp3": frozenset({".mp3"}),
    "flac": frozenset({".flac"}),
    "wav": frozenset({".wav", ".aiff", ".aif"}),
    "m4a": frozenset({".m4a", ".aac", ".alac"}),
    "ogg": frozenset({".ogg", ".oga", ".opus"}),
    "other": frozenset({".wma", ".ape", ".wv"}),
}

FORMAT_FILTER_LABELS: dict[str, str] = {
    "all": "Все форматы",
    "mp3": "MP3",
    "flac": "FLAC",
    "wav": "WAV / AIFF",
    "m4a": "M4A / AAC",
    "ogg": "OGG / Opus",
    "other": "Другие",
}


def human_size(num_bytes: int) -> str:
    """Размер в удобном виде (русские единицы)."""
    size = float(max(0, num_bytes))
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if size < 1024 or unit == "ТБ":
            if unit == "Б":
                return f"{int(size)} Б"
            return f"{size:.1f} {unit}".replace(".", ",")
        size /= 1024
    return f"{size:.1f} ТБ"


def human_duration(seconds: float) -> str:
    if not seconds or seconds <= 0:
        return "—"
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def plural_ru(number: int, one: str, few: str, many: str) -> str:
    number = abs(number)
    if number % 10 == 1 and number % 100 != 11:
        return one
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return few
    return many


@dataclass
class AudioFile:
    """Один аудиофайл и всё, что о нём известно."""

    path: str
    size: int = 0
    mtime_ns: int = 0
    quick_hash: str = ""
    sha256: str = ""
    duration: float = 0.0
    bitrate: int = 0  # кбит/с
    sample_rate: int = 0  # Гц
    bits_per_sample: int = 0
    channels: int = 0
    fmt: str = ""
    codec: str = ""  # кодек из метаданных, например alac или mp4a
    artist: str = ""
    title: str = ""
    album: str = ""
    year: str = ""
    fingerprint: bytes = b""  # raw chromaprint, uint32 little-endian
    fp_duration: float = 0.0
    error: str = ""

    # Заполняется при группировке.
    similarity: float = 1.0
    match_type: str = "exact"  # exact | acoustic
    is_keeper: bool = False

    @property
    def suffix(self) -> str:
        return os.path.splitext(self.path)[1].lower()

    @property
    def is_lossless(self) -> bool:
        """Lossless-формат, в том числе ALAC в контейнере M4A."""
        if self.suffix in LOSSLESS_EXTENSIONS:
            return True
        return self.codec.strip().lower() in {"alac", "flac", "ape", "wavpack"}

    @property
    def stem(self) -> str:
        return os.path.splitext(os.path.basename(self.path))[0]

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)

    @property
    def folder(self) -> str:
        return os.path.dirname(self.path)

    @property
    def effective_duration(self) -> float:
        return self.duration or self.fp_duration

    @property
    def display_title(self) -> str:
        if self.title and self.artist:
            return f"{self.artist} — {self.title}"
        if self.title:
            return self.title
        return self._guess_from_filename()

    @property
    def display_subtitle(self) -> str:
        parts = [self.artist] if self.artist else []
        if self.album:
            parts.append(self.album)
        if self.year:
            parts.append(str(self.year))
        return " · ".join(parts)

    @property
    def format_label(self) -> str:
        return (self.suffix.lstrip(".") or "?").upper()

    @property
    def bitrate_text(self) -> str:
        return f"{self.bitrate} кбит/с" if self.bitrate else "—"

    @property
    def sample_rate_text(self) -> str:
        if not self.sample_rate:
            return "—"
        if self.sample_rate % 1000 == 0:
            return f"{self.sample_rate // 1000} кГц"
        return f"{self.sample_rate / 1000:.1f} кГц".replace(".", ",")

    @property
    def size_text(self) -> str:
        return human_size(self.size)

    @property
    def duration_text(self) -> str:
        return human_duration(self.effective_duration)

    @property
    def similarity_text(self) -> str:
        if self.match_type == "exact":
            return "Точная копия"
        if self.similarity >= 0.999:
            return "100 %"
        return f"{self.similarity * 100:.0f} %"

    def _guess_from_filename(self) -> str:
        stem = self.stem
        if " - " in stem:
            left, right = stem.split(" - ", 1)
            if left.strip() and right.strip():
                return f"{left.strip()} — {right.strip()}"
        return stem


@dataclass
class DuplicateGroup:
    """Группа файлов, которые являются дубликатами друг друга."""

    files: list[AudioFile]
    kind: str = "exact"  # exact | acoustic | mixed
    similarity: float = 1.0
    keeper: AudioFile | None = None
    index: int = 0

    @property
    def total_size(self) -> int:
        return sum(f.size for f in self.files)

    @property
    def reclaimable(self) -> int:
        keeper_size = self.keeper.size if self.keeper else 0
        return max(0, self.total_size - keeper_size)

    @property
    def title(self) -> str:
        source = self.keeper or (self.files[0] if self.files else None)
        return source.display_title if source else "Без названия"

    @property
    def sort_key(self) -> tuple:
        return (self.reclaimable, self.total_size, self.title.lower())

    def sorted_files(self) -> list[AudioFile]:
        """Файлы по убыванию качества."""
        from .quality import quality_key

        return sorted(self.files, key=quality_key, reverse=True)


@dataclass
class ScanOptions:
    folders: list[str] = field(default_factory=list)
    threshold: float = 0.12  # максимальная доля ошибок отпечатка (BER)
    min_duration: float = 10.0
    fingerprint_length: int = 120
    workers: int = 4
    use_acoustic: bool = True
    extensions: frozenset[str] = AUDIO_EXTENSIONS
    duration_tolerance: float = 8.0


@dataclass
class ScanStats:
    scanned: int = 0
    analyzed: int = 0
    groups: int = 0
    duplicate_files: int = 0
    exact_groups: int = 0
    acoustic_groups: int = 0
    reclaimable: int = 0
    elapsed: float = 0.0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class ScanResult:
    files: list[AudioFile] = field(default_factory=list)
    groups: list[DuplicateGroup] = field(default_factory=list)
    stats: ScanStats = field(default_factory=ScanStats)


ProgressCallback = Callable[[str, int, int, str], None]
