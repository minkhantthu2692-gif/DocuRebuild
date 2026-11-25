from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Query, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import DbSession
from app.core.errors import AppError
from app.schemas.fonts import FontFaceSummary, FontsResponse
from app.services import fonts as font_service

router = APIRouter(prefix="/fonts", tags=["fonts"])

FONT_MEDIA_TYPES = {
    "ttf": "font/ttf",
    "otf": "font/otf",
    "woff": "font/woff",
    "woff2": "font/woff2",
}


def _face_payload(row) -> dict:
    return {
        "id": row.id,
        "family": row.family,
        "style": row.style,
        "weight": row.weight,
        "italic": row.italic,
        "source": "imported",
        "format": row.format,
        "file_name": row.file_name,
    }


@router.get("", response_model=FontsResponse)
def list_fonts(
    session: DbSession,
    refresh: Annotated[bool, Query()] = False,
) -> FontsResponse:
    """List installed system fonts and fonts imported into DocuRebuild."""
    return font_service.list_fonts(session, refresh=refresh)


@router.post(
    "/import",
    response_model=FontFaceSummary,
    status_code=status.HTTP_201_CREATED,
)
def import_font(
    session: DbSession,
    file: Annotated[UploadFile, File(description="TTF, OTF, WOFF or WOFF2 font file")],
) -> dict:
    """Validate and store one font face in the local font library.

    The uploaded name is never used as a path. The file is checked by its own
    header and parsed before it is written, and duplicate uploads return the
    existing face instead of storing the same bytes twice.
    """
    try:
        data = file.file.read(font_service.MAX_FONT_BYTES + 1)
    finally:
        file.file.close()
    if len(data) > font_service.MAX_FONT_BYTES:
        raise AppError(
            422,
            "font_too_large",
            f"Font files must be {font_service.MAX_FONT_BYTES // (1024 * 1024)} MB or smaller.",
        )
    row = font_service.import_font(session, file.filename, data)
    return _face_payload(row)


@router.get("/{font_id}/file")
def read_font_file(font_id: str, session: DbSession) -> FileResponse:
    """Serve an imported font file to the renderer.

    The renderer requests this with its launch token and registers the bytes
    through the FontFace API, so a CSS ``url()`` never bypasses the API token.
    """
    row, path = font_service.font_file(session, font_id)
    return FileResponse(
        path,
        media_type=FONT_MEDIA_TYPES.get(row.format, "application/octet-stream"),
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "ETag": f'"{row.sha256}"',
            "Content-Disposition": "inline",
        },
    )


@router.delete("/{font_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_font(font_id: str, session: DbSession) -> Response:
    """Remove an imported font and its stored file. System fonts are untouched."""
    font_service.delete_font(session, font_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
