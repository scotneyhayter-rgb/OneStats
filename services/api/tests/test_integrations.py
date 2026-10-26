"""Workspace API & Integrations — security, isolation, lifecycle and SSRF tests.

Covers the mandatory security constraints: secrets encrypted at rest and never returned in plaintext,
backend-only decryption, workspace isolation (RLS), role-based permission gating, secure rotation and
revocation, audit records for every credential action, and SSRF protection for custom endpoints. DB-backed
tests run in a single rolled-back transaction as the least-privilege app role under FORCE RLS; skipped
without a live DB. No real external network calls are made (the provider client is stubbed).
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import create_engine, text

from onestats.core import crypto, net
from onestats.core.config import Settings, get_settings
from onestats.db.workspace import set_workspace
from onestats.domain import integrations, permissions

settings = get_settings()
pytestmark_db = pytest.mark.skipif(not settings.db_configured, reason="no live database credential configured")

ACTOR = "11111111-1111-1111-1111-111111111111"

# Two real Fernet keys so rotation (MultiFernet: first encrypts, any decrypts) is exercised.
KEY_NEW = crypto.new_key()
KEY_OLD = crypto.new_key()
TS = Settings(env="test", db_password=None, _env_file=None, encryption_key=f"{KEY_NEW},{KEY_OLD}")
TS_OLD_ONLY = Settings(env="test", db_password=None, _env_file=None, encryption_key=KEY_OLD)


# ----------------------------------------------------------------- crypto (secret-at-rest)

def test_encrypt_decrypt_roundtrip_and_ciphertext_opaque():
    secret = "super-secret-api-key-xyz"
    token = crypto.encrypt(secret, TS)
    assert token != secret and secret not in token          # ciphertext never reveals the plaintext
    assert crypto.decrypt(token, TS) == secret


def test_decrypt_rejects_tampered_or_foreign_token():
    with pytest.raises(ValueError):
        crypto.decrypt("not-a-valid-token", TS)
    other = crypto.encrypt("x", Settings(env="test", db_password=None, _env_file=None, encryption_key=crypto.new_key()))
    with pytest.raises(ValueError):
        crypto.decrypt(other, TS)                            # a token from an unrelated key cannot be read


def test_key_rotation_old_ciphertext_still_decrypts():
    # encrypt under the OLD key only, then decrypt with a config where OLD is a secondary key
    token = crypto.encrypt("rotate-me", TS_OLD_ONLY)
    assert crypto.decrypt(token, TS) == "rotate-me"          # MultiFernet tries every configured key
    rotated = crypto.rotate(token, TS)                       # re-encrypt under the current (first) key
    assert crypto.decrypt(rotated, TS) == "rotate-me"


# ----------------------------------------------------------------- SSRF guard

@pytest.mark.parametrize("url", [
    "http://example.com",                 # http not allowed by default
    "https://localhost/data",             # loopback name
    "https://127.0.0.1/data",             # loopback IP
    "https://10.0.0.5/x",                 # private
    "https://192.168.1.10/x",             # private
    "https://169.254.169.254/latest",     # link-local (cloud metadata) — classic SSRF target
    "https://user:pass@example.com/x",    # credentials in URL
    "ftp://example.com",                  # wrong scheme
    "https:///nohost",                    # missing host
    "",                                   # empty
])
def test_ssrf_guard_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        net.validate_public_url(url)


def test_ssrf_guard_allows_public_https_ip_literal():
    # an IP literal resolves locally (no DNS) and is globally routable → accepted
    assert net.validate_public_url("https://8.8.8.8/health") == "https://8.8.8.8/health"


# ----------------------------------------------------------------- provider registry

def test_provider_registry_lists_schemas_without_secrets():
    provs = {p["id"]: p for p in integrations.providers()}
    assert "playhq" in provs and "custom_api" in provs
    playhq = provs["playhq"]
    assert any(f["key"] == "api_key" for f in playhq["secret_fields"])
    assert any(f["key"] == "org_id" for f in playhq["config_fields"])
    assert provs["custom_api"]["custom_url"] is True


# ----------------------------------------------------------------- DB-backed lifecycle / isolation

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


def _ws(conn, name):
    wid = conn.execute(text("INSERT INTO workspace(name, type) VALUES (:n,'club') RETURNING id"),
                       {"n": name}).scalar_one()
    set_workspace(conn, wid)
    return wid


def _no_plaintext(rows, secret: str):
    """Assert the secret never appears anywhere in an API-facing payload."""
    assert secret not in json.dumps(rows, default=str)


@pytestmark_db
def test_create_lists_masked_and_secret_recoverable_backend_only(conn):
    wid = _ws(conn, "INTEG A")
    row = integrations.create_credential(conn, TS, wid, ACTOR, provider="playhq",
                                         secrets={"api_key": "KEY-AAA-111"},
                                         config={"org_id": "org-1", "tenant": "ca"})
    assert row["provider"] == "playhq" and row["status"] == "active" and row["has_secret"] is True
    assert "secret_enc" not in row and "secrets" not in row       # never returned
    listed = integrations.list_credentials(conn, wid)
    _no_plaintext(listed, "KEY-AAA-111")
    # backend-only decryption for connector use
    data = integrations.get_secret(conn, TS, wid, "playhq")
    assert data["secrets"]["api_key"] == "KEY-AAA-111" and data["config"]["org_id"] == "org-1"


@pytestmark_db
def test_rotate_replaces_secret_and_never_leaks(conn):
    wid = _ws(conn, "INTEG ROT")
    row = integrations.create_credential(conn, TS, wid, ACTOR, provider="playhq",
                                         secrets={"api_key": "OLD-KEY"}, config={"org_id": "o", "tenant": "ca"})
    integrations.rotate_credential(conn, TS, wid, ACTOR, uuid.UUID(row["id"]), secrets={"api_key": "NEW-KEY"})
    assert integrations.get_secret(conn, TS, wid, "playhq")["secrets"]["api_key"] == "NEW-KEY"
    _no_plaintext(integrations.list_credentials(conn, wid), "NEW-KEY")


@pytestmark_db
def test_disable_and_revoke_block_secret_use(conn):
    wid = _ws(conn, "INTEG REV")
    row = integrations.create_credential(conn, TS, wid, ACTOR, provider="playhq",
                                         secrets={"api_key": "K"}, config={"org_id": "o"})
    cid = uuid.UUID(row["id"])
    integrations.set_enabled(conn, wid, ACTOR, cid, False)
    assert integrations.get_secret(conn, TS, wid, "playhq") is None       # disabled → unusable
    integrations.set_enabled(conn, wid, ACTOR, cid, True)
    assert integrations.get_secret(conn, TS, wid, "playhq") is not None
    revoked = integrations.revoke_credential(conn, wid, ACTOR, cid)
    assert revoked["status"] == "revoked" and revoked["has_secret"] is False   # ciphertext wiped
    assert integrations.get_secret(conn, TS, wid, "playhq") is None
    # the stored ciphertext column is actually NULL after revoke
    enc = conn.execute(text("SELECT secret_enc FROM workspace_credential WHERE id=:i"), {"i": cid}).scalar_one()
    assert enc is None


@pytestmark_db
def test_workspace_isolation(conn):
    wid_a = conn.execute(text("INSERT INTO workspace(name, type) VALUES ('ISO A','club') RETURNING id")).scalar_one()
    wid_b = conn.execute(text("INSERT INTO workspace(name, type) VALUES ('ISO B','club') RETURNING id")).scalar_one()
    set_workspace(conn, wid_a)
    integrations.create_credential(conn, TS, wid_a, ACTOR, provider="playhq",
                                   secrets={"api_key": "A-SECRET"}, config={"org_id": "oa"})
    # workspace B must not see or use A's credential
    set_workspace(conn, wid_b)
    assert integrations.list_credentials(conn, wid_b) == []
    assert integrations.get_secret(conn, TS, wid_b, "playhq") is None


@pytestmark_db
def test_same_provider_different_credentials_per_workspace(conn):
    wid_a = conn.execute(text("INSERT INTO workspace(name, type) VALUES ('SP A','club') RETURNING id")).scalar_one()
    wid_b = conn.execute(text("INSERT INTO workspace(name, type) VALUES ('SP B','club') RETURNING id")).scalar_one()
    set_workspace(conn, wid_a)
    integrations.create_credential(conn, TS, wid_a, ACTOR, provider="playhq",
                                   secrets={"api_key": "KEY-A"}, config={"org_id": "org-a"})
    set_workspace(conn, wid_b)
    integrations.create_credential(conn, TS, wid_b, ACTOR, provider="playhq",
                                   secrets={"api_key": "KEY-B"}, config={"org_id": "org-b"})
    set_workspace(conn, wid_a)
    assert integrations.get_secret(conn, TS, wid_a, "playhq")["secrets"]["api_key"] == "KEY-A"
    set_workspace(conn, wid_b)
    assert integrations.get_secret(conn, TS, wid_b, "playhq")["secrets"]["api_key"] == "KEY-B"


@pytestmark_db
def test_validation_rejects_unknown_provider_missing_secret_and_ssrf(conn):
    wid = _ws(conn, "INTEG VAL")
    with pytest.raises(ValueError, match="unknown_provider"):
        integrations.create_credential(conn, TS, wid, ACTOR, provider="nope", secrets={"api_key": "x"})
    with pytest.raises(ValueError, match="missing_secret"):
        integrations.create_credential(conn, TS, wid, ACTOR, provider="playhq", secrets={}, config={"org_id": "o"})
    with pytest.raises(ValueError, match="internal_address|url_"):
        integrations.create_credential(conn, TS, wid, ACTOR, provider="custom_api",
                                       secrets={}, config={"base_url": "https://127.0.0.1/x"})


@pytestmark_db
def test_import_configure_permission_gating(conn):
    """The endpoints are gated by 'import.configure' — held by workspace admins, not ordinary roles."""
    wid = _ws(conn, "INTEG PERM")
    admin = conn.execute(text("INSERT INTO app_user(username) VALUES ('integ_admin') RETURNING id")).scalar_one()
    viewer = conn.execute(text("INSERT INTO app_user(username) VALUES ('integ_viewer') RETURNING id")).scalar_one()
    permissions.grant_role(conn, admin, wid, "workspace_admin")
    permissions.grant_role(conn, viewer, wid, "viewer")
    assert "import.configure" in permissions.effective_permissions(conn, admin, wid, False)
    assert "import.configure" not in permissions.effective_permissions(conn, viewer, wid, False)


@pytestmark_db
def test_audit_records_every_action(conn):
    wid = _ws(conn, "INTEG AUDIT")
    row = integrations.create_credential(conn, TS, wid, ACTOR, provider="playhq",
                                         secrets={"api_key": "K"}, config={"org_id": "o"})
    cid = uuid.UUID(row["id"])
    integrations.rotate_credential(conn, TS, wid, ACTOR, cid, secrets={"api_key": "K2"})
    integrations.revoke_credential(conn, wid, ACTOR, cid)
    actions = {a["action"] for a in integrations.integration_audit(conn, wid)}
    assert {"integration.credential.create", "integration.credential.rotate",
            "integration.credential.revoke"} <= actions
    _no_plaintext(integrations.integration_audit(conn, wid), "K2")          # audit carries no secrets


@pytestmark_db
def test_test_connectivity_records_result_without_network(conn, monkeypatch):
    # stub the provider client so no real external call is made
    monkeypatch.setattr("onestats.domain.autosync.playhq.PlayHQClient.get",
                        lambda self, path, params=None: {"data": []})
    wid = _ws(conn, "INTEG TEST")
    row = integrations.create_credential(conn, TS, wid, ACTOR, provider="playhq",
                                         secrets={"api_key": "K"}, config={"org_id": "o", "tenant": "ca"})
    res = integrations.test_connectivity(conn, TS, wid, ACTOR, uuid.UUID(row["id"]))
    assert res["test_ok"] is True and res["last_test_ok"] is True
    _no_plaintext([res], "K")
    assert any(a["action"] == "integration.credential.test" for a in integrations.integration_audit(conn, wid))


@pytestmark_db
def test_bind_connector_uses_workspace_credential(conn, monkeypatch):
    from onestats.domain.autosync.connectors import catalog
    base = catalog.get("playhq")
    wid = _ws(conn, "INTEG BIND")
    # with no stored credential, the connector is returned unchanged
    assert integrations.bind_connector(conn, TS, wid, base) is base
    integrations.create_credential(conn, TS, wid, ACTOR, provider="playhq",
                                   secrets={"api_key": "BOUND-KEY"}, config={"org_id": "bound-org", "tenant": "ca"})
    bound = integrations.bind_connector(conn, TS, wid, base)
    assert bound is not base
    assert bound._org_id() == "bound-org"                   # uses the workspace credential's org, not global
    client = bound._client()
    assert client._key == "BOUND-KEY" and client._tenant == "ca"


# ----------------------------------------------------------------- API wiring / auth gating (no DB)

def test_integration_routes_registered():
    from fastapi.testclient import TestClient

    from onestats.main import create_app
    client = TestClient(create_app(Settings(env="test", db_password=None, _env_file=None)))
    paths = set(client.app.openapi()["paths"].keys())
    base = "/api/v1/workspaces/{workspace_id}/integrations"
    for p in ("/providers", "/credentials", "/credentials/{cred_id}/rotate",
              "/credentials/{cred_id}/test", "/credentials/{cred_id}/revoke", "/audit"):
        assert f"{base}{p}" in paths, p


def test_integration_requires_authentication():
    from fastapi.testclient import TestClient

    from onestats.main import create_app
    client = TestClient(create_app(Settings(env="test", db_password=None, _env_file=None)))
    wid = uuid.uuid4()
    base = f"/api/v1/workspaces/{wid}/integrations"
    assert client.get(f"{base}/credentials").status_code == 401
    assert client.post(f"{base}/credentials", json={"provider": "playhq", "secrets": {}}).status_code == 401
    assert client.get(f"{base}/audit").status_code == 401
