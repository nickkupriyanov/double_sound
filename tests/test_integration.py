from __future__ import annotations

import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

import pytest

from app.core.engine import ScanEngine
from app.core.fingerprint import find_fpcalc, similarity
from app.core.models import ScanOptions

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or find_fpcalc() is None,
    reason="нужны ffmpeg и fpcalc",
)


def _write_song(path: Path, seed: int, seconds: int = 12) -> None:
    rate = 22050
    notes = [220, 247, 262, 294, 330, 349, 392, 440, 494, 523]
    state = seed
    sequence = []
    for _ in range(seconds * 4):
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        sequence.append(notes[state % len(notes)])

    step = rate // 4
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        for base in sequence:
            for n in range(step):
                t = n / rate
                envelope = min(1.0, n / 500) * min(1.0, (step - n) / 800)
                value = (
                    0.28 * math.sin(2 * math.pi * base * t)
                    + 0.12 * math.sin(2 * math.pi * base * 2 * t)
                    + 0.05 * math.sin(2 * math.pi * base * 3 * t)
                )
                frames += struct.pack("<h", int(value * envelope * 32767))
        handle.writeframes(bytes(frames))


def _encode(source: Path, destination: Path, *args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), *args, str(destination)],
        check=True,
    )


def test_same_song_different_formats_has_high_similarity(tmp_path: Path):
    source = tmp_path / "song.wav"
    _write_song(source, seed=7)
    _encode(source, tmp_path / "song.flac")
    _encode(source, tmp_path / "song.mp3", "-codec:a", "libmp3lame", "-b:a", "128k")

    from app.core.fingerprint import compute_fingerprint

    wav_blob, _ = compute_fingerprint(str(source), 60)
    flac_blob, _ = compute_fingerprint(str(tmp_path / "song.flac"), 60)
    mp3_blob, _ = compute_fingerprint(str(tmp_path / "song.mp3"), 60)
    assert similarity(wav_blob, flac_blob) > 0.9
    assert similarity(wav_blob, mp3_blob) > 0.9


def test_fingerprint_can_read_file_from_stdin(tmp_path: Path, monkeypatch):
    import app.core.fingerprint as fingerprint

    source = tmp_path / "song.wav"
    _write_song(source, seed=11)
    flac = tmp_path / "Песня.flac"
    _encode(source, flac)

    normal, _ = fingerprint.compute_fingerprint(str(flac), 60)
    monkeypatch.setattr(fingerprint, "_needs_stdin", lambda _argument: True)
    streamed, _ = fingerprint.compute_fingerprint(str(flac), 60)
    assert similarity(normal, streamed) > 0.99


def test_different_songs_have_low_similarity(tmp_path: Path):
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    _write_song(first, seed=1)
    _write_song(second, seed=99)

    from app.core.fingerprint import compute_fingerprint

    first_blob, _ = compute_fingerprint(str(first), 60)
    second_blob, _ = compute_fingerprint(str(second), 60)
    assert similarity(first_blob, second_blob) < 0.8


def test_engine_finds_groups_and_exact_copies(tmp_path: Path):
    music = tmp_path / "music"
    music.mkdir()
    source = music / "song_a.wav"
    _write_song(source, seed=3)
    _encode(source, music / "song_a.flac")
    _encode(source, music / "song_a.mp3", "-codec:a", "libmp3lame", "-b:a", "192k")
    shutil.copy2(music / "song_a.mp3", music / "song_a_copy.mp3")

    other = music / "song_b.wav"
    _write_song(other, seed=42)

    options = ScanOptions(
        folders=[str(music)],
        min_duration=5,
        fingerprint_length=60,
        workers=2,
    )
    engine = ScanEngine(options, tmp_path / "cache.sqlite3")
    try:
        result = engine.scan()
    finally:
        engine.close()

    assert result.stats.scanned == 5
    assert len(result.groups) == 1
    group = result.groups[0]
    assert len(group.files) == 4
    exact = [file for file in group.files if file.match_type == "exact"]
    assert len(exact) == 2
    assert group.keeper is not None
    assert group.keeper.format_label in {"WAV", "FLAC"}
    assert result.stats.reclaimable > 0
