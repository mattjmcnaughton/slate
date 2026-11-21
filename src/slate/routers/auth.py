"""Sign in with Amp: /auth/signin, /auth/callback, /auth/signout."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature

from slate.auth import (
    OAUTH_COOKIE,
    OAUTH_MAX_AGE,
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    OAuthError,
    OAuthTransaction,
    SessionAuthenticator,
    new_transaction,
)
from slate.deps import ContainerDep

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/signin")
async def signin(container: ContainerDep, return_to: str = "/") -> RedirectResponse:
    if container.oauth is None or container.signer is None:
        raise HTTPException(503, "Sign in with Amp is not configured on this deployment")
    tx = new_transaction(return_to)
    resp = RedirectResponse(container.oauth.authorization_url(tx), status_code=303)
    resp.set_cookie(
        OAUTH_COOKIE,
        container.signer.dumps(tx.__dict__, salt="oauth"),
        max_age=OAUTH_MAX_AGE,
        httponly=True,
        secure=container.secure_cookies,
        samesite="lax",
        path="/auth",
    )
    return resp


@router.get("/callback")
async def callback(
    request: Request,
    container: ContainerDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if container.oauth is None or container.signer is None:
        raise HTTPException(503, "Sign in with Amp is not configured on this deployment")
    if error:
        raise HTTPException(400, f"Sign-in was not completed: {error}")
    raw = request.cookies.get(OAUTH_COOKIE)
    try:
        data = container.signer.loads(raw or "", max_age=OAUTH_MAX_AGE, salt="oauth")
        tx = OAuthTransaction(**data)
    except (BadSignature, TypeError) as e:
        raise HTTPException(400, "Sign-in expired; start again") from e
    if not code or state != tx.state:
        raise HTTPException(400, "Sign-in state mismatch; start again")
    try:
        user = await container.oauth.exchange(code, tx)
    except OAuthError as e:
        raise HTTPException(400, f"Sign-in failed: {e}") from e
    if user.id not in container.allowed_user_ids:
        raise HTTPException(403, f"{user.name} ({user.id}) is not allowed to use this app")
    auth = container.authenticator
    assert isinstance(auth, SessionAuthenticator)
    resp = RedirectResponse(tx.return_to, status_code=303)
    resp.delete_cookie(OAUTH_COOKIE, path="/auth")
    resp.set_cookie(
        SESSION_COOKIE,
        auth.session_cookie(user),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=container.secure_cookies,
        samesite="lax",
    )
    return resp


@router.post("/signout")
async def signout() -> RedirectResponse:
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp
