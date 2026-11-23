"""Application configuration via environment variables.

Production (on the Box) uses the defaults: SQL storage (Neon Postgres via
DATABASE_URL), OIDC sign-in with Auth0, no seed.
``just dev`` sets SLATE_STORAGE=memory, SLATE_AUTH=dev, SLATE_SEED=demo.
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_database_url() -> str:
    data_dir = os.environ.get("AMP_DEPLOYMENT_DATA_DIRECTORY")
    path = f"{data_dir}/slate.db" if data_dir else "./data.db"
    return f"sqlite+aiosqlite:///{path}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    log_level: str = "INFO"
    log_format: str = "json"
    host: str = "0.0.0.0"
    port: int = 8000

    database_url: str = Field(default_factory=_default_database_url)

    # memory: the in-process fake (data is lost on restart). sql: DATABASE_URL.
    slate_storage: Literal["memory", "sql"] = "sql"
    # dev: always signed in as a fake user. oidc: sign in with OIDC_ISSUER (Auth0).
    slate_auth: Literal["dev", "oidc"] = "oidc"
    # demo: load sample data at startup when the database is empty.
    slate_seed: Literal["none", "demo"] = "none"
    # Freeze the clock for reproducible dev data, such as 2026-11-21T09:00:00-05:00.
    slate_fixed_now: str | None = None

    # Comma-separated bearer tokens for API clients and agents.
    slate_api_tokens: str = ""
    # Comma-separated verified emails allowed to sign in. Empty allows nobody.
    slate_allowed_emails: str = ""

    # Exactly as the provider's discovery document reports it (Auth0 ends with "/").
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""
    # Public base URL, such as https://slate.mattjmcnaughton.com. Amp sets
    # AMP_DEPLOYMENT_URL on a Box; SLATE_PUBLIC_URL overrides it (custom domain).
    slate_public_url: str = ""
    amp_deployment_url: str = ""
    app_session_secret: str = ""

    @property
    def api_tokens(self) -> frozenset[str]:
        return frozenset(t.strip() for t in self.slate_api_tokens.split(",") if t.strip())

    @property
    def allowed_emails(self) -> frozenset[str]:
        return frozenset(
            e.strip().lower() for e in self.slate_allowed_emails.split(",") if e.strip()
        )

    @property
    def redirect_uri(self) -> str:
        if self.oidc_redirect_uri:
            return self.oidc_redirect_uri
        base = self.slate_public_url or self.amp_deployment_url
        return base.rstrip("/") + "/auth/callback" if base else ""
