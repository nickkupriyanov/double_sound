"""Поиск аудиофайлов и чтение метаданных."""

from __future__ import annotations

import base64
import os
import re
from typing import Iterable

from mutagen import File as MutagenFile

from .hashing import quick_hash
from .models import AUDIO_EXTENSIONS, AudioFile

SKIP_DIRECTORIES = {
    "$RECYCLE.BIN",
    "System Volume Information",
    ".Trash",
    ".Trashes",
    "@eaDir",
    "#recycle",
    "lost+found",
    ".git",
    "node_modules",
}

_YEAR_RE = re.compile(r"(19|20)\d{2}")


def iter_audio_files(
    folders: Iterable[str],
    extensions: frozenset[str] = AUDIO_EXTENSIONS,
    warnings: list[str] | None = None,
) -> list[str]:
    """Рекурсивно собирает аудиофайлы, пропуская системные каталоги."""
    found: list[str] = []
    seen_paths: set[str] = set()
    seen_inodes: set[tuple[int, int]] = set()

    for folder in folders:
        root = os.path.abspath(os.path.expanduser(folder))
        if not os.path.isdir(root):
            if warnings is not None:
                warnings.append(f"Папка недоступна: {root}")
            continue

        stack = [root]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as iterator:
                    entries = list(iterator)
            except OSError as exc:
                if warnings is not None:
                    warnings.append(f"Нет доступа к папке {current}: {exc.strerror or exc}")
                continue

            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name.startswith(".") or entry.name in SKIP_DIRECTORIES:
                            continue
                        stack.append(entry.path)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    extension = os.path.splitext(entry.name)[1].lower()
                    if extension not in extensions:
                        continue
                    path_key = os.path.normcase(os.path.abspath(entry.path))
                    if path_key in seen_paths:
                        continue
                    stat = entry.stat(follow_symlinks=False)
                    # На некоторых сетевых/FAT-разделах st_ino равен нулю;
                    # в этом случае нельзя считать файлы жёсткими ссылками.
                    if stat.st_ino:
                        inode_key = (stat.st_dev, stat.st_ino)
                        if inode_key in seen_inodes:
                            continue
                        seen_inodes.add(inode_key)
                    seen_paths.add(path_key)
                    found.append(entry.path)
                except OSError:
                    continue

    found.sort(key=lambda value: value.lower())
    return found


def _first_tag(tags, *keys: str) -> str:
    if not tags:
        return ""
    for key in keys:
        try:
            value = tags.get(key)
        except Exception:
            continue
        if not value:
            continue
        if isinstance(value, (list, tuple)):
            if not value:
                continue
            value = value[0]
        text = str(value).strip()
        if text:
            return text
    return ""


def read_metadata(path: str) -> dict:
    """Читает теги и технические параметры. Ошибки не фатальны."""
    result = {
        "duration": 0.0,
        "bitrate": 0,
        "sample_rate": 0,
        "bits_per_sample": 0,
        "channels": 0,
        "codec": "",
        "artist": "",
        "title": "",
        "album": "",
        "year": "",
    }
    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        return result
    if audio is None:
        return result

    info = getattr(audio, "info", None)
    if info is not None:
        try:
            result["duration"] = float(getattr(info, "length", 0.0) or 0.0)
        except (TypeError, ValueError):
            pass
        try:
            bitrate = int(getattr(info, "bitrate", 0) or 0)
            result["bitrate"] = round(bitrate / 1000) if bitrate > 0 else 0
        except (TypeError, ValueError):
            pass
        try:
            result["sample_rate"] = int(getattr(info, "sample_rate", 0) or 0)
        except (TypeError, ValueError):
            pass
        try:
            result["bits_per_sample"] = int(
                getattr(info, "bits_per_sample", 0) or 0
            )
        except (TypeError, ValueError):
            pass
        try:
            result["channels"] = int(getattr(info, "channels", 0) or 0)
        except (TypeError, ValueError):
            pass
        codec = getattr(info, "codec", "")
        if codec:
            result["codec"] = str(codec).strip().lower()

    tags = getattr(audio, "tags", None)
    result["artist"] = _first_tag(tags, "artist", "albumartist", "album artist")
    result["title"] = _first_tag(tags, "title")
    result["album"] = _first_tag(tags, "album")
    year = _first_tag(tags, "date", "year", "originaldate")
    match = _YEAR_RE.search(year)
    result["year"] = match.group(0) if match else ""
    return result


def prepare_audio_file(path: str, compute_quick_hash: bool = True) -> AudioFile:
    """Собирает сведения о файле (без обращения к кэшу)."""
    stat = os.stat(path)
    audio = AudioFile(
        path=os.path.abspath(path),
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        fmt=os.path.splitext(path)[1].lstrip(".").upper(),
    )
    if compute_quick_hash:
        try:
            audio.quick_hash = quick_hash(path)
        except OSError as exc:
            audio.error = f"не читается: {exc.strerror or exc}"
            return audio

    try:
        meta = read_metadata(path)
    except Exception as exc:  # pragma: no cover - защита от странных файлов
        audio.error = f"ошибка чтения тегов: {exc}"
        return audio

    for key, value in meta.items():
        setattr(audio, key, value)
    return audio


def extract_cover(path: str, limit: int = 8 * 1024 * 1024) -> bytes | None:
    """Достаёт встроенную обложку, если она есть."""
    try:
        audio = MutagenFile(path)
    except Exception:
        return None
    if audio is None:
        return None

    tags = getattr(audio, "tags", None)
    pictures = getattr(audio, "pictures", None)
    try:
        if pictures:
            data = pictures[0].data
            if data and len(data) <= limit:
                return data
        if tags is None:
            return None

        # MP3 / ID3
        try:
            apics = tags.getall("APIC")
            if apics:
                data = apics[0].data
                if data and len(data) <= limit:
                    return data
        except Exception:
            pass

        # MP4 / M4A
        try:
            covers = tags.get("covr")
            if covers:
                data = bytes(covers[0])
                if len(data) <= limit:
                    return data
        except Exception:
            pass

        # OGG / Opus
        try:
            raw = tags.get("metadata_block_picture")
            if raw:
                from mutagen.flac import Picture

                picture = Picture(base64.b64decode(raw[0]))
                if picture.data and len(picture.data) <= limit:
                    return picture.data
        except Exception:
            pass
    except Exception:
        return None
    return None
