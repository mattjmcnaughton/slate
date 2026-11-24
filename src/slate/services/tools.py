"""The agent tool catalog, shared by the sidebar assistant and the MCP server.

Each tool is a plain async function over ``TaskService``. ``call_tool`` is the
single entry point for agents, and it is where the workspace's Agent mode is
enforced (not in any prompt):

- reads run;
- writes run now in ``apply`` mode and become Pending changes in ``suggest`` mode;
- deletes always become Pending changes.

A write is checked (``prepare``) before it is stored as a Pending change, so the
caller hears about an unknown task or project at once. Applying re-validates,
because the owner may have edited the input. Applying and dismissing are not
tools: only a browser session can do them (``routers/agent.py``).

Excluded on purpose, so no agent can reach them: API keys, agent and workspace
settings, AGENT.md, applying Pending changes, and deleting projects, areas, or
labels.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from slate.domain import (
    AgentMode,
    Area,
    Label,
    PendingChange,
    PendingStatus,
    Project,
    Task,
    TaskFilter,
    TaskStatus,
    task_key,
)
from slate.dtos import tools as t
from slate.repositories.base import NotFoundError
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

if TYPE_CHECKING:
    from slate.auth import User
    from slate.clock import Clock
    from slate.repositories.base import UnitOfWorkFactory

Kind = Literal["read", "write", "delete"]


class ToolError(Exception):
    """A rejection the caller can show or fix. The message never echoes input values."""

    def __init__(self, code: str, message: str) -> None:
        self.code, self.message = code, message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class ToolContext:
    uow_factory: UnitOfWorkFactory
    clock: Clock
    user: User
    origin: str  # agent (the sidebar) | mcp


Draft = tuple[str, BaseModel]  # (summary, input for one Pending change)


@dataclass(frozen=True)
class CatalogTool:
    name: str
    kind: Kind
    description: str
    input: type[BaseModel]
    run: Callable[[TaskService, Any], Awaitable[BaseModel]]
    # Writes: check and normalize the input, then split it into Pending changes.
    prepare: Callable[[TaskService, Any], Awaitable[Any]] | None = None
    drafts: Callable[[TaskService, Any], Awaitable[list[Draft]]] | None = None


# --- projections -------------------------------------------------------------------


def task_row(task: Task, numbers: dict[UUID, int] | None = None) -> t.TaskRow:
    parent = (numbers or {}).get(task.parent_id) if task.parent_id else None
    return t.TaskRow(
        id=task.id,
        key=task_key(task.number or 0),
        title=task.title,
        status=task.status,
        priority=task.priority,
        project_id=task.project_id,
        area_id=task.area_id,
        label_ids=list(task.label_ids),
        due_date=task.due_date,
        due_time=task.due_time,
        repeat=task.recurrence.text if task.recurrence else None,
        parent_key=task_key(parent) if parent else None,
    )


def _pending_row(p: PendingChange) -> t.PendingRow:
    return t.PendingRow(
        id=p.id, tool=p.tool, origin=p.origin, status=str(p.status), summary=p.summary
    )


# --- reads ---------------------------------------------------------------------------


async def get_overview(svc: TaskService, _: t.Empty) -> t.Overview:
    uow = svc.uow
    today = await svc.today()
    settings = await uow.settings.get()
    open_tasks = await uow.tasks.list(TaskFilter(sort="due"))
    return t.Overview(
        today=today,
        timezone=settings.timezone,
        agent_mode=str(settings.agent_mode),
        areas=[t.AreaRow(id=a.id, name=a.name) for a in await uow.areas.list()],
        projects=[
            t.ProjectRow(
                id=p.id, name=p.name, area_id=p.area_id, status=p.status, target_date=p.target_date
            )
            for p in await uow.projects.list()
            if p.status not in ("done", "canceled")
        ],
        labels=[t.LabelRow(id=lb.id, name=lb.name) for lb in await uow.labels.list()],
        overdue=[task_row(x) for x in open_tasks if x.due_date and x.due_date < today][:50],
        due_today=[task_row(x) for x in open_tasks if x.due_date == today][:50],
        inbox=[task_row(x) for x in open_tasks if x.is_inbox and x.parent_id is None][:50],
        open_task_count=len(open_tasks),
        pending_change_count=len(await uow.pending_changes.list(PendingStatus.PENDING)),
    )


async def find_tasks(svc: TaskService, a: t.FindTasks) -> t.TaskList:
    found = await svc.list(
        TaskFilter(
            q=a.q,
            project_id=a.project_id,
            area_id=a.area_id,
            label_id=a.label_id,
            inbox=a.inbox,
            statuses=tuple(a.status),
            due_before=a.due_before,
            due_after=a.due_after,
            include_closed=a.include_closed,
            limit=a.limit + 1,
        )
    )
    return t.TaskList(tasks=[task_row(x) for x in found[: a.limit]], truncated=len(found) > a.limit)


async def get_task(svc: TaskService, a: t.TaskRef) -> t.TaskDetail:
    task = await svc.get(a.ref)
    subs = await svc.list(TaskFilter(parent_id=task.id, include_closed=True))
    comments = await svc.uow.comments.list_for_task(task.id)
    return t.TaskDetail(
        **task_row(task).__dict__,
        description=task.description,
        subtasks=[task_row(s) for s in subs],
        comments=[
            t.CommentRow(
                id=c.id, body=c.body, created_at=c.created_at.isoformat() if c.created_at else ""
            )
            for c in comments[-20:]
        ],
    )


async def list_pending_changes(svc: TaskService, _: t.Empty) -> t.PendingList:
    rows = await svc.uow.pending_changes.list(PendingStatus.PENDING)
    return t.PendingList(pending_changes=[_pending_row(p) for p in rows])


# --- writes: tasks -------------------------------------------------------------------


async def _check_refs(svc: TaskService, f: t.TaskFields) -> None:
    uow = svc.uow
    if f.project_id and await uow.projects.get(f.project_id) is None:
        raise ValidationError("Unknown project_id; read get_overview for ids")
    if f.area_id and await uow.areas.get(f.area_id) is None:
        raise ValidationError("Unknown area_id; read get_overview for ids")
    for lid in f.label_ids or []:
        if await uow.labels.get(lid) is None:
            raise ValidationError("Unknown label id; read get_overview for ids")


async def _prepare_task(svc: TaskService, f: t.TaskFields) -> t.TaskFields:
    """Check one task and resolve its words to fields, so the stored draft is exact."""
    update: dict[str, Any] = {}
    if f.ref is not None:
        update["ref"] = task_key((await svc.get(f.ref)).number or 0)
    elif not (f.title or "").strip():
        raise ValidationError("A new task needs a title")
    if f.parent is not None:
        parent = await svc.get(f.parent)
        if parent.parent_id is not None:
            raise ValidationError("Subtasks can only be one level deep")
        update["parent"] = task_key(parent.number or 0)
    await _check_refs(svc, f)
    if f.due_string:
        parsed = await svc.parse_schedule(f.due_string)
        if parsed.error:
            raise ValidationError(
                f"due_string {f.due_string!r} is not one date phrase; send one such as "
                "'fri', '12/4', or 'dec 4 5pm'"
            )
        if parsed.recurrence is not None:
            update["repeat_string"] = f.due_string
        elif parsed.due is not None:
            update["due_date"], update["due_time"] = parsed.due.date, parsed.due.time
        update["due_string"] = None
    repeat = update.get("repeat_string") or f.repeat_string
    if repeat:
        parsed = await svc.parse_schedule(repeat)
        if parsed.recurrence is None:
            raise ValidationError("Could not read the repeat rule")
    out = f.model_copy(update=update)
    if "due_string" in out.model_fields_set and out.due_string is None:
        out.model_fields_set.discard("due_string")
    return out


async def _save_one(svc: TaskService, f: t.TaskFields) -> Task:
    f = await _prepare_task(svc, f)
    recurrence = None
    if f.repeat_string:
        recurrence = (await svc.parse_schedule(f.repeat_string)).recurrence
    parent_id = (await svc.get(f.parent)).id if f.parent else None
    if f.ref is None:
        return await svc.create(
            Task(
                title=(f.title or "").strip(),
                description=f.description or "",
                status=f.status or TaskStatus.TODO,
                priority=f.priority or 0,
                project_id=f.project_id,
                area_id=f.area_id,
                label_ids=list(f.label_ids or []),
                parent_id=parent_id,
                due_date=None if f.clear_due else f.due_date,
                due_time=None if f.clear_due else f.due_time,
                recurrence=recurrence,
            )
        )
    sent = f.model_fields_set
    simple = ("title", "description", "status", "priority", "project_id", "area_id", "label_ids")
    changes: dict[str, Any] = {k: getattr(f, k) for k in simple if k in sent}
    if "label_ids" in changes:
        changes["label_ids"] = list(changes["label_ids"] or [])
    if f.parent:
        changes["parent_id"] = parent_id
    if "due_date" in sent:
        changes["due_date"] = f.due_date
        changes["due_time"] = f.due_time
    if f.clear_due:
        changes["due_date"] = changes["due_time"] = None
    if recurrence is not None:
        changes["recurrence"] = recurrence
    return await svc.update(f.ref, changes)


async def save_tasks(svc: TaskService, a: t.SaveTasks) -> t.WriteResult:
    saved = [await _save_one(svc, f) for f in a.tasks]
    made = sum(1 for f in a.tasks if f.ref is None)
    return t.WriteResult(
        outcome="applied",
        summary=f"Saved {len(saved)} task(s): {made} new, {len(saved) - made} updated",
        tasks=[task_row(x) for x in saved],
    )


async def _prepare_save_tasks(svc: TaskService, a: t.SaveTasks) -> t.SaveTasks:
    return t.SaveTasks(tasks=[await _prepare_task(svc, f) for f in a.tasks])


async def _drafts_save_tasks(svc: TaskService, a: t.SaveTasks) -> list[Draft]:
    out: list[Draft] = []
    for f in a.tasks:
        if f.ref is None:
            summary = f"New task: {f.title}"
        else:
            summary = f"Update {f.ref}: {f.title or (await svc.get(f.ref)).title}"
        out.append((summary, t.SaveTasks(tasks=[f])))
    return out


def _one_task(verb: str) -> Callable[[TaskService, t.TaskRef], Awaitable[list[Draft]]]:
    async def drafts(svc: TaskService, a: t.TaskRef) -> list[Draft]:
        task = await svc.get(a.ref)
        return [(f"{verb} {task_key(task.number or 0)}: {task.title}", a)]

    return drafts


async def _prepare_ref(svc: TaskService, a: t.TaskRef) -> t.TaskRef:
    return t.TaskRef(ref=task_key((await svc.get(a.ref)).number or 0))


async def complete_task(svc: TaskService, a: t.TaskRef) -> t.WriteResult:
    task = await svc.complete(a.ref)
    note = f", next due {task.due_date}" if not task.is_closed and task.due_date else ""
    return t.WriteResult(
        outcome="applied",
        summary=f"Completed {task_key(task.number or 0)}{note}",
        tasks=[task_row(task)],
    )


async def reopen_task(svc: TaskService, a: t.TaskRef) -> t.WriteResult:
    task = await svc.reopen(a.ref)
    return t.WriteResult(
        outcome="applied", summary=f"Reopened {task_key(task.number or 0)}", tasks=[task_row(task)]
    )


async def delete_task(svc: TaskService, a: t.TaskRef) -> t.WriteResult:
    task = await svc.get(a.ref)
    await svc.delete(task.id)
    return t.WriteResult(outcome="applied", summary=f"Deleted {task_key(task.number or 0)}")


async def _drafts_delete(svc: TaskService, a: t.TaskRef) -> list[Draft]:
    task = await svc.get(a.ref)
    subs = await svc.list(TaskFilter(parent_id=task.id, include_closed=True))
    comments = (await svc.uow.comments.count_by_task([task.id])).get(task.id, 0)
    summary = f"Delete {task_key(task.number or 0)}: {task.title}"
    if subs or comments:
        summary += f" (also deletes {len(subs)} subtask(s) and {comments} comment(s))"
    return [(summary, a)]


async def add_comment(svc: TaskService, a: t.AddComment) -> t.WriteResult:
    task = await svc.get(a.ref)
    await svc.add_comment(task.id, a.body)
    return t.WriteResult(outcome="applied", summary=f"Commented on {task_key(task.number or 0)}")


async def _prepare_comment(svc: TaskService, a: t.AddComment) -> t.AddComment:
    return a.model_copy(update={"ref": task_key((await svc.get(a.ref)).number or 0)})


async def _drafts_comment(svc: TaskService, a: t.AddComment) -> list[Draft]:
    return [(f"Comment on {a.ref}: {a.body[:200]}", a)]


# --- writes: projects, areas, labels -----------------------------------------------------


def _fields(a: BaseModel, *names: str) -> dict[str, Any]:
    return {n: getattr(a, n) for n in names if n in a.model_fields_set}


async def _prepare_project(svc: TaskService, a: t.SaveProject) -> t.SaveProject:
    if a.id is not None and await svc.uow.projects.get(a.id) is None:
        raise NotFoundError("project")
    if a.id is None and not a.name:
        raise ValidationError("A new project needs a name")
    if a.area_id and await svc.uow.areas.get(a.area_id) is None:
        raise ValidationError("Unknown area_id; read get_overview for ids")
    return a


async def save_project(svc: TaskService, a: t.SaveProject) -> t.WriteResult:
    await _prepare_project(svc, a)
    fields = _fields(a, "name", "area_id", "status", "description", "target_date")
    if a.id is None:
        p = await svc.uow.projects.add(Project(**fields))
    else:
        p = await svc.uow.projects.get(a.id)
        assert p is not None
        for k, v in fields.items():
            setattr(p, k, v if k != "description" else (v or ""))
        p = await svc.uow.projects.update(p)
    return t.WriteResult(outcome="applied", summary=f"Saved project {p.name}")


async def _prepare_named(repo_name: str, svc: TaskService, a: Any) -> Any:
    if a.id is not None and await getattr(svc.uow, repo_name).get(a.id) is None:
        raise NotFoundError(repo_name)
    if a.id is None and not a.name:
        raise ValidationError("A name is required")
    return a


def _save_named(repo_name: str, cls: type, label: str) -> Callable[..., Awaitable[t.WriteResult]]:
    async def run(svc: TaskService, a: Any) -> t.WriteResult:
        await _prepare_named(repo_name, svc, a)
        repo = getattr(svc.uow, repo_name)
        fields = _fields(a, "name", "color")
        if a.id is None:
            e = await repo.add(cls(**fields))
        else:
            e = await repo.get(a.id)
            for k, v in fields.items():
                if v is not None:
                    setattr(e, k, v)
            e = await repo.update(e)
        return t.WriteResult(outcome="applied", summary=f"Saved {label} {e.name}")

    return run


def _drafts_named(label: str) -> Callable[..., Awaitable[list[Draft]]]:
    async def drafts(svc: TaskService, a: Any) -> list[Draft]:
        verb = "New" if a.id is None else "Update"
        return [(f"{verb} {label}: {a.name or ''}".strip(), a)]

    return drafts


# --- writes: import ------------------------------------------------------------------------


def _batch(a: t.ImportTasks) -> ImportBatch:
    return ImportBatch(
        source=a.source,
        areas=[ImportArea(**x.model_dump()) for x in a.areas],
        projects=[ImportProject(**x.model_dump()) for x in a.projects],
        labels=[ImportLabel(**x.model_dump()) for x in a.labels],
        tasks=[
            ImportTask(
                **x.model_dump(exclude={"comments"}),
                comments=[ImportComment(**c.model_dump()) for c in x.comments],
            )
            for x in a.tasks
        ],
    )


async def import_tasks(svc: TaskService, a: t.ImportTasks) -> t.WriteResult:
    report = await run_import(svc, _batch(a))
    created = sum(report.created.values())
    updated = sum(report.updated.values())
    summary = f"Imported from {a.source}: {created} created, {updated} updated"
    if report.warnings:
        summary += f"; {len(report.warnings)} warning(s): " + "; ".join(report.warnings[:5])
    detail = {f"created_{k}": v for k, v in report.created.items()}
    detail |= {f"updated_{k}": v for k, v in report.updated.items()}
    return t.WriteResult(outcome="applied", summary=summary, detail=detail)


async def _drafts_import(svc: TaskService, a: t.ImportTasks) -> list[Draft]:
    parts = [f"{len(a.tasks)} task(s)"]
    for name, items in (("project", a.projects), ("area", a.areas), ("label", a.labels)):
        if items:
            parts.append(f"{len(items)} {name}(s)")
    return [(f"Import from {a.source}: " + ", ".join(parts), a)]


async def _same(svc: TaskService, a: Any) -> Any:
    return a


# --- the catalog ---------------------------------------------------------------------


def _all_one(summary: str) -> Callable[[TaskService, Any], Awaitable[list[Draft]]]:
    async def drafts(svc: TaskService, a: Any) -> list[Draft]:
        return [(summary, a)]

    return drafts


CATALOG: tuple[CatalogTool, ...] = (
    CatalogTool(
        "get_overview",
        "read",
        "Start here. Today's date and time zone, the Agent mode, every area, open project and "
        "label with ids, overdue tasks, tasks due today, Inbox tasks, and counts.",
        t.Empty,
        get_overview,
    ),
    CatalogTool(
        "find_tasks",
        "read",
        "Search and filter tasks. Open tasks only unless include_closed or status says otherwise.",
        t.FindTasks,
        find_tasks,
    ),
    CatalogTool(
        "get_task",
        "read",
        "One task with its description, subtasks, and latest comments.",
        t.TaskRef,
        get_task,
    ),
    CatalogTool(
        "list_pending_changes",
        "read",
        "Changes drafted by agents that wait for the owner to apply them in Slate.",
        t.Empty,
        list_pending_changes,
    ),
    CatalogTool(
        "save_tasks",
        "write",
        "Create or update one or many tasks in one call (omit ref to create). Use due_string "
        "and repeat_string for dates in words; never compute dates yourself. A missing date "
        "stays empty: never default it to today.",
        t.SaveTasks,
        save_tasks,
        _prepare_save_tasks,
        _drafts_save_tasks,
    ),
    CatalogTool(
        "complete_task",
        "write",
        "Complete a task. A repeating task rolls forward to its next date.",
        t.TaskRef,
        complete_task,
        _prepare_ref,
        _one_task("Complete"),
    ),
    CatalogTool(
        "reopen_task",
        "write",
        "Reopen a done or canceled task.",
        t.TaskRef,
        reopen_task,
        _prepare_ref,
        _one_task("Reopen"),
    ),
    CatalogTool(
        "delete_task",
        "delete",
        "Delete a task with its subtasks and comments. Always waits for the owner's approval.",
        t.TaskRef,
        delete_task,
        _prepare_ref,
        _drafts_delete,
    ),
    CatalogTool(
        "add_comment",
        "write",
        "Add a comment to a task.",
        t.AddComment,
        add_comment,
        _prepare_comment,
        _drafts_comment,
    ),
    CatalogTool(
        "save_project",
        "write",
        "Create a project (omit id) or update one.",
        t.SaveProject,
        save_project,
        _prepare_project,
        _drafts_named("project"),
    ),
    CatalogTool(
        "save_area",
        "write",
        "Create an area (omit id) or update one.",
        t.SaveArea,
        _save_named("areas", Area, "area"),
        lambda svc, a: _prepare_named("areas", svc, a),
        _drafts_named("area"),
    ),
    CatalogTool(
        "save_label",
        "write",
        "Create a label (omit id) or update one.",
        t.SaveLabel,
        _save_named("labels", Label, "label"),
        lambda svc, a: _prepare_named("labels", svc, a),
        _drafts_named("label"),
    ),
    CatalogTool(
        "import_tasks",
        "write",
        "Import areas, projects, labels, and tasks (with comments) from another tool, such as "
        "a pasted Linear or Todoist export. Every record needs a stable source_id; re-running "
        "updates records instead of duplicating them. Send at most about 200 tasks per call.",
        t.ImportTasks,
        import_tasks,
        _same,
        _drafts_import,
    ),
)

TOOLS = {tool.name: tool for tool in CATALOG}


# --- dispatch ------------------------------------------------------------------------


def _reject(e: Exception) -> ToolError:
    if isinstance(e, ToolError):
        return e
    if isinstance(e, NotFoundError):
        return ToolError("not_found", "No such record in this workspace.")
    if isinstance(e, ValidationError):
        return ToolError("invalid", str(e))
    if isinstance(e, PydanticValidationError):
        fields = sorted({".".join(map(str, x["loc"])) or "input" for x in e.errors()})
        return ToolError("invalid_arguments", f"Check {', '.join(fields)[:300]}.")
    return ToolError("failed", "The operation could not be completed.")


def _service(uow: Any, ctx: ToolContext, via: str) -> TaskService:
    svc = TaskService(uow, ctx.clock)
    svc.via = via
    return svc


def _input_json(a: BaseModel) -> dict[str, Any]:
    return a.model_dump(mode="json", exclude_unset=True)


async def call_tool(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> BaseModel:
    """Run one catalog tool for an agent, applying the workspace's Agent mode."""
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolError("unknown_tool", "No such tool.")
    try:
        args = tool.input.model_validate(arguments)
        async with ctx.uow_factory(ctx.user.workspace_id) as uow:
            svc = _service(uow, ctx, ctx.origin)
            if tool.kind == "read":
                return await tool.run(svc, args)
            assert tool.prepare and tool.drafts
            mode = (await uow.settings.get()).agent_mode
            args = await tool.prepare(svc, args)
            if tool.kind == "delete" or mode != AgentMode.APPLY:
                ids = []
                drafts = await tool.drafts(svc, args)
                for summary, draft in drafts:
                    p = await uow.pending_changes.add(
                        PendingChange(
                            tool=name,
                            input=_input_json(draft),
                            summary=summary,
                            origin=ctx.origin,
                            created_by=ctx.user.id,
                        )
                    )
                    ids.append(p.id)
                await uow.commit()
                return t.WriteResult(
                    outcome="pending",
                    summary=f"{len(ids)} change(s) wait for the owner to apply them in Slate",
                    pending_change_ids=ids,
                )
            result = await tool.run(svc, args)
            await uow.commit()
            return result
    except Exception as e:
        raise _reject(e) from None


async def apply_pending(
    ctx: ToolContext, pending_id: UUID, edited: dict[str, Any] | None = None
) -> PendingChange:
    """Apply a Pending change once, optionally with the owner's edits.

    A change that is no longer pending is returned as it is, so a second Apply
    does nothing. A rejected input leaves the change pending for another edit.
    """
    async with ctx.uow_factory(ctx.user.workspace_id) as uow:
        p = await uow.pending_changes.get(pending_id)
        if p is None:
            raise NotFoundError("pending change")
        if p.status != PendingStatus.PENDING:
            return p
        tool = TOOLS[p.tool]
        try:
            args = tool.input.model_validate(edited if edited is not None else p.input)
            result = await tool.run(_service(uow, ctx, p.origin), args)
        except Exception as e:
            raise _reject(e) from None
        p.status = PendingStatus.APPLIED
        p.input = _input_json(args)
        p.result = result.model_dump(mode="json")
        if not await uow.pending_changes.resolve(p):
            raise ToolError("conflict", "This change was already resolved.")
        await uow.commit()
        return await uow.pending_changes.get(pending_id) or p


async def dismiss_pending(ctx: ToolContext, pending_id: UUID) -> PendingChange:
    async with ctx.uow_factory(ctx.user.workspace_id) as uow:
        p = await uow.pending_changes.get(pending_id)
        if p is None:
            raise NotFoundError("pending change")
        if p.status == PendingStatus.PENDING:
            p.status = PendingStatus.DISMISSED
            await uow.pending_changes.resolve(p)
            await uow.commit()
        return await uow.pending_changes.get(pending_id) or p


def tool_schema(tool: CatalogTool) -> dict[str, Any]:
    """The input JSON schema an agent sees."""
    schema = tool.input.model_json_schema()
    schema.setdefault("properties", {})
    schema["type"] = "object"
    return schema
