"""Оркестрация сканирования: файлы → хеши → отпечатки → группы."""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .cache import Cache
from .fingerprint import (
    FingerprintError,
    compute_fingerprint,
    find_fpcalc,
    similarity,
)
from .grouping import build_groups
from .hashing import sha256_file
from .models import (
    AudioFile,
    ProgressCallback,
    ScanOptions,
    ScanResult,
    ScanStats,
)
from .paths import default_cache_path
from .scanner import iter_audio_files, prepare_audio_file

MAX_MESSAGES = 60


class ScanCancelled(Exception):
    """Пользователь отменил сканирование."""


def _remember(bucket: list[str], message: str) -> None:
    if len(bucket) < MAX_MESSAGES:
        bucket.append(message)


def _run_parallel(items, worker, handle, workers: int, check_cancel) -> None:
    """Параллельная обработка с быстрой отменой.

    При отмене уже запущенные задачи завершаются (fpcalc и SHA-256 умеют
    прерываться), а ещё не начатые — снимаются с очереди. Благодаря этому
    интерфейс не ждёт обработки всех оставшихся файлов.
    """
    if not items:
        return
    pool = ThreadPoolExecutor(max_workers=max(1, min(workers, len(items))))
    futures = {pool.submit(worker, item): item for item in items}
    try:
        for future in as_completed(futures):
            check_cancel()
            handle(futures[future], future)
    except BaseException:
        for future in futures:
            future.cancel()
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)


class ScanEngine:
    def __init__(self, options: ScanOptions, cache_path: str | Path | None = None):
        self.options = options
        self.cache_path = Path(cache_path) if cache_path else default_cache_path()
        self._cache = Cache(self.cache_path)

    def close(self) -> None:
        self._cache.close()

    # ------------------------------------------------------------------ scan
    def scan(
        self,
        progress: ProgressCallback | None = None,
        cancel_event=None,
    ) -> ScanResult:
        progress = progress or (lambda *args: None)
        started = time.monotonic()
        warnings: list[str] = []
        errors: list[str] = []
        stats = ScanStats()

        def check_cancel() -> None:
            if cancel_event is not None and cancel_event.is_set():
                raise ScanCancelled()

        def report(stage: str, done: int, total: int, current: str = "") -> None:
            progress(stage, done, total, current)

        report("Поиск файлов", 0, 0)
        paths = iter_audio_files(self.options.folders, self.options.extensions, warnings)
        stats.scanned = len(paths)
        check_cancel()

        if not paths:
            stats.elapsed = time.monotonic() - started
            stats.warnings = warnings
            self._cache.commit()
            return ScanResult(files=[], groups=[], stats=stats)

        report("Чтение тегов", 0, len(paths))
        files = self._load_files(paths, report, check_cancel, warnings, errors)
        stats.analyzed = len(files)

        check_cancel()
        if len(files) < 2:
            stats.elapsed = time.monotonic() - started
            stats.warnings = warnings
            stats.errors = errors
            self._cache.commit()
            return ScanResult(files=files, groups=[], stats=stats)

        self._compute_hashes(files, report, check_cancel, errors, cancel_event)
        check_cancel()
        sha_buckets = self._sha_buckets(files)

        self._compute_fingerprints(
            files,
            report,
            check_cancel,
            warnings,
            errors,
            cancel_event,
        )
        check_cancel()

        sim_pairs = self._compare_fingerprints(files, report, check_cancel)
        check_cancel()

        report("Группировка", 0, 1)
        groups = build_groups(files, sim_pairs, sha_buckets)
        report("Группировка", 1, 1)

        stats.groups = len(groups)
        stats.duplicate_files = sum(len(group.files) for group in groups)
        stats.exact_groups = sum(1 for group in groups if group.kind == "exact")
        stats.acoustic_groups = sum(1 for group in groups if group.kind != "exact")
        stats.reclaimable = sum(group.reclaimable for group in groups)
        stats.warnings = warnings
        stats.errors = errors
        stats.elapsed = time.monotonic() - started
        self._cache.commit()

        return ScanResult(files=files, groups=groups, stats=stats)

    # --------------------------------------------------------------- loading
    def _load_files(
        self,
        paths: list[str],
        report,
        check_cancel,
        warnings: list[str],
        errors: list[str],
    ) -> list[AudioFile]:
        total = len(paths)
        files: list[AudioFile] = []
        missing: list[str] = []
        done = 0

        for path in paths:
            check_cancel()
            try:
                stat = os.stat(path)
            except OSError as exc:
                _remember(errors, f"{path}: {exc.strerror or exc}")
                done += 1
                continue
            if stat.st_size < 16 * 1024:
                done += 1
                continue
            cached = self._cache.get(path, stat.st_size, stat.st_mtime_ns)
            if cached is not None and cached.quick_hash:
                files.append(cached)
                done += 1
                if done % 200 == 0 or done == total:
                    report("Чтение тегов", done, total, cached.filename)
            else:
                missing.append(path)

        if missing:
            def handle_file(path: str, future) -> None:
                nonlocal done
                done += 1
                try:
                    audio = future.result()
                except Exception as exc:  # noqa: BLE001 - файл может быть любым
                    _remember(errors, f"{path}: {exc}")
                    report("Чтение тегов", done, total, os.path.basename(path))
                    return

                if audio.error:
                    _remember(errors, f"{audio.path}: {audio.error}")
                if audio.quick_hash:
                    files.append(audio)
                    try:
                        self._cache.put(audio)
                    except Exception as exc:  # pragma: no cover
                        _remember(warnings, f"Не удалось записать кэш: {exc}")
                report("Чтение тегов", done, total, audio.filename)

            _run_parallel(
                missing,
                prepare_audio_file,
                handle_file,
                self.options.workers,
                check_cancel,
            )

        self._cache.commit()

        # Слишком короткие треки не могут быть дубликатами песен.
        minimum = self.options.min_duration
        filtered = [
            audio
            for audio in files
            if audio.effective_duration <= 0 or audio.effective_duration >= minimum
        ]
        if len(filtered) < len(files):
            report("Чтение тегов", total, total, "")
        files = sorted(filtered, key=lambda audio: audio.path.lower())
        files = self._drop_short_duplicates(files)
        return files

    @staticmethod
    def _drop_short_duplicates(files: list[AudioFile]) -> list[AudioFile]:
        """Один и тот же путь не должен встречаться дважды (жёсткие ссылки)."""
        by_path: dict[str, AudioFile] = {}
        for audio in files:
            by_path.setdefault(audio.path, audio)
        return list(by_path.values())

    # ---------------------------------------------------------------- hashes
    def _compute_hashes(
        self, files: list[AudioFile], report, check_cancel, errors, cancel_event=None
    ) -> None:
        buckets: dict[tuple[int, str], list[AudioFile]] = {}
        for audio in files:
            buckets.setdefault((audio.size, audio.quick_hash), []).append(audio)

        candidates: list[AudioFile] = []
        for bucket in buckets.values():
            if len(bucket) < 2:
                continue
            if not bucket[0].sha256:
                candidates.append(bucket[0])

        total = len(candidates)
        report("Точные копии", 0, total)
        if not candidates:
            self._assign_hashes(buckets)
            return

        done = 0

        def handle_hash(audio: AudioFile, future) -> None:
            nonlocal done
            done += 1
            try:
                audio.sha256 = future.result()
                self._cache.put(audio)
            except Exception as exc:  # noqa: BLE001
                check_cancel()
                _remember(
                    errors,
                    f"{audio.path}: не удалось прочитать для SHA-256 ({exc})",
                )
            report("Точные копии", done, total, audio.filename)

        _run_parallel(
            candidates,
            lambda audio: sha256_file(audio.path, cancel_event),
            handle_hash,
            self.options.workers,
            check_cancel,
        )

        self._assign_hashes(buckets)
        self._cache.commit()

    def _assign_hashes(self, buckets: dict[tuple[int, str], list[AudioFile]]) -> None:
        """Одинаковые по быстрому хешу файлы получают общий SHA-256."""
        changed = False
        for bucket in buckets.values():
            if len(bucket) < 2:
                continue
            known = next((audio.sha256 for audio in bucket if audio.sha256), "")
            if not known:
                continue
            for audio in bucket:
                if not audio.sha256:
                    audio.sha256 = known
                    self._cache.put(audio)
                    changed = True
        if changed:
            self._cache.commit()

    @staticmethod
    def _sha_buckets(files: list[AudioFile]) -> dict[str, list[AudioFile]]:
        buckets: dict[str, list[AudioFile]] = {}
        for audio in files:
            if audio.sha256:
                buckets.setdefault(audio.sha256, []).append(audio)
        return buckets

    # ----------------------------------------------------------- fingerprints
    def _representatives(self, files: list[AudioFile]) -> list[AudioFile]:
        representatives: list[AudioFile] = []
        seen: set[str] = set()
        for audio in files:
            if audio.sha256:
                if audio.sha256 in seen:
                    continue
                seen.add(audio.sha256)
            representatives.append(audio)
        return representatives

    def _compute_fingerprints(
        self,
        files: list[AudioFile],
        report,
        check_cancel,
        warnings: list[str],
        errors: list[str],
        cancel_event=None,
    ) -> None:
        if not self.options.use_acoustic:
            return

        fpcalc = find_fpcalc()
        if not fpcalc:
            _remember(
                warnings,
                "fpcalc не найден: поиск по звучанию недоступен, "
                "будут найдены только точные копии.",
            )
            return

        representatives = self._representatives(files)
        targets = [audio for audio in representatives if not audio.fingerprint]
        total = len(targets)
        report("Аудиоотпечатки", 0, total)
        if not targets:
            return

        done = 0

        def handle_fingerprint(audio: AudioFile, future) -> None:
            nonlocal done
            done += 1
            try:
                blob, duration = future.result()
                audio.fingerprint = blob
                audio.fp_duration = duration
                if audio.duration <= 0:
                    audio.duration = duration
                self._cache.put(audio)
            except (FingerprintError, OSError) as exc:
                check_cancel()
                _remember(errors, f"{audio.path}: {exc}")
            except Exception as exc:  # noqa: BLE001
                check_cancel()
                _remember(errors, f"{audio.path}: ошибка отпечатка ({exc})")
            report("Аудиоотпечатки", done, total, audio.filename)

        _run_parallel(
            targets,
            lambda audio: compute_fingerprint(
                audio.path,
                self.options.fingerprint_length,
                fpcalc,
                cancel_event,
            ),
            handle_fingerprint,
            self.options.workers,
            check_cancel,
        )

        self._cache.commit()

    # -------------------------------------------------------------- compares
    def _compare_fingerprints(
        self,
        files: list[AudioFile],
        report,
        check_cancel,
    ) -> dict[tuple[str, str], float]:
        representatives = [
            audio for audio in self._representatives(files) if audio.fingerprint
        ]
        if len(representatives) < 2:
            return {}

        representatives.sort(
            key=lambda audio: (
                audio.effective_duration <= 0,
                audio.effective_duration,
                audio.path.lower(),
            )
        )

        threshold = 1.0 - self.options.threshold
        tolerance = self.options.duration_tolerance
        total = len(representatives)
        report("Сравнение отпечатков", 0, total)
        pairs: dict[tuple[str, str], float] = {}

        for index, left in enumerate(representatives):
            check_cancel()
            left_duration = left.effective_duration
            for pair_index, right in enumerate(representatives[index + 1 :]):
                if pair_index % 512 == 0:
                    check_cancel()
                right_duration = right.effective_duration
                if left_duration > 0 and right_duration > 0:
                    delta = right_duration - left_duration
                    if delta > tolerance:
                        break
                    if abs(delta) > tolerance:
                        continue
                try:
                    score = similarity(left.fingerprint, right.fingerprint)
                except ValueError:
                    continue
                if score >= threshold:
                    pairs[(left.path, right.path)] = score
            report("Сравнение отпечатков", index + 1, total, left.filename)

        # Пары в обратном порядке сортировки длительности не теряются:
        # они уже проверены, когда левый элемент был раньше по списку.
        return pairs
