"""FastAPI dependencies. Everything comes from ``app.state.container``."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from slate.auth import User, bearer
from slate.container import Container
from slate.domain import ApiKeyKind
from slate.repositories.base import UnitOfWork
from slate.services.accounts import check_key
from slate.services.tasks import TaskService


def get_container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]


# Declares the scheme in OpenAPI (the Authorize button in /docs); the key itself is
# read and checked below, so a missing header falls through to the session cookie.
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="apiKey",
    description="A REST API key from Settings → API keys. MCP keys are refused here.",
)


async def get_user(
    request: Request,
    container: ContainerDep,
    _: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User:
    """The caller: an API key (``Authorization: Bearer``) or the browser session."""
    if secret := bearer(request):
        holder = await check_key(container.uow_factory, secret, container.clock)
        if holder is None:
            raise HTTPException(401, "Invalid or revoked API key")
        if holder.key.kind != ApiKeyKind.REST:
            raise HTTPException(403, f"A {holder.key.kind} key cannot use the REST API")
        return User(
            id=holder.account.id,
            workspace_id=holder.key.workspace_id,
            name=holder.account.name,
            email=holder.account.email,
            via="key",
            key_kind=str(holder.key.kind),
        )
    user = await container.authenticator.authenticate(request)
    if user is None:
        raise HTTPException(401, "Not signed in")
    return user


UserDep = Annotated[User, Depends(get_user)]


def require_browser(user: UserDep) -> User:
    """For key management and settings: an API key may not manage itself or its owner."""
    if user.via == "key":
        raise HTTPException(403, "This needs a browser session, not an API key")
    return user


BrowserUserDep = Annotated[User, Depends(require_browser)]


async def get_uow(container: ContainerDep, user: UserDep) -> AsyncIterator[UnitOfWork]:
    """One unit of work per request, scoped to the caller's workspace."""
    async with container.uow_factory(user.workspace_id) as uow:
        yield uow
        await uow.commit()


UowDep = Annotated[UnitOfWork, Depends(get_uow)]


def get_service(uow: UowDep, container: ContainerDep) -> TaskService:
    return TaskService(uow, container.clock)


ServiceDep = Annotated[TaskService, Depends(get_service)]
