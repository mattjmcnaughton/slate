"""Composition root: builds the object graph from settings.

Tests build a ``Container`` directly with fakes; ``build_container`` is the only
place that reads settings to choose implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from itsdangerous import URLSafeTimedSerializer

from slate.auth import (
    Authenticator,
    DevAuthenticator,
    OAuthProvider,
    OIDCProvider,
    SessionAuthenticator,
)
from slate.clock import Clock, FixedClock, SystemClock
from slate.repositories.memory import MemoryUnitOfWorkFactory

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from slate.config import Settings
    from slate.repositories.base import UnitOfWorkFactory


@dataclass
class Container:
    clock: Clock
    uow_factory: UnitOfWorkFactory
    authenticator: Authenticator
    oauth: OAuthProvider | None = None
    signer: URLSafeTimedSerializer | None = None
    allowed_user_ids: frozenset[str] = frozenset()
    allowed_emails: frozenset[str] = frozenset()
    secure_cookies: bool = True
    # Where the provider sends the browser after sign-out; must be one of its
    # Allowed Logout URLs. "" means this request's own base URL.
    public_url: str = ""
    # Run in order at startup (migrations, seeding); each gets the container.
    startup: list[Callable[[Container], Awaitable[None]]] = field(default_factory=list)
    shutdown: list[Callable[[], Awaitable[None]]] = field(default_factory=list)


def oauth_configuration_error(settings: Settings) -> str | None:
    if not settings.oidc_issuer:
        return "Sign-in is not configured (OIDC_ISSUER)."
    if not settings.oidc_client_id or not settings.oidc_client_secret:
        return "Sign-in is not configured (OIDC_CLIENT_ID / OIDC_CLIENT_SECRET)."
    if len(settings.app_session_secret) < 32:
        return "APP_SESSION_SECRET must be at least 32 characters."
    if not settings.redirect_uri:
        return "No redirect URI (set OIDC_REDIRECT_URI, SLATE_PUBLIC_URL, or AMP_DEPLOYMENT_URL)."
    return None


def build_container(settings: Settings) -> Container:
    clock: Clock = (
        FixedClock(datetime.fromisoformat(settings.slate_fixed_now))
        if settings.slate_fixed_now
        else SystemClock()
    )

    startup: list = []
    shutdown: list = []
    if settings.slate_storage == "memory":
        uow_factory: UnitOfWorkFactory = MemoryUnitOfWorkFactory(clock)
    else:
        from slate.db import make_engine, make_sessionmaker, run_migrations
        from slate.repositories.sql import SqlUnitOfWorkFactory

        engine = make_engine(settings.database_url)
        uow_factory = SqlUnitOfWorkFactory(make_sessionmaker(engine), clock)

        async def migrate(_: Container) -> None:
            await run_migrations(engine)

        startup.append(migrate)
        shutdown.append(engine.dispose)

    secure = not settings.redirect_uri.startswith("http://")
    if settings.slate_auth == "dev":
        from slate.seed import provision_dev_user, seed_if_empty

        startup.append(provision_dev_user)
        if settings.slate_seed == "demo":
            startup.append(seed_if_empty)
        return Container(
            clock=clock,
            uow_factory=uow_factory,
            authenticator=DevAuthenticator(),
            startup=startup,
            shutdown=shutdown,
            secure_cookies=False,
        )

    # Without a session secret nothing can be signed; a random one keeps the app
    # up (sessions reset on restart) and /auth/signin explains what is missing.
    secret = settings.app_session_secret or __import__("secrets").token_urlsafe(48)
    signer = URLSafeTimedSerializer(secret)
    oauth = (
        OIDCProvider(
            settings.oidc_issuer,
            settings.oidc_client_id,
            settings.oidc_client_secret,
            settings.redirect_uri,
        )
        if oauth_configuration_error(settings) is None
        else None
    )
    return Container(
        clock=clock,
        uow_factory=uow_factory,
        authenticator=SessionAuthenticator(signer),
        oauth=oauth,
        signer=signer,
        allowed_user_ids=settings.allowed_user_ids,
        allowed_emails=settings.allowed_emails,
        secure_cookies=secure,
        public_url=settings.public_url,
        startup=startup,
        shutdown=shutdown,
    )
