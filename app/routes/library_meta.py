"""
Metadados da biblioteca para frontend: artistas e álbuns (pastas).
"""

from __future__ import annotations

import logging
from typing import Annotated
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.deps import get_library
from app.services.library import MusicLibrary

logger = logging.getLogger(__name__)

router = APIRouter(tags=["library"])


def _safe_album_folder_segment(value: str) -> str | None:
    """Um segmento de pasta (sem path traversal)."""
    s = unquote(value).strip()
    if not s or ".." in s or "/" in s or "\\" in s or s in (".", ".."):
        return None
    return s


@router.get("/artists")
async def list_artists(
    library: Annotated[MusicLibrary, Depends(get_library)],
) -> dict:
    """Lista nomes de pasta de primeiro nível (artistas) com pelo menos uma faixa."""
    if not library.songs:
        return {"artists": [], "total_artists": 0}
    names = library.indexes.list_artists()
    return {"artists": names, "total_artists": len(names)}


@router.get("/albums/{artist}")
async def list_albums_for_artist(
    artist: str,
    library: Annotated[MusicLibrary, Depends(get_library)],
) -> dict:
    """Álbuns (subpastas) para o artista indicado."""
    raw = unquote(artist).strip()
    canon = library.indexes.canonical_artist(raw)
    if canon is None:
        raise HTTPException(status_code=404, detail=f"Artista não encontrado: {raw}")
    albums = library.indexes.list_albums_for_artist(raw)
    assert albums is not None
    return {
        "artist": canon,
        "albums": albums,
        "total_albums": len(albums),
    }


@router.get("/library/cover/{artist}/{album}")
async def album_cover_art(
    artist: str,
    album: str,
    library: Annotated[MusicLibrary, Depends(get_library)],
) -> FileResponse:
    """
    Serve `cover.jpg` / `cover.png` / `cover.jpeg` na pasta do álbum (se existir).
    """
    a = _safe_album_folder_segment(artist)
    b = _safe_album_folder_segment(album)
    if a is None or b is None:
        raise HTTPException(status_code=400, detail="Parâmetros inválidos.")

    root = library.music_root.resolve()
    folder = (root / a / b).resolve()
    try:
        folder.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=404, detail="Caminho inválido.")

    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Álbum não encontrado.")

    for fname, media in (
        ("cover.jpg", "image/jpeg"),
        ("cover.jpeg", "image/jpeg"),
        ("cover.png", "image/png"),
    ):
        path = folder / fname
        if path.is_file():
            return FileResponse(path, media_type=media)

    raise HTTPException(status_code=404, detail="Sem capa neste álbum.")
