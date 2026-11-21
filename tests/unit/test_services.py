"""Task, agenda, and import rules, on the memory fake with a fixed clock."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from slate.clock import FixedClock
from slate.domain import Area, Project, Task, TaskFilter, TaskStatus
from slate.repositories.memory import MemoryUnitOfWorkFactory
from slate.scheduling import Recurrence, RecurrenceMode
from slate.services.agenda import build_agenda, project_progress
from slate.services.importer import (
    ImportBatch,
    ImportComment,
    ImportProject,
    ImportTask,
    run_import,
)
from slate.services.tasks import TaskService, ValidationError

# Saturday 2026-11-21, 09:00 in New York.
NOW = datetime(2026, 11, 21, 14, 0, tzinfo=UTC)
DAILY = Recurrence("FREQ=DAILY", RecurrenceMode.FIXED, date(2026, 11, 1), text="every day")


@pytest.fixture
def clock():
    return FixedClock(NOW)


@pytest.fixture
def svc(clock):
    uow = MemoryUnitOfWorkFactory(clock)()
    return TaskService(uow, clock)


async def test_late_fixed_run_skips_to_after_today(svc, clock):
    t = await svc.create(Task(title="Water plants", due_date=date(2026, 11, 18), recurrence=DAILY))
    done = await svc.complete(t.id)
    # Due the 18th, completed on the 21st: next is the 22nd, not the 19th.
    assert done.due_date == date(2026, 11, 22)
    assert done.status == TaskStatus.TODO
    assert done.completed_runs == 1
    kinds = [a.kind for a in await svc.uow.activity.list_for_task(t.id)]
    assert kinds == ["created", "completed_run"]


async def test_after_completion_counts_from_today(svc):
    rec = Recurrence("FREQ=DAILY;INTERVAL=3", RecurrenceMode.AFTER_COMPLETION, date(2026, 11, 1))
    t = await svc.create(Task(title="Water ferns", due_date=date(2026, 11, 15), recurrence=rec))
    assert (await svc.complete(t.id)).due_date == date(2026, 11, 24)


async def test_series_with_count_ends_done(svc):
    rec = Recurrence("FREQ=DAILY;COUNT=2", RecurrenceMode.FIXED, date(2026, 11, 21))
    t = await svc.create(Task(title="Two runs", recurrence=rec))
    assert t.due_date == date(2026, 11, 21)
    once = await svc.complete(t.id)
    assert once.status == TaskStatus.TODO and once.due_date == date(2026, 11, 22)
    # The rule has no run after the 22nd, so the second completion ends it.
    twice = await svc.complete(t.id)
    assert twice.status == TaskStatus.DONE


async def test_moving_a_repeating_run_keeps_the_rule(svc):
    t = await svc.create(Task(title="Run", due_date=date(2026, 11, 21), recurrence=DAILY))
    moved = await svc.update(t.id, {"due_date": date(2026, 11, 25)})
    assert moved.recurrence == DAILY and moved.due_date == date(2026, 11, 25)


async def test_subtask_rules(svc):
    parent = await svc.create(Task(title="Parent"))
    child = await svc.create(Task(title="Child", parent_id=parent.id))
    with pytest.raises(ValidationError):
        await svc.create(Task(title="Grandchild", parent_id=child.id))
    with pytest.raises(ValidationError):
        await svc.create(Task(title="Repeating child", parent_id=parent.id, recurrence=DAILY))
    assert await svc.open_subtasks(parent.id) == 1


async def test_task_in_project_drops_direct_area(svc):
    area = await svc.uow.areas.add(Area(name="Home"))
    proj = await svc.uow.projects.add(Project(name="Kitchen", area_id=area.id))
    t = await svc.create(Task(title="x", project_id=proj.id, area_id=area.id))
    assert t.area_id is None and t.project_id == proj.id


async def test_agenda_ghosts_and_overdue(svc):
    await svc.create(Task(title="Late", due_date=date(2026, 11, 19)))
    await svc.create(Task(title="Daily", due_date=date(2026, 11, 21), recurrence=DAILY))
    ag = await build_agenda(svc.uow, date(2026, 11, 21), date(2026, 11, 21), date(2026, 11, 23))
    assert [t.title for t in ag.overdue] == ["Late"]
    assert [t.title for t in ag.days[0].tasks] == ["Daily"]
    assert ag.days[0].ghosts == []
    assert [g.date for d in ag.days for g in d.ghosts] == [date(2026, 11, 22), date(2026, 11, 23)]


async def test_progress_ignores_repeating_and_canceled(svc):
    proj = await svc.uow.projects.add(Project(name="Marathon"))
    await svc.create(Task(title="Buy shoes", project_id=proj.id, status=TaskStatus.DONE))
    await svc.create(Task(title="Register", project_id=proj.id))
    await svc.create(Task(title="Skip", project_id=proj.id, status=TaskStatus.CANCELED))
    await svc.create(Task(title="Run", project_id=proj.id, recurrence=DAILY))
    p = (await project_progress(svc.uow, [proj]))[proj.id]
    assert (p.done, p.total) == (1, 2)


async def test_import_is_idempotent_and_keeps_history(svc):
    old = datetime(2024, 5, 1, 12, tzinfo=UTC)
    batch = ImportBatch(
        source="todoist",
        projects=[ImportProject(source_id="p1", name="Home")],
        tasks=[
            ImportTask(
                source_id="t2", title="Child", parent_source_id="t1", project_source_id="p1"
            ),
            ImportTask(
                source_id="t1",
                title="Parent",
                project_source_id="p1",
                repeat="every week",
                created_at=old,
                comments=[ImportComment(source_id="c1", body="note", created_at=old)],
            ),
            ImportTask(source_id="t3", title="Odd", repeat="every blue moon"),
        ],
    )
    first = await run_import(svc, batch)
    assert first.created == {"projects": 1, "tasks": 3, "comments": 1}
    assert any("blue moon" in w for w in first.warnings)
    second = await run_import(svc, batch)
    assert second.created == {}
    assert second.updated == {"projects": 1, "tasks": 3, "comments": 1}

    tasks = await svc.list(TaskFilter())
    assert len(tasks) == 3
    parent = await svc.uow.tasks.get_by_source("todoist", "t1")
    child = await svc.uow.tasks.get_by_source("todoist", "t2")
    odd = await svc.uow.tasks.get_by_source("todoist", "t3")
    assert parent.created_at == old and parent.recurrence is not None
    assert child.parent_id == parent.id
    assert odd.recurrence is None and "every blue moon" in odd.description
