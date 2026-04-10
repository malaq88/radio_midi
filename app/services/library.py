"""
Varredura da biblioteca de músicas: .mp3 recursivos, metadados opcionais, playlists por pasta.
"""

from __future__ import annotations

import logging
from pathlib import Path

from mutagen import File as MutagenFile

from app.config import DEVICE_PLAYLIST_MAP, settings
from app.models.song import Song
from app.services.library_index import LibraryIndexes, folder_segments_for_path

logger = logging.getLogger(__name__)


def _read_id3_tags(path: Path) -> tuple[str | None, str | None]:
    """
    Extrai title/artist quando possível, sem falhar se o arquivo estiver corrompido ou sem tags.
    """
    try:
        audio = MutagenFile(path, easy=True)
        if audio is None:
            return None, None
        title = (audio.get("title") or [None])[0]
        artist = (audio.get("artist") or [None])[0]
        return title, artist
    except Exception as exc:  # noqa: BLE001 — não derrubar o scan por um arquivo ruim
        logger.debug("Metadados ignorados para %s: %s", path, exc)
        return None, None


def count_file_extensions_under(root: Path) -> dict[str, int]:
    """
    Conta extensões de todos os ficheiros sob `root` (útil quando a biblioteca MP3 vem vazia).

    Só deve ser usada em respostas de diagnóstico; pode ser custosa em árvores enormes.
    """
    if not root.is_dir():
        return {}
    counts: dict[str, int] = {}
    try:
        for p in root.rglob("*"):
            if p.is_file():
                ext = p.suffix.lower() or "(sem extensão)"
                counts[ext] = counts.get(ext, 0) + 1
    except OSError as exc:
        logger.warning("Não foi possível analisar extensões em %s: %s", root, exc)
        return {}
    return dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))


def _iter_mp3_paths(root: Path):
    """
    Percorre recursivamente e devolve ficheiros cujo sufixo é .mp3 em qualquer capitalização.

    `Path.rglob('*.mp3')` no Linux **não** inclui `.MP3`, o que é uma causa frequente de biblioteca vazia.
    """
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() == ".mp3":
            yield path


def _playlist_group_for_file(music_root: Path, file_path: Path) -> str:
    """Nome da playlist = primeiro componente relativo à raiz; 'root' se estiver na raiz."""
    try:
        rel = file_path.relative_to(music_root.resolve())
    except ValueError:
        return "root"
    parts = rel.parts
    if len(parts) <= 1:
        return "root"
    return parts[0]


class MusicLibrary:
    """
    Mantém a lista de faixas e índices por grupo de pasta.

    Thread-safe o suficiente para leitura concorrente após o scan inicial (lista imutável em uso).
    """

    def __init__(self) -> None:
        self._music_root: Path = settings.music_dir.resolve()
        self._songs: list[Song] = []
        self._by_playlist: dict[str, list[Song]] = {}
        self._indexes = LibraryIndexes()

    @property
    def music_root(self) -> Path:
        return self._music_root

    @property
    def songs(self) -> list[Song]:
        return self._songs

    def scan(self) -> None:
        """
        Percorre music_dir por *.mp3, preenche self._songs e agrupa em self._by_playlist.

        Chamado no startup da aplicação.
        """
        root = settings.music_dir.resolve()
        self._music_root = root

        if not root.is_dir():
            logger.error("Pasta de música inexistente ou não é diretório: %s", root)
            self._songs = []
            self._by_playlist = {}
            self._indexes = LibraryIndexes()
            self._indexes.rebuild([])
            return

        found: list[Song] = []
        for path in sorted(_iter_mp3_paths(root), key=lambda p: str(p).lower()):
            if not path.is_file():
                continue
            try:
                group = _playlist_group_for_file(root, path)
                title, artist = _read_id3_tags(path)
                fa, fal = folder_segments_for_path(root, path)
                song = Song(
                    path=path,
                    filename=path.name,
                    playlist_group=group,
                    title=title,
                    artist=artist,
                    folder_artist=fa,
                    folder_album=fal,
                )
                found.append(song)
            except OSError as exc:
                logger.warning("Não foi possível ler arquivo %s: %s", path, exc)

        by_pl: dict[str, list[Song]] = {}
        for s in found:
            by_pl.setdefault(s.playlist_group, []).append(s)

        self._songs = found
        self._by_playlist = by_pl
        self._indexes.rebuild(found)

        if not found:
            logger.warning(
                "Nenhum ficheiro .mp3 encontrado em %s. "
                "Confirme: ficheiros têm extensão .mp3 (qualquer maiúsculas), "
                "não só pastas vazias; MUSIC_DIR aponta para a pasta certa; reinicie o servidor após mudanças.",
                root,
            )
        else:
            logger.info(
                "Biblioteca carregada: %d faixa(s) em %d playlist(s) por pasta.",
                len(found),
                len(by_pl),
            )

    def get_all_songs(self) -> list[Song]:
        return list(self._songs)

    def songs_in_playlist(self, playlist_name: str) -> list[Song]:
        """Retorna cópia da lista de músicas da subpasta `playlist_name`."""
        return list(self._by_playlist.get(playlist_name, []))

    def playlist_names(self) -> list[str]:
        return sorted(self._by_playlist.keys())

    def resolve_device_playlist(self, device_id: str) -> list[Song]:
        """
        Lista de faixas para o dispositivo: pasta mapeada ou fallback para toda a biblioteca.

        Se o mapeamento apontar para uma pasta vazia/inexistente, usa todas as faixas (random).
        """
        mapped = DEVICE_PLAYLIST_MAP.get(device_id)
        if not mapped:
            return self.get_all_songs()
        subset = self.songs_in_playlist(mapped)
        if not subset:
            logger.info(
                "Playlist '%s' vazia ou inexistente para device_id=%s; usando biblioteca completa.",
                mapped,
                device_id,
            )
            return self.get_all_songs()
        return subset

    @property
    def indexes(self) -> LibraryIndexes:
        """Índices artista/álbum (atualizados no último scan)."""
        return self._indexes
