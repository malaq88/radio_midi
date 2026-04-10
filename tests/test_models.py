"""Modelos Pydantic."""

from pathlib import Path

import pytest

from app.models.song import PlaylistInfo, Song, SongPublic
from app.models.upload import SkippedItem, UploadResult


def test_song_frozen():
    s = Song(
        path=Path("/tmp/x.mp3"),
        filename="x.mp3",
        playlist_group="root",
    )
    with pytest.raises(Exception):
        s.filename = "y.mp3"  # type: ignore[misc]


def test_song_public_dump():
    m = SongPublic(
        filename="a.mp3",
        playlist_group="rock",
        relative_path="rock/a.mp3",
    )
    d = m.model_dump()
    assert d["relative_path"] == "rock/a.mp3"


def test_playlist_info():
    p = PlaylistInfo(name="rock", song_count=3)
    assert p.model_dump()["song_count"] == 3


def test_upload_result():
    u = UploadResult(success=True, message="ok", files=["a/b.mp3"])
    assert u.skipped == []
    s = SkippedItem(path="x", reason="bad")
    assert s.reason == "bad"
