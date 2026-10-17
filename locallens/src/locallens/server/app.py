"""The web application: API plus the built React app, served by one process."""
from __future__ import annotations

import logging
import logging.handlers
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import routes_auth, routes_chat, routes_datasets
from .auth import CSRF_HEADER, CSRF_VALUE
from .config import Settings
from .runtime import Runtime

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                                "script-src 'self'; connect-src 'self'; font-src 'self' data:; "
                                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
}


def _setup_logging(settings: Settings) -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("locallens")
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in log.handlers):
        h = logging.handlers.RotatingFileHandler(settings.log_dir / "server.log", maxBytes=2_000_000, backupCount=5)
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)


def create_app(settings: Settings | None = None, slm_factory: Callable[[], object] | None = None) -> FastAPI:
    settings = settings or Settings()
    _setup_logging(settings)
    rt = Runtime(settings, slm_factory)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.preload_model:
            rt.preload()
        yield

    app = FastAPI(title="LocalLens", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.rt = rt

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # state-changing API calls must carry a header a foreign web page cannot set (CSRF defence)
        if request.url.path.startswith("/api") and request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
                return JSONResponse({"detail": "Missing request header."}, status_code=403)
        try:
            response = await call_next(request)
        except Exception:
            logging.getLogger("locallens").exception("unhandled error on %s", request.url.path)
            response = JSONResponse({"detail": "Something went wrong on the server."}, status_code=500)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health():
        return {"ok": True, "model_loaded": rt.model_loaded, "model_present": settings.model_path.exists(),
                "model_error": rt.model_error[:200]}

    for r in (routes_auth.router, routes_datasets.router, routes_chat.router):
        app.include_router(r)

    web = Path(settings.web_dir)
    if (web / "index.html").exists():
        if (web / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=web / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not found."}, status_code=404)
            candidate = (web / path).resolve()
            if path and candidate.is_file() and web.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(web / "index.html")
    return app
