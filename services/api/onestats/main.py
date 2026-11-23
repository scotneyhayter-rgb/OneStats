"""OneStats FastAPI application factory (Phase 2 foundation).

Startup/shutdown handling, API versioning, CORS for the local desktop client, structured
logging, and consistent error handling. No cricket-domain logic and no authentication
system yet (deliberately — a fake auth system is not created in this phase).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from onestats import __version__
from onestats.api.v1.router import api_v1
from onestats.core.config import Settings, get_settings
from onestats.core.errors import register_error_handlers
from onestats.core.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    log = get_logger("onestats.app")
    log.info("Starting %s v%s (env=%s)", settings.app_name, __version__, settings.env)
    if not settings.db_configured:
        log.warning(
            "Database credential not configured - DB features unavailable until "
            "ONESTATS_DB_PASSWORD (or ONESTATS_DB_URL) is set in the environment/.env"
        )
    else:
        # First-run bootstrap: ensure a Super Admin setup token exists if none set up yet.
        try:
            from onestats.db.session import get_engine
            from onestats.domain.bootstrap import ensure_setup_token

            engine = get_engine(settings)
            if engine is not None:
                with engine.begin() as conn:
                    ensure_setup_token(conn, settings)
        except Exception as exc:  # noqa: BLE001 - never block startup on bootstrap check
            log.warning("Setup-token bootstrap skipped: %s", type(exc).__name__)

        # Internet Research Engine: start the in-process background worker that drives research jobs
        # (reconciles stale jobs, claims and runs them step by step). Only when a DB is configured;
        # disabled by ONESTATS_RESEARCH_WORKER=0. A failure here never blocks startup.
        try:
            from onestats.db.session import get_engine
            from onestats.domain.research import worker as research_worker

            eng = get_engine(settings)
            if eng is not None:
                research_worker.start_worker(eng, settings)
        except Exception as exc:  # noqa: BLE001
            log.warning("Research worker not started: %s", type(exc).__name__)
    yield
    try:
        from onestats.domain.research import worker as research_worker

        research_worker.stop_worker()
    except Exception:  # noqa: BLE001, S110 - best-effort shutdown
        pass
    log.info("Shutting down %s", settings.app_name)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = settings
    # Ensure endpoints resolve THIS app's settings (not the cached global), so tests
    # and alternate configurations are honoured consistently.
    app.dependency_overrides[get_settings] = lambda: settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    # Per-request id (Part 6 accountability): stamp every request with a stable id so a
    # sensitive action in the audit log can be traced back to the exact request. Echoed as a
    # response header for client-side correlation. No secrets; a client-supplied value is
    # accepted (for cross-tier tracing) but length-bounded.
    import uuid as _uuid

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = (request.headers.get("X-Request-Id") or "")[:64] or _uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response

    # Maintenance-mode gate (update system): while a controlled server update is in progress, reject
    # new writes with 503 so no scorecard/data change lands mid-migration. Reads stay available
    # (preserve read-only access). Auth, setup and the Super-Admin system-update routes are exempt so
    # an administrator can still sign in and exit maintenance.
    _MAINT_EXEMPT = ("/system/updates/", "/auth/", "/setup")

    @app.middleware("http")
    async def maintenance_gate(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            path = request.url.path
            if not any(seg in path for seg in _MAINT_EXEMPT):
                from onestats.db.session import get_engine
                from onestats.domain import updates

                eng = get_engine(settings)
                if eng is not None and updates.is_maintenance(eng):
                    return JSONResponse(
                        status_code=503,
                        content={"detail": "OneStats is updating (maintenance mode). Please try again shortly.",
                                 "maintenance": True},
                    )
        return await call_next(request)

    app.include_router(api_v1, prefix=settings.api_v1_prefix)

    # Optional one-origin web app: when configured, serve the built SPA so the browser loads the app and
    # calls the API from the same host (no CORS). Off by default → the JSON root is kept for the desktop
    # build and health checks. See docs/77-web-app.md.
    front = _frontend_dir(settings)
    if front is not None:
        _serve_frontend(app, front)
    else:
        @app.get("/", include_in_schema=False)
        def root() -> dict:
            return {"service": settings.app_name, "version": __version__, "docs": "/docs"}

    return app


def _frontend_dir(settings: Settings) -> Path | None:
    """The directory of the built SPA to serve, or None when web-app serving is off or no build is present
    (so a misconfiguration never breaks API startup)."""
    if not settings.serve_frontend:
        return None
    if settings.frontend_dist:
        p = Path(settings.frontend_dist)
    else:  # best-effort default: apps/desktop/dist next to the repo
        p = Path(__file__).resolve().parents[3] / "apps" / "desktop" / "dist"
    try:
        return p if (p / "index.html").is_file() else None
    except OSError:
        return None


def _serve_frontend(app: FastAPI, front: Path) -> None:
    """Mount the SPA: hashed assets as static files, every other non-API path falls back to index.html
    (client-side routing). API, docs and asset paths are never shadowed."""
    from fastapi.staticfiles import StaticFiles

    root = front.resolve()
    index = root / "index.html"
    assets = root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        # never serve the SPA for API/docs/asset routes — let those 404 as themselves
        if full_path == "api" or full_path.startswith(("api/", "docs", "redoc", "openapi.json", "assets/")):
            raise HTTPException(status_code=404)
        candidate = (root / full_path).resolve() if full_path else index
        if full_path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(str(candidate))      # a real static file (favicon, manifest, …)
        return FileResponse(str(index))               # client route → SPA entry point


app = create_app()
