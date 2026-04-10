"""app.security_upload."""

import pytest
from fastapi import HTTPException

from app.security_upload import require_upload_api_key


def test_require_upload_disabled(monkeypatch):
    from app.config import Settings

    import app.security_upload as sec

    s = Settings(upload_api_key="")
    monkeypatch.setattr(sec, "settings", s)
    with pytest.raises(HTTPException) as ei:
        require_upload_api_key(None, None)
    assert ei.value.status_code == 503


def test_require_upload_missing_token(patched_settings, monkeypatch):
    import app.security_upload as sec

    monkeypatch.setattr(sec, "settings", patched_settings)
    with pytest.raises(HTTPException) as ei:
        require_upload_api_key(None, None)
    assert ei.value.status_code == 401


def test_require_upload_x_api_key_ok(patched_settings, monkeypatch):
    import app.security_upload as sec

    monkeypatch.setattr(sec, "settings", patched_settings)
    assert patched_settings.upload_api_key
    require_upload_api_key(patched_settings.upload_api_key, None)


def test_require_upload_bearer_ok(patched_settings, monkeypatch):
    import app.security_upload as sec

    monkeypatch.setattr(sec, "settings", patched_settings)
    require_upload_api_key(None, f"Bearer {patched_settings.upload_api_key}")


def test_require_upload_wrong_key(patched_settings, monkeypatch):
    import app.security_upload as sec

    monkeypatch.setattr(sec, "settings", patched_settings)
    with pytest.raises(HTTPException) as ei:
        require_upload_api_key("definitely-wrong-key", None)
    assert ei.value.status_code == 401
