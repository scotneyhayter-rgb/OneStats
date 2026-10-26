"""Local database backups for the standalone install (section 9 of the standalone spec).

Creates verified PostgreSQL dumps of the OneStats database using the installed ``pg_dump`` (the same
PostgreSQL that serves the app — never a different engine), writes them to the configured backup
directory (outside anything an uninstaller removes), and verifies each dump is readable. Restore is
intentionally NOT exposed here as a one-click API action: it is destructive and runs via the
documented CLI (``scripts/onestats-backup.py restore``) with explicit confirmation.
"""

from __future__ import annotations

import datetime as dt
import glob
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from onestats.core.config import Settings


def _backup_dir(settings: Settings) -> Path:
    base = settings.backup_dir or os.path.join(settings.media_root, "backups")
    d = Path(base)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _find_tool(name: str) -> str | None:
    """Locate a PostgreSQL client tool (pg_dump/pg_restore): PATH first, then a standard Windows
    install, then an ONESTATS_PG_BIN override."""
    override = os.environ.get("ONESTATS_PG_BIN")
    if override:
        cand = Path(override) / (name + (".exe" if os.name == "nt" else ""))
        if cand.exists():
            return str(cand)
    found = shutil.which(name)
    if found:
        return found
    for base in sorted(glob.glob(r"C:\Program Files\PostgreSQL\*\bin"), reverse=True):
        cand = Path(base) / (name + ".exe")
        if cand.exists():
            return str(cand)
    return None


def _conn_parts(settings: Settings) -> dict[str, str]:
    """Resolve host/port/db/user + password for pg_dump from the runtime DB URL."""
    url = settings.database_url or ""
    # strip the SQLAlchemy driver prefix (postgresql+psycopg://…)
    cleaned = url.replace("postgresql+psycopg://", "postgresql://").replace("postgresql+psycopg2://", "postgresql://")
    p = urlparse(cleaned)
    return {
        "host": p.hostname or settings.db_host,
        "port": str(p.port or settings.db_port),
        "dbname": (p.path or "/").lstrip("/") or settings.db_name,
        "user": p.username or settings.db_user,
        "password": p.password or (settings.db_password or ""),
    }


def _dump_identity(settings: Settings, parts: dict[str, str]) -> tuple[str, str]:
    """The role used for backup/restore. The data is FORCE-RLS protected, so a complete dump needs a
    role that bypasses RLS — a PostgreSQL superuser (default 'postgres') or a BYPASSRLS role. Configured
    via ONESTATS_PG_SUPERUSER / ONESTATS_PG_SUPERUSER_PASSWORD; otherwise backups cannot read all rows."""
    su = os.environ.get("ONESTATS_PG_SUPERUSER")
    su_pw = os.environ.get("ONESTATS_PG_SUPERUSER_PASSWORD")
    if su_pw:
        return (su or "postgres", su_pw)
    return (parts["user"], parts["password"])


_RLS_HINT = (
    "Backups need PostgreSQL superuser (or BYPASSRLS) access because the data is protected by "
    "row-level security. Set ONESTATS_PG_SUPERUSER_PASSWORD (and optionally ONESTATS_PG_SUPERUSER, "
    "default 'postgres') in your OneStats config, then try again. See docs/75-standalone-windows.md."
)


def create_backup(settings: Settings) -> dict[str, object]:
    """Create and verify a compressed custom-format dump. Returns file info; raises on failure."""
    pg_dump = _find_tool("pg_dump")
    if pg_dump is None:
        raise RuntimeError("pg_dump not found. Install PostgreSQL client tools or set ONESTATS_PG_BIN.")
    parts = _conn_parts(settings)
    user, password = _dump_identity(settings, parts)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = _backup_dir(settings) / f"onestats-{stamp}.dump"
    env = dict(os.environ, PGPASSWORD=password)
    cmd = [pg_dump, "-h", parts["host"], "-p", parts["port"], "-U", user,
           "-d", parts["dbname"], "-F", "c", "-f", str(out)]
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)  # noqa: S603
    if res.returncode != 0 or not out.exists():
        out.unlink(missing_ok=True)  # never leave a partial/failed dump behind
        err = res.stderr.strip()[:300]
        if "row-level security" in res.stderr:
            raise RuntimeError(_RLS_HINT)
        raise RuntimeError(f"Backup failed: {err}")

    # Verify: a dump is only "successful" if pg_restore can read its table of contents.
    verified = verify_backup(out)
    if not verified:
        raise RuntimeError("Backup file was created but failed verification (unreadable archive).")
    return {"file": out.name, "path": str(out), "size_bytes": out.stat().st_size,
            "created_at": dt.datetime.now().isoformat(), "verified": True}


def verify_backup(path: Path) -> bool:
    pg_restore = _find_tool("pg_restore")
    if pg_restore is None:
        return False
    res = subprocess.run([pg_restore, "--list", str(path)], capture_output=True, text=True)  # noqa: S603
    return res.returncode == 0 and bool(res.stdout.strip())


def restore_backup(settings: Settings, path: Path) -> bool:
    """Restore a verified dump into the OneStats database. DESTRUCTIVE: replaces current contents.
    Callers (the CLI) must confirm first; this is never exposed as a one-click API action."""
    pg_restore = _find_tool("pg_restore")
    if pg_restore is None:
        raise RuntimeError("pg_restore not found. Install PostgreSQL client tools or set ONESTATS_PG_BIN.")
    parts = _conn_parts(settings)
    user, password = _dump_identity(settings, parts)
    env = dict(os.environ, PGPASSWORD=password)
    cmd = [pg_restore, "-h", parts["host"], "-p", parts["port"], "-U", user,
           "-d", parts["dbname"], "--clean", "--if-exists", "--no-owner", str(path)]
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)  # noqa: S603
    if res.stderr:
        print(res.stderr[:1000])
    return res.returncode == 0


def list_backups(settings: Settings) -> list[dict[str, object]]:
    d = _backup_dir(settings)
    rows: list[dict[str, object]] = []
    for p in sorted(d.glob("onestats-*.dump"), reverse=True):
        st = p.stat()
        rows.append({"file": p.name, "size_bytes": st.st_size,
                     "created_at": dt.datetime.fromtimestamp(st.st_mtime).isoformat()})
    return rows
