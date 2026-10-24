"""Оценка качества аудиофайла — чтобы предложить, какую копию оставить."""

from __future__ import annotations

from .models import AudioFile


def is_lossless(audio: AudioFile) -> bool:
    return audio.is_lossless


def quality_key(audio: AudioFile) -> tuple:
    """Чем больше, тем лучше.

    Сначала lossless, затем частота дискретизации, «удобство» формата
    (сжатый lossless лучше несжатого WAV при том же качестве), битрейт и размер.
    """
    suffix = audio.suffix
    lossless = audio.is_lossless
    if suffix in {".flac", ".alac"} or audio.codec == "alac":
        format_rank = 3
    elif suffix in {".ape", ".wv"}:
        format_rank = 2
    elif suffix in {".wav", ".aiff", ".aif"}:
        format_rank = 1
    else:
        format_rank = 0
    if lossless:
        # При одинаковом качестве (частота и разрядность) компактный
        # lossless-файл удобнее: FLAC предпочтительнее раздутого ALAC/WAV.
        return (
            1,
            audio.sample_rate or 0,
            audio.bits_per_sample or 0,
            format_rank,
            -(audio.size or 0),
            -len(audio.path),
        )
    return (
        0,
        audio.sample_rate or 0,
        0,
        format_rank,
        audio.bitrate or 0,
        audio.size or 0,
        -len(audio.path),  # детерминированный порядок при полном равенстве
    )


def quality_badge(audio: AudioFile) -> str:
    bits = ["Без потерь" if is_lossless(audio) else "С потерями"]
    if audio.sample_rate:
        bits.append(audio.sample_rate_text)
    if audio.bits_per_sample:
        bits.append(f"{audio.bits_per_sample} бит")
    if audio.bitrate and not is_lossless(audio):
        bits.append(f"{audio.bitrate} кбит/с")
    return " · ".join(bits)


def pick_keeper(files: list[AudioFile]) -> AudioFile | None:
    if not files:
        return None
    return max(files, key=quality_key)


def rank_group(files: list[AudioFile]) -> AudioFile | None:
    """Проставляет is_keeper и возвращает лучший файл."""
    keeper = pick_keeper(files)
    for audio in files:
        audio.is_keeper = audio is keeper
    return keeper
