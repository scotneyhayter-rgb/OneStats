"""Workspace API & Integrations management (per-workspace credentials).

Each workspace configures its own external-provider credentials. The **secret** is encrypted at rest
(``core.crypto``) with a key kept outside the database; non-secret config lives alongside it. Secrets are
**never** returned by any read, logged, or exported — only the backend decrypts them, and only to make a
provider request. Every credential action is audited in the workspace audit log. FORCE RLS isolates rows
to their workspace, so a club can never see or use another's credentials. SSRF protection guards any
custom endpoint.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from onestats.core import crypto, net
from onestats.core.config import Settings
from onestats.domain import audit


@dataclass(frozen=True)
class SecretField:
    key: str
    label: str
    required: bool = True


@dataclass(frozen=True)
class ConfigField:
    key: str
    label: str
    default: str | None = None
    required: bool = True


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    secret_fields: tuple[SecretField, ...]
    config_fields: tuple[ConfigField, ...] = ()
    testable: bool = False
    custom_url: bool = False
    notes: str | None = None


# Supported integration providers and their configuration schemas. Built-in providers use fixed, vetted
# hosts; "custom_api" accepts a user URL that is SSRF-validated. A provider here does NOT imply a verified
# live connection — that is proven only by a successful Test.
PROVIDERS: dict[str, Provider] = {
    "playhq": Provider(
        id="playhq", name="PlayHQ", testable=True,
        secret_fields=(SecretField("api_key", "API key (Client ID)"),),
        config_fields=(ConfigField("org_id", "Organisation ID"),
                       ConfigField("tenant", "Tenant (e.g. ca)", default="ca")),
        notes="PlayHQ public API. Cricket uses tenant 'ca' (host api.caprod.playhq.com)."),
    "custom_api": Provider(
        id="custom_api", name="Custom API (advanced)", testable=True, custom_url=True,
        secret_fields=(SecretField("api_key", "API key / token", required=False),),
        config_fields=(ConfigField("base_url", "Base URL (https)"),),
        notes="A validated HTTPS endpoint. Internal/private addresses are refused (SSRF protection). This "
              "does not add support for arbitrary undocumented APIs — it only performs a reachability check."),
}


def providers() -> list[dict[str, Any]]:
    out = []
    for p in PROVIDERS.values():
        out.append({"id": p.id, "name": p.name, "testable": p.testable, "custom_url": p.custom_url,
                    "notes": p.notes,
                    "secret_fields": [{"key": f.key, "label": f.label, "required": f.required} for f in p.secret_fields],
                    "config_fields": [{"key": f.key, "label": f.label, "default": f.default, "required": f.required}
                                      for f in p.config_fields]})
    return out


def _public_row(r: dict[str, Any]) -> dict[str, Any]:
    """A credential row WITHOUT the secret — safe to return to the UI."""
    return {"id": str(r["id"]), "provider": r["provider"], "label": r["label"], "enabled": r["enabled"],
            "status": r["status"], "config": r["config"] or {}, "has_secret": bool(r["secret_enc"]),
            "last_test_ok": r["last_test_ok"], "last_test_at": r["last_test_at"].isoformat() if r["last_test_at"] else None,
            "last_test_message": r["last_test_message"],
            "last_success_at": r["last_success_at"].isoformat() if r["last_success_at"] else None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None}


_COLS = ("id, workspace_id, provider, label, secret_enc, config, enabled, status, last_test_ok, "
         "last_test_at, last_test_message, last_success_at, created_at")


def list_credentials(conn: Connection, workspace_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(text(f"SELECT {_COLS} FROM workspace_credential WHERE workspace_id = :w "
                             "ORDER BY provider, label"), {"w": workspace_id}).mappings().all()
    return [_public_row(dict(r)) for r in rows]


def _get(conn: Connection, workspace_id: UUID, cred_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(text(f"SELECT {_COLS} FROM workspace_credential WHERE id = :id AND workspace_id = :w"),
                     {"id": cred_id, "w": workspace_id}).mappings().first()
    return dict(r) if r else None


def _validate(provider: str, config: dict[str, Any], secrets: dict[str, Any]) -> None:
    p = PROVIDERS.get(provider)
    if p is None:
        raise ValueError("unknown_provider")
    for f in p.secret_fields:
        if f.required and not (secrets or {}).get(f.key):
            raise ValueError(f"missing_secret:{f.key}")
    for f in p.config_fields:
        if f.required and not (config or {}).get(f.key) and not f.default:
            raise ValueError(f"missing_config:{f.key}")
    if p.custom_url:
        net.validate_public_url(str((config or {}).get("base_url", "")))   # SSRF guard


def create_credential(conn: Connection, settings: Settings, workspace_id: UUID, actor: str, *, provider: str,
                      secrets: dict[str, Any], config: dict[str, Any] | None = None,
                      label: str = "") -> dict[str, Any]:
    config = config or {}
    _validate(provider, config, secrets)
    secret_enc = crypto.encrypt(json.dumps(secrets), settings)
    cid = conn.execute(
        text("INSERT INTO workspace_credential(workspace_id, provider, label, secret_enc, config, created_by) "
             "VALUES (:w,:p,:l,:s,CAST(:c AS jsonb),:a) "
             "ON CONFLICT ON CONSTRAINT uq_workspace_credential DO UPDATE SET secret_enc = EXCLUDED.secret_enc, "
             "config = EXCLUDED.config, status = 'active', enabled = true, rotated_at = now(), updated_at = now() "
             "RETURNING id"),
        {"w": workspace_id, "p": provider, "l": label, "s": secret_enc, "c": json.dumps(config), "a": actor},
    ).scalar_one()
    audit.write_audit(conn, workspace_id, actor, "integration.credential.create", entity="integration",
                      entity_id=provider, after={"provider": provider, "label": label})   # no secret
    return _public_row(_get(conn, workspace_id, cid))


def rotate_credential(conn: Connection, settings: Settings, workspace_id: UUID, actor: str, cred_id: UUID, *,
                      secrets: dict[str, Any]) -> dict[str, Any]:
    row = _get(conn, workspace_id, cred_id)
    if row is None:
        raise ValueError("credential_not_found")
    _validate(row["provider"], row["config"] or {}, secrets)
    conn.execute(text("UPDATE workspace_credential SET secret_enc = :s, rotated_at = now(), status='active', "
                      "updated_at = now() WHERE id = :id AND workspace_id = :w"),
                 {"s": crypto.encrypt(json.dumps(secrets), settings), "id": cred_id, "w": workspace_id})
    audit.write_audit(conn, workspace_id, actor, "integration.credential.rotate", entity="integration",
                      entity_id=row["provider"])
    return _public_row(_get(conn, workspace_id, cred_id))


def set_enabled(conn: Connection, workspace_id: UUID, actor: str, cred_id: UUID, enabled: bool) -> dict[str, Any]:
    row = _get(conn, workspace_id, cred_id)
    if row is None:
        raise ValueError("credential_not_found")
    conn.execute(text("UPDATE workspace_credential SET enabled = :e, updated_at = now() WHERE id = :id AND workspace_id = :w"),
                 {"e": enabled, "id": cred_id, "w": workspace_id})
    audit.write_audit(conn, workspace_id, actor, "integration.credential." + ("enable" if enabled else "disable"),
                      entity="integration", entity_id=row["provider"])
    return _public_row(_get(conn, workspace_id, cred_id))


def revoke_credential(conn: Connection, workspace_id: UUID, actor: str, cred_id: UUID) -> dict[str, Any]:
    row = _get(conn, workspace_id, cred_id)
    if row is None:
        raise ValueError("credential_not_found")
    # wipe the encrypted secret and mark revoked, so it can no longer be decrypted or used
    conn.execute(text("UPDATE workspace_credential SET secret_enc = NULL, status = 'revoked', enabled = false, "
                      "revoked_at = now(), updated_at = now() WHERE id = :id AND workspace_id = :w"),
                 {"id": cred_id, "w": workspace_id})
    audit.write_audit(conn, workspace_id, actor, "integration.credential.revoke", entity="integration",
                      entity_id=row["provider"])
    return _public_row(_get(conn, workspace_id, cred_id))


def get_secret(conn: Connection, settings: Settings, workspace_id: UUID, provider: str,
               label: str = "") -> dict[str, Any] | None:
    """Backend-only: the decrypted secrets for an ACTIVE, ENABLED credential (for a provider request).
    Returns None when absent/revoked/disabled. Never exposed through the API."""
    r = conn.execute(
        text("SELECT secret_enc, config FROM workspace_credential WHERE workspace_id = :w AND provider = :p "
             "AND label = :l AND status = 'active' AND enabled = true AND secret_enc IS NOT NULL"),
        {"w": workspace_id, "p": provider, "l": label}).mappings().first()
    if r is None:
        return None
    return {"secrets": json.loads(crypto.decrypt(r["secret_enc"], settings)), "config": r["config"] or {}}


def bind_connector(conn: Connection, settings: Settings, workspace_id: UUID, connector: Any) -> Any:
    """Return a credential-bound copy of an AutoSync connector when the workspace has a stored credential
    for its provider, else the connector unchanged. This is how a sync run uses the **workspace's own**
    credential (backend-only, decrypted here, never exposed) instead of any global/env configuration — so
    two workspaces can use the same provider with different credentials."""
    provider = getattr(getattr(connector, "info", None), "connector_id", None)
    if provider == "playhq":
        data = get_secret(conn, settings, workspace_id, "playhq")
        if data is not None:
            from onestats.domain.autosync.playhq import PlayHQClient, PlayHQConnector, host_for_tenant
            secrets, config = data["secrets"], data["config"]
            tenant = config.get("tenant") or "ca"

            def _factory() -> PlayHQClient:
                return PlayHQClient(api_key=secrets["api_key"], tenant=tenant,
                                    base_url=host_for_tenant(tenant))

            return PlayHQConnector(client_factory=_factory, org_id=config.get("org_id"))
    return connector


def test_connectivity(conn: Connection, settings: Settings, workspace_id: UUID, actor: str,
                      cred_id: UUID) -> dict[str, Any]:
    """Actually attempt an authenticated request with the stored credential and record the result (no
    secret in the message). This is the only thing that proves a connection works."""
    row = _get(conn, workspace_id, cred_id)
    if row is None:
        raise ValueError("credential_not_found")
    data = get_secret(conn, settings, workspace_id, row["provider"], row["label"])
    if data is None:
        return _record_test(conn, workspace_id, actor, cred_id, False, "No active credential to test.")
    ok, message = _run_test(settings, row["provider"], data["secrets"], data["config"])
    return _record_test(conn, workspace_id, actor, cred_id, ok, message)


def _run_test(settings: Settings, provider: str, secrets: dict[str, Any], config: dict[str, Any]) -> tuple[bool, str]:
    try:
        if provider == "playhq":
            from onestats.domain.autosync.playhq import PlayHQClient, host_for_tenant
            tenant = config.get("tenant") or "ca"
            client = PlayHQClient(api_key=secrets["api_key"], tenant=tenant, base_url=host_for_tenant(tenant))
            client.get(f"/v1/organisations/{config.get('org_id')}/seasons")
            return True, "Connected — PlayHQ returned data for this organisation."
        if provider == "custom_api":
            import httpx
            url = net.validate_public_url(str(config.get("base_url", "")))   # SSRF guard before the request
            headers = {"x-api-key": secrets["api_key"]} if secrets.get("api_key") else {}
            r = httpx.get(url, headers=headers, timeout=15.0)
            return (r.status_code < 500), f"Endpoint responded with HTTP {r.status_code}."
        return False, "No connectivity test for this provider."
    except ValueError as exc:
        return False, f"Configuration error: {exc}"
    except Exception as exc:                                              # noqa: BLE001 - report, never leak secrets
        return False, f"Connection failed ({type(exc).__name__})."


def _record_test(conn: Connection, workspace_id: UUID, actor: str, cred_id: UUID, ok: bool, message: str) -> dict[str, Any]:
    conn.execute(text("UPDATE workspace_credential SET last_test_ok = :ok, last_test_at = now(), "
                      "last_test_message = :m, updated_at = now() WHERE id = :id AND workspace_id = :w"),
                 {"ok": ok, "m": message[:300], "id": cred_id, "w": workspace_id})
    audit.write_audit(conn, workspace_id, actor, "integration.credential.test", entity="integration",
                      entity_id=str(cred_id), after={"ok": ok})
    row = _get(conn, workspace_id, cred_id)
    return {**_public_row(row), "test_ok": ok, "test_message": message}


def integration_audit(conn: Connection, workspace_id: UUID, *, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT action, actor, entity_id, at FROM audit_log WHERE workspace_id = :w "
             "AND entity = 'integration' ORDER BY at DESC LIMIT :lim"),
        {"w": workspace_id, "lim": limit}).mappings().all()
    return [{"action": r["action"], "actor": r["actor"], "provider": r["entity_id"],
             "at": r["at"].isoformat() if r["at"] else None} for r in rows]
