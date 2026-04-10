"""
Gerador de rádio 24/7: FFmpeg lê uma playlist em shuffle, re-encode para MP3 contínuo
e um servidor HTTP local faz fan-out para vários clientes.

Não corre dentro dos handlers FastAPI — executar como processo dedicado:

    cd /raiz/do/projeto && source .venv/bin/activate
    python -m app.services.radio_generator

Requisitos: `ffmpeg` no PATH, `MUSIC_DIR` com .mp3 (mesmas regras que a biblioteca).

O FastAPI expõe GET /radio/live como proxy para RADIO_LIVE_STREAM_URL (por defeito
http://127.0.0.1:9000/stream).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    root = logging.getLogger()
    if not root.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
        root.addHandler(h)
    root.setLevel(logging.INFO)


def _iter_mp3_paths(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() == ".mp3":
            try:
                p.resolve().relative_to(root.resolve())
            except ValueError:
                continue
            out.append(p)
    return sorted(out, key=lambda x: str(x).lower())


def _duration_seconds(path: Path) -> float:
    try:
        from mutagen.mp3 import MP3

        info = MP3(str(path)).info
        if info.length and info.length > 0:
            return float(info.length)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Duração por defeito para %s: %s", path, exc)
    return 180.0


def _escape_concat_path(path: Path) -> str:
    s = str(path.resolve())
    return s.replace("'", "'\\''")


def _write_ffconcat(paths: list[Path], dest: Path) -> None:
    lines = ["ffconcat version 1.0"]
    for p in paths:
        lines.append("file '" + _escape_concat_path(p) + "'")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _shuffle_avoid_adjacent_repeat(paths: list[Path], last_played: Path | None) -> list[Path]:
    if len(paths) <= 1:
        return paths[:]
    arr = paths[:]
    random.shuffle(arr)
    if last_played is not None and arr[0] == last_played:
        arr[0], arr[1] = arr[1], arr[0]
    return arr


@dataclass
class LiveRadioState:
    """Estado partilhado para GET /status (JSON)."""

    started_at: float = field(default_factory=time.monotonic)
    ffmpeg_cycles: int = 0
    ffmpeg_pid: int | None = None
    last_ffmpeg_returncode: int | None = None
    last_error: str | None = None
    connected_clients: int = 0
    playlist_paths: list[str] = field(default_factory=list)
    durations_sec: list[float] = field(default_factory=list)
    round_started_at: float = 0.0
    last_round_last_path: str | None = None
    music_dir: str = ""
    bytes_broadcast: int = 0

    def to_public_dict(self) -> dict[str, Any]:
        now = time.monotonic()
        elapsed_round = now - self.round_started_at if self.round_started_at else 0.0
        current = self._estimate_now_playing(elapsed_round)
        return {
            "service": "radio_midi_live",
            "ok": True,
            "uptime_seconds": round(now - self.started_at, 1),
            "music_dir": self.music_dir,
            "ffmpeg_pid": self.ffmpeg_pid,
            "ffmpeg_cycles": self.ffmpeg_cycles,
            "last_ffmpeg_returncode": self.last_ffmpeg_returncode,
            "connected_clients": self.connected_clients,
            "playlist_tracks": len(self.playlist_paths),
            "round_elapsed_seconds": round(elapsed_round, 1),
            "bytes_broadcast": self.bytes_broadcast,
            "now_playing": current,
            "last_error": self.last_error,
        }

    def _estimate_now_playing(self, elapsed_round: float) -> dict[str, Any] | None:
        if not self.playlist_paths or not self.durations_sec:
            return None
        if elapsed_round < 0:
            return None
        acc = 0.0
        for i, d in enumerate(self.durations_sec):
            acc += d
            if elapsed_round < acc:
                return {
                    "index": i,
                    "path": self.playlist_paths[i],
                    "title": Path(self.playlist_paths[i]).stem,
                }
        return {
            "index": len(self.playlist_paths) - 1,
            "path": self.playlist_paths[-1],
            "title": Path(self.playlist_paths[-1]).stem,
        }


class StreamBroadcaster:
    """Um produtor (FFmpeg stdout) → N filas (clientes HTTP)."""

    def __init__(self, max_queue: int = 96) -> None:
        self._max_queue = max_queue
        self._queues: list[asyncio.Queue[bytes | None]] = []

    def subscribe(self) -> asyncio.Queue[bytes | None]:
        q: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=self._max_queue)
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[bytes | None]) -> None:
        try:
            self._queues.remove(q)
        except ValueError:
            pass

    async def broadcast(self, chunk: bytes) -> None:
        for q in list(self._queues):
            try:
                q.put_nowait(chunk)
            except asyncio.QueueFull:
                logger.warning("Cliente lento removido da rádio (fila cheia).")
                self.unsubscribe(q)

    def subscriber_count(self) -> int:
        return len(self._queues)


async def _pump_ffmpeg(
    proc: asyncio.subprocess.Process,
    broadcaster: StreamBroadcaster,
    state: LiveRadioState,
) -> None:
    assert proc.stdout
    try:
        while True:
            chunk = await proc.stdout.read(65536)
            if not chunk:
                break
            state.bytes_broadcast += len(chunk)
            await broadcaster.broadcast(chunk)
    except Exception as exc:  # noqa: BLE001
        state.last_error = str(exc)
        logger.exception("Erro ao ler stdout do FFmpeg")


async def _drain_stderr(proc: asyncio.subprocess.Process, state: LiveRadioState) -> None:
    assert proc.stderr
    try:
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            text = line.decode(errors="replace").rstrip()
            if text:
                logger.info("[ffmpeg] %s", text)
                low = text.lower()
                if "error" in low or "invalid" in low:
                    state.last_error = text[:500]
    except Exception as exc:  # noqa: BLE001
        logger.debug("stderr ffmpeg: %s", exc)


async def _run_one_ffmpeg_round(
    concat_file: Path,
    broadcaster: StreamBroadcaster,
    state: LiveRadioState,
) -> int:
    if shutil.which("ffmpeg") is None:
        state.last_error = "ffmpeg não encontrado no PATH"
        logger.error(state.last_error)
        await asyncio.sleep(10)
        return -1

    cmd = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "info",
        "-re",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c:a",
        "libmp3lame",
        "-b:a",
        "192k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-f",
        "mp3",
        "-",
    ]
    logger.info("A iniciar FFmpeg (ciclo %d): %d ficheiros na lista", state.ffmpeg_cycles + 1, len(state.playlist_paths))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=1024 * 1024,
    )
    state.ffmpeg_pid = proc.pid
    stderr_task = asyncio.create_task(_drain_stderr(proc, state))
    code_fut = asyncio.create_task(proc.wait())
    pump_fut = asyncio.create_task(_pump_ffmpeg(proc, broadcaster, state))
    await asyncio.wait({pump_fut, code_fut}, return_when=asyncio.ALL_COMPLETED)
    stderr_task.cancel()
    try:
        await stderr_task
    except asyncio.CancelledError:
        pass
    rc = await code_fut
    state.last_ffmpeg_returncode = rc if rc is not None else -1
    state.ffmpeg_pid = None
    state.ffmpeg_cycles += 1
    logger.warning(
        "FFmpeg terminou (returncode=%s); a reiniciar novo ciclo em breve.",
        state.last_ffmpeg_returncode,
    )
    return int(state.last_ffmpeg_returncode or 0)


async def radio_loop(music_root: Path, broadcaster: StreamBroadcaster, state: LiveRadioState) -> None:
    last_end: Path | None = None
    if music_root.is_dir():
        state.music_dir = str(music_root.resolve())
    while True:
        try:
            paths = _iter_mp3_paths(music_root)
            if not paths:
                state.last_error = "Sem ficheiros .mp3 em MUSIC_DIR"
                logger.error("%s — a aguardar 60s", state.last_error)
                await asyncio.sleep(60)
                continue

            ordered = _shuffle_avoid_adjacent_repeat(paths, last_end)
            last_end = ordered[-1]
            state.last_round_last_path = str(last_end)

            durations = [_duration_seconds(p) for p in ordered]
            state.playlist_paths = [str(p) for p in ordered]
            state.durations_sec = durations
            state.round_started_at = time.monotonic()

            fd, tmp_name = tempfile.mkstemp(suffix=".ffconcat")
            os.close(fd)
            tmp_path = Path(tmp_name)
            try:
                _write_ffconcat(ordered, tmp_path)
                await _run_one_ffmpeg_round(tmp_path, broadcaster, state)
            finally:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

            await asyncio.sleep(0.3)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            state.last_error = str(exc)
            logger.exception("Erro no ciclo da rádio")
            await asyncio.sleep(5)


def _parse_request_line(raw: bytes) -> tuple[str, str] | None:
    try:
        line = raw.decode("ascii", errors="ignore").strip()
    except Exception:
        return None
    parts = line.split()
    if len(parts) < 2:
        return None
    return parts[0].upper(), parts[1].split("?", 1)[0]


async def _drain_http_headers(reader: asyncio.StreamReader) -> None:
    for _ in range(64):
        line = await reader.readline()
        if not line or line in (b"\r\n", b"\n"):
            break


async def handle_http_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    broadcaster: StreamBroadcaster,
    state: LiveRadioState,
) -> None:
    peer = writer.get_extra_info("peername")
    try:
        first = await reader.readline()
        parsed = _parse_request_line(first)
        if not parsed:
            writer.write(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
            await writer.drain()
            return
        method, path = parsed
        await _drain_http_headers(reader)

        if path not in ("/", "/stream", "/status"):
            writer.write(b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n")
            await writer.drain()
            return

        if path == "/status":
            body = json.dumps(state.to_public_dict(), ensure_ascii=False).encode("utf-8")
            header = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json; charset=utf-8\r\n"
                b"Cache-Control: no-store\r\n"
                b"Connection: close\r\n"
                b"Content-Length: "
                + str(len(body)).encode()
                + b"\r\n\r\n"
            )
            writer.write(header + body)
            await writer.drain()
            return

        if method == "HEAD":
            writer.write(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: audio/mpeg\r\n"
                b"Cache-Control: no-store, no-cache, must-revalidate\r\n"
                b"Connection: close\r\n\r\n"
            )
            await writer.drain()
            return

        if method != "GET":
            writer.write(b"HTTP/1.1 405 Method Not Allowed\r\nConnection: close\r\n\r\n")
            await writer.drain()
            return

        state.connected_clients += 1
        logger.info("Cliente de stream ligado desde %s (total=%d)", peer, state.connected_clients)
        writer.write(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: audio/mpeg\r\n"
            b"Cache-Control: no-store, no-cache, must-revalidate\r\n"
            b"Pragma: no-cache\r\n"
            b"X-Content-Type-Options: nosniff\r\n"
            b"Connection: close\r\n\r\n"
        )
        await writer.drain()

        q = broadcaster.subscribe()
        try:
            while True:
                chunk = await q.get()
                if chunk is None:
                    break
                writer.write(chunk)
                await writer.drain()
        except (BrokenPipeError, ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            broadcaster.unsubscribe(q)
            state.connected_clients = max(0, state.connected_clients - 1)
            logger.info("Cliente de stream desligado desde %s (total=%d)", peer, state.connected_clients)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Cliente HTTP %s: %s", peer, exc)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def async_main() -> None:
    _configure_logging()
    from app.config import settings

    music_root = settings.music_dir
    host = settings.radio_live_bind_host
    port = settings.radio_live_bind_port

    if not music_root.is_dir():
        logger.error("MUSIC_DIR não é uma pasta: %s", music_root)
        sys.exit(1)

    broadcaster = StreamBroadcaster()
    state = LiveRadioState()
    state.music_dir = str(music_root.resolve())

    async def client_cb(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await handle_http_client(reader, writer, broadcaster, state)

    server = await asyncio.start_server(client_cb, host, port, limit=2**16)
    addr = ", ".join(str(s.getsockname()) for s in server.sockets or [])
    logger.info("Rádio 24/7 à escuta em http://%s (stream=/stream status=/status)", addr)

    radio_task = asyncio.create_task(radio_loop(music_root, broadcaster, state))
    try:
        async with server:
            await server.serve_forever()
    finally:
        radio_task.cancel()
        try:
            await radio_task
        except asyncio.CancelledError:
            pass


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("Encerrado pelo utilizador.")


if __name__ == "__main__":
    main()
