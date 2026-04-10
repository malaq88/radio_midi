"""Modelos de domínio para faixas e agrupamento por pasta (playlist)."""

from pathlib import Path

from pydantic import BaseModel, Field


class Song(BaseModel):
    """
    Representa um arquivo .mp3 na biblioteca.

    `playlist_group` é o primeiro segmento de diretório relativo a music_dir
    (ex.: rock, chill) ou "root" se o arquivo está diretamente na raiz.

    `folder_artist` / `folder_album` derivam da árvore `music/Artista/Álbum/ficheiro.mp3`.
    """

    model_config = {"frozen": True}

    path: Path = Field(description="Caminho absoluto do arquivo.")
    filename: str
    playlist_group: str
    title: str | None = None
    artist: str | None = None
    folder_artist: str | None = Field(
        default=None,
        description="Primeira pasta sob MUSIC_DIR (nome canónico no disco).",
    )
    folder_album: str | None = Field(
        default=None,
        description="Segunda pasta (álbum) quando o caminho tem pelo menos 3 segmentos.",
    )


class SongPublic(BaseModel):
    """Resposta da API para listagem (sem expor caminho completo do sistema de arquivos)."""

    filename: str
    playlist_group: str
    title: str | None = None
    artist: str | None = None
    folder_artist: str | None = None
    folder_album: str | None = None
    relative_path: str = Field(
        description="Caminho relativo à pasta music_dir, para identificação única na UI."
    )


class PlaylistInfo(BaseModel):
    """Grupo de músicas nomeado pela pasta (bonus: GET /songs inclui esta estrutura)."""

    name: str
    song_count: int
