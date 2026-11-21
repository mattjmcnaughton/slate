"""Task business rules: creation, edits, completion, recurrence roll-forward."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from slate.domain import (
    CLOSED_STATUSES,
    Activity,
    Comment,
    Task,
    TaskFilter,
    TaskStatus,
)
from slate.repositories.base import NotFoundError
from slate.scheduling import (
    EntityRef,
    ParseContext,
    QuickAddResult,
    Recurrence,
    ScheduleResult,
    first_on_or_after,
    next_due,
    parse_quick_add,
    parse_schedule,
)

if TYPE_CHECKING:
    from slate.clock import Clock
    from slate.repositories.base import UnitOfWork


class ValidationError(ValueError):
    """A request that breaks a domain rule; routers turn it into HTTP 422."""


def parse_task_ref(ref: str | int) -> int:
    s = str(ref).strip().upper()
    if s.startswith("SLT-"):
        s = s[4:]
    if not s.isdigit():
        raise NotFoundError(f"task {ref}")
    return int(s)


def _jsonable(v: Any) -> Any:
    if isinstance(v, date | time | datetime):
        return v.isoformat()
    if isinstance(v, Recurrence):
        return v.text or v.rrule
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    return str(v) if hasattr(v, "value") else v


TRACKED = (
    "title",
    "description",
    "status",
    "priority",
    "project_id",
    "area_id",
    "parent_id",
    "due_date",
    "due_time",
    "recurrence",
    "label_ids",
)


class TaskService:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None:
        self.uow = uow
        self.clock = clock

    # --- time ---------------------------------------------------------------

    async def tz(self) -> ZoneInfo:
        return ZoneInfo((await self.uow.settings.get()).timezone)

    async def local_now(self) -> datetime:
        return self.clock.now().astimezone(await self.tz())

    async def today(self) -> date:
        return (await self.local_now()).date()

    async def parse_context(self) -> ParseContext:
        def ref(e: Any) -> EntityRef:
            slug = e.name.lower().replace(" ", "-")
            return EntityRef(e.id, e.name, (slug,))

        return ParseContext(
            now=await self.local_now(),
            areas=tuple(ref(a) for a in await self.uow.areas.list()),
            projects=tuple(ref(p) for p in await self.uow.projects.list()),
            labels=tuple(ref(lb) for lb in await self.uow.labels.list()),
        )

    async def parse(self, text: str) -> QuickAddResult:
        return parse_quick_add(text, await self.parse_context())

    async def parse_schedule(self, text: str) -> ScheduleResult:
        return parse_schedule(text, await self.parse_context())

    # --- reads --------------------------------------------------------------

    async def get(self, ref: str | int) -> Task:
        task = await self.uow.tasks.get(parse_task_ref(ref))
        if task is None:
            raise NotFoundError(f"task {ref}")
        return task

    async def list(self, f: TaskFilter) -> list[Task]:
        return await self.uow.tasks.list(f)

    # --- writes -------------------------------------------------------------

    async def _validate(self, t: Task) -> None:
        if not t.title.strip():
            raise ValidationError("Title is required")
        if t.priority not in (0, 1, 2, 3, 4):
            raise ValidationError("Priority must be 0-4")
        if t.project_id is not None:
            project = await self.uow.projects.get(t.project_id)
            if project is None:
                raise ValidationError(f"Unknown project {t.project_id}")
            # A task in a project takes its area from the project.
            t.area_id = None
        if t.area_id is not None and await self.uow.areas.get(t.area_id) is None:
            raise ValidationError(f"Unknown area {t.area_id}")
        for lid in t.label_ids:
            if await self.uow.labels.get(lid) is None:
                raise ValidationError(f"Unknown label {lid}")
        if t.parent_id is not None:
            parent = await self.uow.tasks.get(t.parent_id)
            if parent is None:
                raise ValidationError(f"Unknown parent {t.parent_id}")
            if parent.parent_id is not None:
                raise ValidationError("Subtasks can only be one level deep")
            if t.id is not None and parent.id == t.id:
                raise ValidationError("A task cannot be its own parent")
            if t.recurrence is not None:
                raise ValidationError("Subtasks cannot repeat")

    async def _log(self, task_id: int, kind: str, data: dict | None = None, at=None) -> None:
        await self.uow.activity.add(
            Activity(task_id=task_id, kind=kind, data=data or {}, created_at=at)
        )

    async def create(self, task: Task, *, log_kind: str = "created") -> Task:
        if task.recurrence is not None and task.due_date is None:
            task.due_date = first_on_or_after(task.recurrence, await self.today())
            if task.due_time is None:
                task.due_time = task.recurrence.time
        await self._validate(task)
        if task.status in CLOSED_STATUSES and task.completed_at is None:
            task.completed_at = self.clock.now()
        created = await self.uow.tasks.add(task)
        await self._log(created.id, log_kind, at=created.created_at)  # type: ignore[arg-type]
        return created

    async def update(self, ref: str | int, changes: dict[str, Any]) -> Task:
        """Apply ``changes`` (field name -> new value) and log what changed.

        A new ``due_date`` on a repeating task moves only this run: the rule is
        kept. Only a new ``recurrence`` replaces the schedule.
        """
        before = await self.get(ref)
        unknown = set(changes) - set(TRACKED)
        if unknown:
            raise ValidationError(f"Unknown fields: {', '.join(sorted(unknown))}")
        after = replace(before, label_ids=list(before.label_ids), **changes)
        if "recurrence" in changes and after.recurrence is not None and "due_date" not in changes:
            after.due_date = first_on_or_after(after.recurrence, await self.today())
            after.due_time = after.recurrence.time
            after.completed_runs = 0
        if "status" in changes and after.status != before.status:
            if after.status == TaskStatus.DONE and before.recurrence is not None:
                raise ValidationError("Use complete to finish a run of a repeating task")
            after.completed_at = self.clock.now() if after.status in CLOSED_STATUSES else None
        await self._validate(after)
        saved = await self.uow.tasks.update(after)
        for field in TRACKED:
            old, new = getattr(before, field), getattr(saved, field)
            if old != new:
                kind = "status" if field == "status" else "updated"
                await self._log(
                    saved.id,  # type: ignore[arg-type]
                    kind,
                    {"field": field, "from": _jsonable(old), "to": _jsonable(new)},
                )
        return saved

    async def complete(self, ref: str | int) -> Task:
        """Complete a task, or one run of a repeating task.

        A repeating task rolls forward to its next date and stays open. When
        its series has ended it becomes done for good.
        """
        task = await self.get(ref)
        if task.is_closed:
            return task
        today = await self.today()
        if task.recurrence is None:
            return await self._close(task, TaskStatus.DONE, "completed")
        runs = task.completed_runs + 1
        nxt = next_due(
            task.recurrence,
            current_due=task.due_date or today,
            completed_on=today,
            today=today,
            completed_runs=runs,
        )
        await self._log(
            task.id,  # type: ignore[arg-type]
            "completed_run",
            {"due": _jsonable(task.due_date), "next": _jsonable(nxt)},
        )
        task.completed_runs = runs
        if nxt is None:
            return await self._close(task, TaskStatus.DONE, "completed")
        task.due_date = nxt
        task.due_time = task.recurrence.time or task.due_time
        if task.status == TaskStatus.BACKLOG:
            task.status = TaskStatus.TODO
        return await self.uow.tasks.update(task)

    async def _close(self, task: Task, status: TaskStatus, kind: str) -> Task:
        prev = task.status
        task.status = status
        task.completed_at = self.clock.now()
        saved = await self.uow.tasks.update(task)
        await self._log(saved.id, kind, {"from": str(prev)})  # type: ignore[arg-type]
        return saved

    async def reopen(self, ref: str | int) -> Task:
        task = await self.get(ref)
        if not task.is_closed:
            return task
        task.status = TaskStatus.TODO
        task.completed_at = None
        saved = await self.uow.tasks.update(task)
        await self._log(saved.id, "reopened")  # type: ignore[arg-type]
        return saved

    async def open_subtasks(self, task_id: int) -> int:
        return len(await self.uow.tasks.list(TaskFilter(parent_id=task_id)))

    async def delete(self, ref: str | int) -> None:
        await self.uow.tasks.delete(parse_task_ref(ref))

    # --- comments -----------------------------------------------------------

    async def add_comment(self, ref: str | int, body: str, created_at=None) -> Comment:
        task = await self.get(ref)
        if not body.strip():
            raise ValidationError("Comment is empty")
        c = await self.uow.comments.add(
            Comment(task_id=task.id, body=body, created_at=created_at)  # type: ignore[arg-type]
        )
        await self._log(task.id, "commented", {"comment_id": c.id}, at=c.created_at)  # type: ignore[arg-type]
        return c
