"""OneStats FastAPI application factory (Phase 2 foundation).

Startup/shutdown handling, API versioning, CORS for the local desktop client, structured
logging, and consistent error handling. No cricket-domain logic and no authentication
system yet (deliberately — a fake auth system is not created in this phase).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    yield
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
    app.include_router(api_v1, prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {"service": settings.app_name, "version": __version__, "docs": "/docs"}

    return app


app = create_app()
