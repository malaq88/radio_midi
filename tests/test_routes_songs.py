"""GET /songs."""

from fastapi.testclient import TestClient


def test_songs_empty_shows_extensions(client_with_flac_only: TestClient):
    r = client_with_flac_only.get("/songs")
    assert r.status_code == 200
    data = r.json()
    assert data["total_songs"] == 0
    assert "file_extensions_in_library" in data


def test_songs_populated(client_populated: TestClient):
    r = client_populated.get("/songs")
    assert r.status_code == 200
    data = r.json()
    assert data["total_songs"] >= 2
    assert any(p["name"] == "root" for p in data["playlists_by_folder"])
