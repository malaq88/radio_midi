"""app.services.library."""

from pathlib import Path
from unittest.mock import patch

import pytest

from tests.conftest import write_min_mp3


def test_playlist_group_for_file_via_scan(patched_settings, tmp_path: Path):
    write_min_mp3(tmp_path / "solo.mp3")
    write_min_mp3(tmp_path / "rock" / "a.mp3")
    from app.services.library import MusicLibrary

    lib = MusicLibrary()
    lib.scan()
    groups = {s.playlist_group for s in lib.songs}
    assert "root" in groups and "rock" in groups


def test_scan_empty_music_dir(patched_settings, tmp_path: Path):
    from app.services.library import MusicLibrary

    lib = MusicLibrary()
    lib.scan()
    assert lib.songs == []


def test_scan_music_dir_is_file_not_folder(monkeypatch, tmp_path: Path):
    import importlib

    from tests.conftest import MODULES_WITH_SETTINGS

    bogus = tmp_path / "not_a_dir"
    bogus.write_bytes(b"x")
    monkeypatch.setenv("MUSIC_DIR", str(bogus))
    from app.config import Settings

    s = Settings()
    for mod_name in MODULES_WITH_SETTINGS:
        mod = importlib.import_module(mod_name)
        monkeypatch.setattr(mod, "settings", s, raising=False)
    from app.services.library import MusicLibrary

    lib = MusicLibrary()
    lib.scan()
    assert lib.songs == []


def test_count_file_extensions_under(tmp_path: Path):
    from app.services.library import count_file_extensions_under

    (tmp_path / "a.mp3").write_text("x")
    (tmp_path / "b.flac").write_text("x")
    d = count_file_extensions_under(tmp_path)
    assert d[".mp3"] == 1 and d[".flac"] == 1


def test_count_file_extensions_not_dir():
    from app.services.library import count_file_extensions_under

    assert count_file_extensions_under(Path("/nonexistent_xyz_123")) == {}


def test_resolve_device_playlist_mapped_and_fallback(patched_settings, tmp_path: Path, monkeypatch):
    write_min_mp3(tmp_path / "rock" / "r.mp3")
    write_min_mp3(tmp_path / "other.mp3")
    from app import config as cfg
    from app.services.library import MusicLibrary

    monkeypatch.setitem(cfg.DEVICE_PLAYLIST_MAP, "d1", "rock")
    lib = MusicLibrary()
    lib.scan()
    assert len(lib.resolve_device_playlist("d1")) == 1
    assert len(lib.resolve_device_playlist("unmapped")) == 2
    monkeypatch.setitem(cfg.DEVICE_PLAYLIST_MAP, "d_empty", "ghost_folder")
    assert len(lib.resolve_device_playlist("d_empty")) == 2


def test_get_all_songs_and_playlist_names(patched_settings, tmp_path: Path):
    write_min_mp3(tmp_path / "a.mp3")
    from app.services.library import MusicLibrary

    lib = MusicLibrary()
    lib.scan()
    assert len(lib.get_all_songs()) == 1
    assert "root" in lib.playlist_names()
    assert len(lib.songs_in_playlist("root")) == 1


@patch("app.services.library.MutagenFile", side_effect=RuntimeError("bad"))
def test_read_id3_tags_swallows(_mock_mutagen, patched_settings, tmp_path: Path):
    write_min_mp3(tmp_path / "x.mp3")
    from app.services.library import MusicLibrary

    lib = MusicLibrary()
    lib.scan()
    assert len(lib.songs) == 1
    assert lib.songs[0].title is None
