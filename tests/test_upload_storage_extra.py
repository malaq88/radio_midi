"""Ramos extra de app.services.upload_storage."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from app.services.upload_storage import (
    extract_zip_mp3_only,
    looks_like_mp3_header,
    sanitize_path_segment,
    sanitize_relative_mp3_path,
    save_stream_to_file,
)


def test_sanitize_segment_truncates_long_name():
    long = "a" * 200 + ".mp3"
    s = sanitize_path_segment(long)
    assert s is not None
    assert len(s) <= 120


def test_sanitize_relative_too_many_parts():
    parts = "/".join([f"p{i}" for i in range(40)]) + "/t.mp3"
    assert sanitize_relative_mp3_path(parts) is None


def test_looks_like_mp3_header_short():
    assert looks_like_mp3_header(b"") is False
    assert looks_like_mp3_header(b"x") is False


@pytest.mark.asyncio
async def test_save_stream_empty_raises(tmp_path: Path):
    async def empty():
        return b""

    dest = tmp_path / "out.mp3"
    with pytest.raises(ValueError, match="vazio"):
        await save_stream_to_file(empty, dest, max_bytes=10000, validate_mp3_header=False)


@pytest.mark.asyncio
async def test_save_stream_oversize(tmp_path: Path):
    body = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff" * 100

    async def big():
        return body

    dest = tmp_path / "big.mp3"
    with pytest.raises(ValueError, match="limite"):
        await save_stream_to_file(big, dest, max_bytes=50, validate_mp3_header=True)


def test_extract_zip_bad_file(tmp_path: Path):
    p = tmp_path / "not.zip"
    p.write_bytes(b"not a zip at all")
    up, skip = extract_zip_mp3_only(
        p, tmp_path / "m", overwrite=True, max_uncompressed_total=10_000_000
    )
    assert up == [] and skip


def test_extract_zip_skips_bad_path(tmp_path: Path):
    root = tmp_path / "m"
    root.mkdir()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../etc/passwd.mp3", b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff" * 200)
    zpath = tmp_path / "x.zip"
    zpath.write_bytes(buf.getvalue())
    up, skip = extract_zip_mp3_only(
        zpath, root, overwrite=True, max_uncompressed_total=10_000_000
    )
    assert not up
    assert any("inválido" in msg or "traversal" in msg.lower() for _, msg in skip)


def test_extract_zip_skips_non_mp3_header(tmp_path: Path):
    root = tmp_path / "m"
    root.mkdir()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a/b.mp3", b"plain text not mp3 " * 400)
    zpath = tmp_path / "x.zip"
    zpath.write_bytes(buf.getvalue())
    up, skip = extract_zip_mp3_only(
        zpath, root, overwrite=True, max_uncompressed_total=10_000_000
    )
    assert not up
    assert skip
