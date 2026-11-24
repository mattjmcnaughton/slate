"""OIDC sign-in (Auth0): /auth/signin, /auth/callback, /auth/signout."""

from __future__ import annotations

from html import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import BadSignature

from slate.auth import (
    OAUTH_COOKIE,
    OAUTH_MAX_AGE,
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    Identity,
    OAuthError,
    OAuthTransaction,
    SessionAuthenticator,
    User,
    new_transaction,
)
from slate.container import Container
from slate.deps import ContainerDep
from slate.services.accounts import is_admitted, sign_in

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


@router.get("/callback", response_model=None)
async def callback(
    request: Request,
    container: ContainerDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse | HTMLResponse:
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
    if not is_admitted(identity, container.allowed_user_ids, container.allowed_emails):
        return await _refused(request, container, identity)
    async with container.uow_factory() as uow:
        signed = await sign_in(uow, identity)
        await uow.commit()
    user = User(
        id=signed.account.id,
        workspace_id=signed.workspace.id,
        name=signed.account.name,
        email=signed.account.email,
        sid=identity.session_id,
    )
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


def _home(request: Request, container: Container) -> str:
    return container.public_url or str(request.base_url)


async def _provider_logout(request: Request, container: Container, sid: str | None) -> str:
    """URL that ends the provider's session and comes back home; home when there is none."""
    home = _home(request, container)
    if container.oauth is None:
        return home
    return await container.oauth.logout_url(sid, home) or home


async def _refused(request: Request, container: Container, identity: Identity) -> HTMLResponse:
    # The provider session is still live, so offer to end it: otherwise every
    # sign-in silently returns this same account and the person is stuck.
    switch = await _provider_logout(request, container, identity.session_id)
    who = escape(identity.email or identity.name)
    body = f"""<!doctype html><meta charset="utf-8"><title>Slate: not allowed</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<body style="font:15px/1.5 system-ui,sans-serif;max-width:34rem;margin:15vh auto;padding:0 1rem">
<h1 style="font-size:20px">This account can't use Slate</h1>
<p>You signed in as <b>{who}</b>. Slate is invite-only, and this account isn't on the list.</p>
<p>If you were invited by email, check that you verified the address. Otherwise send the
owner this account id: <code>{escape(identity.subject)}</code></p>
<p><a href="{escape(switch)}">Sign in with a different account</a></p>
</body>"""
    return HTMLResponse(body, status_code=403)


@router.post("/signout")
async def signout(request: Request, container: ContainerDep) -> RedirectResponse:
    """End Slate's session and the provider's, so the next sign-in can pick an account."""
    user = await container.authenticator.authenticate(request)
    resp = RedirectResponse(
        await _provider_logout(request, container, user.sid if user else None), status_code=303
    )
    resp.delete_cookie(SESSION_COOKIE)
    return resp
