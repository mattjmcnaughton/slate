"""Authentication: OIDC sign-in (Auth0) for the browser, bearer tokens for agents.

Pieces, all injected through the container:

- ``Authenticator`` resolves the request's browser user, or None.
  - ``DevAuthenticator``: always the same dev user (local development).
  - ``SessionAuthenticator``: a signed session cookie set after OIDC sign-in.
  Bearer API keys are checked in ``deps.get_user`` against the database
  (``services/accounts.py``), not here.
- ``OAuthProvider`` does the network half of OAuth.
  - ``OIDCProvider``: any OIDC issuer (Auth0) with PKCE and a verified RS256 ID token.
  - ``FakeOAuthProvider`` (tests): returns a fixed identity for any code.

Access tokens are not kept. Sign-in upserts a row in ``users`` keyed by the
provider's (issuer, subject); the session holds that user's id, workspace id,
name, and email.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode
from uuid import UUID

import httpx
import jwt
from fastapi import Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

SCOPES = "openid profile email"

SESSION_COOKIE = "slate_session"
OAUTH_COOKIE = "slate_oauth"
SESSION_MAX_AGE = 30 * 24 * 3600
OAUTH_MAX_AGE = 10 * 60


@dataclass(frozen=True)
class User:
    """The signed-in person and the workspace every request of theirs acts in."""

    id: UUID
    workspace_id: UUID
    name: str
    email: str | None = None
    via: str = "session"  # session | key | dev
    key_kind: str | None = None  # rest | mcp, when via == "key"


def bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


class Authenticator(Protocol):
    async def authenticate(self, request: Request) -> User | None: ...


DEV_IDENTITY_ISSUER = "dev"


class DevAuthenticator:
    """Every request is the dev user: local development only.

    ``user`` is set at startup, once the dev account and workspace exist.
    """

    def __init__(self) -> None:
        self.user: User | None = None

    async def authenticate(self, request: Request) -> User | None:
        return self.user


class SessionAuthenticator:
    def __init__(self, signer: URLSafeTimedSerializer) -> None:
        self.signer = signer

    async def authenticate(self, request: Request) -> User | None:
        raw = request.cookies.get(SESSION_COOKIE)
        if not raw:
            return None
        try:
            data = self.signer.loads(raw, max_age=SESSION_MAX_AGE, salt="session")
            return User(
                id=UUID(data["id"]),
                workspace_id=UUID(data["ws"]),
                name=data["name"],
                email=data.get("email"),
            )
        except (BadSignature, KeyError, ValueError, TypeError):
            return None  # includes cookies from before workspaces existed

    def session_cookie(self, user: User) -> str:
        return self.signer.dumps(
            {
                "id": str(user.id),
                "ws": str(user.workspace_id),
                "name": user.name,
                "email": user.email,
            },
            salt="session",
        )


# --- OAuth ---------------------------------------------------------------------


@dataclass(frozen=True)
class OAuthTransaction:
    state: str
    nonce: str
    verifier: str
    return_to: str


def new_transaction(return_to: str) -> OAuthTransaction:
    return OAuthTransaction(
        state=secrets.token_urlsafe(32),
        nonce=secrets.token_urlsafe(32),
        verifier=secrets.token_urlsafe(48),
        return_to=safe_return_to(return_to),
    )


def safe_return_to(value: str | None) -> str:
    """Only same-origin paths; anything else goes home."""
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/"
    return value


def challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class OAuthError(Exception):
    pass


@dataclass(frozen=True)
class Identity:
    """Who the identity provider says signed in. ``email`` is set only when verified."""

    issuer: str
    subject: str
    name: str
    email: str | None = None


class OAuthProvider(Protocol):
    async def authorization_url(self, tx: OAuthTransaction) -> str: ...
    async def exchange(self, code: str, tx: OAuthTransaction) -> Identity: ...


class OIDCProvider:
    """Authorization code flow with PKCE against any OIDC issuer (Auth0 in production).

    Endpoints come from the issuer's discovery document, fetched on first use.
    """

    def __init__(
        self,
        issuer: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.issuer = issuer
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.http = http or httpx.AsyncClient(timeout=10)
        self._meta: dict | None = None
        self._keys: dict[str, jwt.PyJWK] = {}

    async def _discover(self) -> dict:
        if self._meta is None:
            url = self.issuer.rstrip("/") + "/.well-known/openid-configuration"
            resp = await self.http.get(url)
            if resp.status_code != 200:
                raise OAuthError(f"discovery failed with HTTP {resp.status_code}")
            meta = resp.json()
            if meta.get("issuer") != self.issuer:
                raise OAuthError("issuer mismatch in discovery document")
            self._meta = meta
        return self._meta

    async def _signing_key(self, id_token: str) -> jwt.PyJWK:
        kid = jwt.get_unverified_header(id_token).get("kid")
        if kid not in self._keys:  # first use or key rotation
            resp = await self.http.get((await self._discover())["jwks_uri"])
            if resp.status_code != 200:
                raise OAuthError(f"JWKS fetch failed with HTTP {resp.status_code}")
            jwks = jwt.PyJWKSet.from_dict(resp.json())
            self._keys = {k.key_id: k for k in jwks.keys if k.key_id}
        if kid not in self._keys:
            raise OAuthError("unknown signing key")
        return self._keys[kid]

    async def authorization_url(self, tx: OAuthTransaction) -> str:
        meta = await self._discover()
        params = {
            "client_id": self.client_id,
            "code_challenge": challenge(tx.verifier),
            "code_challenge_method": "S256",
            "nonce": tx.nonce,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "state": tx.state,
        }
        return f"{meta['authorization_endpoint']}?{urlencode(params)}"

    async def exchange(self, code: str, tx: OAuthTransaction) -> Identity:
        meta = await self._discover()
        resp = await self.http.post(
            meta["token_endpoint"],
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": tx.verifier,
                "redirect_uri": self.redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            raise OAuthError(f"token exchange failed with HTTP {resp.status_code}")
        id_token = resp.json().get("id_token")
        if not isinstance(id_token, str):
            raise OAuthError("no ID token")
        try:
            key = await self._signing_key(id_token)
            claims = jwt.decode(
                id_token,
                key.key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=self.issuer,
                options={"require": ["exp", "sub", "iss", "aud"]},
                leeway=60,
            )
        except jwt.PyJWTError as e:
            raise OAuthError(f"invalid ID token: {e}") from e
        if claims.get("nonce") != tx.nonce:
            raise OAuthError("nonce mismatch")
        if claims.get("azp") not in (None, self.client_id):
            raise OAuthError("wrong authorized party")
        email = claims.get("email") if claims.get("email_verified") else None
        name = claims.get("name") or email or claims.get("nickname") or "Slate user"
        return Identity(issuer=self.issuer, subject=claims["sub"], name=name, email=email)


class FakeOAuthProvider:
    """Accepts any code and signs in as ``identity``. For tests only."""

    def __init__(self, identity: Identity) -> None:
        self.identity = identity

    async def authorization_url(self, tx: OAuthTransaction) -> str:
        return f"https://auth.example.test/authorize?{urlencode({'state': tx.state})}"

    async def exchange(self, code: str, tx: OAuthTransaction) -> Identity:
        if code == "bad":
            raise OAuthError("bad code")
        return self.identity
