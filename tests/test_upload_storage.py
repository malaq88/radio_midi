"""app.services.upload_storage."""

import zipfile
from pathlib import Path

import pytest

from app.services.upload_storage import (
    looks_like_mp3_header,
    sanitize_path_segment,
    sanitize_relative_mp3_path,
    save_stream_to_file,
    extract_zip_mp3_only,
)


def test_sanitize_path_segment():
    assert sanitize_path_segment("  ok.mp3  ") == "ok.mp3"
    assert sanitize_path_segment("..") is None
    assert sanitize_path_segment("") is None
    assert sanitize_path_segment("weird|name") == "weird_name"


def test_sanitize_relative_mp3_path():
    assert sanitize_relative_mp3_path("a/b.mp3") == "a/b.mp3"
    assert sanitize_relative_mp3_path("../x.mp3") is None
    assert sanitize_relative_mp3_path("a/b.txt") is None


@pytest.mark.parametrize(
    "chunk,expected",
    [
        (b"", False),
        (b"ID3\x00\x00", True),
        (b"\x00" * 100 + b"\xff\xfb\x90\x00", True),
    ],
)
def test_looks_like_mp3_header(chunk: bytes, expected: bool):
    assert looks_like_mp3_header(chunk) is expected


@pytest.mark.asyncio
async def test_save_stream_to_file_ok(tmp_path: Path):
    dest = tmp_path / "out.mp3"
    chunks = [b"ID3\x03\x00\x00\x00\x00\x00\x00\xff\xfb\x90", b"\x00" * 100]

    async def read_chunk():
        return chunks.pop(0) if chunks else b""

    n = await save_stream_to_file(read_chunk, dest, max_bytes=100_000, validate_mp3_header=True)
    assert n > 0 and dest.is_file()


@pytest.mark.asyncio
async def test_save_stream_rejects_bad_header(tmp_path: Path):
    dest = tmp_path / "bad.mp3"

    async def read_chunk():
        return b"NOTMP3" + b"\x00" * 100

    with pytest.raises(ValueError, match="MP3"):
        await save_stream_to_file(read_chunk, dest, max_bytes=1000, validate_mp3_header=True)


@pytest.mark.asyncio
async def test_save_stream_too_large(tmp_path: Path):
    dest = tmp_path / "big.mp3"
    header = b"ID3\x03\x00\x00\x00\x00\x00\x00"

    async def read_chunk():
        return header + b"x" * 500

    with pytest.raises(ValueError, match="limite"):
        await save_stream_to_file(read_chunk, dest, max_bytes=50, validate_mp3_header=True)


@pytest.mark.asyncio
async def test_save_stream_empty(tmp_path: Path):
    dest = tmp_path / "empty.mp3"

    async def read_chunk():
        return b""

    with pytest.raises(ValueError):
        await save_stream_to_file(read_chunk, dest, max_bytes=100, validate_mp3_header=False)


def test_extract_zip_bad_file(tmp_path: Path):
    p = tmp_path / "n.zip"
    p.write_bytes(b"not a zip")
    up, skip = extract_zip_mp3_only(
        p,
        tmp_path / "music",
        overwrite=False,
        max_uncompressed_total=10_000_000,
    )
    assert up == [] and skip and "(zip)" in skip[0][0]


def test_extract_zip_mp3_roundtrip(tmp_path: Path):
    music = tmp_path / "music"
    zpath = tmp_path / "a.zip"
    mp3_body = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" + b"\x00" * 500
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("sub/track.mp3", mp3_body)
    up, skip = extract_zip_mp3_only(
        zpath,
        music,
        overwrite=True,
        max_uncompressed_total=10_000_000,
    )
    assert up == ["sub/track.mp3"] and not skip
    assert (music / "sub" / "track.mp3").is_file()


def test_extract_zip_skips_non_mp3(tmp_path: Path):
    music = tmp_path / "music"
    zpath = tmp_path / "a.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("a.txt", b"hello")
    up, skip = extract_zip_mp3_only(
        zpath,
        music,
        overwrite=True,
        max_uncompressed_total=10_000_000,
    )
    assert up == [] and skip
