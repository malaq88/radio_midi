"""app.services — lazy __getattr__."""

import pytest

from app.services import MusicLibrary, PlaylistStreamMode, stream_playlist_forever


def test_lazy_imports():
    assert MusicLibrary is not None
    assert PlaylistStreamMode.SHUFFLE
    assert callable(stream_playlist_forever)


def test_getattr_unknown():
    import app.services as svc

    with pytest.raises(AttributeError):
        _ = svc.NonExistentSymbol  # type: ignore[attr-defined]
