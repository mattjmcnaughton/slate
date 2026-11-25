"""Repository and unit-of-work interfaces.

Two implementations exist: ``memory`` (an in-process fake for tests and local
development) and ``sql`` (SQLAlchemy on SQLite or Postgres). The contract tests
in ``tests/integration/test_repository_contract.py`` run against both.

A unit of work is opened for one workspace (``uow_factory(workspace_id)``).
Every owned repository (areas, projects, labels, tasks, comments, activity,
settings) reads and writes only that workspace: an id from another workspace
behaves exactly like an id that does not exist. ``users``, ``workspaces``, and
``api_keys`` are not workspace-scoped; sign-in and key checks use them from a
unit of work opened without a workspace.
"""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Protocol, Self

if TYPE_CHECKING:
    from uuid import UUID

    from slate.domain import (
        Account,
        Activity,
        AgentMessage,
        ApiKey,
        Area,
        Comment,
        Label,
        PendingChange,
        PendingStatus,
        Project,
        Settings,
        Task,
        TaskFilter,
        Workspace,
    )


class NotFoundError(LookupError):
    """Raised by ``update``/``delete`` when the id does not exist in this workspace."""


class EntityRepository[T](Protocol):
    async def get(self, id: UUID) -> T | None: ...
    async def get_by_source(self, source: str, source_id: str) -> T | None: ...
    async def add(self, entity: T) -> T:
        """Insert into this workspace and return the entity with timestamps set.

        ``created_at``/``updated_at`` already set on the entity are kept, so
        imports can preserve original timestamps.
        """
        ...

    async def update(self, entity: T) -> T:
        """Persist every field and bump ``updated_at``."""
        ...

    async def delete(self, id: UUID) -> None: ...


class AreaRepository(EntityRepository["Area"], Protocol):
    async def list(self) -> builtins.list[Area]:
        """All areas ordered by position, then id."""
        ...


class ProjectRepository(EntityRepository["Project"], Protocol):
    async def list(self, area_id: UUID | None = None) -> builtins.list[Project]:
        """Projects ordered by position, then id."""
        ...


class LabelRepository(EntityRepository["Label"], Protocol):
    async def list(self) -> builtins.list[Label]:
        """All labels ordered by name."""
        ...


class TaskRepository(EntityRepository["Task"], Protocol):
    async def list(self, f: TaskFilter) -> builtins.list[Task]: ...

    async def get_by_number(self, number: int) -> Task | None:
        """The task whose key is SLT-<number> in this workspace."""
        ...

    async def add(self, entity: Task) -> Task:
        """Insert, assigning the workspace's next task number."""
        ...

    async def delete(self, id: UUID) -> None:
        """Delete the task, its subtasks, comments, and activity."""
        ...


class CommentRepository(EntityRepository["Comment"], Protocol):
    async def list_for_task(self, task_id: UUID) -> list[Comment]:
        """Oldest first."""
        ...

    async def count_by_task(self, task_ids: list[UUID]) -> dict[UUID, int]: ...


class ActivityRepository(Protocol):
    async def add(self, entity: Activity, /) -> Activity: ...
    async def list_for_task(self, task_id: UUID) -> list[Activity]:
        """Oldest first."""
        ...


class SettingsRepository(Protocol):
    """The current workspace's settings."""

    async def get(self) -> Settings: ...
    async def save(self, settings: Settings) -> Settings: ...


class PendingChangeRepository(Protocol):
    async def add(self, change: PendingChange) -> PendingChange: ...
    async def get(self, id: UUID) -> PendingChange | None: ...
    async def list(self, status: PendingStatus | None = None) -> builtins.list[PendingChange]:
        """Oldest first."""
        ...

    async def resolve(self, change: PendingChange) -> bool:
        """Set status, error, result, and input if still pending; False otherwise."""
        ...


class AgentMessageRepository(Protocol):
    async def add(self, message: AgentMessage, /) -> AgentMessage: ...
    async def list_for_user(self, user_id: UUID) -> list[AgentMessage]:
        """Oldest first."""
        ...

    async def clear(self, user_id: UUID) -> None: ...


class UserRepository(Protocol):
    async def get(self, id: UUID) -> Account | None: ...
    async def record_sign_in(self, account: Account) -> Account:
        """Upsert by (issuer, subject): refresh name and email, stamp ``last_login_at``."""
        ...


class WorkspaceRepository(Protocol):
    async def get(self, id: UUID) -> Workspace | None: ...
    async def for_owner(self, user_id: UUID) -> Workspace | None: ...
    async def add(self, workspace: Workspace) -> Workspace: ...


class ApiKeyRepository(Protocol):
    async def add(self, key: ApiKey) -> ApiKey: ...
    async def get_by_digest(self, digest: str) -> ApiKey | None: ...
    async def list_for_user(self, user_id: UUID) -> list[ApiKey]:
        """Newest first, revoked keys included."""
        ...

    async def update(self, key: ApiKey) -> ApiKey: ...


class UnitOfWork(Protocol):
    """Repositories are read-only members so implementations may narrow their types."""

    @property
    def users(self) -> UserRepository: ...
    @property
    def workspaces(self) -> WorkspaceRepository: ...
    @property
    def api_keys(self) -> ApiKeyRepository: ...
    @property
    def areas(self) -> AreaRepository: ...
    @property
    def projects(self) -> ProjectRepository: ...
    @property
    def labels(self) -> LabelRepository: ...
    @property
    def tasks(self) -> TaskRepository: ...
    @property
    def comments(self) -> CommentRepository: ...
    @property
    def activity(self) -> ActivityRepository: ...
    @property
    def settings(self) -> SettingsRepository: ...
    @property
    def pending_changes(self) -> PendingChangeRepository: ...
    @property
    def agent_messages(self) -> AgentMessageRepository: ...

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, *exc: object) -> None:
        """Roll back anything not committed."""
        ...

    async def commit(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self, workspace_id: UUID | None = None) -> UnitOfWork:
        """Open a unit of work. Owned repositories need ``workspace_id``."""
        ...
