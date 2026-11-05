"""Configuration management — all settings from environment / .env.

Secrets (the onestats_app DB password) are NEVER hardcoded. They are read from the
environment or a gitignored .env file. The database URL is assembled from parts so the
password can come from a dedicated env var without appearing in any committed file.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ONESTATS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    env: str = Field(default="development")
    app_name: str = Field(default="OneStats API")
    api_v1_prefix: str = Field(default="/api/v1")
    log_level: str = Field(default="INFO")
    log_json: bool = Field(default=False)

    # --- Local security / CORS (dev defaults; localhost only) ---
    cors_origins: list[str] = Field(
        default=[
            "http://localhost:1420",   # Tauri dev (Vite)
            "http://localhost:5173",   # Vite default
            "tauri://localhost",       # Tauri production webview (macOS/Linux)
            "http://tauri.localhost",  # Tauri 2 production webview (Windows WebView2)
            "https://tauri.localhost", # Tauri 2 production webview (Windows, https variant)
        ]
    )

    # --- Database (least-privilege onestats_app role) ---
    db_host: str = Field(default="localhost")
    db_port: int = Field(default=5432)
    db_name: str = Field(default="onestats")
    db_user: str = Field(default="onestats_app")
    # Runtime password comes from ONESTATS_DB_PASSWORD (env/.env) — never committed.
    db_password: str | None = Field(default=None)
    # Optional full override; if set, takes precedence (e.g. ONESTATS_DB_URL=...).
    db_url_override: str | None = Field(default=None, alias="ONESTATS_DB_URL")

    # --- Migration role (Option B: separate migration-owner from runtime) ---
    # Migrations run as onestats_migrator (owner of the tables / runs DDL). The runtime
    # app NEVER uses this; only Alembic does. Password from ONESTATS_MIGRATOR_PASSWORD.
    migrator_user: str = Field(default="onestats_migrator")
    migrator_password: str | None = Field(default=None)

    # --- Media / logo uploads (workspace-isolated; deliverable 9/20) ---
    media_root: str = Field(default="media")
    max_logo_bytes: int = Field(default=2_000_000)  # 2 MB
    max_logo_pixels: int = Field(default=4096)  # per side; anti decompression-bomb
    # Player/person profile photos — larger than logos (phone photos), still bounded for safety.
    max_photo_bytes: int = Field(default=15_000_000)  # 15 MB
    max_photo_pixels: int = Field(default=10000)  # per side; anti decompression-bomb
    # Research source documents (newspaper scans, PDFs, photographs) — larger than logos.
    max_source_bytes: int = Field(default=30_000_000)  # 30 MB
    # Media archive originals (Phase 11) — preserved at original quality.
    max_media_bytes: int = Field(default=60_000_000)  # 60 MB
    # --- OneVault integration (Phase 11) — OPTIONAL. OneStats runs fully without it. ---
    # The adapter stays interface-only (reports unavailable) unless a REAL OneVault API is configured
    # AND explicitly marked verified. No OneVault API is assumed; the separate OneVault app is untouched.
    onevault_api_url: str | None = Field(default=None)
    onevault_verified: bool = Field(default=False)

    # --- AutoSync connectors (Phase 9) — secrets from env/.env, never committed ---
    # PlayHQ public API key (a UUID "Client ID") and tenant short-name (e.g. 'ca' for cricket).
    # When the key is absent the PlayHQ connector stays interface-only (cannot fetch).
    playhq_api_key: str | None = Field(default=None)       # x-api-key (Client ID, a UUID) — entered later
    playhq_tenant: str = Field(default="ca")                # x-phq-tenant: cricket = "ca"
    playhq_org_id: str | None = Field(default="2a9c6833-92cb-466b-aea8-16fa8277887d")  # RMCC organisation
    # host is region-specific; None → derived from the tenant (CA → api.caprod.playhq.com). Override to pin.
    playhq_base_url: str | None = Field(default=None)
    # Trove (National Library of Australia) API key for historical newspaper search. Free for
    # non-commercial use (register at trove.nla.gov.au). When absent, newspaper search reports that a
    # key is required and fetches nothing. Base URL is overridable for testing.
    trove_api_key: str | None = Field(default=None)
    trove_base_url: str = Field(default="https://api.trove.nla.gov.au/v3")

    # --- Auth / sessions ---
    session_ttl_hours: int = Field(default=12)
    # Local file where the one-time super-admin setup token is written on first run
    # (gitignored; operator-readable). Never logged.
    setup_token_file: str = Field(default=".onestats-setup-token")

    # Phase 15 publishing: the base URL public report/profile snapshots are served from (static host or a
    # future central service). Display/export only — None when not yet deployed. No recurring cost implied.
    public_base_url: str | None = Field(default=None)

    # --- Update system (release management) ---
    # Release channel this server reports to clients: "stable" (default) or "testing".
    release_channel: str = Field(default="stable")
    # HTTPS URL of the update manifest (Tauri latest.json). Defaults to the official OneStats public
    # GitHub Releases endpoint (scotneyhayter-rgb/OneStats); the desktop updater fetches & verifies it
    # directly — the server never proxies downloads. Override with ONESTATS_RELEASE_MANIFEST_URL, or set
    # it to None to report "no update service configured". No recurring cost (GitHub Releases is free).
    release_manifest_url: str | None = Field(
        default="https://github.com/scotneyhayter-rgb/OneStats/releases/latest/download/latest.json"
    )
    # Minutes between automatic (non-blocking) update checks in the desktop app.
    update_check_interval_minutes: int = Field(default=240)
    # Directory for pre-update database backups. None → <media_root>/backups.
    backup_dir: str | None = Field(default=None)

    # Secret-at-rest encryption key(s) for per-workspace API/integration credentials — kept OUT of the
    # application database (env var / OS keystore). Comma-separated Fernet keys; the first encrypts, any
    # decrypts (key rotation). None → an insecure development key is used (warned); set in production.
    encryption_key: str | None = Field(default=None)

    def _build_url(self, user: str, password: str) -> str:
        return str(
            PostgresDsn.build(
                scheme="postgresql+psycopg",
                username=user,
                password=password,
                host=self.db_host,
                port=self.db_port,
                path=self.db_name,
            )
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str | None:
        """Runtime (onestats_app) SQLAlchemy URL, or None if no credential is configured."""
        if self.db_url_override:
            return self.db_url_override
        if self.db_password is None:
            return None
        return self._build_url(self.db_user, self.db_password)

    @property
    def migration_url(self) -> str | None:
        """URL used to APPLY migrations: the migrator role if configured, else the runtime
        URL (fallback for single-role setups). None if nothing is configured."""
        if self.migrator_password is not None:
            return self._build_url(self.migrator_user, self.migrator_password)
        return self.database_url

    @property
    def db_configured(self) -> bool:
        return self.database_url is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()
