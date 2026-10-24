"""Аудиоотпечатки Chromaprint и сравнение по доле битовых ошибок."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path

import numpy as np

from .paths import app_dir, resource_path

FP_FRAME_SECONDS = 0.1238  # длительность одного кадра отпечатка Chromaprint
_POPCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)


class FingerprintError(RuntimeError):
    pass


def _fpcalc_name() -> str:
    return "fpcalc.exe" if os.name == "nt" else "fpcalc"


def find_fpcalc() -> str | None:
    """Ищет fpcalc: переменная окружения, ресурсы приложения, PATH."""
    override = os.environ.get("FPCALC", "").strip().strip('"')
    if override and Path(override).is_file():
        return override

    name = _fpcalc_name()
    candidates = [
        resource_path(name),
        app_dir() / name,
        Path(sys.executable).resolve().parent / name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    found = shutil.which("fpcalc")
    if found:
        return found
    return None


def fpcalc_available() -> bool:
    return find_fpcalc() is not None


def _silent_flags() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def _tool_path(path: str) -> str:
    """Короткий ASCII-путь для fpcalc на Windows.

    fpcalc — консольная программа, и в зависимости от сборки она может
    неправильно принимать аргументы с кириллицей. Короткое имя 8.3 решает
    проблему, если оно включено в системе.
    """
    if os.name != "nt" or all(ord(char) < 128 for char in path):
        return path
    try:
        import ctypes
        from ctypes import wintypes

        function = ctypes.windll.kernel32.GetShortPathNameW
        function.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        function.restype = wintypes.DWORD
        required = function(path, None, 0)
        if not required:
            return path
        buffer = ctypes.create_unicode_buffer(required)
        if not function(path, buffer, required):
            return path
        short = buffer.value
        if short and all(ord(char) < 128 for char in short):
            return short
    except Exception:
        pass
    return path


def _needs_stdin(argument: str) -> bool:
    return os.name == "nt" and not all(ord(char) < 128 for char in argument)


def compute_fingerprint(
    path: str,
    length: int = 120,
    fpcalc: str | None = None,
    cancel_event=None,
) -> tuple[bytes, float]:
    """Возвращает (сырой отпечаток uint32 LE, длительность файла в секундах)."""
    executable = fpcalc or find_fpcalc()
    if not executable:
        raise FingerprintError(
            "Не найден fpcalc. Положите fpcalc.exe рядом с программой "
            "или установите пакет chromaprint."
        )

    argument = _tool_path(path)
    command = [
        executable,
        "-raw",
        "-json",
        "-length",
        str(max(10, int(length))),
    ]
    source = None
    if _needs_stdin(argument):
        # Если короткое имя 8.3 недоступно, передаём файл через stdin:
        # так кириллица в пути не зависит от кодировки консольной программы.
        try:
            source = open(path, "rb")
        except OSError as exc:
            raise FingerprintError(f"Не удалось открыть файл: {exc}") from exc
        command.append("-")
    else:
        command.append(argument)

    try:
        process = subprocess.Popen(
            command,
            stdin=source,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_silent_flags(),
        )
    except OSError as exc:
        if source is not None:
            source.close()
        raise FingerprintError(f"Не удалось запустить fpcalc: {exc}") from exc

    deadline = time.monotonic() + 300
    stdout = b""
    stderr = b""
    try:
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if cancel_event is not None and cancel_event.is_set():
                    process.kill()
                    process.communicate()
                    raise FingerprintError("сканирование отменено") from None
                if time.monotonic() >= deadline:
                    process.kill()
                    process.communicate()
                    raise FingerprintError(
                        "fpcalc не успел обработать файл за 5 минут"
                    ) from None
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
        if source is not None:
            source.close()

    if process.returncode != 0:
        message = stderr.decode("utf-8", "replace").strip().splitlines()
        detail = message[-1] if message else f"код {process.returncode}"
        raise FingerprintError(f"fpcalc: {detail}")

    try:
        payload = json.loads(stdout.decode("utf-8", "replace"))
        values = payload["fingerprint"]
        duration = float(payload.get("duration") or 0.0)
    except (ValueError, KeyError, TypeError) as exc:
        raise FingerprintError("fpcalc вернул некорректный ответ") from exc

    if not values:
        raise FingerprintError("отпечаток пуст (слишком короткий файл или тишина)")

    array = np.asarray(values, dtype="<u4")
    return array.tobytes(), duration


def fingerprint_array(blob: bytes) -> np.ndarray:
    if not blob:
        return np.empty(0, dtype="<u4")
    return np.frombuffer(blob, dtype="<u4")


def _hamming_bits(left: np.ndarray, right: np.ndarray) -> int:
    xor = np.bitwise_xor(left, right)
    return int(_POPCOUNT[xor.view(np.uint8)].sum(dtype=np.int64))


@lru_cache(maxsize=4096)
def _array_from_blob(blob: bytes) -> np.ndarray:
    # Небольшой кэш на время одного сканирования: отпечатки сравниваются многократно.
    return fingerprint_array(blob)


def _score_at_shift(left: np.ndarray, right: np.ndarray, shift: int) -> tuple[int, int]:
    """Возвращает (число совпавших бит, число бит) для сдвига."""
    if shift >= 0:
        a = left[shift:]
        b = right
    else:
        a = left
        b = right[-shift:]
    frames = min(a.size, b.size)
    if frames <= 0:
        return 0, 0
    return frames * 32 - _hamming_bits(a[:frames], b[:frames]), frames * 32


def similarity(
    left_blob: bytes,
    right_blob: bytes,
    max_shift: int = 24,
    min_overlap_seconds: float = 15.0,
) -> float:
    """Схожесть двух отпечатков от 0 до 1.

    1.0 — одинаковая запись. Порог 0.88 надёжно отделяет дубликаты от
    разных песен (обычно у разных песен схожесть около 0.5).
    """
    left = _array_from_blob(left_blob)
    right = _array_from_blob(right_blob)
    if left.size == 0 or right.size == 0:
        return 0.0

    min_frames = max(40, int(min_overlap_seconds / FP_FRAME_SECONDS))
    min_frames = min(min_frames, min(left.size, right.size))
    if min_frames <= 0:
        return 0.0

    shifts = [0]
    for distance in range(1, max_shift + 1):
        shifts.extend((distance, -distance))

    # Быстрая проверка по прореженному отпечатку: разные песни отсеиваются,
    # не прогоняя все сдвиги по всему отпечатку.
    probe_left = left[::2]
    probe_right = right[::2]
    probe_shifts = [0]
    for distance in range(1, max_shift // 2 + 1):
        probe_shifts.extend((distance, -distance))
    probe_best = 0.0
    for shift in probe_shifts:
        matched, bits = _score_at_shift(probe_left, probe_right, shift)
        if bits:
            probe_best = max(probe_best, matched / bits)
    if probe_best < 0.72:
        return probe_best

    best = 0.0
    for shift in shifts:
        matched, bits = _score_at_shift(left, right, shift)
        if not bits:
            continue
        frames = bits // 32
        if frames < min_frames:
            continue
        score = matched / bits
        if score > best:
            best = score
            if best >= 0.9999:
                break

    return max(0.0, best)
