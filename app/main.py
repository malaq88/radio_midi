"""
Ponto de entrada FastAPI: lifespan carrega a biblioteca; rotas em `app.routes`.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import DEVICE_PLAYLIST_MAP, PROJECT_ROOT, settings
from app.routes import api_router
from app.services.library import MusicLibrary


def _configure_logging() -> None:
    """Log em stdout: útil em Docker/systemd; nível INFO para conexões e faixas."""
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: escaneia `MUSIC_DIR` uma vez. Não reescaneia automaticamente em runtime
    (pode-se adicionar POST /admin/rescan depois se necessário).
    """
    _configure_logging()
    log = logging.getLogger(__name__)
    log.info(
        "Iniciando biblioteca: music_dir=%s read_chunk=%s emit_chunk=%s queue_depth=%s",
        settings.music_dir,
        settings.stream_chunk_size,
        settings.stream_emit_chunk_size,
        settings.stream_queue_max_chunks,
    )
    log.info("Mapeamento dispositivo→playlist: %s", DEVICE_PLAYLIST_MAP)
    if settings.upload_api_key:
        log.info("Upload HTTP ativo (UPLOAD_API_KEY configurada).")
        if settings.upload_api_key == "radio_midi_dev":
            log.warning(
                "A usar chave de API de desenvolvimento (radio_midi_dev); altere UPLOAD_API_KEY em produção."
            )
    else:
        log.warning("Upload HTTP desativado: defina UPLOAD_API_KEY para POST /upload.")

    library = MusicLibrary()
    library.scan()
    app.state.library = library

    radio_proc: subprocess.Popen | None = None
    if settings.radio_live_autostart:
        env = os.environ.copy()
        radio_proc = subprocess.Popen(
            [sys.executable, "-m", "app.services.radio_generator"],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=None,
            stderr=None,
        )
        app.state.radio_live_subprocess = radio_proc
        log.info(
            "Rádio live autostart: subprocess pid=%s (python -m app.services.radio_generator)",
            radio_proc.pid,
        )

    yield

    if radio_proc is not None:
        log.info("A terminar subprocess da rádio live (pid=%s).", radio_proc.pid)
        radio_proc.terminate()
        try:
            radio_proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            radio_proc.kill()
            radio_proc.wait(timeout=3)

    log.info("Encerrando aplicação.")


app = FastAPI(
    title="Radio MIDI — streaming local",
    description=(
        "Serviço de streaming contínuo (audio/mpeg) para vários clientes HTTP, "
        "com rádio aleatória e playlists por dispositivo."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(api_router)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def index_page() -> FileResponse:
    """Interface web (HTML/CSS/JS estático, estilo Spotify)."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health(request: Request) -> dict:
    """Saúde do serviço e quantidade de faixas indexadas."""
    lib = getattr(request.app.state, "library", None)
    if lib is None:
        raise HTTPException(status_code=503, detail="Biblioteca não inicializada.")
    ok = len(lib.songs) > 0
    return {
        "status": "ok" if ok else "degraded",
        "tracks": len(lib.songs),
        "music_dir": str(lib.music_root),
    }
