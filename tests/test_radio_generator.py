"""app.services.radio_generator — funções puras e HTTP handler."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.radio_generator import (
    LiveRadioState,
    StreamBroadcaster,
    _escape_concat_path,
    _parse_request_line,
    _shuffle_avoid_adjacent_repeat,
    _write_ffconcat,
    handle_http_client,
)


def test_escape_concat_path():
    p = Path("/tmp/foo'bar.mp3")
    assert "'" in _escape_concat_path(p)


def test_shuffle_avoid_adjacent_repeat():
    paths = [Path("/a/1.mp3"), Path("/a/2.mp3")]
    out = _shuffle_avoid_adjacent_repeat(paths, None)
    assert set(out) == set(paths)


def test_shuffle_single():
    one = [Path("/a.mp3")]
    assert _shuffle_avoid_adjacent_repeat(one, Path("/a.mp3")) == one


def test_write_ffconcat(tmp_path: Path):
    a = tmp_path / "a.mp3"
    b = tmp_path / "b.mp3"
    a.write_bytes(b"x")
    b.write_bytes(b"x")
    dest = tmp_path / "list.txt"
    _write_ffconcat([a, b], dest)
    text = dest.read_text()
    assert "ffconcat" in text and "a.mp3" in text


def test_parse_request_line():
    assert _parse_request_line(b"GET /stream HTTP/1.1\r\n") == ("GET", "/stream")
    assert _parse_request_line(b"bad") is None


def test_live_radio_state_estimate():
    st = LiveRadioState()
    st.playlist_paths = ["/a.mp3"]
    st.durations_sec = [10.0]
    st.round_started_at = __import__("time").monotonic()
    d = st.to_public_dict()
    assert d["ok"] is True
    assert st._estimate_now_playing(5.0) is not None
    assert st._estimate_now_playing(-1) is None


@pytest.mark.asyncio
async def test_stream_broadcaster():
    b = StreamBroadcaster(max_queue=8)
    q = b.subscribe()
    await b.broadcast(b"abc")
    assert await q.get() == b"abc"
    b.unsubscribe(q)
    assert b.subscriber_count() == 0


@pytest.mark.asyncio
async def test_handle_http_status():
    broadcaster = StreamBroadcaster()
    state = LiveRadioState()
    reader = asyncio.StreamReader()
    writer = MagicMock()
    writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 9))
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()

    req = b"GET /status HTTP/1.1\r\nHost: x\r\n\r\n"
    reader.feed_data(req)
    reader.feed_eof()

    await handle_http_client(reader, writer, broadcaster, state)
    blobs = [c.args[0] for c in writer.write.call_args_list if c.args]
    written = b"".join(blobs)
    assert b"200 OK" in written
    body = written.split(b"\r\n\r\n", 1)[1]
    assert json.loads(body.decode())["ok"] is True


@pytest.mark.asyncio
async def test_handle_http_404_path():
    broadcaster = StreamBroadcaster()
    state = LiveRadioState()
    reader = asyncio.StreamReader()
    writer = MagicMock()
    writer.get_extra_info = MagicMock(return_value=None)
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    reader.feed_data(b"GET /nope HTTP/1.1\r\n\r\n")
    reader.feed_eof()
    await handle_http_client(reader, writer, broadcaster, state)
    assert any(b"404" in c.args[0] for c in writer.write.call_args_list if c.args)
