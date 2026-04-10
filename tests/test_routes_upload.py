"""POST /upload."""

import io
import zipfile

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile


def _mp3_body() -> bytes:
    return b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" + b"\x00" * 800


def test_upload_requires_key(client_populated: TestClient):
    files = {"file": ("t.mp3", _mp3_body(), "application/octet-stream")}
    r = client_populated.post("/upload", files=files)
    assert r.status_code == 401


def test_upload_single_ok(client_populated: TestClient, patched_settings):
    files = {"file": ("track.mp3", _mp3_body(), "audio/mpeg")}
    r = client_populated.post(
        "/upload",
        files=files,
        headers={"X-API-Key": patched_settings.upload_api_key or ""},
    )
    assert r.status_code == 200
    assert r.json()["success"] is True


def test_upload_single_ok_filename_without_mp3_extension(
    client_populated: TestClient, patched_settings
):
    files = {"file": ("track", _mp3_body(), "audio/mpeg")}
    r = client_populated.post(
        "/upload",
        files=files,
        headers={"X-API-Key": patched_settings.upload_api_key or ""},
    )
    assert r.status_code == 200
    assert r.json()["success"] is True


def test_upload_bad_header(client_populated: TestClient, patched_settings):
    files = {"file": ("x.mp3", b"NOTMP3DATA" * 50, "audio/mpeg")}
    r = client_populated.post(
        "/upload",
        files=files,
        headers={"X-API-Key": patched_settings.upload_api_key or ""},
    )
    assert r.status_code == 400


def test_upload_zip_ok(client_populated: TestClient, patched_settings):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("z.mp3", _mp3_body())
    buf.seek(0)
    files = {"file": ("album.zip", buf.read(), "application/zip")}
    r = client_populated.post(
        "/upload/zip",
        files=files,
        headers={"X-API-Key": patched_settings.upload_api_key or ""},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True


def test_upload_zip_not_zip(client_populated: TestClient, patched_settings):
    files = {"file": ("x.txt", b"hi", "text/plain")}
    r = client_populated.post(
        "/upload/zip",
        files=files,
        headers={"X-API-Key": patched_settings.upload_api_key or ""},
    )
    assert r.status_code == 400


def test_upload_zip_corrupt_body(client_populated: TestClient, patched_settings):
    files = {"file": ("bad.zip", b"not a real zip content", "application/zip")}
    r = client_populated.post(
        "/upload/zip",
        files=files,
        headers={"X-API-Key": patched_settings.upload_api_key or ""},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert body["skipped"]


@pytest.mark.asyncio
async def test_upload_single_mp3_direct_empty_filename_400(client_populated: TestClient):
    from unittest.mock import MagicMock

    from app.routes.upload import upload_single_mp3

    library = client_populated.app.state.library
    req = MagicMock()
    req.app = client_populated.app
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    uf = UploadFile(filename="", file=io.BytesIO(_mp3_body()))
    with pytest.raises(HTTPException) as exc:
        await upload_single_mp3(req, library, None, uf, None, False)
    assert exc.value.status_code == 400


def test_upload_single_empty_filename(client_populated: TestClient, patched_settings):
    # filename vazio: multipart não vira UploadFile → validação FastAPI (422).
    files = {"file": ("", _mp3_body(), "audio/mpeg")}
    r = client_populated.post(
        "/upload",
        files=files,
        headers={"X-API-Key": patched_settings.upload_api_key or ""},
    )
    assert r.status_code == 422
    errs = r.json().get("detail", [])
    assert isinstance(errs, list)
    assert any("file" in (e.get("loc") or []) for e in errs)


def test_upload_single_relative_path_dotdot(client_populated: TestClient, patched_settings):
    files = {"file": ("t.mp3", _mp3_body(), "audio/mpeg")}
    data = {"relative_path": "../evil"}
    r = client_populated.post(
        "/upload",
        files=files,
        data=data,
        headers={"X-API-Key": patched_settings.upload_api_key or ""},
    )
    assert r.status_code == 400


def test_upload_single_title_fallback_from_relative_path(
    client_populated: TestClient, patched_settings
):
    """relative_path válido: usa o stem como title fallback."""
    files = {"file": ("blob.mp3", _mp3_body(), "audio/mpeg")}
    data = {"relative_path": "Compil/03 - My Nice Title.mp3"}
    r = client_populated.post(
        "/upload",
        files=files,
        data=data,
        headers={"X-API-Key": patched_settings.upload_api_key or ""},
    )
    assert r.status_code == 200
