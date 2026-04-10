"""GET /artists, /albums, /library/cover."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_artists_empty(client: TestClient):
    r = client.get("/artists")
    assert r.json()["total_artists"] == 0


def test_artists_populated(client_populated: TestClient):
    r = client_populated.get("/artists")
    assert r.status_code == 200
    assert "ArtistZ" in r.json()["artists"]


def test_albums_404(client_populated: TestClient):
    r = client_populated.get("/albums/NoOne")
    assert r.status_code == 404


def test_albums_ok(client_populated: TestClient):
    r = client_populated.get("/albums/ArtistZ")
    assert r.status_code == 200
    assert "Album1" in r.json()["albums"]


def test_cover_bad_params(client_populated: TestClient):
    r = client_populated.get("/library/cover/../x/y")
    assert r.status_code == 404


def test_cover_missing_album(client_populated: TestClient):
    r = client_populated.get("/library/cover/ArtistZ/GhostAlbum")
    assert r.status_code == 404


def test_cover_serves_jpg(client_populated: TestClient, tmp_path: Path):
    album = tmp_path / "ArtistZ" / "Album1"
    album.mkdir(parents=True, exist_ok=True)
    (album / "cover.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 200)
    r = client_populated.get("/library/cover/ArtistZ/Album1")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/")
