"""CI-only: provision the least-privilege runtime role so backend tests run under real RLS.

In production OneStats uses an owner/runtime split (docs/06-workspace-isolation.md): the tables are
owned by ``onestats_migrator`` and the app always connects as the **non-superuser** ``onestats_app``,
so ROW LEVEL SECURITY (with FORCE) actually applies to it. A plain Postgres service container makes
its ``POSTGRES_USER`` a superuser, and superusers bypass RLS — which would make the workspace-isolation
tests meaningless. So in CI the container's superuser is ``onestats_migrator`` (owner / runs DDL), and
this script, run as that role before migrations, creates ``onestats_app`` as a NOSUPERUSER role with
DML-only grants. pytest then connects as ``onestats_app`` and RLS is enforced exactly as in production.

Idempotent. Reads connection details from the same ONESTATS_* env the app/alembic use. CI-only —
never run against a real database.
"""
from __future__ import annotations

import os

import psycopg
from psycopg import sql

host = os.environ.get("ONESTATS_DB_HOST", "localhost")
port = os.environ.get("ONESTATS_DB_PORT", "5432")
db = os.environ.get("ONESTATS_DB_NAME", "onestats")
app_user = os.environ.get("ONESTATS_DB_USER", "onestats_app")
app_pw = os.environ["ONESTATS_DB_PASSWORD"]
migrator_pw = os.environ["ONESTATS_MIGRATOR_PASSWORD"]

# Connect as the owner/superuser role (the CI container's POSTGRES_USER = onestats_migrator).
dsn = f"host={host} port={port} dbname={db} user=onestats_migrator password={migrator_pw}"

app = sql.Identifier(app_user)
dbname = sql.Identifier(db)

with psycopg.connect(dsn, autocommit=True) as conn:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (app_user,))
    exists = cur.fetchone() is not None
    verb = sql.SQL("ALTER" if exists else "CREATE")
    cur.execute(sql.SQL("{} ROLE {} LOGIN PASSWORD {} NOSUPERUSER").format(
        verb, app, sql.Literal(app_pw)))
    cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(dbname, app))
    cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(app))
    # Tables are created later by onestats_migrator; default privileges route DML + sequence
    # access to the app role automatically as each table/sequence is created by migrations.
    cur.execute(sql.SQL(
        "ALTER DEFAULT PRIVILEGES FOR ROLE onestats_migrator IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}").format(app))
    cur.execute(sql.SQL(
        "ALTER DEFAULT PRIVILEGES FOR ROLE onestats_migrator IN SCHEMA public "
        "GRANT USAGE, SELECT ON SEQUENCES TO {}").format(app))

print(f"CI DB bootstrap: role {app_user!r} ready (NOSUPERUSER, DML + default privileges).")
