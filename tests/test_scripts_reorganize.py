"""scripts/reorganize_music.py."""

import importlib.util
import sys
from pathlib import Path

from tests.conftest import write_min_mp3


def _load_reorganize_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "reorganize_music.py"
    spec = importlib.util.spec_from_file_location("reorganize_music_test_mod", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_reorganize_main_runs(tmp_path, monkeypatch):
    music = tmp_path / "lib"
    music.mkdir()
    write_min_mp3(music / "z.mp3")
    mod = _load_reorganize_module()
    monkeypatch.setattr(sys, "argv", ["prog", "--music-dir", str(music)])
    code = mod.main()
    assert code in (0, 2)


def test_reorganize_file_not_found(tmp_path, monkeypatch):
    mod = _load_reorganize_module()
    ghost = tmp_path / "nope"
    monkeypatch.setattr(sys, "argv", ["prog", "--music-dir", str(ghost)])
    code = mod.main()
    assert code == 1
