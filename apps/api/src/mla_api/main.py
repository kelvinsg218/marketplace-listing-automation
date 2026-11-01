"""Application factory. The ASGI entry point is mla_api.asgi:app."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from mla_api import __version__
from mla_api.db import make_engine, make_sessionmaker
from mla_api.mailer import DisabledMailer, Mailer, OutboxMailer
from mla_api.routers import auth, orgs, products
from mla_api.security import LoginLimiter
from mla_api.settings import Settings, get_settings
from mla_api.storage import LocalStorage

log = logging.getLogger("mla_api")

CSRF_HEADER = "x-mla-client"
_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def create_app(settings: Settings | None = None, *, mailer: Mailer | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="MLA Web API", version=__version__,
                  docs_url=None if settings.environment == "production" else "/api/docs",
                  openapi_url=None if settings.environment == "production" else "/api/openapi.json")
    engine = make_engine(settings.database_url)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)
    app.state.login_limiter = LoginLimiter(settings.login_max_failures, settings.login_window_seconds)
    app.state.storage = LocalStorage(settings.storage_dir)
    if mailer is None:
        mailer = (DisabledMailer() if settings.environment == "production"
                  else OutboxMailer(settings.storage_dir.parent / "outbox"))
    app.state.mailer = mailer

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):
        # Cookie auth + SameSite=Lax, plus a custom header that cross-site forms cannot send and cross-origin
        # scripts cannot add without a CORS preflight we do not allow.
        if (request.method in _UNSAFE and request.url.path.startswith("/api/")
                and request.headers.get(CSRF_HEADER) != "web"):
            return JSONResponse({"detail": "Requisição recusada (cabeçalho de origem ausente)."}, status_code=403)
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                           allow_methods=["GET", "POST", "PATCH", "DELETE"],
                           allow_headers=["content-type", CSRF_HEADER])

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("Erro não tratado em %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Erro interno. Tente novamente; se persistir, contate o suporte."},
                            status_code=500)

    @app.get("/api/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    app.include_router(auth.router)
    app.include_router(orgs.router)
    app.include_router(products.router)

    if settings.web_dist_dir and settings.web_dist_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.web_dist_dir, html=True), name="web")
    return app

