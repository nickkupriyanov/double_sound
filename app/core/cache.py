"""Кэш результатов анализа в SQLite.

Повторное сканирование тех же папок не требует заново считать хеши и
аудиоотпечатки: запись переиспользуется, пока не изменились размер и mtime.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import AudioFile

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path        TEXT PRIMARY KEY,
    size        INTEGER NOT NULL,
    mtime_ns    INTEGER NOT NULL,
    quick_hash  TEXT NOT NULL DEFAULT '',
    sha256      TEXT NOT NULL DEFAULT '',
    fingerprint BLOB,
    fp_duration REAL NOT NULL DEFAULT 0,
    meta        TEXT NOT NULL DEFAULT '{}'
);
"""

_META_FIELDS = (
    "duration",
    "bitrate",
    "sample_rate",
    "bits_per_sample",
    "channels",
    "fmt",
    "codec",
    "artist",
    "title",
    "album",
    "year",
)


class Cache:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = self._connect()
        except sqlite3.DatabaseError:
            # Повреждённый кэш не должен мешать работе — начинаем заново.
            try:
                self.path.replace(self.path.with_suffix(self.path.suffix + ".corrupt"))
            except OSError:
                self.path.unlink(missing_ok=True)
            self._conn = self._connect()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=15)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.executescript(_SCHEMA)
        connection.commit()
        return connection

    def get(self, path: str, size: int, mtime_ns: int) -> AudioFile | None:
        row = self._conn.execute(
            "SELECT quick_hash, sha256, fingerprint, fp_duration, meta "
            "FROM files WHERE path = ? AND size = ? AND mtime_ns = ?",
            (path, size, mtime_ns),
        ).fetchone()
        if not row:
            return None
        quick_hash, sha256, fingerprint, fp_duration, meta_json = row
        try:
            meta = json.loads(meta_json or "{}")
        except ValueError:
            meta = {}
        values = {key: meta.get(key, "") for key in _META_FIELDS}
        values["duration"] = float(values["duration"] or 0.0)
        for key in ("bitrate", "sample_rate", "bits_per_sample", "channels"):
            try:
                values[key] = int(values[key] or 0)
            except (TypeError, ValueError):
                values[key] = 0
        return AudioFile(
            path=path,
            size=size,
            mtime_ns=mtime_ns,
            quick_hash=quick_hash or "",
            sha256=sha256 or "",
            fingerprint=bytes(fingerprint or b""),
            fp_duration=float(fp_duration or 0.0),
            **values,
        )

    def put(self, audio: AudioFile) -> None:
        meta = {key: getattr(audio, key) for key in _META_FIELDS}
        self._conn.execute(
            "INSERT INTO files(path, size, mtime_ns, quick_hash, sha256, "
            "fingerprint, fp_duration, meta) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET "
            "size=excluded.size, mtime_ns=excluded.mtime_ns, "
            "quick_hash=excluded.quick_hash, sha256=excluded.sha256, "
            "fingerprint=excluded.fingerprint, fp_duration=excluded.fp_duration, "
            "meta=excluded.meta",
            (
                audio.path,
                audio.size,
                audio.mtime_ns,
                audio.quick_hash,
                audio.sha256,
                sqlite3.Binary(audio.fingerprint) if audio.fingerprint else None,
                audio.fp_duration,
                json.dumps(meta, ensure_ascii=False),
            ),
        )

    def delete(self, paths: list[str]) -> None:
        if not paths:
            return
        self._conn.executemany("DELETE FROM files WHERE path = ?", ((p,) for p in paths))
        self._conn.commit()

    def commit(self) -> None:
        self._conn.commit()

    def clear(self) -> None:
        self._conn.execute("DELETE FROM files")
        self._conn.commit()
        self._conn.execute("VACUUM")

    def stats(self) -> tuple[int, int]:
        row = self._conn.execute("SELECT COUNT(*), COALESCE(SUM(size), 0) FROM files").fetchone()
        return int(row[0] or 0), int(row[1] or 0)

    def close(self) -> None:
        try:
            self._conn.commit()
        finally:
            self._conn.close()

    def __enter__(self) -> "Cache":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
