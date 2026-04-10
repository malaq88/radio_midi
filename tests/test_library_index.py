"""app.services.library_index."""

from pathlib import Path

import pytest

from app.models.song import Song
from app.services.library_index import (
    LibraryIndexes,
    folder_segments_for_path,
    sort_songs_by_track_filename,
)


def test_folder_segments_three_levels(tmp_path: Path):
    root = tmp_path
    f = root / "Art" / "Alb" / "t.mp3"
    f.parent.mkdir(parents=True)
    f.touch()
    assert folder_segments_for_path(root, f) == ("Art", "Alb")


def test_folder_segments_two_levels(tmp_path: Path):
    root = tmp_path
    f = root / "Art" / "t.mp3"
    f.parent.mkdir(parents=True)
    f.touch()
    assert folder_segments_for_path(root, f) == ("Art", "_singles")


def test_folder_segments_root_file(tmp_path: Path):
    root = tmp_path
    f = root / "t.mp3"
    f.touch()
    assert folder_segments_for_path(root, f) == ("root", "root")


def test_folder_segments_outside(tmp_path: Path):
    root = tmp_path
    other = tmp_path.parent / "other.mp3"
    assert folder_segments_for_path(root, other) == ("root", "root")


def test_sort_songs_by_track_filename():
    s1 = Song(
        path=Path("/a/10 - z.mp3"),
        filename="10 - z.mp3",
        playlist_group="x",
    )
    s2 = Song(
        path=Path("/a/2 - a.mp3"),
        filename="2 - a.mp3",
        playlist_group="x",
    )
    s3 = Song(
        path=Path("/a/no.mp3"),
        filename="no.mp3",
        playlist_group="x",
    )
    out = sort_songs_by_track_filename([s3, s1, s2])
    assert [x.filename for x in out] == ["2 - a.mp3", "10 - z.mp3", "no.mp3"]


def test_library_indexes_rebuild_and_queries():
    root = Path("/m")
    songs = [
        Song(
            path=root / "A" / "B" / "01 - x.mp3",
            filename="01 - x.mp3",
            playlist_group="A",
            folder_artist="A",
            folder_album="B",
        ),
        Song(
            path=root / "A" / "B" / "02 - y.mp3",
            filename="02 - y.mp3",
            playlist_group="A",
            folder_artist="A",
            folder_album="B",
        ),
    ]
    idx = LibraryIndexes()
    idx.rebuild(songs)
    assert idx.list_artists() == ["A"]
    assert idx.canonical_artist("a") == "A"
    assert idx.canonical_artist("unknown") is None
    assert idx.list_albums_for_artist("A") == ["B"]
    assert idx.list_albums_for_artist("Z") is None
    pool = idx.songs_for_artist("A")
    assert pool is not None and len(pool) == 2
    assert idx.songs_for_album("A", "B") is not None
    assert idx.songs_for_album("A", "Z") is None
    assert idx.canonical_album_key("a", "b") == ("A", "B")
    assert idx.songs_under_top_folder("A") == pool
