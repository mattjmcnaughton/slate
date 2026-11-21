"""SQLAlchemy repositories for SQLite and Postgres.

Filter and sort semantics mirror ``repositories/filtering.py``; the contract
tests check that this module and the memory fake agree.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.exc import IntegrityError

from slate.domain import (
    CLOSED_STATUSES,
    Activity,
    Area,
    Comment,
    Label,
    Project,
    ProjectStatus,
    Settings,
    Task,
    TaskStatus,
)
from slate.models import (
    ActivityRow,
    AreaRow,
    CommentRow,
    LabelRow,
    ProjectRow,
    SettingsRow,
    TaskLabelRow,
    TaskRow,
)
from slate.repositories.base import NotFoundError
from slate.scheduling import Recurrence, RecurrenceMode

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from slate.clock import Clock
    from slate.domain import TaskFilter


# --- row <-> entity mapping -------------------------------------------------

_SIMPLE = {
    "areas": (AreaRow, Area, ("name", "color", "position")),
    "projects": (
        ProjectRow,
        Project,
        ("name", "area_id", "description", "target_date", "color", "position"),
    ),
    "labels": (LabelRow, Label, ("name", "color")),
    "comments": (CommentRow, Comment, ("task_id", "body")),
}

_COMMON = ("id", "source", "source_id", "created_at", "updated_at")


def _to_entity(name: str, row: Any) -> Any:
    _, cls, fields = _SIMPLE[name]
    kwargs = {f: getattr(row, f) for f in (*fields, *_COMMON)}
    if name == "projects":
        kwargs["status"] = ProjectStatus(row.status)
    return cls(**kwargs)


def _fill_row(name: str, row: Any, e: Any) -> None:
    _, _, fields = _SIMPLE[name]
    for f in (*fields, "source", "source_id"):
        setattr(row, f, getattr(e, f))
    if name == "projects":
        row.status = str(e.status)


def _task_to_entity(row: TaskRow, label_ids: list[int]) -> Task:
    rec = None
    if row.recurrence_rrule:
        rec = Recurrence(
            rrule=row.recurrence_rrule,
            mode=RecurrenceMode(row.recurrence_mode or "fixed"),
            dtstart=row.recurrence_dtstart or row.due_date,  # type: ignore[arg-type]
            time=row.recurrence_time,
            text=row.recurrence_text or "",
        )
    return Task(
        id=row.id,
        title=row.title,
        description=row.description or "",
        status=TaskStatus(row.status),
        priority=row.priority,
        project_id=row.project_id,
        area_id=row.area_id,
        parent_id=row.parent_id,
        due_date=row.due_date,
        due_time=row.due_time,
        recurrence=rec,
        completed_runs=row.completed_runs,
        completed_at=row.completed_at,
        label_ids=sorted(label_ids),
        position=row.position,
        source=row.source,
        source_id=row.source_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _fill_task_row(row: TaskRow, t: Task) -> None:
    for f in (
        "title",
        "description",
        "priority",
        "project_id",
        "area_id",
        "parent_id",
        "due_date",
        "due_time",
        "completed_runs",
        "completed_at",
        "position",
        "source",
        "source_id",
    ):
        setattr(row, f, getattr(t, f))
    row.status = str(t.status)
    rec = t.recurrence
    row.recurrence_rrule = rec.rrule if rec else None
    row.recurrence_mode = str(rec.mode) if rec else None
    row.recurrence_dtstart = rec.dtstart if rec else None
    row.recurrence_time = rec.time if rec else None
    row.recurrence_text = rec.text if rec else None


# --- repositories -------------------------------------------------------------


class _SqlRepo:
    name: str

    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self.s = session
        self.clock = clock

    @property
    def row_cls(self) -> Any:
        return _SIMPLE[self.name][0]

    async def get(self, id: int) -> Any:
        row = await self.s.get(self.row_cls, id)
        return _to_entity(self.name, row) if row else None

    async def get_by_source(self, source: str, source_id: str) -> Any:
        row = (
            await self.s.execute(
                select(self.row_cls).where(
                    self.row_cls.source == source, self.row_cls.source_id == source_id
                )
            )
        ).scalar_one_or_none()
        return _to_entity(self.name, row) if row else None

    async def add(self, entity: Any) -> Any:
        if entity.source and await self.get_by_source(entity.source, entity.source_id):
            raise ValueError(f"duplicate {self.name} source {entity.source}:{entity.source_id}")
        now = self.clock.now()
        row = self.row_cls()
        _fill_row(self.name, row, entity)
        row.created_at = entity.created_at or now
        row.updated_at = entity.updated_at or row.created_at
        self.s.add(row)
        await self.s.flush()
        return _to_entity(self.name, row)

    async def update(self, entity: Any) -> Any:
        row = await self.s.get(self.row_cls, entity.id)
        if row is None:
            raise NotFoundError(f"{self.name} {entity.id}")
        _fill_row(self.name, row, entity)
        row.updated_at = self.clock.now()
        await self.s.flush()
        return _to_entity(self.name, row)

    async def delete(self, id: int) -> None:
        row = await self.s.get(self.row_cls, id)
        if row is None:
            raise NotFoundError(f"{self.name} {id}")
        await self.s.delete(row)
        await self.s.flush()


class SqlAreaRepository(_SqlRepo):
    name = "areas"

    async def list(self) -> list[Area]:
        rows = (
            await self.s.execute(select(AreaRow).order_by(AreaRow.position, AreaRow.id))
        ).scalars()
        return [_to_entity(self.name, r) for r in rows]

    async def delete(self, id: int) -> None:
        # Portable SET NULL: SQLite enforces foreign keys only when asked.
        from sqlalchemy import update

        await self.s.execute(
            update(ProjectRow).where(ProjectRow.area_id == id).values(area_id=None)
        )
        await self.s.execute(update(TaskRow).where(TaskRow.area_id == id).values(area_id=None))
        await super().delete(id)


class SqlProjectRepository(_SqlRepo):
    name = "projects"

    async def list(self, area_id: int | None = None) -> list[Project]:
        q = select(ProjectRow).order_by(ProjectRow.position, ProjectRow.id)
        if area_id is not None:
            q = q.where(ProjectRow.area_id == area_id)
        return [_to_entity(self.name, r) for r in (await self.s.execute(q)).scalars()]

    async def delete(self, id: int) -> None:
        from sqlalchemy import update

        await self.s.execute(
            update(TaskRow).where(TaskRow.project_id == id).values(project_id=None)
        )
        await super().delete(id)


class SqlLabelRepository(_SqlRepo):
    name = "labels"

    async def list(self) -> list[Label]:
        rows = (
            await self.s.execute(select(LabelRow).order_by(func.lower(LabelRow.name)))
        ).scalars()
        return [_to_entity(self.name, r) for r in rows]

    async def delete(self, id: int) -> None:
        await self.s.execute(delete(TaskLabelRow).where(TaskLabelRow.label_id == id))
        await super().delete(id)


class SqlCommentRepository(_SqlRepo):
    name = "comments"

    async def list_for_task(self, task_id: int) -> list[Comment]:
        q = (
            select(CommentRow)
            .where(CommentRow.task_id == task_id)
            .order_by(CommentRow.created_at, CommentRow.id)
        )
        return [_to_entity(self.name, r) for r in (await self.s.execute(q)).scalars()]

    async def count_by_task(self, task_ids: list[int]) -> dict[int, int]:
        if not task_ids:
            return {}
        q = (
            select(CommentRow.task_id, func.count())
            .where(CommentRow.task_id.in_(task_ids))
            .group_by(CommentRow.task_id)
        )
        return {tid: n for tid, n in (await self.s.execute(q)).all()}


class SqlTaskRepository:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self.s = session
        self.clock = clock

    async def _labels(self, task_ids: list[int]) -> dict[int, list[int]]:
        out: dict[int, list[int]] = {i: [] for i in task_ids}
        if task_ids:
            q = select(TaskLabelRow.task_id, TaskLabelRow.label_id).where(
                TaskLabelRow.task_id.in_(task_ids)
            )
            for tid, lid in (await self.s.execute(q)).all():
                out[tid].append(lid)
        return out

    async def _set_labels(self, task_id: int, label_ids: list[int]) -> None:
        await self.s.execute(delete(TaskLabelRow).where(TaskLabelRow.task_id == task_id))
        for lid in dict.fromkeys(label_ids):
            self.s.add(TaskLabelRow(task_id=task_id, label_id=lid))

    async def _entity(self, row: TaskRow) -> Task:
        return _task_to_entity(row, (await self._labels([row.id]))[row.id])

    async def get(self, id: int) -> Task | None:
        row = await self.s.get(TaskRow, id)
        return await self._entity(row) if row else None

    async def get_by_source(self, source: str, source_id: str) -> Task | None:
        q = select(TaskRow).where(TaskRow.source == source, TaskRow.source_id == source_id)
        row = (await self.s.execute(q)).scalar_one_or_none()
        return await self._entity(row) if row else None

    async def add(self, entity: Task) -> Task:
        if entity.source and await self.get_by_source(entity.source, entity.source_id or ""):
            raise ValueError(f"duplicate tasks source {entity.source}:{entity.source_id}")
        now = self.clock.now()
        row = TaskRow()
        _fill_task_row(row, entity)
        row.created_at = entity.created_at or now
        row.updated_at = entity.updated_at or row.created_at
        self.s.add(row)
        await self.s.flush()
        await self._set_labels(row.id, entity.label_ids)
        await self.s.flush()
        return await self._entity(row)

    async def update(self, entity: Task) -> Task:
        row = await self.s.get(TaskRow, entity.id)
        if row is None:
            raise NotFoundError(f"tasks {entity.id}")
        _fill_task_row(row, entity)
        row.updated_at = self.clock.now()
        await self._set_labels(row.id, entity.label_ids)
        await self.s.flush()
        return await self._entity(row)

    async def delete(self, id: int) -> None:
        row = await self.s.get(TaskRow, id)
        if row is None:
            raise NotFoundError(f"tasks {id}")
        child_ids = (
            await self.s.execute(select(TaskRow.id).where(TaskRow.parent_id == id))
        ).scalars()
        ids = [id, *child_ids]
        for model in (TaskLabelRow, CommentRow, ActivityRow):
            await self.s.execute(delete(model).where(model.task_id.in_(ids)))
        await self.s.execute(delete(TaskRow).where(TaskRow.parent_id == id))
        await self.s.execute(delete(TaskRow).where(TaskRow.id == id))
        await self.s.flush()
        self.s.expunge_all()

    async def list(self, f: TaskFilter) -> list[Task]:
        q = select(TaskRow)
        if f.statuses:
            q = q.where(TaskRow.status.in_([str(s) for s in f.statuses]))
        elif not f.include_closed:
            q = q.where(TaskRow.status.not_in([str(s) for s in CLOSED_STATUSES]))
        if f.project_id is not None:
            q = q.where(TaskRow.project_id == f.project_id)
        if f.area_id is not None:
            in_area_projects = select(ProjectRow.id).where(ProjectRow.area_id == f.area_id)
            q = q.where(
                or_(
                    TaskRow.project_id.in_(in_area_projects),
                    (TaskRow.project_id.is_(None)) & (TaskRow.area_id == f.area_id),
                )
            )
        if f.inbox:
            q = q.where(TaskRow.project_id.is_(None), TaskRow.area_id.is_(None))
        if f.parent_id is not None:
            q = q.where(
                TaskRow.parent_id.is_(None)
                if f.parent_id == 0
                else TaskRow.parent_id == f.parent_id
            )
        if f.priorities:
            q = q.where(TaskRow.priority.in_(f.priorities))
        if f.label_id is not None:
            q = q.where(
                TaskRow.id.in_(
                    select(TaskLabelRow.task_id).where(TaskLabelRow.label_id == f.label_id)
                )
            )
        if f.has_due is not None:
            q = q.where(TaskRow.due_date.is_not(None) if f.has_due else TaskRow.due_date.is_(None))
        if f.recurring is not None:
            col = TaskRow.recurrence_rrule
            q = q.where(col.is_not(None) if f.recurring else col.is_(None))
        if f.due_before is not None:
            q = q.where(TaskRow.due_date <= f.due_before)
        if f.due_after is not None:
            q = q.where(TaskRow.due_date >= f.due_after)
        if f.q:
            pat = f"%{f.q.lower()}%"
            q = q.where(
                or_(func.lower(TaskRow.title).like(pat), func.lower(TaskRow.description).like(pat))
            )

        primary = {
            "priority": case((TaskRow.priority == 0, None), else_=TaskRow.priority),
            "created": TaskRow.created_at,
            "updated": TaskRow.updated_at,
            "position": TaskRow.position,
        }.get(f.sort, TaskRow.due_date)
        direction = primary.desc() if f.order == "desc" else primary.asc()
        q = q.order_by(
            case((primary.is_(None), 1), else_=0),
            direction,
            case((TaskRow.due_date.is_(None), 1), else_=0),
            TaskRow.due_date,
            case((TaskRow.priority == 0, 9), else_=TaskRow.priority),
            TaskRow.id,
        )
        if f.limit:
            q = q.limit(f.limit)
        rows = list((await self.s.execute(q)).scalars())
        labels = await self._labels([r.id for r in rows])
        return [_task_to_entity(r, labels[r.id]) for r in rows]


class SqlActivityRepository:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self.s = session
        self.clock = clock

    @staticmethod
    def _entity(r: ActivityRow) -> Activity:
        return Activity(
            id=r.id, task_id=r.task_id, kind=r.kind, data=r.data or {}, created_at=r.created_at
        )

    async def add(self, activity: Activity) -> Activity:
        row = ActivityRow(
            task_id=activity.task_id,
            kind=activity.kind,
            data=activity.data,
            created_at=activity.created_at or self.clock.now(),
        )
        self.s.add(row)
        await self.s.flush()
        return self._entity(row)

    async def list_for_task(self, task_id: int) -> list[Activity]:
        q = (
            select(ActivityRow)
            .where(ActivityRow.task_id == task_id)
            .order_by(ActivityRow.created_at, ActivityRow.id)
        )
        return [self._entity(r) for r in (await self.s.execute(q)).scalars()]


class SqlSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.s = session

    async def get(self) -> Settings:
        row = await self.s.get(SettingsRow, 1)
        return Settings(timezone=row.timezone) if row else Settings()

    async def save(self, settings: Settings) -> Settings:
        row = await self.s.get(SettingsRow, 1)
        if row is None:
            self.s.add(SettingsRow(id=1, timezone=settings.timezone))
        else:
            row.timezone = settings.timezone
        await self.s.flush()
        return settings


class SqlUnitOfWork:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], clock: Clock) -> None:
        self._sessionmaker = sessionmaker
        self._clock = clock

    async def __aenter__(self) -> Self:
        s = self._sessionmaker()
        self.session = s
        self.areas = SqlAreaRepository(s, self._clock)
        self.projects = SqlProjectRepository(s, self._clock)
        self.labels = SqlLabelRepository(s, self._clock)
        self.tasks = SqlTaskRepository(s, self._clock)
        self.comments = SqlCommentRepository(s, self._clock)
        self.activity = SqlActivityRepository(s, self._clock)
        self.settings = SqlSettingsRepository(s)
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.session.rollback()
        await self.session.close()

    async def commit(self) -> None:
        try:
            await self.session.commit()
        except IntegrityError as e:  # surface as a domain error
            await self.session.rollback()
            raise ValueError(str(e.orig)) from e


class SqlUnitOfWorkFactory:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], clock: Clock) -> None:
        self.sessionmaker = sessionmaker
        self.clock = clock

    def __call__(self) -> SqlUnitOfWork:
        return SqlUnitOfWork(self.sessionmaker, self.clock)
