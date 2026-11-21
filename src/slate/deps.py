"""FastAPI dependencies. Everything comes from ``app.state.container``."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from slate.auth import User
from slate.container import Container
from slate.repositories.base import UnitOfWork
from slate.services.tasks import TaskService


def get_container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_user(request: Request, container: ContainerDep) -> User:
    user = await container.authenticator.authenticate(request)
    if user is None:
        raise HTTPException(401, "Not signed in")
    return user


UserDep = Annotated[User, Depends(get_user)]


async def get_uow(container: ContainerDep, _: UserDep) -> AsyncIterator[UnitOfWork]:
    """One unit of work per request, committed when the handler succeeds."""
    async with container.uow_factory() as uow:
        yield uow
        await uow.commit()


UowDep = Annotated[UnitOfWork, Depends(get_uow)]


def get_service(uow: UowDep, container: ContainerDep) -> TaskService:
    return TaskService(uow, container.clock)


ServiceDep = Annotated[TaskService, Depends(get_service)]
