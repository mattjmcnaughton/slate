"""Application configuration via environment variables.

Production (on the Box) uses the defaults: SQL storage, Sign in with Amp, no seed.
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
    # dev: always signed in as a fake user. amp: Sign in with Amp.
    slate_auth: Literal["dev", "amp"] = "amp"
    # demo: load sample data at startup when the database is empty.
    slate_seed: Literal["none", "demo"] = "none"
    # Freeze the clock for reproducible dev data, such as 2026-11-21T09:00:00-05:00.
    slate_fixed_now: str | None = None

    # Comma-separated bearer tokens for API clients and agents.
    slate_api_tokens: str = ""
    # Comma-separated Amp user IDs allowed to sign in. Empty allows nobody in amp mode.
    slate_allowed_user_ids: str = ""

    amp_oauth_client_id: str = ""
    amp_oauth_client_secret: str = ""
    amp_oauth_redirect_uri: str = ""
    amp_deployment_url: str = ""
    app_session_secret: str = ""

    @property
    def api_tokens(self) -> frozenset[str]:
        return frozenset(t.strip() for t in self.slate_api_tokens.split(",") if t.strip())

    @property
    def allowed_user_ids(self) -> frozenset[str]:
        return frozenset(u.strip() for u in self.slate_allowed_user_ids.split(",") if u.strip())

    @property
    def redirect_uri(self) -> str:
        if self.amp_oauth_redirect_uri:
            return self.amp_oauth_redirect_uri
        if self.amp_deployment_url:
            return self.amp_deployment_url.rstrip("/") + "/auth/callback"
        return ""
