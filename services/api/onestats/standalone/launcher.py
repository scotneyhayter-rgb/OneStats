"""Self-starting backend launcher for the standalone OneStats desktop app.

Launched by the Tauri app as a sidecar (no console). Responsibilities, in order:
  1. Resolve the per-user data directory (%LOCALAPPDATA%\\OneStats) and set up file logging.
  2. Load per-user configuration (onestats.env) into the environment, if present.
  3. Ensure the media/backup directories exist.
  4. Wait for the local PostgreSQL to accept connections (it is a normal auto-starting Windows
     service on this machine; we never start a second database engine).
  5. Apply database migrations (Alembic `upgrade head`) — forward-only and idempotent, so existing
     cricket data is preserved and never overwritten.
  6. Serve the API on the loopback interface only (127.0.0.1), never exposed to the network.

Any failure writes a clear message to the log and exits non-zero so the app can show a recovery
screen. This module performs no destructive operations.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DB_WAIT_TIMEOUT_SECONDS = 60

log = logging.getLogger("onestats.standalone")


def data_dir() -> Path:
    """Per-user writable data directory for the standalone install (config, logs, media, backups)."""
    base = os.environ.get("ONESTATS_DATA_DIR")
    if base:
        return Path(base)
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if root:
        return Path(root) / "OneStats"
    return Path.home() / ".onestats"


def _configure_logging(dir_: Path) -> None:
    logs = dir_ / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(logs / "server.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # Also echo to stderr so the Tauri sidecar can capture startup lines.
    stderr = logging.StreamHandler(sys.stderr)
    stderr.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(stderr)


def load_config(dir_: Path) -> None:
    """Load `<data_dir>/onestats.env` (KEY=VALUE lines) into os.environ without overriding values
    already set in the environment. Secrets live only in this per-user file, never in source."""
    cfg = dir_ / "onestats.env"
    if not cfg.exists():
        log.info("No per-user config at %s (using environment/defaults).", cfg)
        return
    for raw in cfg.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)
    log.info("Loaded per-user config from %s", cfg)


def _ensure_dirs(dir_: Path) -> None:
    media = os.environ.get("ONESTATS_MEDIA_ROOT") or str(dir_ / "media")
    backups = os.environ.get("ONESTATS_BACKUP_DIR") or str(dir_ / "backups")
    os.environ.setdefault("ONESTATS_MEDIA_ROOT", media)
    os.environ.setdefault("ONESTATS_BACKUP_DIR", backups)
    Path(media).mkdir(parents=True, exist_ok=True)
    Path(backups).mkdir(parents=True, exist_ok=True)


def wait_for_db(timeout: int = DB_WAIT_TIMEOUT_SECONDS) -> bool:
    """Block until the configured database accepts connections, or timeout. Non-fatal retries."""
    from onestats.core.config import get_settings
    from onestats.db.session import check_connection

    get_settings.cache_clear()  # pick up env just loaded
    settings = get_settings()
    if not settings.db_configured:
        log.error("No database credential configured. Cannot start OneStats backend.")
        return False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = check_connection(settings)
        if st.connected:
            log.info("Database connection OK.")
            return True
        log.info("Waiting for the local database… (%s)", st.detail)
        time.sleep(2)
    log.error("Timed out waiting for the local database after %ss.", timeout)
    return False


def run_migrations() -> bool:
    """Apply Alembic migrations forward to head. Forward-only and idempotent — existing data is
    preserved and never overwritten. Returns True on success."""
    try:
        import onestats
        from alembic import command
        from alembic.config import Config

        migrations_dir = Path(onestats.__file__).parent / "db" / "migrations"
        cfg = Config()
        cfg.set_main_option("script_location", str(migrations_dir))
        # env.py resolves the URL from settings (ONESTATS_MIGRATOR_PASSWORD / ONESTATS_DB_PASSWORD).
        log.info("Applying database migrations (upgrade head)…")
        command.upgrade(cfg, "head")
        log.info("Database schema is up to date.")
        return True
    except Exception:  # noqa: BLE001 - report clearly; never leave a half-applied silent failure
        log.exception("Database migration failed.")
        return False


def serve(port: int = DEFAULT_PORT) -> None:
    import uvicorn

    from onestats.main import create_app

    app = create_app()
    log.info("Starting OneStats API on http://%s:%s (loopback only).", LOOPBACK_HOST, port)
    uvicorn.run(app, host=LOOPBACK_HOST, port=port, log_level="info")


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    port = DEFAULT_PORT
    for i, a in enumerate(argv):
        if a == "--port" and i + 1 < len(argv):
            try:
                port = int(argv[i + 1])
            except ValueError:
                pass

    dir_ = data_dir()
    dir_.mkdir(parents=True, exist_ok=True)
    _configure_logging(dir_)
    log.info("OneStats standalone backend starting. Data dir: %s", dir_)

    # Standalone defaults: this is a local, single-PC deployment bound to loopback.
    os.environ.setdefault("ONESTATS_ENV", "production")
    load_config(dir_)
    _ensure_dirs(dir_)

    if not wait_for_db():
        return 2
    if not run_migrations():
        return 3
    try:
        serve(port)
    except Exception:  # noqa: BLE001
        log.exception("The OneStats backend stopped unexpectedly.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
