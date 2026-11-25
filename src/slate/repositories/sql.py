"""SQLAlchemy repositories for SQLite and Postgres.

Filter and sort semantics mirror ``repositories/filtering.py``; the contract
tests check that this module and the memory fake agree. Every owned query
filters on the unit of work's ``workspace_id``.
"""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any, Self

from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from slate.domain import (
    CLOSED_STATUSES,
    Account,
    Activity,
    AgentMessage,
    AgentMode,
    ApiKey,
    ApiKeyKind,
    Area,
    Comment,
    Label,
    PendingChange,
    PendingStatus,
    Project,
    ProjectStatus,
    Settings,
    Task,
    TaskStatus,
    Workspace,
)
from slate.models import (
    ActivityRow,
    AgentMessageRow,
    ApiKeyRow,
    AreaRow,
    CommentRow,
    LabelRow,
    PendingChangeRow,
    ProjectRow,
    TaskLabelRow,
    TaskRow,
    UserRow,
    WorkspaceRow,
)
from slate.repositories.base import NotFoundError
from slate.scheduling import Recurrence, RecurrenceMode

if TYPE_CHECKING:
    from uuid import UUID

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

_COMMON = ("id", "workspace_id", "source", "source_id", "created_at", "updated_at")


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


def _task_to_entity(row: TaskRow, label_ids: list[UUID]) -> Task:
    rec = None
    # _fill_task_row always stores dtstart with an rrule; due_date covers older rows.
    dtstart = row.recurrence_dtstart or row.due_date
    if row.recurrence_rrule and dtstart:
        rec = Recurrence(
            rrule=row.recurrence_rrule,
            mode=RecurrenceMode(row.recurrence_mode or "fixed"),
            dtstart=dtstart,
            time=row.recurrence_time,
            text=row.recurrence_text or "",
        )
    return Task(
        id=row.id,
        workspace_id=row.workspace_id,
        number=row.number,
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


# --- workspace-owned repositories ---------------------------------------------


class _Owned:
    def __init__(self, session: AsyncSession, clock: Clock, workspace_id: UUID | None) -> None:
        self.s = session
        self.clock = clock
        self._ws = workspace_id

    @property
    def ws(self) -> UUID:
        if self._ws is None:
            raise RuntimeError("this unit of work was opened without a workspace")
        return self._ws


class _SqlRepo(_Owned):
    name: str

    @property
    def row_cls(self) -> Any:
        return _SIMPLE[self.name][0]

    async def _row(self, id: UUID) -> Any:
        q = select(self.row_cls).where(self.row_cls.id == id, self.row_cls.workspace_id == self.ws)
        return (await self.s.execute(q)).scalar_one_or_none()

    async def get(self, id: UUID) -> Any:
        row = await self._row(id)
        return _to_entity(self.name, row) if row else None

    async def get_by_source(self, source: str, source_id: str) -> Any:
        q = select(self.row_cls).where(
            self.row_cls.workspace_id == self.ws,
            self.row_cls.source == source,
            self.row_cls.source_id == source_id,
        )
        row = (await self.s.execute(q)).scalar_one_or_none()
        return _to_entity(self.name, row) if row else None

    async def add(self, entity: Any) -> Any:
        if entity.source and await self.get_by_source(entity.source, entity.source_id):
            raise ValueError(f"duplicate {self.name} source {entity.source}:{entity.source_id}")
        now = self.clock.now()
        row = self.row_cls(id=entity.id, workspace_id=self.ws)
        _fill_row(self.name, row, entity)
        row.created_at = entity.created_at or now
        row.updated_at = entity.updated_at or row.created_at
        self.s.add(row)
        await self.s.flush()
        return _to_entity(self.name, row)

    async def update(self, entity: Any) -> Any:
        row = await self._row(entity.id)
        if row is None:
            raise NotFoundError(f"{self.name} {entity.id}")
        _fill_row(self.name, row, entity)
        row.updated_at = self.clock.now()
        await self.s.flush()
        return _to_entity(self.name, row)

    async def delete(self, id: UUID) -> None:
        row = await self._row(id)
        if row is None:
            raise NotFoundError(f"{self.name} {id}")
        await self.s.delete(row)
        await self.s.flush()


class SqlAreaRepository(_SqlRepo):
    name = "areas"

    async def list(self) -> builtins.list[Area]:
        q = select(AreaRow).where(AreaRow.workspace_id == self.ws)
        rows = (await self.s.execute(q.order_by(AreaRow.position, AreaRow.id))).scalars()
        return [_to_entity(self.name, r) for r in rows]

    async def delete(self, id: UUID) -> None:
        # Cleared here rather than by the foreign key: a composite SET NULL
        # would also null workspace_id.
        if await self._row(id) is None:
            raise NotFoundError(f"areas {id}")
        for model in (ProjectRow, TaskRow):
            await self.s.execute(
                update(model)
                .where(model.workspace_id == self.ws, model.area_id == id)
                .values(area_id=None)
            )
        await super().delete(id)


class SqlProjectRepository(_SqlRepo):
    name = "projects"

    async def list(self, area_id: UUID | None = None) -> builtins.list[Project]:
        q = select(ProjectRow).where(ProjectRow.workspace_id == self.ws)
        if area_id is not None:
            q = q.where(ProjectRow.area_id == area_id)
        q = q.order_by(ProjectRow.position, ProjectRow.id)
        return [_to_entity(self.name, r) for r in (await self.s.execute(q)).scalars()]

    async def delete(self, id: UUID) -> None:
        if await self._row(id) is None:
            raise NotFoundError(f"projects {id}")
        await self.s.execute(
            update(TaskRow)
            .where(TaskRow.workspace_id == self.ws, TaskRow.project_id == id)
            .values(project_id=None)
        )
        await super().delete(id)


class SqlLabelRepository(_SqlRepo):
    name = "labels"

    async def list(self) -> builtins.list[Label]:
        q = select(LabelRow).where(LabelRow.workspace_id == self.ws)
        rows = (await self.s.execute(q.order_by(func.lower(LabelRow.name), LabelRow.id))).scalars()
        return [_to_entity(self.name, r) for r in rows]

    async def delete(self, id: UUID) -> None:
        if await self._row(id) is None:
            raise NotFoundError(f"labels {id}")
        await self.s.execute(
            delete(TaskLabelRow).where(
                TaskLabelRow.workspace_id == self.ws, TaskLabelRow.label_id == id
            )
        )
        await super().delete(id)


class SqlCommentRepository(_SqlRepo):
    name = "comments"

    async def list_for_task(self, task_id: UUID) -> list[Comment]:
        q = (
            select(CommentRow)
            .where(CommentRow.workspace_id == self.ws, CommentRow.task_id == task_id)
            .order_by(CommentRow.created_at, CommentRow.id)
        )
        return [_to_entity(self.name, r) for r in (await self.s.execute(q)).scalars()]

    async def count_by_task(self, task_ids: list[UUID]) -> dict[UUID, int]:
        if not task_ids:
            return {}
        q = (
            select(CommentRow.task_id, func.count())
            .where(CommentRow.workspace_id == self.ws, CommentRow.task_id.in_(task_ids))
            .group_by(CommentRow.task_id)
        )
        return {tid: n for tid, n in (await self.s.execute(q)).all()}


class SqlTaskRepository(_Owned):
    async def _labels(self, task_ids: builtins.list[UUID]) -> dict[UUID, builtins.list[UUID]]:
        out: dict[UUID, list[UUID]] = {i: [] for i in task_ids}
        if task_ids:
            q = select(TaskLabelRow.task_id, TaskLabelRow.label_id).where(
                TaskLabelRow.workspace_id == self.ws, TaskLabelRow.task_id.in_(task_ids)
            )
            for tid, lid in (await self.s.execute(q)).all():
                out[tid].append(lid)
        return out

    async def _set_labels(self, task_id: UUID, label_ids: builtins.list[UUID]) -> None:
        await self.s.execute(
            delete(TaskLabelRow).where(
                TaskLabelRow.workspace_id == self.ws, TaskLabelRow.task_id == task_id
            )
        )
        for lid in dict.fromkeys(label_ids):
            self.s.add(TaskLabelRow(task_id=task_id, label_id=lid, workspace_id=self.ws))

    async def _entity(self, row: TaskRow) -> Task:
        return _task_to_entity(row, (await self._labels([row.id]))[row.id])

    async def _one(self, *where: Any) -> TaskRow | None:
        q = select(TaskRow).where(TaskRow.workspace_id == self.ws, *where)
        return (await self.s.execute(q)).scalar_one_or_none()

    async def get(self, id: UUID) -> Task | None:
        row = await self._one(TaskRow.id == id)
        return await self._entity(row) if row else None

    async def get_by_number(self, number: int) -> Task | None:
        row = await self._one(TaskRow.number == number)
        return await self._entity(row) if row else None

    async def get_by_source(self, source: str, source_id: str) -> Task | None:
        row = await self._one(TaskRow.source == source, TaskRow.source_id == source_id)
        return await self._entity(row) if row else None

    async def _next_number(self) -> int:
        # One UPDATE ... RETURNING: concurrent creates in a workspace serialize on
        # the workspace row, so numbers are never handed out twice.
        q = (
            update(WorkspaceRow)
            .where(WorkspaceRow.id == self.ws)
            .values(next_task_number=WorkspaceRow.next_task_number + 1)
            .returning(WorkspaceRow.next_task_number)
        )
        return (await self.s.execute(q)).scalar_one() - 1

    async def add(self, entity: Task) -> Task:
        if entity.source and await self.get_by_source(entity.source, entity.source_id or ""):
            raise ValueError(f"duplicate tasks source {entity.source}:{entity.source_id}")
        now = self.clock.now()
        row = TaskRow(id=entity.id, workspace_id=self.ws, number=await self._next_number())
        _fill_task_row(row, entity)
        row.created_at = entity.created_at or now
        row.updated_at = entity.updated_at or row.created_at
        self.s.add(row)
        await self.s.flush()
        await self._set_labels(row.id, entity.label_ids)
        await self.s.flush()
        return await self._entity(row)

    async def update(self, entity: Task) -> Task:
        row = await self._one(TaskRow.id == entity.id)
        if row is None:
            raise NotFoundError(f"tasks {entity.id}")
        _fill_task_row(row, entity)
        row.updated_at = self.clock.now()
        await self._set_labels(row.id, entity.label_ids)
        await self.s.flush()
        return await self._entity(row)

    async def delete(self, id: UUID) -> None:
        if await self._one(TaskRow.id == id) is None:
            raise NotFoundError(f"tasks {id}")
        child_ids = (
            await self.s.execute(
                select(TaskRow.id).where(TaskRow.workspace_id == self.ws, TaskRow.parent_id == id)
            )
        ).scalars()
        ids = [id, *child_ids]
        for model in (TaskLabelRow, CommentRow, ActivityRow):
            await self.s.execute(
                delete(model).where(model.workspace_id == self.ws, model.task_id.in_(ids))
            )
        await self.s.execute(
            delete(TaskRow).where(TaskRow.workspace_id == self.ws, TaskRow.parent_id == id)
        )
        await self.s.execute(
            delete(TaskRow).where(TaskRow.workspace_id == self.ws, TaskRow.id == id)
        )
        await self.s.flush()
        self.s.expunge_all()

    async def list(self, f: TaskFilter) -> builtins.list[Task]:
        q = select(TaskRow).where(TaskRow.workspace_id == self.ws)
        if f.statuses:
            q = q.where(TaskRow.status.in_([str(s) for s in f.statuses]))
        elif not f.include_closed:
            q = q.where(TaskRow.status.not_in([str(s) for s in CLOSED_STATUSES]))
        if f.project_id is not None:
            q = q.where(TaskRow.project_id == f.project_id)
        if f.area_id is not None:
            in_area_projects = select(ProjectRow.id).where(
                ProjectRow.workspace_id == self.ws, ProjectRow.area_id == f.area_id
            )
            q = q.where(
                or_(
                    TaskRow.project_id.in_(in_area_projects),
                    (TaskRow.project_id.is_(None)) & (TaskRow.area_id == f.area_id),
                )
            )
        if f.inbox:
            q = q.where(TaskRow.project_id.is_(None), TaskRow.area_id.is_(None))
        if f.top_level:
            q = q.where(TaskRow.parent_id.is_(None))
        if f.parent_id is not None:
            q = q.where(TaskRow.parent_id == f.parent_id)
        if f.priorities:
            q = q.where(TaskRow.priority.in_(f.priorities))
        if f.label_id is not None:
            q = q.where(
                TaskRow.id.in_(
                    select(TaskLabelRow.task_id).where(
                        TaskLabelRow.workspace_id == self.ws, TaskLabelRow.label_id == f.label_id
                    )
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


class SqlActivityRepository(_Owned):
    @staticmethod
    def _entity(r: ActivityRow) -> Activity:
        return Activity(
            id=r.id,
            workspace_id=r.workspace_id,
            task_id=r.task_id,
            kind=r.kind,
            data=r.data or {},
            created_at=r.created_at,
        )

    async def add(self, activity: Activity) -> Activity:
        row = ActivityRow(
            id=activity.id,
            workspace_id=self.ws,
            task_id=activity.task_id,
            kind=activity.kind,
            data=activity.data,
            created_at=activity.created_at or self.clock.now(),
        )
        self.s.add(row)
        await self.s.flush()
        return self._entity(row)

    async def list_for_task(self, task_id: UUID) -> list[Activity]:
        q = (
            select(ActivityRow)
            .where(ActivityRow.workspace_id == self.ws, ActivityRow.task_id == task_id)
            .order_by(ActivityRow.created_at, ActivityRow.id)
        )
        return [self._entity(r) for r in (await self.s.execute(q)).scalars()]


class SqlSettingsRepository(_Owned):
    async def get(self) -> Settings:
        row = await self.s.get(WorkspaceRow, self.ws)
        if row is None:
            return Settings()
        return Settings(
            timezone=row.timezone,
            agent_enabled=bool(row.agent_enabled),
            agent_mode=AgentMode(row.agent_mode or "suggest"),
            agent_instructions=row.agent_instructions or "",
        )

    async def save(self, settings: Settings) -> Settings:
        row = await self.s.get(WorkspaceRow, self.ws)
        if row is None:
            raise NotFoundError(f"workspace {self.ws}")
        row.timezone = settings.timezone
        row.agent_enabled = settings.agent_enabled
        row.agent_mode = str(settings.agent_mode)
        row.agent_instructions = settings.agent_instructions
        await self.s.flush()
        return settings


class SqlPendingChangeRepository(_Owned):
    @staticmethod
    def _entity(r: PendingChangeRow) -> PendingChange:
        return PendingChange(
            id=r.id,
            workspace_id=r.workspace_id,
            tool=r.tool,
            input=r.input,
            summary=r.summary,
            origin=r.origin,
            created_by=r.created_by,
            status=PendingStatus(r.status),
            error=r.error,
            result=r.result,
            created_at=r.created_at,
            resolved_at=r.resolved_at,
        )

    async def add(self, change: PendingChange) -> PendingChange:
        row = PendingChangeRow(
            id=change.id,
            workspace_id=self.ws,
            tool=change.tool,
            input=change.input,
            summary=change.summary,
            origin=change.origin,
            created_by=change.created_by,
            status=str(change.status),
            error=change.error,
            result=change.result,
            created_at=change.created_at or self.clock.now(),
            resolved_at=change.resolved_at,
        )
        self.s.add(row)
        await self.s.flush()
        return self._entity(row)

    async def get(self, id: UUID) -> PendingChange | None:
        q = select(PendingChangeRow).where(
            PendingChangeRow.id == id, PendingChangeRow.workspace_id == self.ws
        )
        row = (await self.s.execute(q)).scalar_one_or_none()
        return self._entity(row) if row else None

    async def list(self, status: PendingStatus | None = None) -> builtins.list[PendingChange]:
        q = select(PendingChangeRow).where(PendingChangeRow.workspace_id == self.ws)
        if status is not None:
            q = q.where(PendingChangeRow.status == str(status))
        q = q.order_by(PendingChangeRow.created_at, PendingChangeRow.id)
        return [self._entity(r) for r in (await self.s.execute(q)).scalars()]

    async def resolve(self, change: PendingChange) -> bool:
        """Move a pending change to its final status; False if it was no longer pending."""
        q = (
            update(PendingChangeRow)
            .where(
                PendingChangeRow.id == change.id,
                PendingChangeRow.workspace_id == self.ws,
                PendingChangeRow.status == str(PendingStatus.PENDING),
            )
            .values(
                status=str(change.status),
                error=change.error,
                result=change.result,
                input=change.input,
                resolved_at=self.clock.now(),
            )
        )
        res = await self.s.execute(q)
        return bool(getattr(res, "rowcount", 0))


class SqlAgentMessageRepository(_Owned):
    @staticmethod
    def _entity(r: AgentMessageRow) -> AgentMessage:
        return AgentMessage(
            id=r.id,
            workspace_id=r.workspace_id,
            user_id=r.user_id,
            role=r.role,
            content=r.content,
            image_count=r.image_count,
            pending_change_ids=list(r.pending_change_ids or []),
            created_at=r.created_at,
        )

    async def add(self, m: AgentMessage) -> AgentMessage:
        row = AgentMessageRow(
            id=m.id,
            workspace_id=self.ws,
            user_id=m.user_id,
            role=m.role,
            content=m.content,
            image_count=m.image_count,
            pending_change_ids=list(m.pending_change_ids),
            created_at=m.created_at or self.clock.now(),
        )
        self.s.add(row)
        await self.s.flush()
        return self._entity(row)

    async def list_for_user(self, user_id: UUID) -> list[AgentMessage]:
        q = (
            select(AgentMessageRow)
            .where(AgentMessageRow.workspace_id == self.ws, AgentMessageRow.user_id == user_id)
            .order_by(AgentMessageRow.created_at, AgentMessageRow.id)
        )
        return [self._entity(r) for r in (await self.s.execute(q)).scalars()]

    async def clear(self, user_id: UUID) -> None:
        await self.s.execute(
            delete(AgentMessageRow).where(
                AgentMessageRow.workspace_id == self.ws, AgentMessageRow.user_id == user_id
            )
        )


# --- accounts -----------------------------------------------------------------


class SqlUserRepository:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self.s = session
        self.clock = clock

    @staticmethod
    def _entity(row: UserRow) -> Account:
        return Account(
            issuer=row.issuer,
            subject=row.subject,
            name=row.name,
            email=row.email,
            id=row.id,
            created_at=row.created_at,
            last_login_at=row.last_login_at,
        )

    async def get(self, id: UUID) -> Account | None:
        row = await self.s.get(UserRow, id)
        return self._entity(row) if row else None

    async def record_sign_in(self, account: Account) -> Account:
        now = self.clock.now()
        q = select(UserRow).where(
            UserRow.issuer == account.issuer, UserRow.subject == account.subject
        )
        row = (await self.s.execute(q)).scalar_one_or_none()
        if row is None:
            row = UserRow(
                id=account.id, issuer=account.issuer, subject=account.subject, created_at=now
            )
            self.s.add(row)
        row.name, row.email, row.last_login_at = account.name, account.email, now
        await self.s.flush()
        return self._entity(row)


class SqlWorkspaceRepository:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self.s = session
        self.clock = clock

    @staticmethod
    def _entity(row: WorkspaceRow) -> Workspace:
        return Workspace(
            owner_id=row.owner_id,
            name=row.name,
            timezone=row.timezone,
            next_task_number=row.next_task_number,
            id=row.id,
            created_at=row.created_at,
        )

    async def get(self, id: UUID) -> Workspace | None:
        row = await self.s.get(WorkspaceRow, id)
        return self._entity(row) if row else None

    async def for_owner(self, user_id: UUID) -> Workspace | None:
        q = select(WorkspaceRow).where(WorkspaceRow.owner_id == user_id)
        row = (await self.s.execute(q)).scalar_one_or_none()
        return self._entity(row) if row else None

    async def add(self, workspace: Workspace) -> Workspace:
        row = WorkspaceRow(
            id=workspace.id,
            owner_id=workspace.owner_id,
            name=workspace.name,
            timezone=workspace.timezone,
            next_task_number=workspace.next_task_number,
            created_at=workspace.created_at or self.clock.now(),
        )
        self.s.add(row)
        await self.s.flush()
        return self._entity(row)


class SqlApiKeyRepository:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self.s = session
        self.clock = clock

    @staticmethod
    def _entity(r: ApiKeyRow) -> ApiKey:
        return ApiKey(
            user_id=r.user_id,
            workspace_id=r.workspace_id,
            name=r.name,
            digest=r.digest,
            kind=ApiKeyKind(r.kind),
            id=r.id,
            created_at=r.created_at,
            last_used_at=r.last_used_at,
            revoked_at=r.revoked_at,
        )

    async def add(self, key: ApiKey) -> ApiKey:
        row = ApiKeyRow(
            id=key.id,
            user_id=key.user_id,
            workspace_id=key.workspace_id,
            name=key.name,
            digest=key.digest,
            kind=str(key.kind),
            created_at=key.created_at or self.clock.now(),
        )
        self.s.add(row)
        await self.s.flush()
        return self._entity(row)

    async def get_by_digest(self, digest: str) -> ApiKey | None:
        q = select(ApiKeyRow).where(ApiKeyRow.digest == digest)
        row = (await self.s.execute(q)).scalar_one_or_none()
        return self._entity(row) if row else None

    async def list_for_user(self, user_id: UUID) -> list[ApiKey]:
        q = select(ApiKeyRow).where(ApiKeyRow.user_id == user_id).order_by(ApiKeyRow.id.desc())
        return [self._entity(r) for r in (await self.s.execute(q)).scalars()]

    async def update(self, key: ApiKey) -> ApiKey:
        row = await self.s.get(ApiKeyRow, key.id)
        if row is None:
            raise NotFoundError(f"api key {key.id}")
        row.name, row.last_used_at, row.revoked_at = key.name, key.last_used_at, key.revoked_at
        await self.s.flush()
        return self._entity(row)


class SqlUnitOfWork:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        clock: Clock,
        workspace_id: UUID | None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._clock = clock
        self.workspace_id = workspace_id

    async def __aenter__(self) -> Self:
        s, c, ws = self._sessionmaker(), self._clock, self.workspace_id
        self.session = s
        self.users = SqlUserRepository(s, c)
        self.workspaces = SqlWorkspaceRepository(s, c)
        self.api_keys = SqlApiKeyRepository(s, c)
        self.areas = SqlAreaRepository(s, c, ws)
        self.projects = SqlProjectRepository(s, c, ws)
        self.labels = SqlLabelRepository(s, c, ws)
        self.tasks = SqlTaskRepository(s, c, ws)
        self.comments = SqlCommentRepository(s, c, ws)
        self.activity = SqlActivityRepository(s, c, ws)
        self.settings = SqlSettingsRepository(s, c, ws)
        self.pending_changes = SqlPendingChangeRepository(s, c, ws)
        self.agent_messages = SqlAgentMessageRepository(s, c, ws)
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

    def __call__(self, workspace_id: UUID | None = None) -> SqlUnitOfWork:
        return SqlUnitOfWork(self.sessionmaker, self.clock, workspace_id)
