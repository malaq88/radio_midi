"""utils.music_organize.cli e módulo music_organize."""

from pathlib import Path

import pytest

from utils.music_organize.cli import cmd_move_loose, main


def test_music_organize_main_report(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MUSIC_DIR", str(tmp_path))
    import importlib

    from tests.conftest import MODULES_WITH_SETTINGS

    from app.config import Settings

    s = Settings()
    for mod_name in MODULES_WITH_SETTINGS:
        mod = importlib.import_module(mod_name)
        monkeypatch.setattr(mod, "settings", s, raising=False)
    tmp_path.mkdir(parents=True, exist_ok=True)
    code = main(["--no-init"])
    assert code == 0


def test_move_loose_dry_run(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MUSIC_DIR", str(tmp_path))
    import importlib

    from tests.conftest import MODULES_WITH_SETTINGS

    from app.config import Settings

    s = Settings()
    for mod_name in MODULES_WITH_SETTINGS:
        mod = importlib.import_module(mod_name)
        monkeypatch.setattr(mod, "settings", s, raising=False)
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "a.mp3").write_bytes(b"x")
    assert cmd_move_loose(tmp_path, "inbox", dry_run=True) == 0


def test_music_organize_package_main_importable():
    import music_organize.__main__  # noqa: F401
    import utils.music_organize.__main__  # noqa: F401
