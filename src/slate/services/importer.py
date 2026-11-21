"""Bulk import for agent-driven migrations from Linear and Todoist.

One request carries areas, projects, labels, and tasks (with comments). Every
record has a ``source`` (such as "todoist") and a ``source_id``; records refer to
each other by source id, so the agent never needs Slate's ids. Re-running the
same payload updates records in place instead of duplicating them.

Repeat rules arrive as free text (Todoist's ``due.string``, such as
"every! 3 days") and go through Slate's own parser. A string the parser cannot
read is reported back and the task is imported without a repeat, keeping the
text in the description so nothing is lost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import TYPE_CHECKING

from slate.domain import Area, Comment, Label, Project, ProjectStatus, Task, TaskStatus

if TYPE_CHECKING:
    from slate.services.tasks import TaskService


@dataclass
class ImportComment:
    source_id: str
    body: str
    created_at: datetime | None = None


@dataclass
class ImportArea:
    source_id: str
    name: str
    color: str | None = None
    position: int = 0


@dataclass
class ImportProject:
    source_id: str
    name: str
    area_source_id: str | None = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    description: str = ""
    target_date: date | None = None
    created_at: datetime | None = None


@dataclass
class ImportLabel:
    source_id: str
    name: str
    color: str | None = None


@dataclass
class ImportTask:
    source_id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: int = 0
    project_source_id: str | None = None
    area_source_id: str | None = None
    parent_source_id: str | None = None
    label_source_ids: list[str] = field(default_factory=list)
    due_date: date | None = None
    due_time: time | None = None
    repeat: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    comments: list[ImportComment] = field(default_factory=list)


@dataclass
class ImportBatch:
    source: str
    areas: list[ImportArea] = field(default_factory=list)
    projects: list[ImportProject] = field(default_factory=list)
    labels: list[ImportLabel] = field(default_factory=list)
    tasks: list[ImportTask] = field(default_factory=list)


@dataclass
class ImportReport:
    created: dict[str, int] = field(default_factory=dict)
    updated: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def bump(self, kind: str, created: bool) -> None:
        d = self.created if created else self.updated
        d[kind] = d.get(kind, 0) + 1


async def run_import(svc: TaskService, batch: ImportBatch) -> ImportReport:
    uow = svc.uow
    src = batch.source
    report = ImportReport()
    ids: dict[str, dict[str, int]] = {"area": {}, "project": {}, "label": {}, "task": {}}

    async def resolve(kind: str, repo, source_id: str | None) -> int | None:
        if not source_id:
            return None
        if source_id in ids[kind]:
            return ids[kind][source_id]
        found = await repo.get_by_source(src, source_id)
        if found is None:
            report.warnings.append(f"{kind} {source_id} not found")
            return None
        ids[kind][source_id] = found.id
        return found.id

    for a in batch.areas:
        existing = await uow.areas.get_by_source(src, a.source_id)
        if existing:
            existing.name, existing.position = a.name, a.position
            existing.color = a.color or existing.color
            saved = await uow.areas.update(existing)
        else:
            saved = await uow.areas.add(
                Area(name=a.name, color=a.color or "#6b7280", position=a.position,
                     source=src, source_id=a.source_id)
            )
        ids["area"][a.source_id] = saved.id  # type: ignore[assignment]
        report.bump("areas", existing is None)

    for lb in batch.labels:
        existing = await uow.labels.get_by_source(src, lb.source_id)
        if existing:
            existing.name = lb.name
            existing.color = lb.color or existing.color
            saved = await uow.labels.update(existing)
        else:
            saved = await uow.labels.add(
                Label(name=lb.name, color=lb.color or "#6b7280", source=src, source_id=lb.source_id)
            )
        ids["label"][lb.source_id] = saved.id  # type: ignore[assignment]
        report.bump("labels", existing is None)

    for p in batch.projects:
        area_id = await resolve("area", uow.areas, p.area_source_id)
        existing = await uow.projects.get_by_source(src, p.source_id)
        fields = dict(name=p.name, area_id=area_id, status=p.status,
                      description=p.description, target_date=p.target_date)
        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
            saved = await uow.projects.update(existing)
        else:
            saved = await uow.projects.add(
                Project(**fields, source=src, source_id=p.source_id, created_at=p.created_at)
            )
        ids["project"][p.source_id] = saved.id  # type: ignore[assignment]
        report.bump("projects", existing is None)

    # Parents before children, whatever order the agent sent.
    ordered = sorted(batch.tasks, key=lambda t: t.parent_source_id is not None)
    for it in ordered:
        recurrence = None
        description = it.description
        due_date, due_time = it.due_date, it.due_time
        if it.repeat:
            parsed = await svc.parse_schedule(it.repeat)
            if parsed.recurrence is not None:
                recurrence = parsed.recurrence
                if due_date is None and parsed.due:
                    due_date, due_time = parsed.due.date, parsed.due.time
            else:
                report.warnings.append(f"task {it.source_id}: could not parse repeat “{it.repeat}”")
                description = f"{description}\n\nOriginal repeat: {it.repeat}".strip()
        parent_id = await resolve("task", uow.tasks, it.parent_source_id)
        if parent_id is not None and recurrence is not None:
            report.warnings.append(f"task {it.source_id}: subtasks cannot repeat; dropped repeat")
            recurrence = None
        task = Task(
            title=it.title,
            description=description,
            status=it.status,
            priority=it.priority,
            project_id=await resolve("project", uow.projects, it.project_source_id),
            area_id=await resolve("area", uow.areas, it.area_source_id),
            parent_id=parent_id,
            label_ids=[i for s in it.label_source_ids if (i := await resolve("label", uow.labels, s))],
            due_date=due_date,
            due_time=due_time,
            recurrence=recurrence,
            completed_at=it.completed_at,
            source=src,
            source_id=it.source_id,
            created_at=it.created_at,
        )
        if task.project_id is not None:
            task.area_id = None
        existing = await uow.tasks.get_by_source(src, it.source_id)
        if existing:
            task.id = existing.id
            task.created_at = existing.created_at
            task.completed_runs = existing.completed_runs
            saved = await uow.tasks.update(task)
        else:
            if task.status in (TaskStatus.DONE, TaskStatus.CANCELED) and task.completed_at is None:
                task.completed_at = task.created_at
            saved = await uow.tasks.add(task)
            await svc._log(saved.id, "imported", {"source": src, "source_id": it.source_id},  # noqa: SLF001
                           at=saved.created_at)
        ids["task"][it.source_id] = saved.id  # type: ignore[assignment]
        report.bump("tasks", existing is None)

        for c in it.comments:
            ec = await uow.comments.get_by_source(src, c.source_id)
            if ec:
                ec.body = c.body
                await uow.comments.update(ec)
            else:
                await uow.comments.add(
                    Comment(task_id=saved.id, body=c.body, source=src, source_id=c.source_id,  # type: ignore[arg-type]
                            created_at=c.created_at)
                )
            report.bump("comments", ec is None)
    return report
