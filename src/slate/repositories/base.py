"""Repository and unit-of-work interfaces.

Two implementations exist: ``memory`` (an in-process fake for tests and local
development) and ``sql`` (SQLAlchemy on SQLite or Postgres). The contract tests
in ``tests/integration/test_repository_contract.py`` run against both.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, Self

if TYPE_CHECKING:
    from slate.domain import (
        Account,
        Activity,
        Area,
        Comment,
        Label,
        Project,
        Settings,
        Task,
        TaskFilter,
    )


class NotFoundError(LookupError):
    """Raised by ``update``/``delete`` when the id does not exist."""


class EntityRepository[T](Protocol):
    async def get(self, id: int) -> T | None: ...
    async def get_by_source(self, source: str, source_id: str) -> T | None: ...
    async def add(self, entity: T) -> T:
        """Insert and return the entity with ``id`` and timestamps set.

        ``created_at``/``updated_at`` already set on the entity are kept, so
        imports can preserve original timestamps.
        """
        ...

    async def update(self, entity: T) -> T:
        """Persist every field and bump ``updated_at``."""
        ...

    async def delete(self, id: int) -> None: ...


class AreaRepository(EntityRepository["Area"], Protocol):
    async def list(self) -> list[Area]:
        """All areas ordered by position, then id."""
        ...


class ProjectRepository(EntityRepository["Project"], Protocol):
    async def list(self, area_id: int | None = None) -> list[Project]:
        """Projects ordered by position, then id."""
        ...


class LabelRepository(EntityRepository["Label"], Protocol):
    async def list(self) -> list[Label]:
        """All labels ordered by name."""
        ...


class TaskRepository(EntityRepository["Task"], Protocol):
    async def list(self, f: TaskFilter) -> list[Task]: ...

    async def delete(self, id: int) -> None:
        """Delete the task, its subtasks, comments, and activity."""
        ...


class CommentRepository(EntityRepository["Comment"], Protocol):
    async def list_for_task(self, task_id: int) -> list[Comment]:
        """Oldest first."""
        ...

    async def count_by_task(self, task_ids: list[int]) -> dict[int, int]: ...


class ActivityRepository(Protocol):
    async def add(self, activity: Activity) -> Activity: ...
    async def list_for_task(self, task_id: int) -> list[Activity]:
        """Oldest first."""
        ...


class SettingsRepository(Protocol):
    async def get(self) -> Settings: ...
    async def save(self, settings: Settings) -> Settings: ...


class UserRepository(Protocol):
    async def get(self, id: int) -> Account | None: ...
    async def record_sign_in(self, account: Account) -> Account:
        """Upsert by (issuer, subject): refresh name and email, stamp ``last_login_at``."""
        ...


class UnitOfWork(Protocol):
    users: UserRepository
    areas: AreaRepository
    projects: ProjectRepository
    labels: LabelRepository
    tasks: TaskRepository
    comments: CommentRepository
    activity: ActivityRepository
    settings: SettingsRepository

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, *exc: object) -> None:
        """Roll back anything not committed."""
        ...

    async def commit(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...
