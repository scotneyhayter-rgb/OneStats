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
_RECOVERY_HASH_KEY = "recovery_token_hash"


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


# --- secure Super Admin account recovery (operator/server access required) ---------------------

def _recovery_file(settings: Settings) -> str:
    return settings.setup_token_file + ".recovery"


def issue_recovery_token(conn: Connection, settings: Settings) -> str:
    """Generate a one-time recovery token (hash stored in the DB, plaintext written to a local operator-
    only file). Run server-side by an operator with host access — this is what makes recovery safe: it
    needs server/file access, so it can never bypass authentication remotely, and it only ever affects the
    GLOBAL Super Admin role (never workspace-isolated data). Returns the token for the operator."""
    token = security.generate_token()
    auth.set_setting(conn, _RECOVERY_HASH_KEY, security.hash_token(token))
    try:
        with open(_recovery_file(settings), "w", encoding="utf-8") as fh:
            fh.write(token)
    except OSError as exc:
        log.error("Could not write recovery token file: %s", type(exc).__name__)
        raise
    log.warning("Super Admin recovery token written to %s", _recovery_file(settings))
    return token


def verify_recovery_token(conn: Connection, token: str) -> bool:
    stored = auth.get_setting(conn, _RECOVERY_HASH_KEY)
    return bool(stored) and security.tokens_equal(stored, security.hash_token(token))


def recover_super_admin(conn: Connection, settings: Settings, token: str, username: str, new_password: str) -> None:
    """Reset/restore a Super Administrator using a valid recovery token: the named user is set active, made
    a Super Admin, given the new password, and required to change it on next login. Single-use."""
    err = security.password_strength_error(new_password)
    if err:
        raise ValueError(err)
    if not verify_recovery_token(conn, token):
        raise ValueError("invalid_recovery_token")
    user = auth.get_user_by_username(conn, username)
    if user is None:
        raise ValueError("user_not_found")
    from sqlalchemy import text
    conn.execute(
        text("UPDATE app_user SET password_hash = :p, is_super_admin = true, status = 'active', "
             "must_change_password = true WHERE id = :id"),
        {"p": security.hash_password(new_password), "id": user["id"]},
    )
    conn.execute(text("INSERT INTO admin_audit(actor, action, target_user_id) "
                      "VALUES ('recovery', 'user.recover_super_admin', :id)"), {"id": user["id"]})
    auth.set_setting(conn, _RECOVERY_HASH_KEY, None)
    try:
        if os.path.exists(_recovery_file(settings)):
            os.remove(_recovery_file(settings))
    except OSError:
        pass
