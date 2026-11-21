"""The memory fake and the SQL repositories must behave the same.

Runs against memory and SQLite always, and against Postgres when
TEST_POSTGRES_URL is set (for example postgresql+asyncpg://localhost/slate_test).
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime

import pytest

from slate.clock import FixedClock
from slate.db import make_engine, make_sessionmaker, run_migrations
from slate.domain import Area, Comment, Label, Project, Task, TaskFilter, TaskStatus
from slate.models import Base
from slate.repositories.memory import MemoryUnitOfWorkFactory
from slate.repositories.sql import SqlUnitOfWorkFactory
from slate.scheduling import Recurrence, RecurrenceMode

NOW = datetime(2026, 11, 21, 14, 0, tzinfo=UTC)

BACKENDS = ["memory", "sqlite"] + (["postgres"] if os.environ.get("TEST_POSTGRES_URL") else [])


@pytest.fixture(params=BACKENDS)
async def uow_factory(request, tmp_path):
    clock = FixedClock(NOW)
    if request.param == "memory":
        yield MemoryUnitOfWorkFactory(clock)
        return
    url = (
        f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
        if request.param == "sqlite"
        else os.environ["TEST_POSTGRES_URL"]
    )
    engine = make_engine(url)
    if request.param == "postgres":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    # Build the schema the way production does, so model/migration drift fails here.
    await run_migrations(engine)
    yield SqlUnitOfWorkFactory(make_sessionmaker(engine), clock)
    await engine.dispose()


async def _seed(uow):
    home = await uow.areas.add(Area(name="Home"))
    work = await uow.areas.add(Area(name="Work"))
    kitchen = await uow.projects.add(Project(name="Kitchen", area_id=home.id))
    errand = await uow.labels.add(Label(name="errand"))
    t = {}
    t["a"] = await uow.tasks.add(
        Task(
            title="Buy tiles",
            project_id=kitchen.id,
            due_date=date(2026, 11, 25),
            priority=2,
            label_ids=[errand.id],
        )
    )
    t["b"] = await uow.tasks.add(
        Task(
            title="Water plants",
            area_id=home.id,
            due_date=date(2026, 11, 21),
            recurrence=Recurrence(
                "FREQ=DAILY", RecurrenceMode.FIXED, date(2026, 11, 1), text="every day"
            ),
        )
    )
    t["c"] = await uow.tasks.add(Task(title="Inbox idea"))
    t["d"] = await uow.tasks.add(
        Task(title="Write report", area_id=work.id, priority=1, due_date=date(2026, 11, 22))
    )
    t["e"] = await uow.tasks.add(
        Task(title="Old thing", status=TaskStatus.DONE, project_id=kitchen.id)
    )
    t["f"] = await uow.tasks.add(
        Task(title="Measure wall", parent_id=t["a"].id, project_id=kitchen.id)
    )
    await uow.commit()
    return home, work, kitchen, errand, t


def titles(tasks):
    return [x.title for x in tasks]


async def test_round_trip_and_filters(uow_factory):
    async with uow_factory() as uow:
        home, work, kitchen, errand, t = await _seed(uow)

    async with uow_factory() as uow:
        got = await uow.tasks.get(t["b"].id)
        assert got.recurrence == t["b"].recurrence
        assert got.created_at == NOW
        assert (await uow.tasks.get(t["a"].id)).label_ids == [errand.id]

        # Default sort: due ascending, undated last, ties by priority then id.
        assert titles(await uow.tasks.list(TaskFilter())) == [
            "Water plants",
            "Write report",
            "Buy tiles",
            "Inbox idea",
            "Measure wall",
        ]
        assert titles(await uow.tasks.list(TaskFilter(sort="priority"))) == [
            "Write report",
            "Buy tiles",
            "Water plants",
            "Inbox idea",
            "Measure wall",
        ]
        assert titles(await uow.tasks.list(TaskFilter(sort="due", order="desc")))[:3] == [
            "Buy tiles",
            "Write report",
            "Water plants",
        ]
        # Area matches direct tasks and tasks of its projects.
        assert set(titles(await uow.tasks.list(TaskFilter(area_id=home.id)))) == {
            "Buy tiles",
            "Water plants",
            "Measure wall",
        }
        assert titles(await uow.tasks.list(TaskFilter(inbox=True))) == ["Inbox idea"]
        assert titles(await uow.tasks.list(TaskFilter(label_id=errand.id))) == ["Buy tiles"]
        assert titles(await uow.tasks.list(TaskFilter(parent_id=t["a"].id))) == ["Measure wall"]
        assert "Measure wall" not in titles(await uow.tasks.list(TaskFilter(parent_id=0)))
        assert titles(await uow.tasks.list(TaskFilter(statuses=(TaskStatus.DONE,)))) == [
            "Old thing"
        ]
        assert len(await uow.tasks.list(TaskFilter(include_closed=True))) == 6
        assert titles(await uow.tasks.list(TaskFilter(recurring=True))) == ["Water plants"]
        assert titles(
            await uow.tasks.list(
                TaskFilter(due_after=date(2026, 11, 22), due_before=date(2026, 11, 25))
            )
        ) == ["Write report", "Buy tiles"]
        assert titles(await uow.tasks.list(TaskFilter(q="TILES"))) == ["Buy tiles"]


async def test_source_uniqueness_and_preserved_timestamps(uow_factory):
    old = datetime(2024, 3, 1, 12, tzinfo=UTC)
    async with uow_factory() as uow:
        a = await uow.tasks.add(
            Task(title="Imported", source="todoist", source_id="99", created_at=old)
        )
        await uow.commit()
    async with uow_factory() as uow:
        got = await uow.tasks.get_by_source("todoist", "99")
        assert got.id == a.id and got.created_at == old
        with pytest.raises(ValueError):
            await uow.tasks.add(Task(title="Dup", source="todoist", source_id="99"))


async def test_delete_cascades(uow_factory):
    async with uow_factory() as uow:
        home, work, kitchen, errand, t = await _seed(uow)
        await uow.comments.add(Comment(task_id=t["a"].id, body="hi"))
        await uow.commit()
    async with uow_factory() as uow:
        await uow.tasks.delete(t["a"].id)
        await uow.projects.delete(kitchen.id)
        await uow.labels.delete(errand.id)
        await uow.commit()
    async with uow_factory() as uow:
        assert await uow.tasks.get(t["f"].id) is None
        assert await uow.comments.list_for_task(t["a"].id) == []
        assert (await uow.tasks.get(t["e"].id)).project_id is None


async def test_settings(uow_factory):
    async with uow_factory() as uow:
        s = await uow.settings.get()
        assert s.timezone == "America/New_York"
        s.timezone = "Europe/Rome"
        await uow.settings.save(s)
        await uow.commit()
    async with uow_factory() as uow:
        assert (await uow.settings.get()).timezone == "Europe/Rome"
