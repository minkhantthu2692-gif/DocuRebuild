"""Local font discovery, import and export resolution.

System fonts are read from the directories the operating system installs them
into. Imported fonts are validated, normalised to a plain TrueType/OpenType
file, and stored in the application data folder so the packaged desktop app can
use them without the original file. Nothing here contacts a network service and
no font is installed into the operating system.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from fontTools.ttLib import TTCollection, TTFont
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import ImportedFont, utcnow
from app.schemas.fonts import FontFaceSummary, FontFamilySummary, FontsResponse

logger = logging.getLogger(__name__)

MAX_FONT_BYTES = 20 * 1024 * 1024
MAX_SYSTEM_FONT_BYTES = 64 * 1024 * 1024
MAX_COLLECTION_FACES = 64
SUPPORTED_EXTENSIONS = frozenset({".ttf", ".otf", ".woff", ".woff2"})
_SFNT_HEADERS = (b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1")
_WOFF_HEADERS = (b"wOFF", b"wOF2")
_SYSTEM_CACHE_SECONDS = 300.0

# Characters that could break a Word font name, a PDF style rule or a filename.
_UNSAFE_FAMILY = re.compile(r"[\x00-\x1f\x7f{}<>;\\\"`]")
_UNSAFE_STYLE = re.compile(r"[\x00-\x1f\x7f{}<>;\\\"`]")


@dataclass(frozen=True)
class SystemFace:
    family: str
    style: str
    weight: int
    italic: bool
    path: Path
    index: int
    format: str


@dataclass(frozen=True)
class ExportFace:
    """One face resolved for Word/PDF export."""

    family: str
    style: str
    weight: int
    italic: bool
    path: Path
    index: int
    format: str


_system_lock = threading.Lock()
_system_cache: tuple[tuple[tuple[str, int], ...], float, list[SystemFace]] | None = None


def sanitize_family(value: object) -> str:
    """Return a safe, display-ready font family name from stored JSON."""
    text = str(value or "").strip().strip('"').strip("'")
    text = _UNSAFE_FAMILY.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:160]


def _sanitize_style(value: object) -> str:
    text = str(value or "").strip()
    text = _UNSAFE_STYLE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:80] or "Regular"


def system_font_directories() -> list[Path]:
    """Return existing system font folders.

    ``DOCUREBUILD_SYSTEM_FONT_DIRS`` overrides detection for tests and for a
    custom Windows installation. Set it to an empty string to disable system
    fonts. Paths are separated with the platform path separator.
    """
    override = os.environ.get("DOCUREBUILD_SYSTEM_FONT_DIRS")
    if override is not None:
        candidates = [Path(part.strip()) for part in override.split(os.pathsep) if part.strip()]
        return [folder for folder in candidates if folder.is_dir()]

    if sys.platform == "win32":
        folders: list[Path] = []
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            # Per-user fonts installed through Windows Settings take precedence.
            folders.append(Path(local_app_data) / "Microsoft" / "Windows" / "Fonts")
        windir = os.environ.get("WINDIR") or r"C:\Windows"
        folders.append(Path(windir) / "Fonts")
    elif sys.platform == "darwin":
        folders = [Path.home() / "Library" / "Fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts")]
    else:
        folders = [
            Path.home() / ".local" / "share" / "fonts",
            Path.home() / ".fonts",
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
        ]
    return [folder for folder in folders if folder.is_dir()]


def clear_system_font_cache() -> None:
    global _system_cache
    with _system_lock:
        _system_cache = None


def _directory_signature(folders: list[Path]) -> tuple[tuple[str, int], ...]:
    signature: list[tuple[str, int]] = []
    for folder in folders:
        try:
            signature.append((str(folder), folder.stat().st_mtime_ns))
        except OSError:
            signature.append((str(folder), 0))
    return tuple(signature)


def _name_value(name_table: Any, name_id: int) -> str:
    try:
        return (name_table.getDebugName(name_id) or "").strip()
    except Exception:
        return ""


def _font_metadata(font: TTFont) -> tuple[str, str, int, bool] | None:
    name_table = font.get("name")
    if name_table is None:
        return None
    family = sanitize_family(_name_value(name_table, 16) or _name_value(name_table, 1))
    if not family:
        return None
    style = _sanitize_style(_name_value(name_table, 17) or _name_value(name_table, 2))

    weight = 400
    italic = False
    os2 = font.get("OS/2")
    if os2 is not None:
        try:
            candidate = int(os2.usWeightClass)
            if 1 <= candidate <= 1000:
                weight = candidate
        except (TypeError, ValueError):
            pass
        try:
            italic = bool(int(os2.fsSelection) & 1)
        except (TypeError, ValueError):
            italic = False
    head = font.get("head")
    if head is not None and not italic:
        try:
            italic = bool(int(head.macStyle) & 2)
        except (TypeError, ValueError):
            italic = False
    return family, style, weight, italic


def _faces_from_collection(path: Path) -> Iterator[SystemFace]:
    collection = TTCollection(str(path), lazy=True)
    try:
        for index, font in enumerate(collection.fonts[:MAX_COLLECTION_FACES]):
            metadata = _font_metadata(font)
            if metadata is None:
                continue
            family, style, weight, italic = metadata
            yield SystemFace(family, style, weight, italic, path, index, "ttc")
    finally:
        try:
            collection.close()
        except Exception:
            pass


def _faces_from_file(path: Path) -> Iterator[SystemFace]:
    if path.suffix.lower() == ".ttc":
        yield from _faces_from_collection(path)
        return
    font = TTFont(str(path), lazy=True)
    try:
        metadata = _font_metadata(font)
    finally:
        try:
            font.close()
        except Exception:
            pass
    if metadata is not None:
        family, style, weight, italic = metadata
        yield SystemFace(family, style, weight, italic, path, 0, path.suffix.lower().lstrip("."))


def _scan_system_fonts(folders: list[Path]) -> list[SystemFace]:
    faces: list[SystemFace] = []
    seen: set[tuple[str, str, int, bool]] = set()
    for folder in folders:
        try:
            entries = sorted(folder.iterdir(), key=lambda item: item.name.casefold())
        except OSError:
            logger.debug("System font folder could not be read: %s", folder)
            continue
        for path in entries:
            if not path.is_file() or path.suffix.lower() not in {".ttf", ".otf", ".ttc"}:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size <= 0 or size > MAX_SYSTEM_FONT_BYTES:
                continue
            try:
                discovered = list(_faces_from_file(path))
            except Exception:
                # A damaged or unsupported file must not hide the rest.
                logger.debug("Font file could not be read: %s", path, exc_info=True)
                continue
            for face in discovered:
                key = (face.family.casefold(), face.style.casefold(), face.weight, face.italic)
                if key in seen:
                    continue
                seen.add(key)
                faces.append(face)
    return faces


def list_system_faces(*, force: bool = False) -> list[SystemFace]:
    global _system_cache
    folders = system_font_directories()
    signature = _directory_signature(folders)
    now = time.monotonic()
    with _system_lock:
        cached = _system_cache
    if (
        not force
        and cached is not None
        and cached[0] == signature
        and now - cached[1] < _SYSTEM_CACHE_SECONDS
    ):
        return list(cached[2])

    faces = _scan_system_fonts(folders)
    with _system_lock:
        _system_cache = (signature, now, faces)
    return list(faces)


def _imported_rows(session: Session) -> list[ImportedFont]:
    statement = select(ImportedFont).order_by(
        func.lower(ImportedFont.family),
        ImportedFont.italic,
        ImportedFont.weight,
    )
    return list(session.execute(statement).scalars().all())


def _summary_from_row(row: ImportedFont) -> FontFaceSummary:
    return FontFaceSummary(
        id=row.id,
        family=row.family,
        style=row.style,
        weight=row.weight,
        italic=row.italic,
        source="imported",
        format=row.format,
        file_name=row.file_name,
    )


def _summary_from_system(face: SystemFace) -> FontFaceSummary:
    return FontFaceSummary(
        id=None,
        family=face.family,
        style=face.style,
        weight=face.weight,
        italic=face.italic,
        source="system",
        format=face.format,
    )


def list_fonts(session: Session, *, refresh: bool = False) -> FontsResponse:
    system_faces = list_system_faces(force=refresh)
    imported_rows = _imported_rows(session)

    grouped: dict[str, dict[str, Any]] = {}

    def bucket(family: str) -> dict[str, Any]:
        key = family.casefold()
        entry = grouped.get(key)
        if entry is None:
            entry = {"name": family, "faces": [], "system": False, "imported": False}
            grouped[key] = entry
        return entry

    for face in system_faces:
        entry = bucket(face.family)
        entry["system"] = True
        entry["faces"].append(_summary_from_system(face))

    for row in imported_rows:
        entry = bucket(row.family)
        entry["imported"] = True
        entry["faces"].append(_summary_from_row(row))

    families: list[FontFamilySummary] = []
    for entry in grouped.values():
        source = "mixed" if entry["system"] and entry["imported"] else (
            "imported" if entry["imported"] else "system"
        )
        faces = sorted(
            entry["faces"],
            key=lambda face: (face.italic, face.weight, face.style.casefold()),
        )
        families.append(
            FontFamilySummary(
                name=entry["name"],
                source=source,
                faces=faces,
                available=True,
            )
        )
    families.sort(key=lambda family: family.name.casefold())

    return FontsResponse(
        families=families,
        imported_count=len(imported_rows),
        system_count=len({face.family.casefold() for face in system_faces}),
        system_directories=[str(folder) for folder in system_font_directories()],
    )


def _parse_upload(data: bytes, extension: str) -> tuple[bytes, str, str, int, bool, str]:
    """Validate an upload and return ``(sfnt_bytes, format, family, weight, italic, style)``."""
    header = data[:4]
    if header not in _SFNT_HEADERS and header not in _WOFF_HEADERS:
        raise AppError(422, "font_invalid", "The selected file is not a supported font.")
    if extension not in SUPPORTED_EXTENSIONS:
        raise AppError(422, "font_unsupported", "Choose a TTF, OTF, WOFF or WOFF2 font file.")

    try:
        font = TTFont(io.BytesIO(data), lazy=False)
    except Exception as exc:
        raise AppError(422, "font_invalid", "The font file could not be read.") from exc

    try:
        metadata = _font_metadata(font)
        if metadata is None:
            raise AppError(422, "font_invalid", "The font file has no usable family name.")
        family, style, weight, italic = metadata

        is_woff = header in _WOFF_HEADERS or font.flavor in {"woff", "woff2"}
        if is_woff:
            font.flavor = None
            font.flavorData = None
            try:
                buffer = io.BytesIO()
                font.save(buffer)
            except Exception as exc:
                raise AppError(
                    422,
                    "font_unsupported",
                    "This web font could not be converted. Choose a TTF or OTF file.",
                ) from exc
            sfnt = buffer.getvalue()
        else:
            sfnt = data
    finally:
        try:
            font.close()
        except Exception:
            pass

    if sfnt[:4] == b"OTTO":
        font_format = "otf"
    elif sfnt[:4] in _SFNT_HEADERS:
        font_format = "ttf"
    else:
        raise AppError(422, "font_unsupported", "This font format cannot be embedded.")
    return sfnt, font_format, family, weight, italic, style


def import_font(session: Session, filename: str | None, data: bytes) -> ImportedFont:
    if not data:
        raise AppError(422, "font_empty", "The selected font file is empty.")
    if len(data) > MAX_FONT_BYTES:
        raise AppError(
            422,
            "font_too_large",
            f"Font files must be {MAX_FONT_BYTES // (1024 * 1024)} MB or smaller.",
        )

    original_name = Path(filename or "font").name
    extension = Path(original_name).suffix.lower()
    sfnt, font_format, family, weight, italic, style = _parse_upload(data, extension)
    digest = hashlib.sha256(sfnt).hexdigest()

    existing = session.execute(
        select(ImportedFont).where(ImportedFont.sha256 == digest)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    settings = get_settings()
    settings.fonts_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}.{font_format}"
    target = settings.fonts_dir / stored_name
    temporary = settings.fonts_dir / f".{stored_name}.tmp"
    try:
        temporary.write_bytes(sfnt)
        os.replace(temporary, target)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise AppError(500, "font_save_failed", "The font could not be saved locally.") from exc

    safe_file_name = re.sub(r"[\x00-\x1f\x7f\\/:*?\"<>|]+", "-", original_name).strip()[:255]
    row = ImportedFont(
        id=str(uuid.uuid4()),
        family=family,
        style=style,
        file_name=safe_file_name or f"{family}.{font_format}",
        stored_name=stored_name,
        format=font_format,
        weight=weight,
        italic=italic,
        size_bytes=len(sfnt),
        sha256=digest,
        created_at=utcnow(),
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        duplicate = session.execute(
            select(ImportedFont).where(ImportedFont.sha256 == digest)
        ).scalar_one_or_none()
        if duplicate is not None:
            return duplicate
        raise AppError(500, "font_save_failed", "The font could not be saved locally.")
    except Exception:
        session.rollback()
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    session.refresh(row)
    return row


def delete_font(session: Session, font_id: str) -> None:
    row = session.get(ImportedFont, font_id)
    if row is None:
        raise AppError(404, "font_not_found", "This font is no longer in the local library.")
    path = get_settings().fonts_dir / row.stored_name
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise AppError(
            500,
            "font_delete_failed",
            "The font file could not be removed. Close any application using it and try again.",
        ) from exc
    session.delete(row)
    session.commit()


def font_file(session: Session, font_id: str) -> tuple[ImportedFont, Path]:
    row = session.get(ImportedFont, font_id)
    if row is None:
        raise AppError(404, "font_not_found", "This font is no longer in the local library.")
    path = get_settings().fonts_dir / row.stored_name
    if not path.is_file():
        raise AppError(404, "font_file_missing", "The stored font file is missing.")
    return row, path


def families_in_document(content: Any) -> list[str]:
    """Collect every font family referenced by a Tiptap document."""
    found: dict[str, str] = {}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "textStyle":
                attrs = value.get("attrs") or {}
                family = sanitize_family(attrs.get("fontFamily"))
                if family:
                    found.setdefault(family.casefold(), family)
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    walk(content)
    return list(found.values())


def export_faces_for_document(content: Any, session: Session | None) -> dict[str, list[ExportFace]]:
    return export_faces(families_in_document(content), session)


def export_faces(families: list[str], session: Session | None) -> dict[str, list[ExportFace]]:
    """Resolve document font names to faces that can be embedded or named.

    The result is keyed by the case-folded family name and keeps the real family
    spelling so an export never trusts arbitrary style text from JSON.
    """
    wanted = {sanitize_family(name).casefold() for name in families}
    wanted.discard("")
    if not wanted:
        return {}

    system_faces = list_system_faces()
    imported_rows = _imported_rows(session) if session is not None else []

    result: dict[str, list[ExportFace]] = {key: [] for key in wanted}
    seen: dict[str, set[tuple[str, int, bool]]] = {key: set() for key in wanted}

    def add(face: ExportFace) -> None:
        key = face.family.casefold()
        if key not in result:
            return
        identity = (face.style.casefold(), face.weight, face.italic)
        if identity in seen[key]:
            return
        seen[key].add(identity)
        result[key].append(face)

    # Imported faces are preferred when the same family is also installed.
    for row in imported_rows:
        key = row.family.casefold()
        if key in wanted:
            add(
                ExportFace(
                    family=row.family,
                    style=row.style,
                    weight=row.weight,
                    italic=row.italic,
                    path=get_settings().fonts_dir / row.stored_name,
                    index=0,
                    format=row.format,
                )
            )
    for face in system_faces:
        if face.family.casefold() in wanted:
            add(
                ExportFace(
                    family=face.family,
                    style=face.style,
                    weight=face.weight,
                    italic=face.italic,
                    path=face.path,
                    index=face.index,
                    format=face.format,
                )
            )

    for key in list(result):
        result[key].sort(key=lambda face: (face.italic, face.weight, face.style.casefold()))
        if not result[key]:
            result.pop(key)
    return result


def embedding_allowed(face: ExportFace) -> bool:
    """Honour the font's OS/2 embedding permission bits."""
    try:
        font = TTFont(str(face.path), fontNumber=face.index, lazy=True)
    except Exception:
        return False
    try:
        os2 = font.get("OS/2")
        if os2 is None:
            return True
        fs_type = int(os2.fsType)
        # Bit 1 is a restricted licence; bit 9 marks a bitmap-only font.
        return not (fs_type & 0x0002) and not (fs_type & 0x0200)
    except Exception:
        return False
    finally:
        try:
            font.close()
        except Exception:
            pass


def face_bytes(face: ExportFace) -> bytes | None:
    """Return a standalone sfnt file for this face.

    A face inside a TrueType collection is extracted so Word and the PDF story
    engine receive a normal single-font file.
    """
    if not face.path.is_file():
        return None
    if face.format == "ttc" or face.path.suffix.lower() == ".ttc":
        try:
            font = TTFont(str(face.path), fontNumber=face.index, lazy=False)
        except Exception:
            return None
        try:
            buffer = io.BytesIO()
            font.save(buffer)
            return buffer.getvalue()
        except Exception:
            return None
        finally:
            try:
                font.close()
            except Exception:
                pass
    try:
        return face.path.read_bytes()
    except OSError:
        return None
