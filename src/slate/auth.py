"""Authentication: Sign in with Amp for the browser, bearer tokens for agents.

Pieces, all injected through the container:

- ``Authenticator`` resolves the request's user, or None.
  - ``DevAuthenticator``: always the same fake user (local development).
  - ``SessionAuthenticator``: a signed session cookie set after Sign in with Amp.
  Both also accept ``Authorization: Bearer <token>`` for tokens in SLATE_API_TOKENS.
- ``OAuthProvider`` does the network half of OAuth.
  - ``AmpOAuthProvider``: auth.ampcode.com with PKCE and a verified RS256 ID token.
  - ``FakeOAuthProvider`` (tests): returns a fixed identity for any code.

We do not call the Amp API on the user's behalf, so access tokens are not kept;
the session holds only the user's identity.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

AMP_ISSUER = "https://auth.ampcode.com"
AMP_RESOURCE = "https://ampcode.com/api/v2"
SCOPES = "openid profile email"

SESSION_COOKIE = "slate_session"
OAUTH_COOKIE = "slate_oauth"
SESSION_MAX_AGE = 30 * 24 * 3600
OAUTH_MAX_AGE = 10 * 60


@dataclass(frozen=True)
class User:
    id: str
    name: str
    email: str | None = None
    via: str = "session"  # session | token | dev


DEV_USER = User(id="user_dev", name="Dev User", email="dev@example.com", via="dev")


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def _token_user(request: Request, tokens: frozenset[str]) -> User | None:
    token = _bearer(request)
    if token and any(hmac.compare_digest(token, t) for t in tokens):
        return User(id="api", name="API client", via="token")
    return None


class Authenticator(Protocol):
    async def authenticate(self, request: Request) -> User | None: ...


class DevAuthenticator:
    def __init__(self, api_tokens: frozenset[str] = frozenset()) -> None:
        self.api_tokens = api_tokens

    async def authenticate(self, request: Request) -> User | None:
        return _token_user(request, self.api_tokens) or DEV_USER


class SessionAuthenticator:
    def __init__(self, signer: URLSafeTimedSerializer, api_tokens: frozenset[str]) -> None:
        self.signer = signer
        self.api_tokens = api_tokens

    async def authenticate(self, request: Request) -> User | None:
        if user := _token_user(request, self.api_tokens):
            return user
        raw = request.cookies.get(SESSION_COOKIE)
        if not raw:
            return None
        try:
            data = self.signer.loads(raw, max_age=SESSION_MAX_AGE, salt="session")
        except BadSignature:
            return None
        return User(id=data["id"], name=data["name"], email=data.get("email"))

    def session_cookie(self, user: User) -> str:
        return self.signer.dumps(
            {"id": user.id, "name": user.name, "email": user.email}, salt="session"
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


class OAuthProvider(Protocol):
    def authorization_url(self, tx: OAuthTransaction) -> str: ...
    async def exchange(self, code: str, tx: OAuthTransaction) -> User: ...


class AmpOAuthProvider:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.http = http or httpx.AsyncClient(timeout=10)
        self._jwks = jwt.PyJWKClient(f"{AMP_ISSUER}/oauth2/jwks", cache_keys=True)

    def authorization_url(self, tx: OAuthTransaction) -> str:
        params = {
            "client_id": self.client_id,
            "code_challenge": challenge(tx.verifier),
            "code_challenge_method": "S256",
            "nonce": tx.nonce,
            "redirect_uri": self.redirect_uri,
            "resource": AMP_RESOURCE,
            "response_type": "code",
            "scope": SCOPES,
            "state": tx.state,
        }
        return f"{AMP_ISSUER}/oauth2/authorize?{urlencode(params)}"

    async def exchange(self, code: str, tx: OAuthTransaction) -> User:
        resp = await self.http.post(
            f"{AMP_ISSUER}/oauth2/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": tx.verifier,
                "redirect_uri": self.redirect_uri,
                "resource": AMP_RESOURCE,
            },
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            raise OAuthError(f"token exchange failed with HTTP {resp.status_code}")
        id_token = resp.json().get("id_token")
        if not isinstance(id_token, str):
            raise OAuthError("no ID token")
        try:
            key = self._jwks.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                key.key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=AMP_ISSUER,
                options={"require": ["exp", "sub", "iss", "aud"]},
                leeway=60,
            )
        except jwt.PyJWTError as e:
            raise OAuthError(f"invalid ID token: {e}") from e
        if claims.get("nonce") != tx.nonce:
            raise OAuthError("nonce mismatch")
        if claims.get("azp") not in (None, self.client_id):
            raise OAuthError("wrong authorized party")
        name = (
            claims.get("name")
            or " ".join(filter(None, [claims.get("given_name"), claims.get("family_name")]))
            or claims.get("email")
            or "Amp user"
        )
        return User(id=claims["sub"], name=name, email=claims.get("email"))


class FakeOAuthProvider:
    """Accepts any code and signs in as ``user``. For tests only."""

    def __init__(self, user: User) -> None:
        self.user = user

    def authorization_url(self, tx: OAuthTransaction) -> str:
        return f"https://auth.example.test/authorize?{urlencode({'state': tx.state})}"

    async def exchange(self, code: str, tx: OAuthTransaction) -> User:
        if code == "bad":
            raise OAuthError("bad code")
        return self.user
