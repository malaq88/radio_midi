"""
Listagem de faixas e agrupamento por pasta (playlists).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from app.deps import get_library
from app.models.song import PlaylistInfo, SongPublic
from app.services.library import MusicLibrary, count_file_extensions_under

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/songs")
async def list_songs(
    library: Annotated[MusicLibrary, Depends(get_library)],
) -> dict:
    """
    Retorna todas as músicas e um resumo por playlist (nome da subpasta).

    Não expõe caminhos absolutos do servidor; apenas caminho relativo à pasta de música.
    """
    songs = library.get_all_songs()
    root = library.music_root

    items: list[SongPublic] = []
    for s in songs:
        try:
            rel = str(s.path.relative_to(root))
        except ValueError:
            rel = s.filename
        items.append(
            SongPublic(
                filename=s.filename,
                playlist_group=s.playlist_group,
                title=s.title,
                artist=s.artist,
                folder_artist=s.folder_artist,
                folder_album=s.folder_album,
                relative_path=rel.replace("\\", "/"),
            )
        )

    playlists = [
        PlaylistInfo(name=name, song_count=len(library.songs_in_playlist(name)))
        for name in library.playlist_names()
    ]

    logger.debug("Listagem /songs: %d faixa(s).", len(items))

    payload: dict = {
        "music_root": str(root),
        "total_songs": len(items),
        "songs": [m.model_dump() for m in items],
        "playlists_by_folder": [p.model_dump() for p in playlists],
    }

    # Ajuda a perceber por que a biblioteca está vazia (ex.: só .m4a, ou só pastas).
    if not items and root.is_dir():
        payload["file_extensions_in_library"] = count_file_extensions_under(root)
        payload["tip"] = (
            "Este serviço só indexa ficheiros .mp3. Confirme extensões acima, "
            "reinicie o uvicorn após copiar músicas, e que MUSIC_DIR é a pasta que está a usar."
        )

    return payload
