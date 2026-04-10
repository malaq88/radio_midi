"""
Serviços da aplicação.

Imports em `__getattr__` evitam carregar mutagen/stream ao correr só o gerador live:
`python -m app.services.radio_generator`
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["MusicLibrary", "PlaylistStreamMode", "stream_playlist_forever"]

if TYPE_CHECKING:
    from app.services.library import MusicLibrary
    from app.services.stream import PlaylistStreamMode, stream_playlist_forever


def __getattr__(name: str) -> Any:
    if name == "MusicLibrary":
        from app.services.library import MusicLibrary

        return MusicLibrary
    if name == "PlaylistStreamMode":
        from app.services.stream import PlaylistStreamMode

        return PlaylistStreamMode
    if name == "stream_playlist_forever":
        from app.services.stream import stream_playlist_forever

        return stream_playlist_forever
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
