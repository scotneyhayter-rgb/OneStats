"""One-time Super Administrator bootstrap (D26).

On first run, when no Super Administrator exists, a one-time setup token is generated; only
its hash is stored in the database, and the plaintext is written to a local, gitignored
file for the operator to read. The first-run setup flow requires that token to create the
initial Super Administrator, after which the token is cleared. The token value is never
logged.
"""

from __future__ import annotations

import os

from sqlalchemy.engine import Connection

from onestats.core import security
from onestats.core.config import Settings
from onestats.core.logging import get_logger
from onestats.domain import auth

log = get_logger("onestats.bootstrap")

_SETUP_HASH_KEY = "setup_token_hash"


def ensure_setup_token(conn: Connection, settings: Settings) -> None:
    """If setup is required and no token exists yet, create one (hash in DB, plaintext in a
    local file). Idempotent; does nothing once a Super Admin exists."""
    if not auth.setup_required(conn):
        return
    if auth.get_setting(conn, _SETUP_HASH_KEY):
        log.warning("First-run setup required: use the setup token in %s", settings.setup_token_file)
        return
    token = security.generate_token()
    auth.set_setting(conn, _SETUP_HASH_KEY, security.hash_token(token))
    try:
        with open(settings.setup_token_file, "w", encoding="utf-8") as fh:
            fh.write(token)
    except OSError as exc:
        log.error("Could not write setup token file: %s", type(exc).__name__)
        raise
    log.warning(
        "First-run setup required: a Super Admin setup token was written to %s",
        settings.setup_token_file,
    )


def verify_setup_token(conn: Connection, token: str) -> bool:
    stored = auth.get_setting(conn, _SETUP_HASH_KEY)
    return bool(stored) and security.tokens_equal(stored, security.hash_token(token))


def create_super_admin(
    conn: Connection, settings: Settings, username: str, password: str, setup_token: str
) -> None:
    """Create the initial Super Administrator. Fails if setup is not required or the token
    is invalid. Clears the setup token on success."""
    if not auth.setup_required(conn):
        raise ValueError("setup_already_complete")
    if not verify_setup_token(conn, setup_token):
        raise ValueError("invalid_setup_token")
    auth.create_user(conn, username, password, display_name=username, is_super_admin=True)
    auth.set_setting(conn, _SETUP_HASH_KEY, None)
    try:
        if os.path.exists(settings.setup_token_file):
            os.remove(settings.setup_token_file)
    except OSError:
        pass
