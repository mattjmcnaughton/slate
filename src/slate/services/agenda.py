"""Today / Upcoming, and project progress."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING

from slate.domain import Project, Task, TaskFilter, TaskStatus
from slate.scheduling import occurrences

if TYPE_CHECKING:
    from slate.repositories.base import UnitOfWork


@dataclass
class Ghost:
    """A projected future run of a fixed repeating task; not a stored row."""

    task: Task
    date: date


@dataclass
class AgendaDay:
    date: date
    tasks: list[Task] = field(default_factory=list)
    ghosts: list[Ghost] = field(default_factory=list)


@dataclass
class Agenda:
    today: date
    overdue: list[Task]
    days: list[AgendaDay]


async def build_agenda(uow: UnitOfWork, today: date, start: date, end: date) -> Agenda:
    """Open tasks due in [start, end] grouped by day, plus overdue when start <= today.

    Each fixed repeating task appears once, on its real due date; its later
    runs inside the window appear as ghosts. After-completion rules have no
    ghosts because their later dates depend on when you finish.
    """
    open_due = await uow.tasks.list(TaskFilter(has_due=True, due_before=end, sort="due"))
    days = {start + timedelta(days=i): AgendaDay(start + timedelta(days=i)) for i in range((end - start).days + 1)}
    overdue: list[Task] = []
    for t in open_due:
        assert t.due_date is not None
        if t.due_date < today:
            if start <= today:
                overdue.append(t)
        elif t.due_date in days:
            days[t.due_date].tasks.append(t)
        if t.recurrence is not None:
            lo = max(start, t.due_date + timedelta(days=1), today + timedelta(days=1))
            for d in occurrences(t.recurrence, start=lo, end=end):
                days[d].ghosts.append(Ghost(t, d))
    return Agenda(today=today, overdue=overdue, days=list(days.values()))


@dataclass
class Progress:
    done: int
    total: int


async def project_progress(uow: UnitOfWork, projects: list[Project]) -> dict[int, Progress]:
    """done / total of non-repeating, non-canceled, top-level-or-sub tasks."""
    tasks = await uow.tasks.list(TaskFilter(include_closed=True, recurring=False))
    out = {p.id: Progress(0, 0) for p in projects if p.id is not None}
    for t in tasks:
        if t.project_id in out and t.status != TaskStatus.CANCELED:
            out[t.project_id].total += 1
            if t.status == TaskStatus.DONE:
                out[t.project_id].done += 1
    return out
