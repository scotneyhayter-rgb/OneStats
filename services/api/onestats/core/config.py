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
            "http://localhost:1420",  # Tauri dev (Vite)
            "http://localhost:5173",  # Vite default
            "tauri://localhost",      # Tauri production webview
        ]
    )

    # --- Database (least-privilege onestats_app role) ---
    db_host: str = Field(default="localhost")
    db_port: int = Field(default=5432)
    db_name: str = Field(default="onestats")
    db_user: str = Field(default="onestats_app")
    # Password comes from ONESTATS_DB_PASSWORD (env/.env) — never committed.
    db_password: str | None = Field(default=None)
    # Optional full override; if set, takes precedence (e.g. ONESTATS_DB_URL=...).
    db_url_override: str | None = Field(default=None, alias="ONESTATS_DB_URL")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str | None:
        """Assemble the SQLAlchemy URL, or None if no credential is configured."""
        if self.db_url_override:
            return self.db_url_override
        if self.db_password is None:
            return None
        dsn = PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            path=self.db_name,
        )
        return str(dsn)

    @property
    def db_configured(self) -> bool:
        return self.database_url is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()
