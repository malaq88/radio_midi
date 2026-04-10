"""
Endpoints de streaming contínuo (rádio): aleatório, dispositivo, artista, álbum e pasta.
"""

from __future__ import annotations

import logging
from typing import Annotated
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from app.deps import get_library
from app.models.song import Song
from app.services.library import MusicLibrary
from app.services.stream import PlaylistStreamMode, stream_playlist_forever

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/radio")


def _stream_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
    }


def _ensure_has_tracks(songs: list[Song]) -> None:
    if not songs:
        raise HTTPException(
            status_code=503,
            detail="Nenhuma música disponível. Verifique MUSIC_DIR e arquivos .mp3.",
        )


def _streaming_response(generator) -> StreamingResponse:
    return StreamingResponse(
        generator,
        media_type="audio/mpeg",
        headers=_stream_headers(),
    )


@router.get("/random")
async def radio_random(
    request: Request,
    library: Annotated[MusicLibrary, Depends(get_library)],
) -> StreamingResponse:
    """
    Stream contínuo: faixas aleatórias de toda a biblioteca (shuffle com memória por ligação).
    """
    songs = library.get_all_songs()
    _ensure_has_tracks(songs)

    client = request.client.host if request.client else "?"
    logger.info("Cliente conectado a /radio/random desde %s", client)

    generator = stream_playlist_forever(
        songs,
        label="random",
        mode=PlaylistStreamMode.SHUFFLE,
    )
    return _streaming_response(generator)


@router.get("/device/{device_id}")
async def radio_device(
    device_id: str,
    request: Request,
    library: Annotated[MusicLibrary, Depends(get_library)],
) -> StreamingResponse:
    """
    Stream por `device_id` (mapeamento de playlist ou biblioteca completa).
    """
    device_id = device_id.strip()
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id inválido.")

    songs = library.resolve_device_playlist(device_id)
    _ensure_has_tracks(songs)

    client = request.client.host if request.client else "?"
    logger.info(
        "Cliente conectado a /radio/device/%s desde %s (%d faixa(s) no pool)",
        device_id,
        client,
        len(songs),
    )

    generator = stream_playlist_forever(
        songs,
        label=f"device:{device_id}",
        mode=PlaylistStreamMode.SHUFFLE,
    )
    return _streaming_response(generator)


@router.get("/artist/{artist_name}")
async def radio_artist(
    artist_name: str,
    request: Request,
    library: Annotated[MusicLibrary, Depends(get_library)],
) -> StreamingResponse:
    """
    Todas as faixas cuja primeira pasta (artista) coincide; shuffle contínuo.
    """
    name = unquote(artist_name).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nome de artista inválido.")

    pool = library.indexes.songs_for_artist(name)
    if pool is None:
        raise HTTPException(status_code=404, detail=f"Artista ou pasta não encontrada: {name}")
    if not pool:
        raise HTTPException(status_code=404, detail=f"Sem faixas para: {name}")

    client = request.client.host if request.client else "?"
    canon = library.indexes.canonical_artist(name)
    logger.info(
        "Cliente /radio/artist/%r (canónico=%r) desde %s — %d faixa(s)",
        name,
        canon,
        client,
        len(pool),
    )

    generator = stream_playlist_forever(
        pool,
        label=f"artist:{canon or name}",
        mode=PlaylistStreamMode.SHUFFLE,
    )
    return _streaming_response(generator)


@router.get("/album/{artist_name}/{album_name}")
async def radio_album(
    artist_name: str,
    album_name: str,
    request: Request,
    library: Annotated[MusicLibrary, Depends(get_library)],
) -> StreamingResponse:
    """
    Faixas de um álbum (pasta); ordem por número no nome do ficheiro; ciclo contínuo.
    """
    art = unquote(artist_name).strip()
    alb = unquote(album_name).strip()
    if not art or not alb:
        raise HTTPException(status_code=400, detail="Artista ou álbum inválido.")

    pool = library.indexes.songs_for_album(art, alb)
    if pool is None:
        raise HTTPException(
            status_code=404,
            detail=f"Álbum não encontrado para o artista indicado: {art} / {alb}",
        )
    if not pool:
        raise HTTPException(status_code=404, detail=f"Sem faixas no álbum: {alb}")

    client = request.client.host if request.client else "?"
    pair = library.indexes.canonical_album_key(art, alb)
    logger.info(
        "Cliente /radio/album desde %s — %s (%d faixa(s))",
        client,
        pair,
        len(pool),
    )

    generator = stream_playlist_forever(
        pool,
        label=f"album:{pair}",
        mode=PlaylistStreamMode.ORDERED_LOOP,
    )
    return _streaming_response(generator)


@router.get("/folder/{folder_name}")
async def radio_folder(
    folder_name: str,
    request: Request,
    library: Annotated[MusicLibrary, Depends(get_library)],
) -> StreamingResponse:
    """
    Todas as faixas sob a pasta de primeiro nível `folder_name` (equivalente a /radio/artist).
    """
    name = unquote(folder_name).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nome de pasta inválido.")

    pool = library.indexes.songs_under_top_folder(name)
    if pool is None:
        raise HTTPException(status_code=404, detail=f"Pasta não encontrada: {name}")
    if not pool:
        raise HTTPException(status_code=404, detail=f"Sem faixas em: {name}")

    client = request.client.host if request.client else "?"
    logger.info("Cliente /radio/folder/%r desde %s — %d faixa(s)", name, client, len(pool))

    generator = stream_playlist_forever(
        pool,
        label=f"folder:{name}",
        mode=PlaylistStreamMode.SHUFFLE,
    )
    return _streaming_response(generator)


@router.get("/file")
async def radio_single_file(
    relative_path: Annotated[str, Query(description="Caminho relativo à pasta de música, ex.: rock/faixa.mp3")],
    library: Annotated[MusicLibrary, Depends(get_library)],
) -> FileResponse:
    """
    Uma única faixa MP3 (adequado para `<audio>` com duração e seek).

    O caminho é validado para ficar sempre dentro de `music_dir`.
    """
    raw = unquote(relative_path).strip().replace("\\", "/").lstrip("/")
    if not raw or any(part == ".." for part in raw.split("/")):
        raise HTTPException(status_code=400, detail="Caminho inválido.")

    root = library.music_root.resolve()
    target = (root / raw).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=404, detail="Ficheiro fora da biblioteca.")

    if not target.is_file() or target.suffix.lower() != ".mp3":
        raise HTTPException(status_code=404, detail="MP3 não encontrado.")

    return FileResponse(
        path=target,
        media_type="audio/mpeg",
        filename=target.name,
        headers={
            "Cache-Control": "no-cache",
            "Accept-Ranges": "bytes",
            "X-Content-Type-Options": "nosniff",
        },
    )
