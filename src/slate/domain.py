"""Domain entities, independent of storage.

Repositories return and accept these dataclasses; SQLAlchemy models never leave
``repositories/sql.py``.
"""

from __future__ import annotations

import os
import threading
import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import StrEnum
from typing import Any
from uuid import UUID

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

_id_lock = threading.Lock()
_last_ms = 0
_last_tail = 0


def new_id() -> UUID:
    """A UUIDv7: time-ordered and increasing within this process.

    Every id is a UUID. Sorting by id is creation order, which breaks ties
    between rows created in the same instant (or under a fixed test clock).
    """
    global _last_ms, _last_tail
    with _id_lock:
        ms = _time.time_ns() // 1_000_000
        if ms <= _last_ms:
            ms, tail = _last_ms, _last_tail + 1
        else:
            tail = int.from_bytes(os.urandom(10), "big") >> 7  # 73 bits: room to count up
        _last_ms, _last_tail = ms, tail
    value = (ms << 80) | (7 << 76) | ((tail >> 62) << 64) | (2 << 62) | (tail & ((1 << 62) - 1))
    return UUID(int=value)


def task_key(number: int) -> str:
    """The human key for a task's per-workspace number, such as SLT-12."""
    return f"{TASK_PREFIX}-{number}"


@dataclass
class Area:
    name: str
    color: str = "#6b7280"
    position: int = 0
    source: str | None = None
    source_id: str | None = None
    workspace_id: UUID | None = None
    id: UUID = field(default_factory=new_id)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Project:
    name: str
    area_id: UUID | None = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    description: str = ""
    target_date: date | None = None
    color: str | None = None
    position: int = 0
    source: str | None = None
    source_id: str | None = None
    workspace_id: UUID | None = None
    id: UUID = field(default_factory=new_id)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Label:
    name: str
    color: str = "#6b7280"
    source: str | None = None
    source_id: str | None = None
    workspace_id: UUID | None = None
    id: UUID = field(default_factory=new_id)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Task:
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: int = 0
    project_id: UUID | None = None
    area_id: UUID | None = None
    parent_id: UUID | None = None
    due_date: date | None = None
    due_time: time | None = None
    recurrence: Recurrence | None = None
    completed_runs: int = 0
    completed_at: datetime | None = None
    label_ids: list[UUID] = field(default_factory=list)
    position: int = 0
    source: str | None = None
    source_id: str | None = None
    number: int | None = None  # per workspace; the key is SLT-<number>
    workspace_id: UUID | None = None
    id: UUID = field(default_factory=new_id)
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
    task_id: UUID
    body: str
    source: str | None = None
    source_id: str | None = None
    workspace_id: UUID | None = None
    id: UUID = field(default_factory=new_id)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Activity:
    """One entry in a task's history.

    ``kind`` is one of: created, updated, status, completed_run, completed,
    reopened, commented, imported. ``data`` holds kind-specific details, such as
    ``{"field": "due_date", "from": "2026-11-20", "to": "2026-11-21"}``.
    """

    task_id: UUID
    kind: str
    data: dict[str, Any] = field(default_factory=dict)
    workspace_id: UUID | None = None
    id: UUID = field(default_factory=new_id)
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
    id: UUID = field(default_factory=new_id)
    created_at: datetime | None = None
    last_login_at: datetime | None = None


@dataclass
class Workspace:
    """The boundary that owns areas, projects, labels, and tasks. One per user for now."""

    owner_id: UUID
    name: str = "Personal"
    timezone: str = "America/New_York"
    next_task_number: int = 1
    id: UUID = field(default_factory=new_id)
    created_at: datetime | None = None


class ApiKeyKind(StrEnum):
    REST = "rest"  # the /api routes
    MCP = "mcp"  # reserved for a future /mcp endpoint; refused by /api


@dataclass
class ApiKey:
    """A user's bearer credential. Only the SHA-256 digest of the secret is stored."""

    user_id: UUID
    workspace_id: UUID
    name: str
    digest: str
    kind: ApiKeyKind = ApiKeyKind.REST
    id: UUID = field(default_factory=new_id)
    created_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


@dataclass(frozen=True)
class TaskFilter:
    """Criteria for listing tasks. Unset fields do not filter.

    ``inbox`` selects tasks with no project and no area. ``area_id`` matches
    tasks filed to the area directly or through one of its projects.
    ``top_level`` selects tasks without a parent. Closed tasks (done,
    canceled) are excluded unless ``include_closed`` or ``statuses`` names them.
    """

    project_id: UUID | None = None
    area_id: UUID | None = None
    inbox: bool = False
    top_level: bool = False
    parent_id: UUID | None = None
    statuses: tuple[TaskStatus, ...] = ()
    priorities: tuple[int, ...] = ()
    label_id: UUID | None = None
    due_before: date | None = None  # inclusive
    due_after: date | None = None  # inclusive
    has_due: bool | None = None
    recurring: bool | None = None
    q: str | None = None
    include_closed: bool = False
    sort: str = "due"  # due | priority | created | updated | position
    order: str = "asc"
    limit: int | None = None
