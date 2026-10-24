"""Экспорт отчёта в CSV (открывается в Excel без настройки кодировки)."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .models import DuplicateGroup, human_duration

HEADERS = [
    "Группа",
    "Тип совпадения",
    "Схожесть, %",
    "Оставить",
    "К удалению",
    "Исполнитель",
    "Название",
    "Альбом",
    "Формат",
    "Битрейт, кбит/с",
    "Частота, Гц",
    "Длительность",
    "Размер, МБ",
    "Путь",
    "SHA-256",
]

_TYPE_LABELS = {
    "exact": "Точная копия",
    "acoustic": "По звучанию",
    "mixed": "Смешанная группа",
}


def write_report(
    path: str | Path,
    groups: list[DuplicateGroup],
    marked_for_delete: set[str] | None = None,
) -> Path:
    marked_for_delete = marked_for_delete or set()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(HEADERS)
        for group in groups:
            for audio in group.sorted_files():
                similarity = 100 if audio.match_type == "exact" else round(audio.similarity * 100)
                writer.writerow(
                    [
                        group.index,
                        _TYPE_LABELS.get(group.kind, group.kind),
                        similarity,
                        "да" if audio.is_keeper else "",
                        "да" if audio.path in marked_for_delete else "",
                        audio.artist,
                        audio.title,
                        audio.album,
                        audio.format_label,
                        audio.bitrate or "",
                        audio.sample_rate or "",
                        human_duration(audio.effective_duration),
                        f"{audio.size / (1024 * 1024):.2f}".replace(".", ","),
                        audio.path,
                        audio.sha256,
                    ]
                )
    return destination


def default_report_name() -> str:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    return f"double_sound_{stamp}.csv"
