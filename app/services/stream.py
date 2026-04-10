"""
Streaming contínuo com fila, agregação de bytes e junção suave entre faixas.

Cada cliente HTTP tem o seu próprio produtor (fila + leitura em disco) e consome em loop,
sem fechar a ligação entre músicas — apenas bytes consecutivos no mesmo corpo da resposta.

Modos: shuffle com histórico (evita repetir as últimas N faixas) e reprodução ordenada em ciclo.
"""

from __future__ import annotations

import asyncio
import logging
import random
import secrets
from collections import deque
from collections.abc import AsyncIterator
from enum import Enum
from pathlib import Path

import aiofiles

from app.config import settings
from app.models.song import Song
from app.services.library_index import sort_songs_by_track_filename

logger = logging.getLogger(__name__)

# Cache do ficheiro opcional de silêncio entre faixas (lido uma vez por processo).
_gap_loaded: bool = False
_gap_payload: bytes = b""


class PlaylistStreamMode(str, Enum):
    """Como escolher a próxima faixa no stream contínuo."""

    SHUFFLE = "shuffle"
    ORDERED_LOOP = "ordered_loop"


def _get_transition_gap_bytes() -> bytes:
    """Carrega bytes do MP3 de junção, se configurado e existente."""
    global _gap_loaded, _gap_payload
    if _gap_loaded:
        return _gap_payload
    _gap_loaded = True
    path = settings.stream_transition_gap_file
    if path is None:
        return _gap_payload
    if not path.is_file():
        logger.warning("stream_transition_gap_file inexistente (padding desativado): %s", path)
        return _gap_payload
    try:
        _gap_payload = path.read_bytes()
        logger.info(
            "Padding entre faixas ativo: %d bytes (%s)",
            len(_gap_payload),
            path,
        )
    except OSError as exc:
        logger.warning("Não foi possível ler padding entre faixas: %s", exc)
    return _gap_payload


async def _emit_coalesce_chunks(
    coalesce: bytearray,
    emit_size: int,
    queue: asyncio.Queue[bytes],
) -> None:
    while len(coalesce) >= emit_size:
        await queue.put(bytes(coalesce[:emit_size]))
        del coalesce[:emit_size]


async def _read_file_in_chunks(path: Path, chunk_size: int) -> AsyncIterator[bytes]:
    """Leitor simples (usado apenas se precisarmos de fallback isolado)."""
    try:
        async with aiofiles.open(path, "rb") as handle:
            while True:
                chunk = await handle.read(chunk_size)
                if not chunk:
                    break
                yield chunk
    except OSError as exc:
        logger.error("Erro ao ler arquivo para stream: %s — %s", path, exc)
        raise


async def stream_playlist_forever(
    candidates: list[Song],
    *,
    label: str,
    chunk_size: int | None = None,
    mode: PlaylistStreamMode = PlaylistStreamMode.SHUFFLE,
    avoid_repeat_last_n: int = 5,
) -> AsyncIterator[bytes]:
    """
    Rádio contínua com fila, agregação e padding opcional.

    * SHUFFLE: `Random` por ligação (semente de `secrets`) e fila das últimas
      `avoid_repeat_last_n` faixas para reduzir repetições imediatas.
    * ORDERED_LOOP: ordem por prefixo numérico no nome do ficheiro; ao fim do álbum volta ao início.
    """
    read_size = chunk_size or settings.stream_chunk_size
    emit_size = settings.stream_emit_chunk_size
    qmax = settings.stream_queue_max_chunks
    gap = _get_transition_gap_bytes()

    if not candidates:
        logger.error("stream_playlist_forever(%s): lista de candidatos vazia.", label)
        return

    queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=qmax)

    async def producer() -> None:
        coalesce = bytearray()
        rng = random.Random(secrets.randbits(64))
        n_avoid = max(0, min(avoid_repeat_last_n, 50))
        recent: deque[str] = deque(maxlen=n_avoid if n_avoid > 0 else 1)

        if mode == PlaylistStreamMode.ORDERED_LOOP:
            ordered = sort_songs_by_track_filename(list(candidates))
            idx = 0
        else:
            ordered = []
            idx = 0

        def pick_shuffle() -> Song:
            forbidden = set(recent)
            pool = [c for c in candidates if str(c.path.resolve()) not in forbidden]
            if len(pool) < max(1, len(candidates) // 3) and len(candidates) > 1:
                pool = list(candidates)
            if not pool:
                pool = list(candidates)
            pick = rng.choice(pool)
            if n_avoid > 0:
                recent.append(str(pick.path.resolve()))
            return pick

        try:
            while True:
                if mode == PlaylistStreamMode.ORDERED_LOOP:
                    song = ordered[idx % len(ordered)]
                    idx += 1
                else:
                    song = pick_shuffle()

                try:
                    rel = str(song.path.relative_to(settings.music_dir.resolve()))
                except ValueError:
                    rel = song.filename

                logger.info(
                    "[%s] Iniciando faixa: %s (playlist_group=%s, mode=%s)",
                    label,
                    rel,
                    song.playlist_group,
                    mode.value,
                )

                try:
                    async with aiofiles.open(song.path, "rb") as handle:
                        while True:
                            chunk = await handle.read(read_size)
                            if not chunk:
                                break
                            coalesce.extend(chunk)
                            await _emit_coalesce_chunks(coalesce, emit_size, queue)
                except OSError as exc:
                    logger.warning("[%s] Erro ao abrir/ler %s: %s — próxima faixa.", label, song.path, exc)
                    continue

                if gap:
                    coalesce.extend(gap)
                    await _emit_coalesce_chunks(coalesce, emit_size, queue)

        except asyncio.CancelledError:
            logger.debug("[%s] Produtor de stream cancelado.", label)
            raise

    task = asyncio.create_task(producer(), name=f"radio-producer:{label}")
    try:
        while True:
            chunk = await queue.get()
            yield chunk
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


__all__ = ["stream_playlist_forever", "PlaylistStreamMode", "_read_file_in_chunks"]
