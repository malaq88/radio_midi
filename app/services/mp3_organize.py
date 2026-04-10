"""
Organização de ficheiros MP3 por metadados ID3: artista / álbum / faixa.

Executado de preferência via asyncio.to_thread para não bloquear o event loop.
"""

from __future__ import annotations

import logging
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.mp3 import MP3

logger = logging.getLogger(__name__)

UNKNOWN_ARTIST = "Unknown Artist"
UNKNOWN_ALBUM = "Unknown Album"
_MAX_DIR_LEN = 120
_MAX_TITLE_LEN = 100


@dataclass(frozen=True)
class Mp3Tags:
    artist: str
    album: str
    title: str
    track_display: str
    cover_data: bytes | None = None
    cover_mime: str | None = None


def _first_tag(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        if not value:
            return None
        value = value[0]
    s = str(value).strip()
    return s or None


def _id3_text(frame) -> str | None:
    if frame is None:
        return None
    if hasattr(frame, "text") and frame.text:
        return str(frame.text[0]).strip() or None
    return str(frame).strip() or None


def format_track_number(raw: str | None) -> str:
    """Normaliza TRCK (ex. '3/12') para prefixo '03'."""
    if not raw:
        return "00"
    part = str(raw).split("/")[0].strip()
    try:
        return f"{int(part):02d}"
    except ValueError:
        digits = "".join(c for c in part if c.isdigit())
        if digits:
            try:
                n = int(digits)
                return f"{min(n, 999):02d}"
            except ValueError:
                pass
    return "00"


def sanitize_fs_component(name: str, *, max_len: int = _MAX_DIR_LEN) -> str:
    """
    Remove caracteres inválidos e normaliza Unicode (NFKD).

    Adequado para um segmento de pasta ou parte do nome do ficheiro.
    """
    if not name or not str(name).strip():
        return "unknown"
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("/", "_").replace("\\", "_")
    s = re.sub(r'[<>:"|?*\x00-\x1f]', "_", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    if not s:
        s = "unknown"
    return s[:max_len]


def read_mp3_metadata(path: Path, *, title_fallback: str) -> Mp3Tags:
    """
    Lê tags EasyID3 e frames ID3 clássicos; extrai a primeira imagem APIC disponível.
    """
    artist = album = title = track_raw = None
    cover_data: bytes | None = None
    cover_mime: str | None = None

    try:
        easy = MutagenFile(path, easy=True)
        if easy is not None:
            artist = _first_tag(easy.get("artist"))
            album = _first_tag(easy.get("album"))
            title = _first_tag(easy.get("title"))
            track_raw = _first_tag(easy.get("tracknumber"))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Mutagen easy tags (%s): %s", path.name, exc)

    try:
        mp3 = MP3(path)
        tags = mp3.tags
        if tags is not None:
            if not artist:
                artist = _id3_text(tags.get("TPE1"))
            if not album:
                album = _id3_text(tags.get("TALB"))
            if not title:
                title = _id3_text(tags.get("TIT2"))
            if not track_raw:
                tr = tags.get("TRCK")
                if tr is not None:
                    track_raw = _id3_text(tr)

            if cover_data is None:
                for key in tags.keys():
                    if str(key).startswith("APIC"):
                        apic = tags[key]
                        cover_data = apic.data
                        cover_mime = getattr(apic, "mime", None)
                        if isinstance(cover_mime, bytes):
                            cover_mime = cover_mime.decode("ascii", errors="ignore")
                        break
    except Exception as exc:  # noqa: BLE001
        logger.debug("Mutagen ID3 (%s): %s", path.name, exc)

    fb = (title_fallback or path.stem or "track").strip()
    final_artist = artist or UNKNOWN_ARTIST
    final_album = album or UNKNOWN_ALBUM
    final_title = title or fb
    track_display = format_track_number(track_raw)

    tags_out = Mp3Tags(
        artist=final_artist,
        album=final_album,
        title=final_title,
        track_display=track_display,
        cover_data=cover_data,
        cover_mime=cover_mime,
    )
    logger.info(
        "Metadados MP3: path=%s artist=%r album=%r title=%r track=%s",
        path.name,
        final_artist,
        final_album,
        final_title,
        track_display,
    )
    return tags_out


def _cover_extension(data: bytes, mime: str | None) -> str:
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if len(data) >= 2 and data[:2] == b"\xff\xd8":
        return ".jpg"
    m = (mime or "").lower()
    if "png" in m:
        return ".png"
    if "jpeg" in m or "jpg" in m:
        return ".jpg"
    return ".jpg"


def _write_cover(album_dir: Path, tags: Mp3Tags, *, overwrite: bool) -> None:
    if not tags.cover_data:
        return
    ext = _cover_extension(tags.cover_data, tags.cover_mime)
    name = "cover.jpg" if ext == ".jpg" else "cover.png"
    album_dir.mkdir(parents=True, exist_ok=True)
    dest = album_dir / name
    if dest.exists() and not overwrite:
        logger.debug("Capa já existe, a manter: %s", dest)
        return
    dest.write_bytes(tags.cover_data)
    logger.info("Capa gravada: %s (%d bytes)", dest, len(tags.cover_data))


def _unique_file(dest: Path, *, overwrite: bool) -> Path:
    if overwrite and dest.exists():
        dest.unlink()
        return dest
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    for i in range(1, 1000):
        cand = parent / f"{stem} ({i}){suffix}"
        if not cand.exists():
            return cand
    raise OSError("Não foi possível encontrar nome de ficheiro livre.")


def _prune_empty_dir_chain(start_dir: Path, music_root: Path) -> None:
    """Remove pastas vazias a partir da antiga pasta do ficheiro (ex. após ZIP)."""
    root = music_root.resolve()
    cur = start_dir.resolve()
    while True:
        if cur == root:
            break
        try:
            if not cur.is_relative_to(root):
                break
        except AttributeError:
            try:
                cur.relative_to(root)
            except ValueError:
                break
        if not cur.is_dir():
            break
        try:
            if any(cur.iterdir()):
                break
        except OSError:
            break
        try:
            parent = cur.parent
            cur.rmdir()
            cur = parent
        except OSError:
            break


def organize_mp3_file(
    src: Path,
    music_root: Path,
    *,
    overwrite: bool,
    extract_cover: bool = True,
    title_fallback: str | None = None,
    skip_if_already_canonical: bool = False,
) -> str:
    """
    Move `src` para music_root/{Artist}/{Album}/{NN} - {Title}.mp3.

    `src` pode estar fora de `music_root` (ex. ficheiro temporário).

    Devolve o caminho relativo POSIX final.
    """
    music_root = music_root.resolve()
    src = src.resolve()
    if not src.is_file():
        raise FileNotFoundError(src)

    fb = title_fallback or src.stem
    tags = read_mp3_metadata(src, title_fallback=fb)

    safe_artist = sanitize_fs_component(tags.artist, max_len=_MAX_DIR_LEN)
    safe_album = sanitize_fs_component(tags.album, max_len=_MAX_DIR_LEN)
    safe_title = sanitize_fs_component(tags.title, max_len=_MAX_TITLE_LEN)
    if safe_title.lower().endswith(".mp3"):
        safe_title = safe_title[:-4]

    filename = f"{tags.track_display} - {safe_title}.mp3"
    if len(filename) > 220:
        filename = filename[:216] + ".mp3"

    album_dir = music_root / safe_artist / safe_album
    canonical = album_dir / filename

    if skip_if_already_canonical:
        try:
            if src.resolve() == canonical.resolve():
                rel_skip = src.relative_to(music_root).as_posix()
                logger.info("Já na localização canónica (sem mover): %s", rel_skip)
                album_dir.mkdir(parents=True, exist_ok=True)
                if extract_cover:
                    try:
                        _write_cover(album_dir, tags, overwrite=overwrite)
                    except OSError as exc:
                        logger.warning("Falha ao gravar capa para %s: %s", album_dir, exc)
                return rel_skip
        except (OSError, ValueError):
            pass

    dest = _unique_file(canonical, overwrite=overwrite)

    album_dir.mkdir(parents=True, exist_ok=True)
    old_rel = _try_relative_to(src, music_root)
    old_parent = src.parent

    shutil.move(str(src), str(dest))

    if extract_cover:
        try:
            _write_cover(album_dir, tags, overwrite=overwrite)
        except OSError as exc:
            logger.warning("Falha ao gravar capa para %s: %s", album_dir, exc)

    new_rel = dest.relative_to(music_root).as_posix()
    logger.info(
        "MP3 organizado: %s -> %s",
        old_rel or str(src),
        new_rel,
    )

    if old_rel:
        _prune_empty_dir_chain(old_parent, music_root)

    return new_rel


def _try_relative_to(path: Path, root: Path) -> str | None:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def organize_uploaded_files(
    relative_paths: list[str],
    music_root: Path,
    *,
    overwrite: bool,
    extract_cover: bool = True,
) -> list[str]:
    """
    Organiza cada MP3 já presente sob music_root (ex. após extração ZIP).

    Ignora entradas em falta; regista erros e mantém o caminho original em caso de falha.
    """
    music_root = music_root.resolve()
    out: list[str] = []
    for rel in relative_paths:
        path = (music_root / rel).resolve()
        try:
            path.relative_to(music_root)
        except ValueError:
            logger.warning("Ignorado (fora da biblioteca): %s", rel)
            out.append(rel.replace("\\", "/"))
            continue
        if not path.is_file():
            logger.warning("Ignorado (não é ficheiro): %s", rel)
            out.append(rel.replace("\\", "/"))
            continue
        try:
            new_rel = organize_mp3_file(
                path,
                music_root,
                overwrite=overwrite,
                extract_cover=extract_cover,
                title_fallback=path.stem,
            )
            out.append(new_rel)
        except Exception:
            logger.exception("Falha ao organizar %s; a manter localização original.", rel)
            out.append(rel.replace("\\", "/"))
    return out


def reorganize_entire_library(
    music_root: Path,
    *,
    overwrite: bool = False,
    extract_cover: bool = True,
) -> tuple[list[str], list[tuple[str, str]]]:
    """
    Percorre todos os .mp3 sob `music_root` e aplica a mesma árvore Artista/Álbum/faixa.

    Ficheiros que já estão no caminho canónico (tags + nome esperado) são ignorados no move,
    mas podem receber capa embutida.

    Devolve (lista de caminhos relativos finais, lista de (caminho, erro)).
    """
    music_root = music_root.resolve()
    if not music_root.is_dir():
        raise FileNotFoundError(music_root)

    snapshot = sorted(
        {p.resolve() for p in music_root.rglob("*.mp3") if p.is_file()},
        key=lambda p: str(p).casefold(),
    )
    ok: list[str] = []
    errors: list[tuple[str, str]] = []

    logger.info(
        "Reorganização em massa: %d ficheiro(s) .mp3 em %s",
        len(snapshot),
        music_root,
    )

    for path in snapshot:
        if not path.is_file():
            continue
        try:
            new_rel = organize_mp3_file(
                path,
                music_root,
                overwrite=overwrite,
                extract_cover=extract_cover,
                title_fallback=path.stem,
                skip_if_already_canonical=True,
            )
            ok.append(new_rel)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Reorganização falhou: %s", path)
            errors.append((str(path), str(exc)))

    logger.info(
        "Reorganização terminada: %d processado(s), %d erro(s)",
        len(ok),
        len(errors),
    )
    return ok, errors
