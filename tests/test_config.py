"""app.config — Settings e validadores."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_music_dir_relative_resolves_to_project_root():
    from app.config import PROJECT_ROOT, Settings

    s = Settings()
    assert s.music_dir.is_absolute()
    assert PROJECT_ROOT.name  # raiz definida


def test_stream_transition_gap_empty_string_becomes_none():
    from app.config import Settings

    s = Settings(stream_transition_gap_file="")
    assert s.stream_transition_gap_file is None


def test_stream_transition_gap_relative_resolves_under_project():
    from app.config import PROJECT_ROOT, Settings

    rel = Path("pyproject.toml")
    s = Settings(stream_transition_gap_file=rel)
    assert s.stream_transition_gap_file == (PROJECT_ROOT / rel).resolve()


def test_stream_transition_gap_absolute_keeps_resolved(tmp_path: Path):
    from app.config import Settings

    abs_p = tmp_path / "gap.wav"
    abs_p.write_bytes(b"")
    s = Settings(stream_transition_gap_file=abs_p)
    assert s.stream_transition_gap_file == abs_p.resolve()


def test_upload_api_key_empty_string_becomes_none():
    from app.config import Settings

    s = Settings(upload_api_key="")
    assert s.upload_api_key is None


def test_stream_chunk_order_validation_error():
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(
            stream_chunk_size=8192,
            stream_emit_chunk_size=4096,
        )


def test_device_playlist_map_exists():
    from app.config import DEVICE_PLAYLIST_MAP

    assert isinstance(DEVICE_PLAYLIST_MAP, dict)
