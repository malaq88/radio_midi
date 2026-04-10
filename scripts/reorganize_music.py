#!/usr/bin/env python3
"""
Reorganiza todos os .mp3 em MUSIC_DIR para {Artista}/{Álbum}/{NN} - {Título}.mp3.

Uso (na raiz do projeto):
  python scripts/reorganize_music.py
  python scripts/reorganize_music.py --music-dir /music
  python scripts/reorganize_music.py --overwrite   # substitui destinos e capas existentes

Requer as mesmas variáveis que o servidor (ex. .env com MUSIC_DIR).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

from app.config import settings  # noqa: E402
from app.services.mp3_organize import reorganize_entire_library  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Reorganizar biblioteca MP3 por ID3.")
    parser.add_argument(
        "--music-dir",
        type=Path,
        default=None,
        help="Pasta raiz (predefinido: MUSIC_DIR do .env / settings)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Substituir ficheiros e capas já existentes no destino canónico",
    )
    parser.add_argument(
        "--no-cover",
        action="store_true",
        help="Não extrair capas embutidas",
    )
    args = parser.parse_args()

    root = (args.music_dir or settings.music_dir).resolve()
    print(f"Biblioteca: {root}", file=sys.stderr)

    try:
        ok, errors = reorganize_entire_library(
            root,
            overwrite=args.overwrite,
            extract_cover=not args.no_cover,
        )
    except FileNotFoundError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    print(f"OK: {len(ok)} ficheiro(s)", file=sys.stderr)
    for rel in ok[:50]:
        print(rel)
    if len(ok) > 50:
        print(f"... e mais {len(ok) - 50}", file=sys.stderr)

    if errors:
        print(f"\nErros: {len(errors)}", file=sys.stderr)
        for path, msg in errors[:20]:
            print(f"  {path}: {msg}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
