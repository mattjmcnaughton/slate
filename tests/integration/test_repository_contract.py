"""The memory fake and the SQL repositories must behave the same.

Runs against memory and SQLite always, and against Postgres when
TEST_POSTGRES_URL is set (for example postgresql+asyncpg://localhost/slate_test).
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from slate.clock import FixedClock
from slate.db import make_engine, make_sessionmaker, run_migrations
from slate.domain import (
    Account,
    Area,
    Comment,
    Label,
    Project,
    Task,
    TaskFilter,
    TaskStatus,
    Workspace,
)
from slate.models import Base
from slate.repositories.base import NotFoundError
from slate.repositories.memory import MemoryUnitOfWorkFactory
from slate.repositories.sql import SqlUnitOfWorkFactory
from slate.scheduling import Recurrence, RecurrenceMode

NOW = datetime(2026, 11, 21, 14, 0, tzinfo=UTC)

BACKENDS = ["memory", "sqlite"] + (["postgres"] if os.environ.get("TEST_POSTGRES_URL") else [])


async def new_workspace(raw, subject: str):
    """A user with their workspace; returns the workspace id."""
    async with raw() as uow:
        acct = await uow.users.record_sign_in(Account("https://iss/", subject, subject))
        ws = await uow.workspaces.add(Workspace(owner_id=acct.id))
        await uow.commit()
    return ws.id


@pytest.fixture(params=BACKENDS)
async def raw_factory(request, tmp_path):
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


@pytest.fixture
async def uow_factory(raw_factory):
    ws = await new_workspace(raw_factory, "a")
    return lambda: raw_factory(ws)


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
        # Tasks are numbered per workspace in creation order: SLT-1, SLT-2, ...
        assert [t[k].number for k in "abcdef"] == [1, 2, 3, 4, 5, 6]
        assert (await uow.tasks.get_by_number(2)).id == t["b"].id
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
        assert "Measure wall" not in titles(await uow.tasks.list(TaskFilter(top_level=True)))
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


async def test_workspaces_are_isolated(raw_factory):
    """Workspace B can neither see nor change nor link to workspace A's rows."""
    ws_a = await new_workspace(raw_factory, "a")
    ws_b = await new_workspace(raw_factory, "b")
    async with raw_factory(ws_a) as uow:
        home, work, kitchen, errand, t = await _seed(uow)
        await uow.tasks.add(Task(title="Imported", source="todoist", source_id="1"))
        await uow.commit()

    async with raw_factory(ws_b) as uow:
        assert await uow.areas.list() == [] and await uow.projects.list() == []
        assert await uow.labels.list() == []
        assert await uow.tasks.list(TaskFilter(include_closed=True)) == []
        assert await uow.tasks.get(t["a"].id) is None
        assert await uow.projects.get(kitchen.id) is None
        assert await uow.tasks.get_by_source("todoist", "1") is None
        # B's numbering starts at 1 too, and the same source id is B's own record.
        mine = await uow.tasks.add(Task(title="Mine", source="todoist", source_id="1"))
        assert mine.number == 1
        with pytest.raises(NotFoundError):
            await uow.tasks.delete(t["a"].id)
        with pytest.raises(NotFoundError):
            await uow.projects.update(kitchen)
        await uow.commit()

    async with raw_factory(ws_a) as uow:
        assert (await uow.tasks.get(t["a"].id)).title == "Buy tiles"
        assert (await uow.tasks.get_by_source("todoist", "1")).title == "Imported"
        assert (await uow.settings.get()).timezone == "America/New_York"


async def test_database_refuses_cross_workspace_links(raw_factory):
    """Even past the services, a row cannot point into another workspace."""
    if isinstance(raw_factory, MemoryUnitOfWorkFactory):
        pytest.skip("the composite foreign keys live in SQL")
    ws_a = await new_workspace(raw_factory, "a")
    ws_b = await new_workspace(raw_factory, "b")
    async with raw_factory(ws_a) as uow:
        project = await uow.projects.add(Project(name="A's"))
        await uow.commit()
    async with raw_factory(ws_b) as uow:
        with pytest.raises((ValueError, IntegrityError)):
            await uow.tasks.add(Task(title="sneaky", project_id=project.id))
            await uow.commit()
