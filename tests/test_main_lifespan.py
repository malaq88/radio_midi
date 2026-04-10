"""Lifespan, autostart da rádio e _configure_logging."""

from __future__ import annotations

import logging
import subprocess
from unittest.mock import MagicMock

import pytest


def test_configure_logging_idempotent():
    from app import main as app_main

    root = logging.getLogger()
    saved = list(root.handlers)
    root.handlers.clear()
    try:
        app_main._configure_logging()
        n = len(root.handlers)
        app_main._configure_logging()
        assert len(root.handlers) == n == 1
    finally:
        root.handlers.clear()
        root.handlers.extend(saved)


@pytest.mark.asyncio
async def test_lifespan_starts_radio_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from app import main as app_main
    from app.config import Settings

    proc = MagicMock()
    proc.pid = 4242
    proc.terminate = MagicMock()
    proc.wait = MagicMock(return_value=None)
    popen = MagicMock(return_value=proc)
    monkeypatch.setattr(app_main.subprocess, "Popen", popen)

    s = Settings(
        music_dir=tmp_path,
        upload_api_key="",
        radio_live_autostart=True,
    )
    monkeypatch.setattr(app_main, "settings", s)
    monkeypatch.setattr(app_main.MusicLibrary, "scan", lambda self: None)

    async with app_main.lifespan(app_main.app):
        assert getattr(app_main.app.state, "radio_live_subprocess", None) is proc

    proc.terminate.assert_called_once()
    proc.wait.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_radio_shutdown_timeout_kills(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    from app import main as app_main
    from app.config import Settings

    proc = MagicMock()
    proc.pid = 7
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    proc.wait = MagicMock(side_effect=[subprocess.TimeoutExpired("x", 1), None])
    monkeypatch.setattr(app_main.subprocess, "Popen", MagicMock(return_value=proc))

    s = Settings(
        music_dir=tmp_path,
        upload_api_key=None,
        radio_live_autostart=True,
    )
    monkeypatch.setattr(app_main, "settings", s)
    monkeypatch.setattr(app_main.MusicLibrary, "scan", lambda self: None)

    async with app_main.lifespan(app_main.app):
        pass

    proc.kill.assert_called_once()
