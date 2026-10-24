from __future__ import annotations

import csv
import sys
from pathlib import Path

from app.core import paths
from app.core.cache import Cache
from app.core.grouping import build_groups
from app.core.models import AudioFile
from app.core.quality import pick_keeper, quality_key
from app.core.report import write_report


def make_audio(path: str, **kwargs) -> AudioFile:
    values = dict(
        path=path,
        size=4_000_000,
        duration=180.0,
        bitrate=320,
        sample_rate=44100,
        channels=2,
        fmt="MP3",
        artist="Artist",
        title="Title",
    )
    values.update(kwargs)
    return AudioFile(**values)


def test_quality_prefers_lossless_flac():
    flac = make_audio("/music/a.flac", fmt="FLAC", bitrate=900, size=30_000_000)
    wav = make_audio("/music/a.wav", fmt="WAV", bitrate=1411, size=50_000_000)
    mp3 = make_audio("/music/a.mp3", bitrate=320, size=8_000_000)
    assert quality_key(flac) > quality_key(wav) > quality_key(mp3)
    assert pick_keeper([mp3, flac, wav]) is flac


def test_quality_prefers_higher_sample_rate():
    cd = make_audio("/music/a.flac", fmt="FLAC", sample_rate=44100, bitrate=900)
    hi = make_audio("/music/b.flac", fmt="FLAC", sample_rate=96000, bitrate=2300)
    assert quality_key(hi) > quality_key(cd)


def test_quality_recognizes_alac_inside_m4a():
    alac = make_audio(
        "/music/a.m4a",
        fmt="M4A",
        codec="alac",
        sample_rate=44100,
        bits_per_sample=16,
        bitrate=900,
        size=40_000_000,
    )
    mp3 = make_audio(
        "/music/a.mp3", fmt="MP3", codec="", sample_rate=44100, bitrate=320
    )
    assert alac.is_lossless
    assert not mp3.is_lossless
    assert quality_key(alac) > quality_key(mp3)


def test_quality_prefers_compact_lossless_over_uncompressed():
    flac = make_audio(
        "/music/a.flac", fmt="FLAC", sample_rate=44100, bits_per_sample=16,
        size=30_000_000,
    )
    alac = make_audio(
        "/music/a.m4a", fmt="M4A", codec="alac", sample_rate=44100,
        bits_per_sample=16, size=40_000_000,
    )
    assert quality_key(flac) > quality_key(alac)


def test_grouping_exact_and_acoustic():
    first = make_audio("/music/first.flac", sha256="abc", match_type="exact")
    copy = make_audio("/music/copy.flac", sha256="abc", match_type="exact")
    other = make_audio("/music/other.mp3", sha256="", match_type="acoustic")
    groups = build_groups(
        [first, copy, other],
        {("/music/first.flac", "/music/other.mp3"): 0.96},
        {"abc": [first, copy]},
    )
    assert len(groups) == 1
    group = groups[0]
    assert group.kind == "mixed"
    assert len(group.files) == 3
    assert copy.match_type == "exact"
    assert other.match_type == "acoustic"
    assert other.similarity == 0.96
    assert group.keeper is not None
    assert sum(file.is_keeper for file in group.files) == 1


def test_grouping_rejects_unrelated_files():
    first = make_audio("/music/a.mp3")
    second = make_audio("/music/b.mp3")
    assert build_groups([first, second], {}, {}) == []


def test_grouping_exact_only():
    first = make_audio("/music/a.mp3", sha256="xyz")
    copy = make_audio("/music/b.mp3", sha256="xyz")
    groups = build_groups([first, copy], {}, {"xyz": [first, copy]})
    assert len(groups) == 1
    assert groups[0].kind == "exact"
    assert groups[0].similarity == 1.0


def test_frozen_app_keeps_data_next_to_executable(tmp_path: Path, monkeypatch):
    executable = tmp_path / "DoubleSound.exe"
    executable.touch()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    assert paths.data_dir() == tmp_path / "data"
    assert paths.default_cache_path() == tmp_path / "data" / "fingerprints.sqlite3"
    assert paths.settings_path() == tmp_path / "data" / "settings.ini"


def test_cache_roundtrip(tmp_path: Path):
    path = str(tmp_path / "song.mp3")
    cache_path = tmp_path / "cache.sqlite3"
    audio = make_audio(path, quick_hash="q", sha256="s", fingerprint=b"\x01\x00\x00\x00")
    audio.fp_duration = 12.5
    with Cache(cache_path) as cache:
        cache.put(audio)
        cache.commit()
        loaded = cache.get(path, audio.size, audio.mtime_ns)
        assert loaded is not None
        assert loaded.title == "Title"
        assert loaded.sha256 == "s"
        assert loaded.fingerprint == b"\x01\x00\x00\x00"
        assert loaded.fp_duration == 12.5

        assert cache.get(path, audio.size, 1) is None
        cache.delete([path])
        assert cache.get(path, audio.size, audio.mtime_ns) is None


def test_report_csv(tmp_path: Path):
    first = make_audio("/music/a.flac", sha256="abc")
    copy = make_audio("/music/b.mp3", sha256="abc")
    groups = build_groups([first, copy], {}, {"abc": [first, copy]})
    marked = {copy.path}
    destination = write_report(tmp_path / "report.csv", groups, marked)
    assert destination.exists()
    with destination.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=";"))
    assert rows[0][0] == "Группа"
    assert len(rows) == 3
    keeper_rows = [row for row in rows[1:] if row[3] == "да"]
    marked_rows = [row for row in rows[1:] if row[4] == "да"]
    assert len(keeper_rows) == 1
    assert marked_rows[0][13] == copy.path
