"""
Upload de MP3 e ZIP com API key, validação, organização por ID3 e re-scan da biblioteca.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Annotated

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile

from app.config import settings
from app.deps import get_library
from app.models.upload import SkippedItem, UploadResult
from app.security_upload import require_upload_api_key
from app.services.library import MusicLibrary
from app.services.mp3_organize import organize_mp3_file, organize_uploaded_files
from app.services.upload_storage import (
    sanitize_path_segment,
    save_stream_to_file,
    extract_zip_mp3_only,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def _refresh_library(request: Request) -> None:
    lib = getattr(request.app.state, "library", None)
    if lib is not None:
        lib.scan()


def _title_fallback_from_request(filename: str, relative_path: str | None) -> str:
    base = Path(filename).stem
    if relative_path and relative_path.strip():
        hint = Path(relative_path.strip().replace("\\", "/")).stem
        if hint:
            return hint
    return base


@router.post("", response_model=UploadResult)
async def upload_single_mp3(
    request: Request,
    library: MusicLibrary = Depends(get_library),
    _: None = Depends(require_upload_api_key),
    file: UploadFile = File(..., description="Ficheiro .mp3"),
    relative_path: Annotated[
        str | None,
        Form(
            description="Opcional: sugerir título quando as tags não têm título (último segmento do caminho).",
        ),
    ] = None,
    overwrite: Annotated[bool, Query(description="Se true, substitui ficheiro/capa no destino.")] = False,
) -> UploadResult:
    """
    Grava o MP3 temporariamente, lê ID3 e move para `{Artist}/{Album}/{NN} - {Title}.mp3`.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nome de ficheiro em falta.")

    name = Path(file.filename).name
    if not name.lower().endswith(".mp3"):
        name = Path(name).stem + ".mp3"
    seg = sanitize_path_segment(name)
    if seg is None or not seg.lower().endswith(".mp3"):
        raise HTTPException(status_code=400, detail="Nome de ficheiro inválido após sanitização.")

    if relative_path and relative_path.strip():
        rp = relative_path.strip().replace("\\", "/")
        if ".." in rp.split("/"):
            raise HTTPException(status_code=400, detail="relative_path inválido.")

    root = library.music_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    title_fb = _title_fallback_from_request(file.filename, relative_path)

    ip = _client_ip(request)
    logger.info("Upload MP3 iniciado (organização por ID3): %s desde %s", seg, ip)

    fd, tmp_name = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        Path(tmp_name).chmod(0o600)
    except OSError:
        pass
    tmp_path = Path(tmp_name)

    async def read_chunk() -> bytes:
        return await file.read(65536)

    try:
        try:
            await save_stream_to_file(
                read_chunk,
                tmp_path,
                max_bytes=settings.upload_max_mp3_bytes,
                validate_mp3_header=True,
            )
        except ValueError as exc:
            logger.warning("Upload MP3 rejeitado: %s", exc)
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        final_rel = await asyncio.to_thread(
            organize_mp3_file,
            tmp_path,
            root,
            overwrite=overwrite,
            extract_cover=True,
            title_fallback=title_fb,
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    _refresh_library(request)
    logger.info("Upload MP3 concluído: %s (%s)", final_rel, ip)
    return UploadResult(
        success=True,
        message="Ficheiro gravado, organizado por artista/álbum e biblioteca atualizada.",
        files=[final_rel.replace("\\", "/")],
        skipped=[],
    )


@router.post("/zip", response_model=UploadResult)
async def upload_zip_album(
    request: Request,
    library: MusicLibrary = Depends(get_library),
    _: None = Depends(require_upload_api_key),
    file: UploadFile = File(..., description="Arquivo .zip contendo apenas .mp3"),
    overwrite: Annotated[bool, Query(description="Se true, substitui ficheiros e capas existentes.")] = False,
) -> UploadResult:
    """
    Extrai .mp3 do ZIP e reorganiza cada um para `{Artist}/{Album}/{NN} - {Title}.mp3`.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Envie um ficheiro com extensão .zip.")

    ip = _client_ip(request)
    logger.info("Upload ZIP iniciado: %s desde %s", file.filename, ip)

    root = library.music_root.resolve()
    root.mkdir(parents=True, exist_ok=True)

    tmp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tf:
            tmp = Path(tf.name)

        async def read_zip_chunk() -> bytes:
            return await file.read(65536)

        async with aiofiles.open(tmp, "wb") as out:
            total = 0
            while True:
                chunk = await read_zip_chunk()
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.upload_max_zip_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"ZIP excede {settings.upload_max_zip_bytes} bytes.",
                    )
                await out.write(chunk)

        uploaded, skipped_raw = await asyncio.to_thread(
            extract_zip_mp3_only,
            tmp,
            root,
            overwrite=overwrite,
            max_uncompressed_total=settings.upload_max_zip_uncompressed_bytes,
        )

        skipped = [SkippedItem(path=a, reason=b) for a, b in skipped_raw]

        if skipped_raw and not uploaded and skipped_raw[0][0] == "(zip)":
            return UploadResult(
                success=False,
                message=skipped_raw[0][1],
                files=[],
                skipped=skipped,
            )

        if not uploaded:
            msg = "Nenhum .mp3 extraído; verifique o conteúdo e os caminhos."
            if skipped_raw:
                msg += f" ({len(skipped_raw)} entradas ignoradas.)"
            _refresh_library(request)
            return UploadResult(success=False, message=msg, files=[], skipped=skipped)

        final_paths = await asyncio.to_thread(
            organize_uploaded_files,
            uploaded,
            root,
            overwrite=overwrite,
            extract_cover=True,
        )

        _refresh_library(request)
        logger.info(
            "Upload ZIP concluído: %d ficheiro(s) organizado(s) desde %s",
            len(final_paths),
            ip,
        )
        return UploadResult(
            success=True,
            message=(
                f"{len(final_paths)} ficheiro(s) extraído(s), organizado(s) por ID3; biblioteca atualizada."
            ),
            files=[p.replace("\\", "/") for p in final_paths],
            skipped=skipped,
        )
    except HTTPException:
        raise
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
