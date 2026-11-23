from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.handlers import install_error_handlers
from app.db.session import get_session_factory, run_migrations
from app.api.routes import (
    ai,
    elements,
    health,
    ocr,
    projects,
    regions,
    settings as settings_routes,
    system,
    tables,
)
from app.services import imports as import_service
from app.services import ocr as ocr_service

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app_settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        app_settings.ensure_layout()
        run_migrations()
        # One explicit conversion from the legacy AI settings blob. Idempotent,
        # and a no-op when no legacy configuration exists.
        from app.services.ai_migrate import run_legacy_ai_migration

        with get_session_factory()() as session:
            run_legacy_ai_migration(session)
        logger.info("DocuRebuild local API ready (data dir: %s)", app_settings.data_dir)
        yield
        import_service.shutdown_import_executor()
        ocr_service.shutdown_ocr_executor()

    app = FastAPI(
        title="DocuRebuild Local API",
        version=app_settings.version,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def require_api_token(request: Request, call_next):
        """Reject local API calls that do not carry the desktop launch token.

        In browser development mode no token is configured, so this is a no-op.
        The desktop shell generates a fresh token per launch and passes it to
        the backend and the renderer only through the process environment and
        an in-memory IPC call.
        """
        token = app_settings.api_token
        if (
            token
            and request.url.path.startswith("/api")
            and request.method != "OPTIONS"
        ):
            provided = request.headers.get("authorization", "")
            if not secrets.compare_digest(provided, f"Bearer {token}"):
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": {
                            "code": "unauthorized",
                            "message": "This local API request is not authorized.",
                        }
                    },
                )
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        return response

    install_error_handlers(app, logger.warning)

    app.include_router(health.router, prefix="/api")
    app.include_router(projects.router, prefix="/api")
    app.include_router(settings_routes.router, prefix="/api")
    app.include_router(system.router, prefix="/api")
    app.include_router(ocr.router, prefix="/api")
    app.include_router(elements.router, prefix="/api")
    app.include_router(regions.router, prefix="/api")
    app.include_router(tables.router, prefix="/api")
    app.include_router(ai.router, prefix="/api")

    web_dist = app_settings.web_dist
    if web_dist is not None:
        web_dist = Path(web_dist).resolve()
        index_file = web_dist / "index.html"
        if index_file.is_file():
            assets_dir = web_dist / "assets"
            if assets_dir.is_dir():
                app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

            @app.get("/{full_path:path}", include_in_schema=False)
            async def serve_web_client(full_path: str) -> FileResponse:
                """Serve the built single-page client from the same origin.

                The desktop shell loads the local API root, so API calls need no
                CORS exception and the launch token can be sent as a header. Any
                unknown non-API path falls back to the client entry point.
                """
                if full_path == "api" or full_path.startswith("api/"):
                    raise HTTPException(status_code=404)
                candidate = (web_dist / full_path).resolve()
                try:
                    candidate.relative_to(web_dist)
                except ValueError:
                    raise HTTPException(status_code=404) from None
                if full_path and candidate.is_file():
                    return FileResponse(candidate)
                return FileResponse(index_file, headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
