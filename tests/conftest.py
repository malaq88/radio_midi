"""Fixtures partilhadas: MUSIC_DIR temporário e cliente HTTP com lifespan."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

# Usado por testes que precisam de reconfigurar Settings sem o fixture completo.
MODULES_WITH_SETTINGS = (
    "app.config",
    "app.main",
    "app.services.library",
    "app.services.stream",
    "app.routes.radio",
    "app.routes.upload",
    "app.security_upload",
)


def write_min_mp3(path: Path) -> None:
    """Bytes que passam looks_like_mp3_header e permitem leitura em stream."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        b"ID3\x03\x00\x00\x00\x00\x00\x00"
        + b"\xff" * 32
        + b"\xff\xfb\x90\x00"
        + b"\x00" * 4096
    )
    path.write_bytes(body)


@pytest.fixture
def patched_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MUSIC_DIR", str(tmp_path))
    monkeypatch.setenv("UPLOAD_API_KEY", "pytest-upload-secret-key")
    monkeypatch.setenv("RADIO_LIVE_AUTOSTART", "false")
    from app.config import Settings

    s = Settings()
    for mod_name in MODULES_WITH_SETTINGS:
        mod = importlib.import_module(mod_name)
        monkeypatch.setattr(mod, "settings", s, raising=False)
    return s


@pytest.fixture
def client(patched_settings, tmp_path: Path):
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_populated(patched_settings, tmp_path: Path):
    """Cliente HTTP com MUSIC_DIR já contendo alguns .mp3 antes do lifespan."""
    write_min_mp3(tmp_path / "root.mp3")
    write_min_mp3(tmp_path / "ArtistZ" / "Album1" / "01 - one.mp3")
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_with_flac_only(patched_settings, tmp_path: Path):
    (tmp_path / "only.flac").write_bytes(b"x")
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture
def library_with_tracks(patched_settings, tmp_path: Path):
    write_min_mp3(tmp_path / "root_track.mp3")
    write_min_mp3(tmp_path / "ArtistA" / "Album1" / "01 - One.mp3")
    write_min_mp3(tmp_path / "ArtistA" / "Album1" / "02 - Two.mp3")
    write_min_mp3(tmp_path / "rock" / "r1.mp3")
    from app.services.library import MusicLibrary

    lib = MusicLibrary()
    lib.scan()
    return lib
