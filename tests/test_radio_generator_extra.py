"""Mais cobertura para app.services.radio_generator (sem FFmpeg real)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.radio_generator import (
    LiveRadioState,
    StreamBroadcaster,
    _configure_logging,
    _duration_seconds,
    _iter_mp3_paths,
    _parse_request_line,
    _run_one_ffmpeg_round,
    handle_http_client,
)


def test_duration_seconds_mutagen_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    p = tmp_path / "a.mp3"
    p.write_bytes(b"x")
    monkeypatch.setattr(
        "mutagen.mp3.MP3",
        MagicMock(side_effect=RuntimeError("bad")),
    )
    assert _duration_seconds(p) == 180.0


def test_duration_seconds_mutagen_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    p = tmp_path / "a.mp3"
    p.write_bytes(b"x")

    class FakeInfo:
        length = 42.5

    class FakeMP3:
        def __init__(self, _path: str) -> None:
            self.info = FakeInfo()

    monkeypatch.setattr("mutagen.mp3.MP3", FakeMP3)
    assert _duration_seconds(p) == 42.5


def test_duration_seconds_mutagen_zero_length(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    p = tmp_path / "a.mp3"
    p.write_bytes(b"x")

    class FakeInfo:
        length = 0.0

    class FakeMP3:
        def __init__(self, _path: str) -> None:
            self.info = FakeInfo()

    monkeypatch.setattr("mutagen.mp3.MP3", FakeMP3)
    assert _duration_seconds(p) == 180.0


def test_iter_mp3_paths_skips_non_mp3(tmp_path: Path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "b.mp3").write_bytes(b"x")
    assert list(_iter_mp3_paths(tmp_path)) == [tmp_path / "b.mp3"]


def test_iter_mp3_paths_skips_symlink_outside_root(tmp_path: Path):
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    real = outside_dir / "s.mp3"
    real.write_bytes(b"x")
    music_root = tmp_path / "music"
    music_root.mkdir()
    link = music_root / "link.mp3"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("symlinks não suportados")
    assert _iter_mp3_paths(music_root) == []


def test_parse_request_line_empty():
    assert _parse_request_line(b"") is None


@pytest.mark.asyncio
async def test_run_one_ffmpeg_no_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.services.radio_generator.shutil.which", lambda _: None)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    concat = tmp_path / "c.txt"
    concat.write_text("ffconcat version 1.0\n")
    st = LiveRadioState()
    rc = await _run_one_ffmpeg_round(concat, StreamBroadcaster(), st)
    assert rc == -1
    assert "ffmpeg" in (st.last_error or "").lower()


@pytest.mark.asyncio
async def test_handle_http_bad_request_line():
    reader = asyncio.StreamReader()
    writer = MagicMock()
    writer.get_extra_info = MagicMock(return_value=None)
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    reader.feed_data(b"\n")
    reader.feed_eof()
    await handle_http_client(reader, writer, StreamBroadcaster(), LiveRadioState())
    assert any(b"400" in c.args[0] for c in writer.write.call_args_list if c.args)


@pytest.mark.asyncio
async def test_handle_http_head():
    reader = asyncio.StreamReader()
    writer = MagicMock()
    writer.get_extra_info = MagicMock(return_value=None)
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    reader.feed_data(b"HEAD /stream HTTP/1.1\r\n\r\n")
    reader.feed_eof()
    await handle_http_client(reader, writer, StreamBroadcaster(), LiveRadioState())
    assert any(b"200 OK" in c.args[0] for c in writer.write.call_args_list if c.args)


@pytest.mark.asyncio
async def test_handle_http_method_not_allowed():
    reader = asyncio.StreamReader()
    writer = MagicMock()
    writer.get_extra_info = MagicMock(return_value=None)
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    reader.feed_data(b"POST /stream HTTP/1.1\r\n\r\n")
    reader.feed_eof()
    await handle_http_client(reader, writer, StreamBroadcaster(), LiveRadioState())
    assert any(b"405" in c.args[0] for c in writer.write.call_args_list if c.args)


@pytest.mark.asyncio
async def test_broadcaster_queue_full_removes_client():
    b = StreamBroadcaster(max_queue=1)
    q = b.subscribe()
    q.put_nowait(b"fill")
    await b.broadcast(b"overflow")
    assert b.subscriber_count() == 0


def test_stream_broadcaster_unsubscribe_unknown_is_safe():
    b = StreamBroadcaster()
    q = b.subscribe()
    b.unsubscribe(q)
    b.unsubscribe(q)


def test_configure_logging_adds_single_handler():
    root = logging.getLogger()
    saved = root.handlers[:]
    root.handlers.clear()
    old_level = root.level
    try:
        _configure_logging()
        assert len(root.handlers) == 1
        _configure_logging()
        assert len(root.handlers) == 1
    finally:
        for h in list(root.handlers):
            root.removeHandler(h)
        root.handlers.extend(saved)
        root.setLevel(old_level)
