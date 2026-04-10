"""Mais ramos de app.services.mp3_organize."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services import mp3_organize as mo
from app.services.mp3_organize import (
    Mp3Tags,
    organize_uploaded_files,
    _first_tag,
    _id3_text,
    format_track_number,
    organize_mp3_file,
    read_mp3_metadata,
    sanitize_fs_component,
)
from tests.conftest import write_min_mp3


@pytest.mark.parametrize(
    "raw,exp",
    [
        ([], None),
        (["x"], "x"),
        (None, None),
    ],
)
def test_first_tag(raw, exp):
    assert _first_tag(raw) == exp


def test_id3_text_none():
    assert _id3_text(None) is None


def test_id3_text_mock_frame():
    frame = MagicMock()
    frame.text = ["  hi  "]
    assert _id3_text(frame) == "hi"


def test_format_track_weird_digits():
    assert format_track_number("ab") == "00"


def test_sanitize_empty_returns_unknown():
    assert sanitize_fs_component("   ") == "unknown"


def test_cover_extension_mime_fallback():
    assert mo._cover_extension(b"\x00\x01", "image/png") == ".png"


def test_write_cover_skips_when_exists_no_overwrite(tmp_path: Path):
    album = tmp_path / "A" / "B"
    album.mkdir(parents=True)
    (album / "cover.jpg").write_bytes(b"\xff\xd8\xff")
    tags = Mp3Tags(
        artist="a",
        album="b",
        title="t",
        track_display="01",
        cover_data=b"\xff\xd8\xff\xe0\x00",
        cover_mime="image/jpeg",
    )
    mo._write_cover(album, tags, overwrite=False)
    assert (album / "cover.jpg").read_bytes() == b"\xff\xd8\xff"


def test_organize_skip_already_canonical(tmp_path: Path):
    root = tmp_path / "m"
    root.mkdir()
    src = tmp_path / "in.mp3"
    write_min_mp3(src)
    rel1 = organize_mp3_file(
        src,
        root,
        overwrite=True,
        extract_cover=False,
        title_fallback="track",
    )
    final = root / rel1
    rel2 = organize_mp3_file(
        final,
        root,
        overwrite=True,
        extract_cover=False,
        title_fallback="track",
        skip_if_already_canonical=True,
    )
    assert rel2 == rel1


def test_unique_file_suffix(tmp_path: Path):
    root = tmp_path / "m"
    album = root / "Unknown Artist" / "Unknown Album"
    album.mkdir(parents=True)
    (album / "00 - dup.mp3").write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x00")

    src = tmp_path / "any.mp3"
    write_min_mp3(src)
    rel = organize_mp3_file(
        src, root, overwrite=False, extract_cover=False, title_fallback="dup"
    )
    assert "dup (1)" in rel


def test_read_mp3_easy_exception(monkeypatch, tmp_path: Path):
    p = tmp_path / "z.mp3"
    write_min_mp3(p)

    def boom(*a, **kw):
        raise RuntimeError("mutagen")

    monkeypatch.setattr(mo, "MutagenFile", boom)
    monkeypatch.setattr(mo, "MP3", boom)
    tags = read_mp3_metadata(p, title_fallback="fb")
    assert tags.title == "fb"


def test_organize_uploaded_files_skips_outside_library(tmp_path: Path):
    root = tmp_path / "m"
    root.mkdir()
    out = organize_uploaded_files(
        ["../outside.mp3"], root, overwrite=True, extract_cover=False
    )
    assert out == ["../outside.mp3"]


def test_organize_uploaded_files_skips_missing(tmp_path: Path):
    root = tmp_path / "m"
    root.mkdir()
    out = organize_uploaded_files(
        ["nope.mp3"], root, overwrite=True, extract_cover=False
    )
    assert out == ["nope.mp3"]


def test_organize_uploaded_files_keeps_rel_on_organize_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "m"
    root.mkdir()
    f = root / "t.mp3"
    write_min_mp3(f)

    def boom(*a, **kw):
        raise RuntimeError("fail organize")

    monkeypatch.setattr(mo, "organize_mp3_file", boom)
    out = organize_uploaded_files(
        ["t.mp3"], root, overwrite=True, extract_cover=False
    )
    assert out == ["t.mp3"]


def test_reorganize_entire_library_error_branch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "m"
    root.mkdir()
    write_min_mp3(root / "bad.mp3")

    def boom(*a, **kw):
        raise OSError("nope")

    monkeypatch.setattr(mo, "organize_mp3_file", boom)
    ok, err = mo.reorganize_entire_library(root, overwrite=True, extract_cover=False)
    assert err and len(ok) == 0
