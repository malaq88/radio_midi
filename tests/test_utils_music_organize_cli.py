"""Testes diretos a utils.music_organize.cli (sem subprocess)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from utils.music_organize import cli


def test_playlist_group_outside_music_root(tmp_path: Path):
    music = tmp_path / "m"
    music.mkdir()
    outside = tmp_path / "out.mp3"
    assert cli._playlist_group(music, outside) == "root"


def test_count_extensions_missing_dir():
    assert cli._count_extensions(Path("/nonexistent_radio_midi_xyz")) == {}


def test_mp3_loose_not_dir():
    assert cli._mp3_loose_in_root(Path("/nonexistent_radio_midi_xyz")) == []


def test_cmd_init(tmp_path: Path):
    root = tmp_path / "music"
    assert cli.cmd_init(root) == 0
    assert root.is_dir()


def test_cmd_report_missing_dir(capsys, tmp_path: Path):
    root = tmp_path / "missing"
    assert cli.cmd_report(root) == 0
    out = capsys.readouterr().out
    assert "MUSIC_DIR" in out and "não existe" in out


def test_cmd_report_counts_and_loose(capsys, tmp_path: Path):
    root = tmp_path / "lib"
    root.mkdir()
    (root / "root.mp3").write_bytes(b"ID3")
    rock = root / "rock"
    rock.mkdir(parents=True, exist_ok=True)
    (rock / "01 - a.mp3").write_bytes(b"ID3")
    (root / "x.flac").write_bytes(b"x")
    assert cli.cmd_report(root) == 0
    out = capsys.readouterr().out
    assert "Total de ficheiros" in out
    assert ".flac" in out or "flac" in out.lower()


def test_cmd_move_loose_music_missing(tmp_path: Path):
    root = tmp_path / "n"
    assert cli.cmd_move_loose(root, "inbox", dry_run=False) == 1


def test_cmd_move_loose_invalid_subdir(tmp_path: Path):
    root = tmp_path / "m"
    root.mkdir()
    assert cli.cmd_move_loose(root, "../evil", dry_run=False) == 1


def test_cmd_move_loose_none(tmp_path: Path, capsys):
    root = tmp_path / "m"
    root.mkdir()
    assert cli.cmd_move_loose(root, "inbox", dry_run=False) == 0
    assert "Nenhum" in capsys.readouterr().out


def test_cmd_move_loose_moves(tmp_path: Path):
    root = tmp_path / "m"
    root.mkdir()
    (root / "loose.mp3").write_bytes(b"x")
    assert cli.cmd_move_loose(root, "inbox", dry_run=False) == 0
    assert (root / "inbox" / "loose.mp3").is_file()


def test_cmd_move_loose_dry_run(tmp_path: Path, capsys):
    root = tmp_path / "m"
    root.mkdir()
    (root / "a.mp3").write_bytes(b"x")
    assert cli.cmd_move_loose(root, "box", dry_run=True) == 0
    assert "dry-run" in capsys.readouterr().out
    assert (root / "a.mp3").exists()


def test_cmd_move_skip_existing_conflict(tmp_path: Path, capsys):
    root = tmp_path / "m"
    root.mkdir()
    (root / "dup.mp3").write_bytes(b"a")
    (root / "inbox").mkdir()
    (root / "inbox" / "dup.mp3").write_bytes(b"b")
    assert cli.cmd_move_loose(root, "inbox", dry_run=False) == 0
    err = capsys.readouterr().err
    assert "Aviso" in err or "saltar" in err


def test_main_auto_mkdir_and_move(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "auto"
    monkeypatch.setattr("app.config.settings", SimpleNamespace(music_dir=root))
    assert cli.main(["--move-loose", "inbox", "--dry-run"]) == 0
    assert root.is_dir()


def test_main_no_init_skips_mkdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    root = tmp_path / "ghost"
    monkeypatch.setattr("app.config.settings", SimpleNamespace(music_dir=root))
    assert cli.main(["--no-init"]) == 0
    assert not root.exists()
