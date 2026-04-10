"""
Gravação segura de MP3 e extração de ZIP (apenas .mp3, sem path traversal).
"""

from __future__ import annotations

import logging
import re
import zipfile
from pathlib import Path

import aiofiles

logger = logging.getLogger(__name__)

_SEGMENT_RE = re.compile(r"^[\w.\- ]+$", re.UNICODE)
_MAX_SEGMENT_LEN = 120
_MAX_REL_PARTS = 32


def sanitize_path_segment(segment: str) -> str | None:
    """Um único componente de caminho (sem /)."""
    s = segment.strip()
    if not s or s in (".", ".."):
        return None
    if len(s) > _MAX_SEGMENT_LEN:
        s = s[:_MAX_SEGMENT_LEN]
    if not _SEGMENT_RE.match(s):
        s = re.sub(r"[^\w.\- ]", "_", s, flags=re.UNICODE).strip("._- ") or None
    if not s or s in (".", ".."):
        return None
    return s


def sanitize_relative_mp3_path(rel: str) -> str | None:
    """Caminho relativo `pasta/faixa.mp3`; rejeita `..` e não-.mp3."""
    if not rel or not rel.strip():
        return None
    norm = rel.replace("\\", "/").strip("/")
    parts: list[str] = []
    for raw in norm.split("/"):
        raw = raw.strip()
        if raw in ("", ".", ".."):
            return None
        seg = sanitize_path_segment(raw)
        if seg is None:
            return None
        parts.append(seg)
    if len(parts) > _MAX_REL_PARTS:
        return None
    if not parts[-1].lower().endswith(".mp3"):
        return None
    return "/".join(parts)


def looks_like_mp3_header(chunk: bytes) -> bool:
    if len(chunk) < 2:
        return False
    if chunk[:3] == b"ID3":
        return True
    for i in range(min(2048, len(chunk) - 1)):
        if chunk[i] == 0xFF and (chunk[i + 1] & 0xE0) == 0xE0:
            return True
    return False


async def save_stream_to_file(
    read_chunk,
    dest: Path,
    *,
    max_bytes: int,
    validate_mp3_header: bool,
) -> int:
    total = 0
    header_checked = False
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(dest, "wb") as handle:
        while True:
            data = await read_chunk()
            if not data:
                break
            if not header_checked:
                header_checked = True
                peek = data[: min(4096, len(data))]
                if validate_mp3_header and not looks_like_mp3_header(peek):
                    await handle.close()
                    dest.unlink(missing_ok=True)
                    raise ValueError("O conteúdo não parece ser MP3 (cabeçalho inválido).")
            total += len(data)
            if total > max_bytes:
                await handle.close()
                dest.unlink(missing_ok=True)
                raise ValueError(f"Ficheiro excede o limite de {max_bytes} bytes.")
            await handle.write(data)
    if total == 0 or not header_checked:
        dest.unlink(missing_ok=True)
        raise ValueError("Ficheiro vazio ou inválido.")
    return total


def extract_zip_mp3_only(
    zip_path: Path,
    music_root: Path,
    *,
    overwrite: bool,
    max_uncompressed_total: int,
) -> tuple[list[str], list[tuple[str, str]]]:
    music_root = music_root.resolve()
    uploaded: list[str] = []
    skipped: list[tuple[str, str]] = []
    running_total = 0

    try:
        zf = zipfile.ZipFile(zip_path, "r")
    except zipfile.BadZipFile:
        return [], [("(zip)", "ficheiro ZIP inválido ou corrompido")]

    with zf:
        for info in zf.infolist():
            if info.is_dir():
                continue

            safe_rel = sanitize_relative_mp3_path(info.filename)
            if safe_rel is None:
                skipped.append((info.filename, "caminho inválido ou não é .mp3"))
                continue

            target = (music_root / safe_rel).resolve()
            try:
                target.relative_to(music_root)
            except ValueError:
                skipped.append((info.filename, "path traversal bloqueado"))
                continue

            if target.exists() and not overwrite:
                skipped.append((info.filename, "ficheiro já existe (overwrite=false)"))
                continue

            if info.file_size > max_uncompressed_total:
                skipped.append((info.filename, "entrada ZIP maior que o limite descomprimido global"))
                continue

            if running_total + info.file_size > max_uncompressed_total:
                skipped.append((info.filename, "limite descomprimido acumulado excedido"))
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            file_written = 0
            aborted = False
            try:
                try:
                    src_cm = zf.open(info, "r")
                except RuntimeError as exc:
                    skipped.append((info.filename, f"entrada ilegível ou encriptada: {exc}"))
                    target.unlink(missing_ok=True)
                    continue
                with src_cm as src, open(target, "wb") as out:
                    first = True
                    while True:
                        chunk = src.read(65536)
                        if not chunk:
                            break
                        if first:
                            first = False
                            peek = chunk[: min(4096, len(chunk))]
                            if not looks_like_mp3_header(peek):
                                skipped.append((info.filename, "conteúdo não parece MP3"))
                                aborted = True
                                break
                        if running_total + file_written + len(chunk) > max_uncompressed_total:
                            skipped.append((info.filename, "limite descomprimido durante escrita"))
                            aborted = True
                            break
                        out.write(chunk)
                        file_written += len(chunk)
                if aborted:
                    target.unlink(missing_ok=True)
                elif file_written == 0:
                    target.unlink(missing_ok=True)
                    skipped.append((info.filename, "entrada vazia"))
                else:
                    running_total += file_written
                    uploaded.append(safe_rel)
                    logger.info("Extraído do ZIP: %s", safe_rel)
            except OSError as exc:
                skipped.append((info.filename, f"erro de I/O: {exc}"))
                target.unlink(missing_ok=True)

    return uploaded, skipped
