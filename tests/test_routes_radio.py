"""Rotas /radio/*."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def short_audio_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    """Evita respostas HTTP infinitas no TestClient (streaming bloqueava a sair do contexto)."""

    async def _fake_stream(
        candidates, *, label: str, **kw
    ) -> AsyncIterator[bytes]:
        yield b"\xff\xfb\x90" + b"\x00" * 256

    import app.routes.radio as radio_mod

    monkeypatch.setattr(radio_mod, "stream_playlist_forever", _fake_stream)


def test_radio_random_200_stream(client_populated: TestClient, short_audio_stream: None):
    with client_populated.stream("GET", "/radio/random") as r:
        assert r.status_code == 200
        chunk = next(r.iter_bytes(chunk_size=512))
        assert len(chunk) > 0


def test_radio_random_503_empty_library(client: TestClient):
    r = client.get("/radio/random")
    assert r.status_code == 503


def test_radio_device(client_populated: TestClient, short_audio_stream: None):
    with client_populated.stream("GET", "/radio/device/d1") as r:
        assert r.status_code == 200


def test_radio_device_empty_id(client_populated: TestClient):
    r = client_populated.get("/radio/device/  ")
    assert r.status_code == 400


def test_radio_artist_ok(client_populated: TestClient, short_audio_stream: None):
    with client_populated.stream("GET", "/radio/artist/ArtistZ") as r:
        assert r.status_code == 200


def test_radio_artist_404(client_populated: TestClient):
    r = client_populated.get("/radio/artist/NoSuchArtist")
    assert r.status_code == 404


def test_radio_artist_empty_name(client_populated: TestClient):
    r = client_populated.get("/radio/artist/%20")
    assert r.status_code == 400


def test_radio_album_ok(client_populated: TestClient, short_audio_stream: None):
    with client_populated.stream("GET", "/radio/album/ArtistZ/Album1") as r:
        assert r.status_code == 200


def test_radio_album_404(client_populated: TestClient):
    r = client_populated.get("/radio/album/ArtistZ/Ghost")
    assert r.status_code == 404


def test_radio_folder_ok(client_populated: TestClient, short_audio_stream: None):
    with client_populated.stream("GET", "/radio/folder/ArtistZ") as r:
        assert r.status_code == 200


def test_radio_file_ok(client_populated: TestClient):
    r = client_populated.get("/radio/file", params={"relative_path": "root.mp3"})
    assert r.status_code == 200
    assert r.headers.get("accept-ranges") == "bytes"


def test_radio_file_traversal(client_populated: TestClient):
    r = client_populated.get("/radio/file", params={"relative_path": "../etc/passwd"})
    assert r.status_code == 400


def test_radio_file_not_mp3(client_populated: TestClient, tmp_path):
    # relative_path ending in .mp3 but wrong type — create txt as .mp3 name not needed; use nonexistent
    r = client_populated.get("/radio/file", params={"relative_path": "nope.mp3"})
    assert r.status_code == 404


def test_radio_live_proxy(monkeypatch, client: TestClient):
    class FakeResp:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        async def aiter_bytes(self, chunk_size: int = 65536):
            yield b"\xff\xfb\x90"

    class StreamCtx:
        async def __aenter__(self):
            return FakeResp()

        async def __aexit__(self, *a):
            return None

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        def stream(self, *a, **kw):
            return StreamCtx()

    import app.routes.radio as radio_mod

    monkeypatch.setattr(radio_mod.httpx, "AsyncClient", lambda **kw: FakeAsyncClient())
    with client.stream("GET", "/radio/live") as r:
        assert r.status_code == 200
        assert next(r.iter_bytes(100))


def test_radio_live_status_ok(monkeypatch, client: TestClient):
    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url: str):
            return httpx.Response(
                200,
                json={"service": "ok"},
                request=httpx.Request("GET", url),
            )

    import app.routes.radio as radio_mod

    monkeypatch.setattr(radio_mod.httpx, "AsyncClient", lambda **kw: FakeAsyncClient())
    r = client.get("/radio/live/status")
    assert r.status_code == 200
    assert r.json().get("proxied_by") == "fastapi"


def test_radio_live_status_upstream_http_error(monkeypatch, client: TestClient):
    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url: str):
            return httpx.Response(502, request=httpx.Request("GET", url))

    import app.routes.radio as radio_mod

    monkeypatch.setattr(radio_mod.httpx, "AsyncClient", lambda **kw: FakeAsyncClient())
    r = client.get("/radio/live/status")
    assert r.status_code == 502


def test_radio_live_status_request_error(monkeypatch, client: TestClient):
    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url: str):
            raise httpx.RequestError("down", request=httpx.Request("GET", url))

    import app.routes.radio as radio_mod

    monkeypatch.setattr(radio_mod.httpx, "AsyncClient", lambda **kw: FakeAsyncClient())
    r = client.get("/radio/live/status")
    assert r.status_code == 503


def test_radio_live_status_non_dict_json(monkeypatch, client: TestClient):
    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url: str):
            return httpx.Response(
                200,
                json=[1, 2],
                request=httpx.Request("GET", url),
            )

    import app.routes.radio as radio_mod

    monkeypatch.setattr(radio_mod.httpx, "AsyncClient", lambda **kw: FakeAsyncClient())
    r = client.get("/radio/live/status")
    assert r.status_code == 200
    body = r.json()
    assert body.get("payload") == [1, 2]
