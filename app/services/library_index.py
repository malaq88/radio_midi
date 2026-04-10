"""
Índices em memória: artistas, álbuns (por pasta) e utilitários de ordenação por faixa.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from app.models.song import Song

logger = logging.getLogger(__name__)

_TRACK_PREFIX = re.compile(r"^(\d+)")


def folder_segments_for_path(music_root: Path, file_path: Path) -> tuple[str, str]:
    """
    Deriva (artista_pasta, album_pasta) a partir de music/Artista/Álbum/ficheiro.mp3.

    Menos de 3 segmentos: usa convenções para não perder ficheiros soltos.
    """
    try:
        rel = file_path.resolve().relative_to(music_root.resolve())
    except ValueError:
        return "root", "root"
    parts = rel.parts
    if len(parts) >= 3:
        return parts[0], parts[1]
    if len(parts) == 2:
        return parts[0], "_singles"
    return "root", "root"


def sort_songs_by_track_filename(songs: list[Song]) -> list[Song]:
    """Ordena por prefixo numérico no nome do ficheiro (ex. 01 - Foo.mp3), depois por nome."""

    def key(s: Song) -> tuple[int, str]:
        m = _TRACK_PREFIX.match(s.filename)
        if m:
            return (int(m.group(1)), s.filename.casefold())
        return (10_000, s.filename.casefold())

    return sorted(songs, key=key)


class LibraryIndexes:
    """Estruturas derivadas do scan; recriadas em cada `MusicLibrary.scan()`."""

    def __init__(self) -> None:
        self._by_artist_cf: dict[str, list[Song]] = {}
        self._artist_canonical: dict[str, str] = {}
        self._by_album_cf: dict[tuple[str, str], list[Song]] = {}
        self._album_canonical: dict[tuple[str, str], tuple[str, str]] = {}
        self._artists_sorted: list[str] = []

    def rebuild(self, songs: list[Song]) -> None:
        by_ar: dict[str, list[Song]] = {}
        ar_canon: dict[str, str] = {}
        by_al: dict[tuple[str, str], list[Song]] = {}
        al_canon: dict[tuple[str, str], tuple[str, str]] = {}

        for s in songs:
            fa = s.folder_artist or "root"
            fal = s.folder_album or "root"
            acf, lcf = fa.casefold(), fal.casefold()
            ar_canon.setdefault(acf, fa)
            al_canon.setdefault((acf, lcf), (fa, fal))
            by_ar.setdefault(acf, []).append(s)
            by_al.setdefault((acf, lcf), []).append(s)

        self._by_artist_cf = by_ar
        self._artist_canonical = ar_canon
        self._by_album_cf = by_al
        self._album_canonical = al_canon
        self._artists_sorted = sorted(ar_canon.values(), key=str.casefold)

        logger.info(
            "Índice biblioteca: %d artista(s), %d álbum(ns), %d faixa(s).",
            len(by_ar),
            len(by_al),
            len(songs),
        )

    def list_artists(self) -> list[str]:
        return list(self._artists_sorted)

    def canonical_artist(self, artist_name: str) -> str | None:
        acf = artist_name.strip().casefold()
        return self._artist_canonical.get(acf)

    def canonical_album_key(self, artist_name: str, album_name: str) -> tuple[str, str] | None:
        acf = artist_name.strip().casefold()
        lcf = album_name.strip().casefold()
        return self._album_canonical.get((acf, lcf))

    def list_albums_for_artist(self, artist_name: str) -> list[str] | None:
        """Nomes de pasta de álbum para o artista; None se artista desconhecido."""
        acf = artist_name.strip().casefold()
        if acf not in self._by_artist_cf:
            return None
        seen: dict[str, str] = {}
        for s in self._by_artist_cf[acf]:
            if s.folder_album:
                k = s.folder_album.casefold()
                seen.setdefault(k, s.folder_album)
        return sorted(seen.values(), key=str.casefold)

    def songs_for_artist(self, artist_name: str) -> list[Song] | None:
        acf = artist_name.strip().casefold()
        if acf not in self._by_artist_cf:
            return None
        return list(self._by_artist_cf[acf])

    def songs_for_album(self, artist_name: str, album_name: str) -> list[Song] | None:
        acf = artist_name.strip().casefold()
        lcf = album_name.strip().casefold()
        key = (acf, lcf)
        if key not in self._by_album_cf:
            return None
        return sort_songs_by_track_filename(list(self._by_album_cf[key]))

    def songs_under_top_folder(self, folder_name: str) -> list[Song] | None:
        """Todas as faixas cuja primeira pasta (relativa a MUSIC_DIR) coincide."""
        return self.songs_for_artist(folder_name)
