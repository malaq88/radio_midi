"""app.services.mp3_organize."""

from pathlib import Path

import pytest

from app.services.mp3_organize import (
    format_track_number,
    sanitize_fs_component,
    read_mp3_metadata,
    organize_mp3_file,
    organize_uploaded_files,
    reorganize_entire_library,
    _cover_extension,
    Mp3Tags,
)
from tests.conftest import write_min_mp3


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, "00"),
        ("3/12", "03"),
        ("10", "10"),
        ("bad", "00"),
        ("12a", "12"),
    ],
)
def test_format_track_number(raw: str | None, expected: str):
    assert format_track_number(raw) == expected


def test_sanitize_fs_component():
    assert sanitize_fs_component("") == "unknown"
    assert ".." not in sanitize_fs_component("a/b")
    assert sanitize_fs_component("  x  ") == "x"


def test_cover_extension():
    assert _cover_extension(b"\x89PNG\r\n\x1a\n", None) == ".png"
    assert _cover_extension(b"\xff\xd8\xff", "image/jpeg") == ".jpg"


def test_read_mp3_metadata_minimal(tmp_path: Path):
    p = tmp_path / "t.mp3"
    write_min_mp3(p)
    tags = read_mp3_metadata(p, title_fallback="FB")
    assert isinstance(tags, Mp3Tags)
    assert tags.title == "FB"
    assert tags.artist  # Unknown Artist default


def test_organize_mp3_file_moves_to_canonical(tmp_path: Path):
    root = tmp_path / "music"
    root.mkdir()
    src = tmp_path / "incoming.mp3"
    write_min_mp3(src)
    rel = organize_mp3_file(src, root, overwrite=True, extract_cover=False, title_fallback="MyTitle")
    assert rel.endswith(".mp3")
    assert (root / rel).is_file()


def test_organize_uploaded_files_missing(patched_settings, tmp_path: Path):
    root = tmp_path / "m"
    root.mkdir()
    out = organize_uploaded_files(["ghost.mp3"], root, overwrite=True, extract_cover=False)
    assert out == ["ghost.mp3"]


def test_reorganize_entire_library(tmp_path: Path):
    root = tmp_path / "m"
    root.mkdir()
    write_min_mp3(root / "deep" / "x.mp3")
    ok, err = reorganize_entire_library(root, overwrite=True, extract_cover=False)
    assert len(ok) >= 1
    assert isinstance(err, list)
