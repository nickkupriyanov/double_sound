"""Хеширование файлов: быстрый отпечаток и полный SHA-256."""

from __future__ import annotations

import hashlib
import os

CHUNK = 1024 * 1024
QUICK_CHUNK = 64 * 1024


def quick_hash(path: str) -> str:
    """BLAKE2b по первым и последним 64 КБ файла.

    Дёшево отсеивает файлы, которые заведомо не совпадают: у одинаковых
    по содержимому файлов совпадает и размер, и этот отпечаток.
    """
    digest = hashlib.blake2b(digest_size=16)
    with open(path, "rb") as handle:
        head = handle.read(QUICK_CHUNK)
        digest.update(head)
        if os.fstat(handle.fileno()).st_size > QUICK_CHUNK:
            try:
                handle.seek(-QUICK_CHUNK, os.SEEK_END)
                digest.update(handle.read(QUICK_CHUNK))
            except OSError:
                pass
    return digest.hexdigest()


def sha256_file(path: str, cancel_event=None) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError("cancelled")
            chunk = handle.read(CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()
