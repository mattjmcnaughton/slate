"""Demo data for local development, dated relative to "today".

Loaded at startup when SLATE_SEED=demo and the database has no areas. It goes
through the real services, so seeded tasks follow the same rules as real ones.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING

from slate.domain import Area, Label, Project, ProjectStatus, Task, TaskStatus
from slate.scheduling import Recurrence, RecurrenceMode
from slate.services.tasks import TaskService

if TYPE_CHECKING:
    from slate.container import Container


async def seed_if_empty(container: Container) -> None:
    async with container.uow_factory() as uow:
        if await uow.areas.list():
            return
        svc = TaskService(uow, container.clock)
        await seed_demo(svc)
        await uow.commit()


# Built from RRULEs directly so the seed does not depend on the parser.
RULES = {
    "every 1st": ("FREQ=MONTHLY;BYMONTHDAY=1", RecurrenceMode.FIXED),
    "every tue": ("FREQ=WEEKLY;BYDAY=TU", RecurrenceMode.FIXED),
    "every sun": ("FREQ=WEEKLY;BYDAY=SU", RecurrenceMode.FIXED),
    "every day": ("FREQ=DAILY", RecurrenceMode.FIXED),
    "every week": ("FREQ=WEEKLY", RecurrenceMode.FIXED),
    "every! 3 days": ("FREQ=DAILY;INTERVAL=3", RecurrenceMode.AFTER_COMPLETION),
}


async def _rule(svc: TaskService, text: str, at: time | None = None) -> Recurrence:
    rrule, mode = RULES[text]
    return Recurrence(rrule, mode, await svc.today(), time=at, text=text)


async def seed_demo(svc: TaskService) -> None:
    uow = svc.uow
    today = await svc.today()

    def d(days: int) -> date:
        return today + timedelta(days=days)

    def ago(days: int) -> datetime:
        return svc.clock.now() - timedelta(days=days)

    home = await uow.areas.add(Area(name="Home", color="#d97706", position=0))
    health = await uow.areas.add(Area(name="Health", color="#16a34a", position=1))
    work = await uow.areas.add(Area(name="Work", color="#2563eb", position=2))
    side = await uow.areas.add(Area(name="Side projects", color="#9333ea", position=3))

    errand = await uow.labels.add(Label(name="errand", color="#f59e0b"))
    calls = await uow.labels.add(Label(name="calls", color="#06b6d4"))
    deep = await uow.labels.add(Label(name="deep-work", color="#6366f1"))
    quick = await uow.labels.add(Label(name="quick", color="#84cc16"))

    kitchen = await uow.projects.add(
        Project(
            name="Kitchen refresh",
            area_id=home.id,
            status=ProjectStatus.ACTIVE,
            description="Paint, new backsplash, and swap the faucet before the holidays.",
            target_date=d(24),
            created_at=ago(30),
        )
    )
    marathon = await uow.projects.add(
        Project(
            name="Half marathon",
            area_id=health.id,
            status=ProjectStatus.ACTIVE,
            description="Spring half. Build to 20 miles a week by February.",
            target_date=d(120),
            created_at=ago(45),
        )
    )
    q1 = await uow.projects.add(
        Project(
            name="Q1 planning",
            area_id=work.id,
            status=ProjectStatus.ACTIVE,
            description="Roadmap, headcount ask, and the offsite agenda.",
            target_date=d(10),
            created_at=ago(14),
        )
    )
    slate = await uow.projects.add(
        Project(
            name="Slate",
            area_id=side.id,
            status=ProjectStatus.ACTIVE,
            description="This app. Replace Linear and Todoist.",
            target_date=d(40),
            created_at=ago(3),
        )
    )
    await uow.projects.add(
        Project(
            name="Garden beds",
            area_id=home.id,
            status=ProjectStatus.PLANNED,
            description="Raised beds along the fence, next spring.",
            target_date=d(150),
            created_at=ago(60),
        )
    )

    async def add(**kw) -> Task:  # noqa: ANN003
        comments = kw.pop("comments", [])
        t = await svc.create(Task(**kw))
        for i, body in enumerate(comments):
            await svc.add_comment(t.id, body, created_at=ago(len(comments) - i))  # type: ignore[arg-type]
        return t

    # Inbox and daily life (Todoist side).
    await add(
        title="Call the dentist to reschedule", due_date=d(0), priority=2, label_ids=[calls.id]
    )
    await add(title="Return library books", due_date=d(-2), label_ids=[errand.id])
    await add(title="Look into a standing desk", description="Budget around $500.")
    await add(title="Buy birthday card for Sam", due_date=d(3), label_ids=[errand.id, quick.id])
    await add(
        title="Pay rent", area_id=home.id, priority=1, recurrence=await _rule(svc, "every 1st")
    )
    await add(
        title="Take out recycling",
        area_id=home.id,
        recurrence=await _rule(svc, "every tue"),
        label_ids=[quick.id],
    )
    await add(
        title="Water the ferns", area_id=home.id, recurrence=await _rule(svc, "every! 3 days")
    )
    await add(
        title="Stretch", area_id=health.id, recurrence=await _rule(svc, "every day", time(7, 0))
    )
    await add(
        title="Weekly review",
        recurrence=await _rule(svc, "every week"),
        priority=3,
        comments=["Check Upcoming, then each active project's board."],
    )

    # Kitchen refresh.
    tiles = await add(
        title="Pick backsplash tile",
        project_id=kitchen.id,
        status=TaskStatus.IN_PROGRESS,
        priority=2,
        due_date=d(2),
        comments=[
            "Narrowed to the white zellige or the green subway.",
            "Green subway is 3 weeks out; zellige ships Monday.",
        ],
    )
    await add(
        title="Order tile samples",
        project_id=kitchen.id,
        parent_id=tiles.id,
        status=TaskStatus.DONE,
    )
    await add(
        title="Measure the backsplash area",
        project_id=kitchen.id,
        parent_id=tiles.id,
        due_date=d(1),
        label_ids=[quick.id],
    )
    await add(
        title="Buy paint and rollers", project_id=kitchen.id, due_date=d(-1), label_ids=[errand.id]
    )
    await add(title="Paint the walls", project_id=kitchen.id, due_date=d(6))
    await add(title="Swap the faucet", project_id=kitchen.id, status=TaskStatus.BACKLOG)
    await add(
        title="Get a plumber quote",
        project_id=kitchen.id,
        status=TaskStatus.DONE,
        label_ids=[calls.id],
    )
    await add(title="Replace cabinet handles", project_id=kitchen.id, status=TaskStatus.CANCELED)

    # Half marathon.
    await add(title="Buy new running shoes", project_id=marathon.id, status=TaskStatus.DONE)
    await add(title="Register for the race", project_id=marathon.id, priority=1, due_date=d(5))
    await add(title="Find a training plan", project_id=marathon.id, status=TaskStatus.IN_PROGRESS)
    await add(title="Long run", project_id=marathon.id, recurrence=await _rule(svc, "every sun"))
    await add(title="Easy run", project_id=marathon.id, recurrence=await _rule(svc, "every tue"))
    await add(title="Book a sports massage", project_id=marathon.id, status=TaskStatus.BACKLOG)

    # Q1 planning.
    await add(
        title="Draft the Q1 roadmap",
        project_id=q1.id,
        status=TaskStatus.IN_PROGRESS,
        priority=1,
        due_date=d(1),
        label_ids=[deep.id],
        comments=["Start from last quarter's retro notes."],
    )
    await add(title="Headcount request", project_id=q1.id, priority=2, due_date=d(4))
    await add(title="Offsite agenda", project_id=q1.id, due_date=d(8))
    await add(title="Collect team input", project_id=q1.id, status=TaskStatus.DONE)
    await add(
        title="1:1 with Priya",
        project_id=q1.id,
        due_date=d(0),
        due_time=time(14, 30),
        label_ids=[calls.id],
    )

    # Slate.
    await add(
        title="Natural-language parser",
        project_id=slate.id,
        status=TaskStatus.IN_PROGRESS,
        priority=1,
        label_ids=[deep.id],
    )
    await add(title="Import from Todoist", project_id=slate.id, due_date=d(7))
    await add(title="Import from Linear", project_id=slate.id, due_date=d(9))
    await add(title="MCP server", project_id=slate.id, status=TaskStatus.BACKLOG)
    await add(title="Deploy to an Amp Box", project_id=slate.id, status=TaskStatus.DONE)

    # A year-old created_at so sorting by created is visibly different.
    old = await uow.tasks.add(
        Task(
            title="Clean out the garage",
            area_id=home.id,
            status=TaskStatus.BACKLOG,
            created_at=datetime(2025, 11, 1, 12, tzinfo=UTC),
        )
    )
    await svc._log(old.id, "created", at=old.created_at)  # type: ignore[arg-type]  # noqa: SLF001
