"""In-memory repositories: the fake used by tests and ``just dev``.

State lives in a ``MemoryDatabase`` shared by every unit of work created from
the same factory. Entities are copied on the way in and out, so callers cannot
mutate stored state by accident. Writes apply immediately; ``commit`` is a
no-op and nothing rolls back, which is the one deliberate difference from SQL.
Owned repositories see only rows of the unit of work's workspace.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Self

from slate.domain import (
    Account,
    Activity,
    ApiKey,
    Area,
    Comment,
    Label,
    Project,
    Settings,
    Task,
    Workspace,
)
from slate.repositories.base import NotFoundError
from slate.repositories.filtering import matches, sort_tasks

if TYPE_CHECKING:
    from uuid import UUID

    from slate.clock import Clock
    from slate.domain import TaskFilter


@dataclass
class MemoryDatabase:
    tables: dict[str, dict[UUID, Any]] = field(default_factory=dict)

    def table(self, name: str) -> dict[UUID, Any]:
        return self.tables.setdefault(name, {})


class _Owned:
    def __init__(self, db: MemoryDatabase, clock: Clock, workspace_id: UUID | None) -> None:
        self.db = db
        self.clock = clock
        self._ws = workspace_id

    @property
    def ws(self) -> UUID:
        if self._ws is None:
            raise RuntimeError("this unit of work was opened without a workspace")
        return self._ws

    def mine(self, name: str) -> list[Any]:
        """This workspace's rows of ``name``, stored objects (not copies)."""
        return [r for r in self.db.table(name).values() if r.workspace_id == self.ws]


class _Repo[T](_Owned):
    name: str

    @property
    def rows(self) -> dict[UUID, T]:
        return self.db.table(self.name)

    def _row(self, id: UUID) -> Any:
        row: Any = self.rows.get(id)
        return row if row is not None and row.workspace_id == self.ws else None

    async def get(self, id: UUID) -> T | None:
        row = self._row(id)
        return copy.deepcopy(row) if row is not None else None

    async def get_by_source(self, source: str, source_id: str) -> T | None:
        for row in self.mine(self.name):
            if row.source == source and row.source_id == source_id:
                return copy.deepcopy(row)
        return None

    async def add(self, entity: T) -> T:
        e: Any = copy.deepcopy(entity)
        source = getattr(e, "source", None)
        if source and await self.get_by_source(source, e.source_id):
            raise ValueError(f"duplicate {self.name} source {source}:{e.source_id}")
        if e.id in self.rows:
            raise ValueError(f"duplicate {self.name} id {e.id}")
        now = self.clock.now()
        e.workspace_id = self.ws
        e.created_at = e.created_at or now
        if hasattr(e, "updated_at"):
            e.updated_at = e.updated_at or e.created_at
        self._before_add(e)
        self.rows[e.id] = e
        return copy.deepcopy(e)

    def _before_add(self, e: Any) -> None:
        pass

    async def update(self, entity: T) -> T:
        e: Any = copy.deepcopy(entity)
        old = self._row(e.id)
        if old is None:
            raise NotFoundError(f"{self.name} {e.id}")
        e.workspace_id = self.ws
        e.updated_at = self.clock.now()
        self.rows[e.id] = e
        return copy.deepcopy(e)

    async def delete(self, id: UUID) -> None:
        if self._row(id) is None:
            raise NotFoundError(f"{self.name} {id}")
        del self.rows[id]

    def _all(self) -> list[T]:
        return [copy.deepcopy(r) for r in self.mine(self.name)]


class MemoryAreaRepository(_Repo[Area]):
    name = "areas"

    async def list(self) -> list[Area]:
        return sorted(self._all(), key=lambda a: (a.position, a.id))

    async def delete(self, id: UUID) -> None:
        await super().delete(id)
        for row in (*self.mine("projects"), *self.mine("tasks")):
            if row.area_id == id:
                row.area_id = None


class MemoryProjectRepository(_Repo[Project]):
    name = "projects"

    async def list(self, area_id: UUID | None = None) -> list[Project]:
        rows = [p for p in self._all() if area_id is None or p.area_id == area_id]
        return sorted(rows, key=lambda p: (p.position, p.id))

    async def delete(self, id: UUID) -> None:
        await super().delete(id)
        for task in self.mine("tasks"):
            if task.project_id == id:
                task.project_id = None


class MemoryLabelRepository(_Repo[Label]):
    name = "labels"

    async def list(self) -> list[Label]:
        return sorted(self._all(), key=lambda label: (label.name.lower(), label.id))

    async def delete(self, id: UUID) -> None:
        await super().delete(id)
        for task in self.mine("tasks"):
            if id in task.label_ids:
                task.label_ids.remove(id)


class MemoryTaskRepository(_Repo[Task]):
    name = "tasks"

    def _before_add(self, e: Any) -> None:
        ws = self.db.table("workspaces")[self.ws]
        e.number = ws.next_task_number
        ws.next_task_number += 1

    async def get_by_number(self, number: int) -> Task | None:
        for row in self.mine(self.name):
            if row.number == number:
                return copy.deepcopy(row)
        return None

    async def update(self, entity: Task) -> Task:
        old = self._row(entity.id)
        if old is not None:
            entity = copy.deepcopy(entity)
            entity.number = old.number  # numbers never change
        return await super().update(entity)

    async def list(self, f: TaskFilter) -> list[Task]:
        projects = {p.id: p for p in self.mine("projects")}
        rows = [t for t in self._all() if matches(t, f, projects)]
        return sort_tasks(rows, f)

    async def delete(self, id: UUID) -> None:
        await super().delete(id)
        for child in [t.id for t in self.mine(self.name) if t.parent_id == id]:
            await self.delete(child)
        for name in ("comments", "activity"):
            table = self.db.table(name)
            for key in [k for k, v in table.items() if v.task_id == id]:
                del table[key]


class MemoryCommentRepository(_Repo[Comment]):
    name = "comments"

    async def list_for_task(self, task_id: UUID) -> list[Comment]:
        rows = [c for c in self._all() if c.task_id == task_id]
        return sorted(rows, key=lambda c: (c.created_at, c.id))

    async def count_by_task(self, task_ids: list[UUID]) -> dict[UUID, int]:
        wanted = set(task_ids)
        counts: dict[UUID, int] = {}
        for c in self.mine(self.name):
            if c.task_id in wanted:
                counts[c.task_id] = counts.get(c.task_id, 0) + 1
        return counts


class MemoryActivityRepository(_Repo[Activity]):
    name = "activity"

    async def list_for_task(self, task_id: UUID) -> list[Activity]:
        rows = [a for a in self._all() if a.task_id == task_id]
        return sorted(rows, key=lambda a: (a.created_at, a.id))


class MemorySettingsRepository(_Owned):
    def _workspace(self) -> Workspace:
        ws = self.db.table("workspaces").get(self.ws)
        if ws is None:
            raise NotFoundError(f"workspace {self.ws}")
        return ws

    async def get(self) -> Settings:
        return Settings(timezone=self._workspace().timezone)

    async def save(self, settings: Settings) -> Settings:
        self._workspace().timezone = settings.timezone
        return copy.deepcopy(settings)


class MemoryUserRepository:
    def __init__(self, db: MemoryDatabase, clock: Clock) -> None:
        self.rows: dict[UUID, Account] = db.table("users")
        self.clock = clock

    async def get(self, id: UUID) -> Account | None:
        return copy.deepcopy(self.rows.get(id))

    async def record_sign_in(self, account: Account) -> Account:
        now = self.clock.now()
        row = next(
            (
                r
                for r in self.rows.values()
                if (r.issuer, r.subject) == (account.issuer, account.subject)
            ),
            None,
        )
        if row is None:
            row = Account(account.issuer, account.subject, account.name, id=account.id)
            row.created_at = now
            self.rows[row.id] = row
        row.name, row.email, row.last_login_at = account.name, account.email, now
        return copy.deepcopy(row)


class MemoryWorkspaceRepository:
    def __init__(self, db: MemoryDatabase, clock: Clock) -> None:
        self.rows: dict[UUID, Workspace] = db.table("workspaces")
        self.clock = clock

    async def get(self, id: UUID) -> Workspace | None:
        return copy.deepcopy(self.rows.get(id))

    async def for_owner(self, user_id: UUID) -> Workspace | None:
        return copy.deepcopy(next((w for w in self.rows.values() if w.owner_id == user_id), None))

    async def add(self, workspace: Workspace) -> Workspace:
        if any(w.owner_id == workspace.owner_id for w in self.rows.values()):
            raise ValueError(f"user {workspace.owner_id} already has a workspace")
        w = copy.deepcopy(workspace)
        w.created_at = w.created_at or self.clock.now()
        self.rows[w.id] = w
        return copy.deepcopy(w)


class MemoryApiKeyRepository:
    def __init__(self, db: MemoryDatabase, clock: Clock) -> None:
        self.rows: dict[UUID, ApiKey] = db.table("api_keys")
        self.clock = clock

    async def add(self, key: ApiKey) -> ApiKey:
        k = copy.deepcopy(key)
        k.created_at = k.created_at or self.clock.now()
        self.rows[k.id] = k
        return copy.deepcopy(k)

    async def get_by_digest(self, digest: str) -> ApiKey | None:
        return copy.deepcopy(next((k for k in self.rows.values() if k.digest == digest), None))

    async def list_for_user(self, user_id: UUID) -> list[ApiKey]:
        rows = [copy.deepcopy(k) for k in self.rows.values() if k.user_id == user_id]
        return sorted(rows, key=lambda k: k.id, reverse=True)

    async def update(self, key: ApiKey) -> ApiKey:
        if key.id not in self.rows:
            raise NotFoundError(f"api key {key.id}")
        self.rows[key.id] = copy.deepcopy(key)
        return copy.deepcopy(key)


class MemoryUnitOfWork:
    def __init__(self, db: MemoryDatabase, clock: Clock, workspace_id: UUID | None) -> None:
        self.workspace_id = workspace_id
        self.users = MemoryUserRepository(db, clock)
        self.workspaces = MemoryWorkspaceRepository(db, clock)
        self.api_keys = MemoryApiKeyRepository(db, clock)
        self.areas = MemoryAreaRepository(db, clock, workspace_id)
        self.projects = MemoryProjectRepository(db, clock, workspace_id)
        self.labels = MemoryLabelRepository(db, clock, workspace_id)
        self.tasks = MemoryTaskRepository(db, clock, workspace_id)
        self.comments = MemoryCommentRepository(db, clock, workspace_id)
        self.activity = MemoryActivityRepository(db, clock, workspace_id)
        self.settings = MemorySettingsRepository(db, clock, workspace_id)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def commit(self) -> None:
        return None


class MemoryUnitOfWorkFactory:
    def __init__(self, clock: Clock, db: MemoryDatabase | None = None) -> None:
        self.clock = clock
        self.db = db or MemoryDatabase()

    def __call__(self, workspace_id: UUID | None = None) -> MemoryUnitOfWork:
        return MemoryUnitOfWork(self.db, self.clock, workspace_id)
