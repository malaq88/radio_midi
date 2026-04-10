"""Cobertura de radio_loop, pump/drain HTTP e estado da rádio live."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.radio_generator import (
    LiveRadioState,
    StreamBroadcaster,
    _drain_stderr,
    _pump_ffmpeg,
    _shuffle_avoid_adjacent_repeat,
    handle_http_client,
    radio_loop,
)
from tests.conftest import write_min_mp3

_REAL_ASYNCIO_SLEEP = asyncio.sleep


def test_shuffle_swap_when_first_equals_last(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def no_shuffle(_: list) -> None:
        return None

    monkeypatch.setattr("app.services.radio_generator.random.shuffle", no_shuffle)
    a = tmp_path / "a.mp3"
    b = tmp_path / "b.mp3"
    a.write_bytes(b"x")
    b.write_bytes(b"y")
    out = _shuffle_avoid_adjacent_repeat([a, b], a)
    assert out[0] == b and out[1] == a


def test_live_radio_now_playing_negative_elapsed():
    st = LiveRadioState()
    st.playlist_paths = ["/x.mp3"]
    st.durations_sec = [10.0]
    assert st._estimate_now_playing(-1.0) is None


def test_live_radio_now_playing_past_end_of_playlist():
    st = LiveRadioState()
    st.playlist_paths = ["/a.mp3", "/b.mp3"]
    st.durations_sec = [1.0, 2.0]
    cur = st._estimate_now_playing(999.0)
    assert cur is not None
    assert cur["index"] == 1
    assert "b" in cur["path"]


async def _sleep_zero(_t: float = 0) -> None:
    await _REAL_ASYNCIO_SLEEP(0)


@pytest.mark.asyncio
async def test_radio_loop_no_mp3_sets_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    import app.services.radio_generator as rg

    monkeypatch.setattr(rg.asyncio, "sleep", _sleep_zero)
    state = LiveRadioState()
    b = StreamBroadcaster()
    task = asyncio.create_task(radio_loop(tmp_path, b, state))
    await asyncio.sleep(0.05)
    assert state.last_error and "Sem ficheiros" in state.last_error
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_radio_loop_one_mp3_runs_ffmpeg_round(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    import app.services.radio_generator as rg

    write_min_mp3(tmp_path / "one.mp3")
    monkeypatch.setattr(rg, "_run_one_ffmpeg_round", AsyncMock(return_value=0))
    monkeypatch.setattr(rg.asyncio, "sleep", _sleep_zero)
    state = LiveRadioState()
    b = StreamBroadcaster()
    task = asyncio.create_task(radio_loop(tmp_path, b, state))
    await asyncio.sleep(0.08)
    assert state.playlist_paths
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_radio_loop_inner_exception(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    import app.services.radio_generator as rg

    def boom(_: Path) -> list:
        raise RuntimeError("scan fail")

    monkeypatch.setattr(rg, "_iter_mp3_paths", boom)
    monkeypatch.setattr(rg.asyncio, "sleep", _sleep_zero)
    state = LiveRadioState()
    b = StreamBroadcaster()
    task = asyncio.create_task(radio_loop(tmp_path, b, state))
    await asyncio.sleep(0.05)
    assert state.last_error == "scan fail"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_pump_ffmpeg_counts_bytes():
    proc = MagicMock()
    proc.stdout = asyncio.StreamReader()
    proc.stdout.feed_data(b"abc")
    proc.stdout.feed_eof()
    b = StreamBroadcaster()
    st = LiveRadioState()
    await _pump_ffmpeg(proc, b, st)
    assert st.bytes_broadcast == 3


@pytest.mark.asyncio
async def test_pump_ffmpeg_records_error(monkeypatch: pytest.MonkeyPatch):
    proc = MagicMock()
    proc.stdout = MagicMock()
    proc.stdout.read = AsyncMock(side_effect=RuntimeError("read fail"))
    b = StreamBroadcaster()
    st = LiveRadioState()
    await _pump_ffmpeg(proc, b, st)
    assert "read fail" in (st.last_error or "")


@pytest.mark.asyncio
async def test_drain_stderr_sets_error_on_invalid_keyword():
    proc = MagicMock()
    proc.stderr = asyncio.StreamReader()
    proc.stderr.feed_data(b"Input #0, invalid data\n")
    proc.stderr.feed_eof()
    st = LiveRadioState()
    await _drain_stderr(proc, st)
    assert st.last_error and "invalid" in st.last_error.lower()


@pytest.mark.asyncio
async def test_handle_http_status_json():
    reader = asyncio.StreamReader()
    writer = MagicMock()
    writer.get_extra_info = MagicMock(return_value=None)
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    reader.feed_data(b"GET /status HTTP/1.1\r\n\r\n")
    reader.feed_eof()
    st = LiveRadioState()
    await handle_http_client(reader, writer, StreamBroadcaster(), st)
    assert any(b"application/json" in c.args[0] for c in writer.write.call_args_list if c.args)


@pytest.mark.asyncio
async def test_handle_http_404_path():
    reader = asyncio.StreamReader()
    writer = MagicMock()
    writer.get_extra_info = MagicMock(return_value=None)
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    reader.feed_data(b"GET /nope HTTP/1.1\r\n\r\n")
    reader.feed_eof()
    await handle_http_client(reader, writer, StreamBroadcaster(), LiveRadioState())
    assert any(b"404" in c.args[0] for c in writer.write.call_args_list if c.args)


@pytest.mark.asyncio
async def test_handle_http_get_stream_end_signal():
    reader = asyncio.StreamReader()
    writer = MagicMock()
    writer.get_extra_info = MagicMock(return_value=None)
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()
    reader.feed_data(b"GET /stream HTTP/1.1\r\n\r\n")
    reader.feed_eof()
    b = StreamBroadcaster()
    st = LiveRadioState()

    async def end_stream() -> None:
        await asyncio.sleep(0.02)
        for q in list(b._queues):
            await q.put(None)

    asyncio.create_task(end_stream())
    await handle_http_client(reader, writer, b, st)
    assert st.connected_clients == 0
