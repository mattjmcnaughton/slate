"""In-memory repositories: the fake used by tests and ``just dev``.

State lives in a ``MemoryDatabase`` shared by every unit of work created from
the same factory. Entities are copied on the way in and out, so callers cannot
mutate stored state by accident. Writes apply immediately; ``commit`` is a
no-op and nothing rolls back, which is the one deliberate difference from SQL.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Self

from slate.domain import Activity, Area, Comment, Label, Project, Settings, Task
from slate.repositories.base import NotFoundError
from slate.repositories.filtering import matches, sort_tasks

if TYPE_CHECKING:
    from slate.clock import Clock
    from slate.domain import TaskFilter


@dataclass
class MemoryDatabase:
    tables: dict[str, dict[int, Any]] = field(default_factory=dict)
    next_ids: dict[str, int] = field(default_factory=dict)
    settings: Settings = field(default_factory=Settings)

    def table(self, name: str) -> dict[int, Any]:
        return self.tables.setdefault(name, {})

    def next_id(self, name: str) -> int:
        n = self.next_ids.get(name, 1)
        self.next_ids[name] = n + 1
        return n


class _Repo[T]:
    name: str

    def __init__(self, db: MemoryDatabase, clock: Clock) -> None:
        self.db = db
        self.clock = clock

    @property
    def rows(self) -> dict[int, T]:
        return self.db.table(self.name)

    async def get(self, id: int) -> T | None:
        row = self.rows.get(id)
        return copy.deepcopy(row) if row is not None else None

    async def get_by_source(self, source: str, source_id: str) -> T | None:
        for row in self.rows.values():
            if row.source == source and row.source_id == source_id:  # type: ignore[attr-defined]
                return copy.deepcopy(row)
        return None

    async def add(self, entity: T) -> T:
        e: Any = copy.deepcopy(entity)
        source = getattr(e, "source", None)
        if source and await self.get_by_source(source, e.source_id):
            raise ValueError(f"duplicate {self.name} source {source}:{e.source_id}")
        now = self.clock.now()
        e.id = self.db.next_id(self.name)
        e.created_at = e.created_at or now
        if hasattr(e, "updated_at"):
            e.updated_at = e.updated_at or e.created_at
        self.rows[e.id] = e
        return copy.deepcopy(e)

    async def update(self, entity: T) -> T:
        e: Any = copy.deepcopy(entity)
        if e.id not in self.rows:
            raise NotFoundError(f"{self.name} {e.id}")
        e.updated_at = self.clock.now()
        self.rows[e.id] = e
        return copy.deepcopy(e)

    async def delete(self, id: int) -> None:
        if self.rows.pop(id, None) is None:
            raise NotFoundError(f"{self.name} {id}")

    def _all(self) -> list[T]:
        return [copy.deepcopy(r) for r in self.rows.values()]


class MemoryAreaRepository(_Repo[Area]):
    name = "areas"

    async def list(self) -> list[Area]:
        return sorted(self._all(), key=lambda a: (a.position, a.id or 0))


class MemoryProjectRepository(_Repo[Project]):
    name = "projects"

    async def list(self, area_id: int | None = None) -> list[Project]:
        rows = [p for p in self._all() if area_id is None or p.area_id == area_id]
        return sorted(rows, key=lambda p: (p.position, p.id or 0))

    async def delete(self, id: int) -> None:
        await super().delete(id)
        for task in self.db.table("tasks").values():
            if task.project_id == id:
                task.project_id = None


class MemoryLabelRepository(_Repo[Label]):
    name = "labels"

    async def list(self) -> list[Label]:
        return sorted(self._all(), key=lambda label: label.name.lower())

    async def delete(self, id: int) -> None:
        await super().delete(id)
        for task in self.db.table("tasks").values():
            if id in task.label_ids:
                task.label_ids.remove(id)


class MemoryTaskRepository(_Repo[Task]):
    name = "tasks"

    async def list(self, f: TaskFilter) -> list[Task]:
        projects = self.db.table("projects")
        rows = [t for t in self._all() if matches(t, f, projects)]
        return sort_tasks(rows, f)

    async def delete(self, id: int) -> None:
        await super().delete(id)
        for child in [t.id for t in self.rows.values() if t.parent_id == id]:
            await self.delete(child)
        for name in ("comments", "activity"):
            table = self.db.table(name)
            for key in [k for k, v in table.items() if v.task_id == id]:
                del table[key]


class MemoryCommentRepository(_Repo[Comment]):
    name = "comments"

    async def list_for_task(self, task_id: int) -> list[Comment]:
        rows = [c for c in self._all() if c.task_id == task_id]
        return sorted(rows, key=lambda c: (c.created_at, c.id or 0))

    async def count_by_task(self, task_ids: list[int]) -> dict[int, int]:
        wanted = set(task_ids)
        counts: dict[int, int] = {}
        for c in self.rows.values():
            if c.task_id in wanted:
                counts[c.task_id] = counts.get(c.task_id, 0) + 1
        return counts


class MemoryActivityRepository(_Repo[Activity]):
    name = "activity"

    async def list_for_task(self, task_id: int) -> list[Activity]:
        rows = [a for a in self._all() if a.task_id == task_id]
        return sorted(rows, key=lambda a: (a.created_at, a.id or 0))


class MemorySettingsRepository:
    def __init__(self, db: MemoryDatabase) -> None:
        self.db = db

    async def get(self) -> Settings:
        return copy.deepcopy(self.db.settings)

    async def save(self, settings: Settings) -> Settings:
        self.db.settings = copy.deepcopy(settings)
        return copy.deepcopy(settings)


class MemoryUnitOfWork:
    def __init__(self, db: MemoryDatabase, clock: Clock) -> None:
        self.areas = MemoryAreaRepository(db, clock)
        self.projects = MemoryProjectRepository(db, clock)
        self.labels = MemoryLabelRepository(db, clock)
        self.tasks = MemoryTaskRepository(db, clock)
        self.comments = MemoryCommentRepository(db, clock)
        self.activity = MemoryActivityRepository(db, clock)
        self.settings = MemorySettingsRepository(db)

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

    def __call__(self) -> MemoryUnitOfWork:
        return MemoryUnitOfWork(self.db, self.clock)
