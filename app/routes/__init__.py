from fastapi import APIRouter

from app.routes import library_meta, radio, songs, upload

api_router = APIRouter()
api_router.include_router(radio.router, tags=["radio"])
api_router.include_router(songs.router, tags=["songs"])
api_router.include_router(library_meta.router)
api_router.include_router(upload.router)

__all__ = ["api_router"]
