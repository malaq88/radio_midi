"""app.services.stream."""

import asyncio
from pathlib import Path

import pytest

from app.models.song import Song
from app.services import stream as stream_mod
from app.services.stream import (
    PlaylistStreamMode,
    _emit_coalesce_chunks,
    _get_transition_gap_bytes,
    _read_file_in_chunks,
    stream_playlist_forever,
)
from tests.conftest import write_min_mp3


@pytest.fixture(autouse=True)
def reset_transition_gap():
    stream_mod._gap_loaded = False
    stream_mod._gap_payload = b""
    yield
    stream_mod._gap_loaded = False
    stream_mod._gap_payload = b""


@pytest.mark.asyncio
async def test_emit_coalesce_chunks():
    q: asyncio.Queue[bytes] = asyncio.Queue()
    coalesce = bytearray(b"abcdefghijklmnop")
    await _emit_coalesce_chunks(coalesce, emit_size=4, queue=q)
    out = []
    while not q.empty():
        out.append(await q.get())
    assert out == [b"abcd", b"efgh", b"ijkl", b"mnop"]
    assert coalesce == b""


@pytest.mark.asyncio
async def test_read_file_in_chunks(tmp_path: Path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc" * 50)
    chunks = []
    async for c in _read_file_in_chunks(p, chunk_size=10):
        chunks.append(c)
    assert b"".join(chunks) == p.read_bytes()


def test_get_transition_gap_none_when_unset(monkeypatch, patched_settings):
    monkeypatch.setattr(patched_settings, "stream_transition_gap_file", None)
    import app.services.stream as sm

    sm._gap_loaded = False
    sm._gap_payload = b""
    monkeypatch.setattr(sm, "settings", patched_settings)
    assert _get_transition_gap_bytes() == b""


def test_get_transition_gap_loads_file(monkeypatch, patched_settings, tmp_path: Path):
    gap = tmp_path / "gap.mp3"
    gap.write_bytes(b"ID3pad")
    monkeypatch.setattr(patched_settings, "stream_transition_gap_file", gap)
    import app.services.stream as sm

    sm._gap_loaded = False
    sm._gap_payload = b""
    monkeypatch.setattr(sm, "settings", patched_settings)
    assert len(_get_transition_gap_bytes()) > 0


@pytest.mark.asyncio
async def test_stream_playlist_ordered_yields_bytes(patched_settings, tmp_path: Path):
    write_min_mp3(tmp_path / "01 - a.mp3")
    write_min_mp3(tmp_path / "02 - b.mp3")
    from app.services.library import MusicLibrary

    lib = MusicLibrary()
    lib.scan()
    songs = lib.get_all_songs()
    agen = stream_playlist_forever(
        songs,
        label="unit",
        mode=PlaylistStreamMode.ORDERED_LOOP,
        chunk_size=256,
    )
    total = 0
    for _ in range(5):
        chunk = await agen.__anext__()
        total += len(chunk)
    await agen.aclose()
    assert total > 0


@pytest.mark.asyncio
async def test_stream_playlist_shuffle_mode(patched_settings, tmp_path: Path):
    write_min_mp3(tmp_path / "a.mp3")
    from app.services.library import MusicLibrary

    lib = MusicLibrary()
    lib.scan()
    agen = stream_playlist_forever(
        lib.get_all_songs(),
        label="sh",
        mode=PlaylistStreamMode.SHUFFLE,
        chunk_size=128,
    )
    c = await agen.__anext__()
    assert len(c) > 0
    await agen.aclose()


@pytest.mark.asyncio
async def test_stream_empty_candidates(patched_settings, tmp_path: Path):
    agen = stream_playlist_forever([], label="empty", mode=PlaylistStreamMode.SHUFFLE)
    with pytest.raises(StopAsyncIteration):
        await agen.__anext__()
