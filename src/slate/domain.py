"""Domain entities, independent of storage.

Repositories return and accept these dataclasses; SQLAlchemy models never leave
``repositories/sql.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from slate.scheduling import Recurrence


class TaskStatus(StrEnum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELED = "canceled"


CLOSED_STATUSES = frozenset({TaskStatus.DONE, TaskStatus.CANCELED})


class ProjectStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    PAUSED = "paused"
    DONE = "done"
    CANCELED = "canceled"


# 0 none, 1 urgent, 2 high, 3 medium, 4 low (Linear's order).
PRIORITIES = (0, 1, 2, 3, 4)

TASK_PREFIX = "SLT"


def task_key(task_id: int) -> str:
    return f"{TASK_PREFIX}-{task_id}"


@dataclass
class Area:
    name: str
    color: str = "#6b7280"
    position: int = 0
    source: str | None = None
    source_id: str | None = None
    id: int | None = None
    uuid: UUID = field(default_factory=uuid4)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Project:
    name: str
    area_id: int | None = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    description: str = ""
    target_date: date | None = None
    color: str | None = None
    position: int = 0
    source: str | None = None
    source_id: str | None = None
    id: int | None = None
    uuid: UUID = field(default_factory=uuid4)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Label:
    name: str
    color: str = "#6b7280"
    source: str | None = None
    source_id: str | None = None
    id: int | None = None
    uuid: UUID = field(default_factory=uuid4)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Task:
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: int = 0
    project_id: int | None = None
    area_id: int | None = None
    parent_id: int | None = None
    due_date: date | None = None
    due_time: time | None = None
    recurrence: Recurrence | None = None
    completed_runs: int = 0
    completed_at: datetime | None = None
    label_ids: list[int] = field(default_factory=list)
    position: int = 0
    source: str | None = None
    source_id: str | None = None
    id: int | None = None
    uuid: UUID = field(default_factory=uuid4)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_closed(self) -> bool:
        return self.status in CLOSED_STATUSES

    @property
    def is_inbox(self) -> bool:
        return self.project_id is None and self.area_id is None


@dataclass
class Comment:
    task_id: int
    body: str
    source: str | None = None
    source_id: str | None = None
    id: int | None = None
    uuid: UUID = field(default_factory=uuid4)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Activity:
    """One entry in a task's history.

    ``kind`` is one of: created, updated, status, completed_run, completed,
    reopened, commented, imported. ``data`` holds kind-specific details, such as
    ``{"field": "due_date", "from": "2026-11-20", "to": "2026-11-21"}``.
    """

    task_id: int
    kind: str
    data: dict[str, Any] = field(default_factory=dict)
    id: int | None = None
    created_at: datetime | None = None


@dataclass
class Settings:
    timezone: str = "America/New_York"


@dataclass
class Account:
    """A person who has signed in, keyed by their identity provider's (issuer, subject)."""

    issuer: str
    subject: str
    name: str
    email: str | None = None
    id: int | None = None
    uuid: UUID = field(default_factory=uuid4)
    created_at: datetime | None = None
    last_login_at: datetime | None = None


@dataclass(frozen=True)
class TaskFilter:
    """Criteria for listing tasks. Unset fields do not filter.

    ``inbox`` selects tasks with no project and no area. ``area_id`` matches
    tasks filed to the area directly or through one of its projects.
    ``parent_id`` set to 0 selects top-level tasks only. Closed tasks (done,
    canceled) are excluded unless ``include_closed`` or ``statuses`` names them.
    """

    project_id: int | None = None
    area_id: int | None = None
    inbox: bool = False
    parent_id: int | None = None
    statuses: tuple[TaskStatus, ...] = ()
    priorities: tuple[int, ...] = ()
    label_id: int | None = None
    due_before: date | None = None  # inclusive
    due_after: date | None = None  # inclusive
    has_due: bool | None = None
    recurring: bool | None = None
    q: str | None = None
    include_closed: bool = False
    sort: str = "due"  # due | priority | created | updated | position
    order: str = "asc"
    limit: int | None = None
