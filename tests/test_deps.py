"""app.deps."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.deps import get_library


def test_get_library_missing():
    req = MagicMock()
    req.app.state.library = None
    with pytest.raises(HTTPException) as ei:
        get_library(req)
    assert ei.value.status_code == 503


def test_get_library_ok(library_with_tracks):
    req = MagicMock()
    req.app.state.library = library_with_tracks
    assert get_library(req) is library_with_tracks
