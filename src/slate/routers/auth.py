"""OIDC sign-in (Auth0): /auth/signin, /auth/callback, /auth/signout."""

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
    User,
    new_transaction,
)
from slate.deps import ContainerDep
from slate.domain import Account

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/signin")
async def signin(container: ContainerDep, return_to: str = "/") -> RedirectResponse:
    if container.oauth is None or container.signer is None:
        raise HTTPException(503, "Sign-in is not configured on this deployment")
    tx = new_transaction(return_to)
    try:
        url = await container.oauth.authorization_url(tx)
    except OAuthError as e:
        raise HTTPException(503, f"Sign-in provider unavailable: {e}") from e
    resp = RedirectResponse(url, status_code=303)
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
        raise HTTPException(503, "Sign-in is not configured on this deployment")
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
        identity = await container.oauth.exchange(code, tx)
    except OAuthError as e:
        raise HTTPException(400, f"Sign-in failed: {e}") from e
    # Only verified emails count; the provider leaves email unset otherwise.
    if not identity.email or identity.email.lower() not in container.allowed_emails:
        raise HTTPException(403, f"{identity.email or identity.name} may not use this app")
    async with container.uow_factory() as uow:
        account = await uow.users.record_sign_in(
            Account(
                issuer=identity.issuer,
                subject=identity.subject,
                name=identity.name,
                email=identity.email,
            )
        )
        await uow.commit()
    user = User(id=str(account.id), name=account.name, email=account.email)
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
