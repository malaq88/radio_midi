"""
Inspeciona MUSIC_DIR, cria a pasta se faltar e opcionalmente move .mp3 soltos
da raiz para uma subpasta (útil após copiar/colar ficheiros na raiz).

Uso (na raiz do repositório, com venv ativo):
  python -m music_organize
  python -m music_organize --move-loose inbox
  python -m music_organize --move-loose rock --dry-run
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections import defaultdict
from pathlib import Path


def _iter_mp3_under(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() == ".mp3":
            yield p


def _playlist_group(music_root: Path, file_path: Path) -> str:
    try:
        rel = file_path.resolve().relative_to(music_root.resolve())
    except ValueError:
        return "root"
    parts = rel.parts
    if len(parts) <= 1:
        return "root"
    return parts[0]


def _count_extensions(root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not root.is_dir():
        return counts
    for p in root.rglob("*"):
        if p.is_file():
            ext = p.suffix.lower() or "(sem extensão)"
            counts[ext] = counts.get(ext, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))


def _mp3_loose_in_root(music_root: Path) -> list[Path]:
    out: list[Path] = []
    if not music_root.is_dir():
        return out
    for p in music_root.iterdir():
        if p.is_file() and p.suffix.lower() == ".mp3":
            out.append(p)
    return sorted(out, key=lambda x: x.name.lower())


def cmd_report(music_root: Path) -> int:
    print(f"MUSIC_DIR (resolvido): {music_root}")
    if not music_root.is_dir():
        print("  (pasta ainda não existe — será criada com --init ou ao correr sem --no-init)")
        return 0

    mp3s = list(_iter_mp3_under(music_root))
    by_group: dict[str, int] = defaultdict(int)
    for p in mp3s:
        by_group[_playlist_group(music_root, p)] += 1

    print(f"  Total de ficheiros .mp3: {len(mp3s)}")
    if by_group:
        print("  Por grupo de pasta (1.º nível sob MUSIC_DIR):")
        for name in sorted(by_group.keys(), key=str.lower):
            print(f"    · {name}: {by_group[name]}")

    other = _count_extensions(music_root)
    non_mp3 = {k: v for k, v in other.items() if k != ".mp3"}
    if non_mp3:
        print("  Outros ficheiros (não servidos como MP3 pela app):")
        for ext, n in list(non_mp3.items())[:20]:
            print(f"    · {ext}: {n}")
        if len(non_mp3) > 20:
            print(f"    … (+{len(non_mp3) - 20} tipos)")

    loose = _mp3_loose_in_root(music_root)
    if loose:
        print(f"  MP3 na raiz de MUSIC_DIR (grupo «root»): {len(loose)}")
        for p in loose[:12]:
            print(f"    - {p.name}")
        if len(loose) > 12:
            print(f"    … (+{len(loose) - 12} ficheiros)")
    return 0


def cmd_init(music_root: Path) -> int:
    music_root.mkdir(parents=True, exist_ok=True)
    print(f"Pasta garantida: {music_root}")
    return 0


def cmd_move_loose(music_root: Path, subdir: str, dry_run: bool) -> int:
    if not music_root.is_dir():
        print(f"Erro: MUSIC_DIR não existe: {music_root}", file=sys.stderr)
        print("Corre primeiro: python -m music_organize --init", file=sys.stderr)
        return 1

    dest_dir = (music_root / subdir).resolve()
    try:
        dest_dir.relative_to(music_root.resolve())
    except ValueError:
        print(f"Erro: subpasta inválida (tem de ficar dentro de MUSIC_DIR): {subdir}", file=sys.stderr)
        return 1

    loose = _mp3_loose_in_root(music_root)
    if not loose:
        print("Nenhum .mp3 solto na raiz de MUSIC_DIR.")
        return 0

    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)

    for p in loose:
        target = dest_dir / p.name
        if target.exists() and target.resolve() != p.resolve():
            print(f"Aviso: destino já existe, a saltar: {target.name}", file=sys.stderr)
            continue
        if dry_run:
            print(f"[dry-run] {p.name}  ->  {target}")
        else:
            shutil.move(str(p), str(target))
            print(f"Movido: {p.name}  ->  {subdir}/")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Configura / inspeciona MUSIC_DIR (mesma regra que app.config: .env MUSIC_DIR ou pasta music/).",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Cria MUSIC_DIR se não existir (e termina; combina com outros flags se quiseres).",
    )
    parser.add_argument(
        "--no-init",
        action="store_true",
        help="Não criar a pasta automaticamente antes do relatório.",
    )
    parser.add_argument(
        "--move-loose",
        metavar="SUBPASTA",
        help="Move todos os .mp3 que estão diretamente na raiz de MUSIC_DIR para MUSIC_DIR/SUBPASTA.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Com --move-loose, apenas mostra o que faria.",
    )
    args = parser.parse_args(argv)

    try:
        from app.config import settings
    except ImportError as e:
        print(
            "Não foi possível importar app.config (corre na raiz do projeto com o venv ativo).",
            file=sys.stderr,
        )
        print(str(e), file=sys.stderr)
        return 1

    music_root: Path = settings.music_dir.resolve()

    if args.init:
        cmd_init(music_root)

    if not args.no_init and not music_root.is_dir():
        music_root.mkdir(parents=True, exist_ok=True)
        print(f"Pasta criada: {music_root}")

    if args.move_loose:
        code = cmd_move_loose(music_root, args.move_loose.strip().strip("/\\"), args.dry_run)
        if code != 0:
            return code

    cmd_report(music_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
