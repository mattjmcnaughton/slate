"""Task filter and sort semantics, as plain Python.

The memory repository uses these directly; the SQL repository implements the
same semantics in SQL, and the contract tests check that both agree.

Sorting: the chosen key ascends (or descends with ``order="desc"``); tasks
without a value for it (no due date, priority 0) always come last. Ties break
by due date, then priority, then id (creation order), all ascending.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from slate.domain import CLOSED_STATUSES

if TYPE_CHECKING:
    from uuid import UUID

    from slate.domain import Project, Task, TaskFilter


def matches(task: Task, f: TaskFilter, projects: dict[UUID, Project]) -> bool:
    if f.statuses:
        if task.status not in f.statuses:
            return False
    elif not f.include_closed and task.status in CLOSED_STATUSES:
        return False
    if f.project_id is not None and task.project_id != f.project_id:
        return False
    if f.area_id is not None:
        project = projects.get(task.project_id) if task.project_id else None
        task_area = project.area_id if project else task.area_id
        if task_area != f.area_id:
            return False
    if f.inbox and not task.is_inbox:
        return False
    if f.top_level and task.parent_id is not None:
        return False
    if f.parent_id is not None and task.parent_id != f.parent_id:
        return False
    if f.priorities and task.priority not in f.priorities:
        return False
    if f.label_id is not None and f.label_id not in task.label_ids:
        return False
    if f.has_due is not None and (task.due_date is not None) != f.has_due:
        return False
    if f.recurring is not None and (task.recurrence is not None) != f.recurring:
        return False
    if f.due_before is not None and (task.due_date is None or task.due_date > f.due_before):
        return False
    if f.due_after is not None and (task.due_date is None or task.due_date < f.due_after):
        return False
    if f.q:
        needle = f.q.lower()
        if needle not in task.title.lower() and needle not in task.description.lower():
            return False
    return True


_FAR = date.max
_EPOCH = datetime.min


def _tiebreak(t: Task) -> tuple:
    return (t.due_date or _FAR, t.priority or 9, t.id)


def sort_tasks(tasks: list[Task], f: TaskFilter) -> list[Task]:
    def primary(t: Task):
        match f.sort:
            case "priority":
                return t.priority if t.priority else None
            case "created":
                return t.created_at
            case "updated":
                return t.updated_at
            case "position":
                return t.position
            case _:
                return t.due_date

    present = [t for t in tasks if primary(t) is not None]
    missing = [t for t in tasks if primary(t) is None]
    present.sort(key=_tiebreak)
    present.sort(key=primary, reverse=f.order == "desc")  # stable sort keeps ties
    missing.sort(key=_tiebreak)
    result = present + missing
    return result[: f.limit] if f.limit else result
