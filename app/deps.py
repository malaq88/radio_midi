"""Dependências FastAPI compartilhadas (injeção de biblioteca de músicas)."""

from fastapi import HTTPException, Request

from app.services.library import MusicLibrary


def get_library(request: Request) -> MusicLibrary:
    """Biblioteca anexada em `app.state` durante o lifespan."""
    lib = getattr(request.app.state, "library", None)
    if lib is None:
        raise HTTPException(status_code=503, detail="Biblioteca não inicializada.")
    return lib
