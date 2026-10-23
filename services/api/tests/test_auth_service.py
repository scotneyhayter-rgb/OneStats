"""Live auth-service tests (rolled back; skipped without a database credential)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from onestats.core import security
from onestats.core.config import Settings, get_settings
from onestats.domain import auth, bootstrap

settings = get_settings()
pytestmark = pytest.mark.skipif(
    not settings.db_configured, reason="no live database credential configured"
)


@pytest.fixture
def conn():
    eng = create_engine(settings.database_url, future=True)
    with eng.connect() as c:
        trans = c.begin()
        try:
            yield c
        finally:
            trans.rollback()
    eng.dispose()


def test_user_auth_and_session_lifecycle(conn):
    uid = auth.create_user(conn, "svc_admin", "Str0ng-Passw0rd!", is_super_admin=True)
    assert auth.count_super_admins(conn) >= 1

    assert auth.authenticate(conn, "svc_admin", "Str0ng-Passw0rd!")["username"] == "svc_admin"
    assert auth.authenticate(conn, "svc_admin", "wrong") is None
    assert auth.authenticate(conn, "no_such_user", "x") is None

    token, _expires = auth.create_session(conn, uid, 12)
    user = auth.validate_session(conn, token)
    assert user and user["username"] == "svc_admin" and user["is_super_admin"] is True

    auth.revoke_session(conn, token)
    assert auth.validate_session(conn, token) is None


def test_bootstrap_creates_super_admin_with_valid_token(conn, tmp_path):
    if not auth.setup_required(conn):
        pytest.skip("a Super Administrator already exists in the database")
    ts = Settings(_env_file=None, setup_token_file=str(tmp_path / "tok"))
    tok = "setup-token-abcdef123456"
    auth.set_setting(conn, "setup_token_hash", security.hash_token(tok))

    bootstrap.create_super_admin(conn, ts, "root_admin", "Sup3r-Secret-Pw!", tok)

    assert auth.setup_required(conn) is False
    assert auth.get_setting(conn, "setup_token_hash") is None


def test_bootstrap_rejects_bad_token(conn, tmp_path):
    if not auth.setup_required(conn):
        pytest.skip("a Super Administrator already exists in the database")
    ts = Settings(_env_file=None, setup_token_file=str(tmp_path / "tok"))
    auth.set_setting(conn, "setup_token_hash", security.hash_token("the-real-token-123456"))
    with pytest.raises(ValueError):
        bootstrap.create_super_admin(conn, ts, "root_admin", "Sup3r-Secret-Pw!", "wrong-token-123456")
