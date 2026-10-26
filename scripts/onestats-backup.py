#!/usr/bin/env python3
"""OneStats local backup / restore (standalone install).

Subcommands:
  backup            Create and verify a PostgreSQL dump in the backup directory.
  list              List existing backups.
  verify  <file>    Verify a backup is a readable archive.
  restore <file>    Restore a backup into the OneStats database.  **DESTRUCTIVE** — requires --confirm.

Connection details are read from the per-user standalone config
(%LOCALAPPDATA%\\OneStats\\onestats.env) or the environment / dev .env. Restore never runs without an
explicit --confirm, and prints exactly what it will overwrite first (data written after the backup
would be lost). This uses the installed PostgreSQL tools (pg_dump/pg_restore) — never a different engine.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))


def _load_config() -> None:
    """Load the per-user standalone config, then the dev .env, into the environment (no overrides)."""
    candidates = []
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if root:
        candidates.append(Path(root) / "OneStats" / "onestats.env")
    candidates.append(ROOT / "services" / "api" / ".env")
    for cfg in candidates:
        if not cfg.exists():
            continue
        for raw in cfg.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="OneStats local backup / restore.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backup")
    sub.add_parser("list")
    v = sub.add_parser("verify"); v.add_argument("file")
    r = sub.add_parser("restore"); r.add_argument("file"); r.add_argument("--confirm", action="store_true")
    args = ap.parse_args(argv)

    _load_config()
    from onestats.core.config import get_settings
    from onestats.domain import backups
    settings = get_settings()

    if args.cmd == "backup":
        info = backups.create_backup(settings)
        print(f"Created & verified: {info['path']} ({info['size_bytes']} bytes)")
        return 0

    if args.cmd == "list":
        rows = backups.list_backups(settings)
        if not rows:
            print("No backups found.")
        for b in rows:
            print(f"  {b['file']:40s} {b['size_bytes']:>12} bytes  {b['created_at']}")
        return 0

    if args.cmd == "verify":
        ok = backups.verify_backup(Path(args.file))
        print("OK — readable archive." if ok else "FAILED — not a readable archive.")
        return 0 if ok else 1

    if args.cmd == "restore":
        path = Path(args.file)
        if not path.exists():
            print(f"ERROR: backup not found: {path}", file=sys.stderr)
            return 2
        if not backups.verify_backup(path):
            print("ERROR: backup failed verification; refusing to restore.", file=sys.stderr)
            return 2
        if not args.confirm:
            print("DESTRUCTIVE: restoring OVERWRITES the current OneStats database. Any data entered")
            print(f"since this backup ({path.name}) would be lost. Re-run with --confirm to proceed.")
            return 1
        rc = backups.restore_backup(settings, path)  # type: ignore[attr-defined]
        print("Restore complete." if rc else "Restore failed — see output above.")
        return 0 if rc else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
