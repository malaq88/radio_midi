"""
Autenticação para uploads: API key obrigatória se o serviço estiver configurado.

Comparação em tempo constante para mitigar timing attacks.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Header, HTTPException

from app.config import settings


def require_upload_api_key(
    x_api_key: Annotated[str | None, Header(description="API key para upload")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """
    Aceita `X-API-Key: <token>` ou `Authorization: Bearer <token>`.

    Se `UPLOAD_API_KEY` não estiver definida, os uploads ficam desativados (503).
    """
    expected = settings.upload_api_key
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Uploads desativados: defina UPLOAD_API_KEY no ambiente.",
        )

    token: str | None = None
    if x_api_key:
        token = x_api_key.strip()
    elif authorization:
        auth = authorization.strip()
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Credenciais em falta: use o cabeçalho X-API-Key ou Authorization: Bearer.",
        )

    if not secrets.compare_digest(token.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Não autorizado.")
