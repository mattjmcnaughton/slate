"""JSON API under /api. Routers stay thin: parse input, call services, present output."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from typing import Annotated, Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, Response

from slate.deps import BrowserUserDep, ContainerDep, ServiceDep, UserDep
from slate.domain import Area, Label, Project, Task, TaskFilter, TaskStatus, task_key
from slate.dtos import (
    ActivityOut,
    AgendaDayOut,
    AgendaOut,
    ApiKeyCreated,
    ApiKeyIn,
    ApiKeyOut,
    AreaIn,
    AreaOut,
    AreaPatch,
    CommentIn,
    CommentOut,
    CompleteOut,
    GhostOut,
    ImportIn,
    ImportOut,
    LabelIn,
    LabelOut,
    LabelPatch,
    ParseIn,
    ParseOut,
    ProjectIn,
    ProjectOut,
    ProjectPatch,
    QuickAddIn,
    RecurrenceOut,
    SettingsOut,
    SettingsPatch,
    TaskIn,
    TaskOut,
    TaskPatch,
    TokenOut,
    UserOut,
)
from slate.repositories.base import NotFoundError
from slate.services.accounts import issue_key, revoke_key
from slate.services.agenda import build_agenda, project_progress
from slate.services.importer import (
    ImportArea,
    ImportBatch,
    ImportComment,
    ImportLabel,
    ImportProject,
    ImportTask,
    run_import,
)
from slate.services.tasks import TaskService, ValidationError

router = APIRouter(prefix="/api", tags=["api"])


# --- presenters ------------------------------------------------------------------


def _rec(rec) -> RecurrenceOut | None:  # noqa: ANN001
    if rec is None:
        return None
    return RecurrenceOut(
        rrule=rec.rrule, mode=str(rec.mode), dtstart=rec.dtstart, time=rec.time, text=rec.text
    )


async def present_tasks(svc: TaskService, tasks: list[Task]) -> list[TaskOut]:
    ids = [t.id for t in tasks]
    comments = await svc.uow.comments.count_by_task(ids)
    children = await svc.uow.tasks.list(TaskFilter(include_closed=True, has_due=None))
    subs: dict[UUID, list[Task]] = {}
    numbers = {c.id: c.number for c in children}
    for c in children:
        if c.parent_id is not None:
            subs.setdefault(c.parent_id, []).append(c)
    out = []
    for t in tasks:
        kids = subs.get(t.id, [])
        out.append(
            TaskOut(
                **{k: v for k, v in asdict(t).items() if k not in ("recurrence",)},
                key=task_key(t.number),  # type: ignore[arg-type]
                parent_key=task_key(numbers[t.parent_id])  # type: ignore[arg-type]
                if t.parent_id in numbers
                else None,
                recurrence=_rec(t.recurrence),
                comment_count=comments.get(t.id, 0),
                subtask_count=len(kids),
                open_subtask_count=sum(1 for k in kids if not k.is_closed),
            )
        )
    return out


async def present_task(svc: TaskService, t: Task) -> TaskOut:
    return (await present_tasks(svc, [t]))[0]


async def _not_found(fn, *a, **kw) -> Any:  # noqa: ANN001
    try:
        return await fn(*a, **kw)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValidationError as e:
        raise HTTPException(422, str(e)) from e


# --- me and settings ---------------------------------------------------------------


@router.get("/me", response_model=UserOut)
async def me(user: UserDep) -> UserOut:
    return UserOut(
        id=user.id,
        workspace_id=user.workspace_id,
        name=user.name,
        email=user.email,
        via=user.via,
    )


@router.get("/settings", response_model=SettingsOut)
async def get_settings(svc: ServiceDep) -> SettingsOut:
    return SettingsOut(timezone=(await svc.uow.settings.get()).timezone)


@router.patch("/settings", response_model=SettingsOut)
async def patch_settings(body: SettingsPatch, svc: ServiceDep, _: BrowserUserDep) -> SettingsOut:
    try:
        ZoneInfo(body.timezone)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise HTTPException(422, f"Unknown time zone {body.timezone}") from e
    s = await svc.uow.settings.get()
    s.timezone = body.timezone
    await svc.uow.settings.save(s)
    return SettingsOut(timezone=s.timezone)


# --- API keys (browser session only) ---------------------------------------------------


@router.get("/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(svc: ServiceDep, user: BrowserUserDep) -> list:
    return await svc.uow.api_keys.list_for_user(user.id)


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(body: ApiKeyIn, svc: ServiceDep, user: BrowserUserDep) -> ApiKeyCreated:
    issued = await issue_key(svc.uow, user.id, user.workspace_id, body.name, body.kind)
    return ApiKeyCreated(**asdict(issued.key), secret=issued.secret)


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: UUID, svc: ServiceDep, user: BrowserUserDep, container: ContainerDep
) -> Response:
    if not await revoke_key(svc.uow, user.id, key_id, container.clock):
        raise HTTPException(404, "API key not found")
    return Response(status_code=204)


# --- areas ---------------------------------------------------------------------------


@router.get("/areas", response_model=list[AreaOut])
async def list_areas(svc: ServiceDep) -> list[Area]:
    return await svc.uow.areas.list()


@router.post("/areas", response_model=AreaOut, status_code=201)
async def create_area(body: AreaIn, svc: ServiceDep) -> Area:
    return await svc.uow.areas.add(Area(**body.model_dump()))


@router.patch("/areas/{area_id}", response_model=AreaOut)
async def patch_area(area_id: UUID, body: AreaPatch, svc: ServiceDep) -> Area:
    area = await svc.uow.areas.get(area_id)
    if area is None:
        raise HTTPException(404, "area not found")
    for k in body.model_fields_set:
        if getattr(body, k) is not None:
            setattr(area, k, getattr(body, k))
    return await svc.uow.areas.update(area)


@router.delete("/areas/{area_id}", status_code=204)
async def delete_area(area_id: UUID, svc: ServiceDep) -> Response:
    await _not_found(svc.uow.areas.delete, area_id)
    return Response(status_code=204)


# --- projects -------------------------------------------------------------------------


async def _present_projects(svc: TaskService, projects: list[Project]) -> list[ProjectOut]:
    progress = await project_progress(svc.uow, projects)
    open_tasks = await svc.uow.tasks.list(TaskFilter())
    counts: dict[UUID, int] = {}
    for t in open_tasks:
        if t.project_id is not None:
            counts[t.project_id] = counts.get(t.project_id, 0) + 1
    return [
        ProjectOut(
            **asdict(p),
            progress_done=progress[p.id].done,
            progress_total=progress[p.id].total,
            open_count=counts.get(p.id, 0),
        )
        for p in projects
    ]


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(svc: ServiceDep, area_id: UUID | None = None) -> list[ProjectOut]:
    return await _present_projects(svc, await svc.uow.projects.list(area_id))


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectIn, svc: ServiceDep) -> ProjectOut:
    if body.area_id is not None and await svc.uow.areas.get(body.area_id) is None:
        raise HTTPException(422, "Unknown area")
    p = await svc.uow.projects.add(Project(**body.model_dump()))
    return (await _present_projects(svc, [p]))[0]


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: UUID, svc: ServiceDep) -> ProjectOut:
    p = await svc.uow.projects.get(project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    return (await _present_projects(svc, [p]))[0]


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def patch_project(project_id: UUID, body: ProjectPatch, svc: ServiceDep) -> ProjectOut:
    p = await svc.uow.projects.get(project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    if body.area_id is not None and await svc.uow.areas.get(body.area_id) is None:
        raise HTTPException(422, "Unknown area")
    nullable = {"area_id", "target_date", "color"}
    for k in body.model_fields_set:
        v = getattr(body, k)
        if v is not None or k in nullable:
            setattr(p, k, v)
    p = await svc.uow.projects.update(p)
    return (await _present_projects(svc, [p]))[0]


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: UUID, svc: ServiceDep) -> Response:
    await _not_found(svc.uow.projects.delete, project_id)
    return Response(status_code=204)


# --- labels -----------------------------------------------------------------------------


@router.get("/labels", response_model=list[LabelOut])
async def list_labels(svc: ServiceDep) -> list[Label]:
    return await svc.uow.labels.list()


@router.post("/labels", response_model=LabelOut, status_code=201)
async def create_label(body: LabelIn, svc: ServiceDep) -> Label:
    return await svc.uow.labels.add(Label(**body.model_dump()))


@router.patch("/labels/{label_id}", response_model=LabelOut)
async def patch_label(label_id: UUID, body: LabelPatch, svc: ServiceDep) -> Label:
    lb = await svc.uow.labels.get(label_id)
    if lb is None:
        raise HTTPException(404, "label not found")
    for k in body.model_fields_set:
        if getattr(body, k) is not None:
            setattr(lb, k, getattr(body, k))
    return await svc.uow.labels.update(lb)


@router.delete("/labels/{label_id}", status_code=204)
async def delete_label(label_id: UUID, svc: ServiceDep) -> Response:
    await _not_found(svc.uow.labels.delete, label_id)
    return Response(status_code=204)


# --- tasks --------------------------------------------------------------------------------


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    svc: ServiceDep,
    project_id: UUID | None = None,
    area_id: UUID | None = None,
    inbox: bool = False,
    parent_id: UUID | None = None,
    top_level: Annotated[bool, Query(description="Only tasks without a parent")] = False,
    status: Annotated[list[TaskStatus] | None, Query()] = None,
    priority: Annotated[list[int] | None, Query()] = None,
    label_id: UUID | None = None,
    due_before: date | None = None,
    due_after: date | None = None,
    has_due: bool | None = None,
    recurring: bool | None = None,
    q: str | None = None,
    include_closed: bool = False,
    sort: Annotated[str, Query(pattern="^(due|priority|created|updated|position)$")] = "due",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "asc",
    limit: Annotated[int | None, Query(ge=1, le=1000)] = None,
) -> list[TaskOut]:
    f = TaskFilter(
        project_id=project_id,
        area_id=area_id,
        inbox=inbox,
        top_level=top_level,
        parent_id=parent_id,
        statuses=tuple(status or ()),
        priorities=tuple(priority or ()),
        label_id=label_id,
        due_before=due_before,
        due_after=due_after,
        has_due=has_due,
        recurring=recurring,
        q=q,
        include_closed=include_closed,
        sort=sort,
        order=order,
        limit=limit,
    )
    return await present_tasks(svc, await svc.list(f))


async def _apply_due_string(svc: TaskService, text: str) -> dict[str, Any]:
    parsed = await svc.parse_schedule(text)
    if parsed.error:
        raise HTTPException(422, parsed.error)
    if parsed.recurrence is not None:
        return {
            "recurrence": parsed.recurrence,
            "due_date": parsed.due.date if parsed.due else None,
            "due_time": parsed.recurrence.time,
        }
    assert parsed.due is not None
    return {"due_date": parsed.due.date, "due_time": parsed.due.time}


@router.post("/tasks", response_model=TaskOut, status_code=201)
async def create_task(body: TaskIn, svc: ServiceDep) -> TaskOut:
    data = body.model_dump(exclude={"due_string"})
    if body.due_string:
        data.update(await _apply_due_string(svc, body.due_string))
    task = await _not_found(svc.create, Task(**data))
    return await present_task(svc, task)


@router.post("/tasks/quick-add", response_model=TaskOut, status_code=201)
async def quick_add(body: QuickAddIn, svc: ServiceDep) -> TaskOut:
    r = await svc.parse(body.text)
    if not r.title:
        raise HTTPException(422, "The task needs a title besides its tokens")
    project_id = r.project_id if r.project_id or r.area_id else body.project_id
    area_id = r.area_id if r.project_id or r.area_id else body.area_id
    label_ids = list(r.label_ids)
    if body.create_missing:
        if r.unknown_project:
            p = await svc.uow.projects.add(Project(name=r.unknown_project))
            project_id, area_id = p.id, None
        for name in r.unknown_labels:
            label_ids.append((await svc.uow.labels.add(Label(name=name))).id)
    task = Task(
        title=r.title,
        status=TaskStatus(r.status) if r.status else TaskStatus.TODO,
        priority=r.priority or 0,
        project_id=project_id,
        area_id=area_id,
        parent_id=body.parent_id,
        label_ids=label_ids,
        due_date=r.due.date if r.due else None,
        due_time=r.due.time if r.due else None,
        recurrence=r.recurrence,
    )
    return await present_task(svc, await _not_found(svc.create, task))


@router.get("/tasks/{ref}", response_model=TaskOut)
async def get_task(ref: str, svc: ServiceDep) -> TaskOut:
    return await present_task(svc, await _not_found(svc.get, ref))


@router.patch("/tasks/{ref}", response_model=TaskOut)
async def patch_task(ref: str, body: TaskPatch, svc: ServiceDep) -> TaskOut:
    sent = body.model_fields_set - {"due_string", "clear_recurrence"}
    nullable = {"project_id", "area_id", "parent_id", "due_date", "due_time"}
    changes: dict[str, Any] = {}
    for k in sent:
        v = getattr(body, k)
        if v is None and k not in nullable:
            continue
        changes[k] = v
    if body.due_string:
        # A plain date moves only this run of a repeating task (the rule is kept);
        # a repeat phrase replaces the schedule.
        changes.update(await _apply_due_string(svc, body.due_string))
    if body.clear_recurrence:
        changes["recurrence"] = None
    if "label_ids" in changes and changes["label_ids"] is None:
        changes["label_ids"] = []
    if "project_id" in changes and changes["project_id"] is not None:
        changes.setdefault("area_id", None)
    return await present_task(svc, await _not_found(svc.update, ref, changes))


@router.delete("/tasks/{ref}", status_code=204)
async def delete_task(ref: str, svc: ServiceDep) -> Response:
    await _not_found(svc.delete, ref)
    return Response(status_code=204)


@router.post("/tasks/{ref}/complete", response_model=CompleteOut)
async def complete_task(ref: str, svc: ServiceDep) -> CompleteOut:
    task = await _not_found(svc.complete, ref)
    open_subs = await svc.open_subtasks(task.id)
    return CompleteOut(task=await present_task(svc, task), open_subtasks=open_subs)


@router.post("/tasks/{ref}/reopen", response_model=TaskOut)
async def reopen_task(ref: str, svc: ServiceDep) -> TaskOut:
    return await present_task(svc, await _not_found(svc.reopen, ref))


@router.get("/tasks/{ref}/comments", response_model=list[CommentOut])
async def list_comments(ref: str, svc: ServiceDep) -> list:
    task = await _not_found(svc.get, ref)
    return await svc.uow.comments.list_for_task(task.id)


@router.post("/tasks/{ref}/comments", response_model=CommentOut, status_code=201)
async def add_comment(ref: str, body: CommentIn, svc: ServiceDep):  # noqa: ANN201
    return await _not_found(svc.add_comment, ref, body.body)


@router.patch("/comments/{comment_id}", response_model=CommentOut)
async def patch_comment(comment_id: UUID, body: CommentIn, svc: ServiceDep):  # noqa: ANN201
    c = await svc.uow.comments.get(comment_id)
    if c is None:
        raise HTTPException(404, "comment not found")
    c.body = body.body
    return await svc.uow.comments.update(c)


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(comment_id: UUID, svc: ServiceDep) -> Response:
    await _not_found(svc.uow.comments.delete, comment_id)
    return Response(status_code=204)


@router.get("/tasks/{ref}/activity", response_model=list[ActivityOut])
async def list_activity(ref: str, svc: ServiceDep) -> list:
    task = await _not_found(svc.get, ref)
    return await svc.uow.activity.list_for_task(task.id)


# --- agenda and parsing ----------------------------------------------------------------


@router.get("/agenda", response_model=AgendaOut)
async def agenda(
    svc: ServiceDep,
    start: date | None = None,
    end: date | None = None,
) -> AgendaOut:
    today = await svc.today()
    start = start or today
    end = end or start + timedelta(days=13)
    if end < start or (end - start).days > 92:
        raise HTTPException(422, "Range must be 0 to 92 days")
    ag = await build_agenda(svc.uow, today, start, end)
    return AgendaOut(
        today=ag.today,
        overdue=await present_tasks(svc, ag.overdue),
        days=[
            AgendaDayOut(
                date=d.date,
                tasks=await present_tasks(svc, d.tasks),
                ghosts=[GhostOut(task_id=g.task.id, date=g.date) for g in d.ghosts],
            )
            for d in ag.days
        ],
    )


@router.post("/parse", response_model=ParseOut)
async def parse(body: ParseIn, svc: ServiceDep) -> ParseOut:
    r = await svc.parse(body.text)
    return ParseOut(
        title=r.title,
        due_date=r.due.date if r.due else None,
        due_time=r.due.time if r.due else None,
        recurrence=_rec(r.recurrence),
        area_id=r.area_id,
        project_id=r.project_id,
        unknown_project=r.unknown_project,
        label_ids=list(r.label_ids),
        unknown_labels=list(r.unknown_labels),
        priority=r.priority,
        status=r.status,
        tokens=[
            TokenOut(
                kind=str(t.kind), start=t.start, end=t.end, text=t.text, unresolved=t.unresolved
            )
            for t in r.tokens
        ],
    )


# --- import ---------------------------------------------------------------------------------


@router.post("/import", response_model=ImportOut)
async def import_batch(body: ImportIn, svc: ServiceDep) -> ImportOut:
    """Idempotent bulk upsert keyed by (source, source_id) within your workspace. Safe to re-run."""
    batch = ImportBatch(
        source=body.source,
        areas=[ImportArea(**a.model_dump()) for a in body.areas],
        projects=[ImportProject(**p.model_dump()) for p in body.projects],
        labels=[ImportLabel(**lb.model_dump()) for lb in body.labels],
        tasks=[
            ImportTask(
                **t.model_dump(exclude={"comments"}),
                comments=[ImportComment(**c.model_dump()) for c in t.comments],
            )
            for t in body.tasks
        ],
    )
    report = await _not_found(run_import, svc, batch)
    return ImportOut(created=report.created, updated=report.updated, warnings=report.warnings)
