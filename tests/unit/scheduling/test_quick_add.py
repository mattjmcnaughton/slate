"""parse_quick_add: tokens mixed anywhere in a line of free text.

All lines are parsed on Saturday 2026-11-21 at 10:00. The context has areas
Home (1), Work (2), Garden (3); projects Taxes (10), Side Projects (11),
Garden (12); labels health (20), errand (21). Token offsets were counted by
hand.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from slate.scheduling import (
    Due,
    RecurrenceMode,
    Token,
    TokenKind,
    parse_quick_add,
)

from .support import ctx, d, t

DATE = TokenKind.DATE
RECURRENCE = TokenKind.RECURRENCE
PROJECT = TokenKind.PROJECT
LABEL = TokenKind.LABEL
PRIORITY = TokenKind.PRIORITY
STATUS = TokenKind.STATUS
FIXED = RecurrenceMode.FIXED
AFTER = RecurrenceMode.AFTER_COMPLETION


@dataclass(frozen=True)
class Case:
    line: str
    title: str
    tokens: tuple[Token, ...] = ()
    due: Due | None = None
    rrule: str | None = None
    mode: RecurrenceMode | None = None
    area_id: int | None = None
    project_id: int | None = None
    unknown_project: str | None = None
    label_ids: tuple[int, ...] = ()
    unknown_labels: tuple[str, ...] = ()
    priority: int | None = None
    status: str | None = None


def due(day: str, at: str | None = None) -> Due:
    return Due(d(day), t(at))


CASES = [
    # The examples from the brief
    Case(
        "Pay rent every 1st #home p1",
        "Pay rent",
        (
            Token(RECURRENCE, 9, 18, "every 1st"),
            Token(PROJECT, 19, 24, "#home"),
            Token(PRIORITY, 25, 27, "p1"),
        ),
        due("2026-12-01"),
        "FREQ=MONTHLY;BYMONTHDAY=1",
        FIXED,
        area_id=1,
        priority=1,
    ),
    Case(
        "Stretch every weekday 7am @health",
        "Stretch",
        (
            Token(RECURRENCE, 8, 25, "every weekday 7am"),
            Token(LABEL, 26, 33, "@health"),
        ),
        due("2026-11-23", "07:00"),
        "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
        FIXED,
        label_ids=(20,),
    ),
    Case(
        "Call mom tomorrow 6pm /doing",
        "Call mom",
        (Token(DATE, 9, 21, "tomorrow 6pm"), Token(STATUS, 22, 28, "/doing")),
        due("2026-11-22", "18:00"),
        status="in_progress",
    ),
    # Numbers and words in a title that are not scheduling
    Case("Read 1984", "Read 1984"),
    Case(
        "Read 1984 tomorrow",
        "Read 1984",
        (Token(DATE, 10, 18, "tomorrow"),),
        due("2026-11-22"),
    ),
    Case("Buy 3 apples and 12 eggs", "Buy 3 apples and 12 eggs"),
    Case("Watch 2001: A Space Odyssey", "Watch 2001: A Space Odyssey"),
    Case("Call 555-1234", "Call 555-1234"),
    Case("Upgrade to Python 3.14", "Upgrade to Python 3.14"),
    Case("Chapter 3:16 notes", "Chapter 3:16 notes"),
    Case("Meet at 5", "Meet at 5"),
    Case("Finish 3rd draft", "Finish 3rd draft"),
    Case("Thank every volunteer", "Thank every volunteer"),
    Case("Write weekly report", "Write weekly report"),
    Case("Daily standup notes", "Daily standup notes"),
    Case("Relax in the sun", "Relax in the sun"),
    Case("Buy sun cream", "Buy sun cream"),
    Case("Lunch 12/3 with Bob", "Lunch 12/3 with Bob"),
    Case("Rest after 2 weeks of travel", "Rest after 2 weeks of travel"),
    Case("Order today-ish", "Order today-ish"),
    Case("Plan tomorrow's menu", "Plan tomorrow's menu"),
    Case("Email a@b.com about /usr/bin p5", "Email a@b.com about /usr/bin p5"),
    # The same words count at the end of the line
    Case(
        "Review notes weekly",
        "Review notes",
        (Token(RECURRENCE, 13, 19, "weekly"),),
        due("2026-11-21"),
        "FREQ=WEEKLY;BYDAY=SA",
        FIXED,
    ),
    Case(
        "Buy milk sun",
        "Buy milk",
        (Token(DATE, 9, 12, "sun"),),
        due("2026-11-22"),
    ),
    Case(
        "Lunch with Bob 12/3",
        "Lunch with Bob",
        (Token(DATE, 15, 19, "12/3"),),
        due("2026-12-03"),
    ),
    Case(
        "Follow up after 2 weeks",
        "Follow up",
        (Token(RECURRENCE, 10, 23, "after 2 weeks"),),
        due("2026-11-21"),
        "FREQ=WEEKLY;INTERVAL=2",
        AFTER,
    ),
    # ... including before trailing sigils
    Case(
        "Pay bills monthly p2",
        "Pay bills",
        (Token(RECURRENCE, 10, 17, "monthly"), Token(PRIORITY, 18, 20, "p2")),
        due("2026-11-21"),
        "FREQ=MONTHLY;BYMONTHDAY=21",
        FIXED,
        priority=2,
    ),
    # ... or when a preposition makes the intent clear
    Case(
        "Meet Sam on fri for lunch",
        "Meet Sam for lunch",
        (Token(DATE, 9, 15, "on fri"),),
        due("2026-11-27"),
    ),
    Case(
        "Rent due the 1st",
        "Rent",
        (Token(DATE, 5, 16, "due the 1st"),),
        due("2026-12-01"),
    ),
    # Several candidates: the end of the line wins and the rest stays
    Case(
        "Plan Monday meeting every Friday",
        "Plan Monday meeting",
        (Token(RECURRENCE, 20, 32, "every Friday"),),
        due("2026-11-27"),
        "FREQ=WEEKLY;BYDAY=FR",
        FIXED,
    ),
    Case(
        "Email Dec 3 report tomorrow",
        "Email Dec 3 report",
        (Token(DATE, 19, 27, "tomorrow"),),
        due("2026-11-22"),
    ),
    Case(
        "Email every Monday report tomorrow 5pm",
        "Email every Monday report",
        (Token(DATE, 26, 38, "tomorrow 5pm"),),
        due("2026-11-22", "17:00"),
    ),
    # ... then the start of the line
    Case(
        "Tomorrow buy tickets for Friday show",
        "buy tickets for Friday show",
        (Token(DATE, 0, 8, "Tomorrow"),),
        due("2026-11-22"),
    ),
    Case(
        "Every morning take vitamins",
        "take vitamins",
        (Token(RECURRENCE, 0, 13, "Every morning"),),
        due("2026-11-21", "09:00"),
        "FREQ=DAILY",
        FIXED,
    ),
    # A time and a date written apart are combined
    Case(
        "Standup 9am with the team tomorrow",
        "Standup with the team",
        (Token(DATE, 8, 11, "9am"), Token(DATE, 26, 34, "tomorrow")),
        due("2026-11-22", "09:00"),
    ),
    Case(
        "Stretch every weekday @health 7am",
        "Stretch",
        (
            Token(RECURRENCE, 8, 21, "every weekday"),
            Token(LABEL, 22, 29, "@health"),
            Token(DATE, 30, 33, "7am"),
        ),
        due("2026-11-23", "07:00"),
        "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
        FIXED,
        label_ids=(20,),
    ),
    # Longer phrases
    Case(
        "Water plants every 3 days starting tomorrow at 9am #home",
        "Water plants",
        (
            Token(RECURRENCE, 13, 50, "every 3 days starting tomorrow at 9am"),
            Token(PROJECT, 51, 56, "#home"),
        ),
        due("2026-11-22", "09:00"),
        "FREQ=DAILY;INTERVAL=3",
        FIXED,
        area_id=1,
    ),
    Case(
        "Take out trash every Mon, Thu at 7pm",
        "Take out trash",
        (Token(RECURRENCE, 15, 36, "every Mon, Thu at 7pm"),),
        due("2026-11-23", "19:00"),
        "FREQ=WEEKLY;BYDAY=MO,TH",
        FIXED,
    ),
    Case(
        "Vacuum every! 3 days",
        "Vacuum",
        (Token(RECURRENCE, 7, 20, "every! 3 days"),),
        due("2026-11-21"),
        "FREQ=DAILY;INTERVAL=3",
        AFTER,
    ),
    Case(
        "Dentist Dec 3 at 2:30pm",
        "Dentist",
        (Token(DATE, 8, 23, "Dec 3 at 2:30pm"),),
        due("2026-12-03", "14:30"),
    ),
    Case(
        "Renew passport in 2 weeks p3 @errand",
        "Renew passport",
        (
            Token(DATE, 15, 25, "in 2 weeks"),
            Token(PRIORITY, 26, 28, "p3"),
            Token(LABEL, 29, 36, "@errand"),
        ),
        due("2026-12-05"),
        label_ids=(21,),
        priority=3,
    ),
    # A phrase stops where other text is attached to it
    Case(
        "Meeting tomorrow 5pm-6pm",
        "Meeting 5pm-6pm",
        (Token(DATE, 8, 16, "tomorrow"),),
        due("2026-11-22"),
    ),
    # Punctuation after a removed token closes up
    Case(
        "Call mom tomorrow.",
        "Call mom.",
        (Token(DATE, 9, 17, "tomorrow"),),
        due("2026-11-22"),
    ),
    Case(
        "Tomorrow, call mom",
        "call mom",
        (Token(DATE, 0, 8, "Tomorrow"),),
        due("2026-11-22"),
    ),
    Case("tomorrow", "", (Token(DATE, 0, 8, "tomorrow"),), due("2026-11-22")),
    # Offsets count characters (code points), not bytes or UTF-16 units
    Case(
        "Party 🎉 tomorrow 8pm",
        "Party 🎉",
        (Token(DATE, 8, 20, "tomorrow 8pm"),),
        due("2026-11-22", "20:00"),
    ),
    # Sigils
    Case(
        "P2 Draft memo MONDAY",
        "Draft memo",
        (Token(PRIORITY, 0, 2, "P2"), Token(DATE, 14, 20, "MONDAY")),
        due("2026-11-23"),
        priority=2,
    ),
    Case("Tidy desk p4", "Tidy desk", (Token(PRIORITY, 10, 12, "p4"),), priority=0),
    # An unknown #name is offered for creation; "#123" is left alone.
    Case(
        "Fix #123 today #nope @new p4",
        "Fix #123",
        (
            Token(DATE, 9, 14, "today"),
            Token(PROJECT, 15, 20, "#nope", unresolved=True),
            Token(LABEL, 21, 25, "@new", unresolved=True),
            Token(PRIORITY, 26, 28, "p4"),
        ),
        due("2026-11-21"),
        unknown_project="nope",
        unknown_labels=("new",),
        priority=0,
    ),
    # "Garden" is both an area and a project: the project wins.
    Case(
        "#garden plant bulbs sat",
        "plant bulbs",
        (Token(PROJECT, 0, 7, "#garden"), Token(DATE, 20, 23, "sat")),
        due("2026-11-28"),
        project_id=12,
    ),
    # A project and an area can both be named.
    Case(
        "File return #taxes #work p2 by Dec 3",
        "File return",
        (
            Token(PROJECT, 12, 18, "#taxes"),
            Token(PROJECT, 19, 24, "#work"),
            Token(PRIORITY, 25, 27, "p2"),
            Token(DATE, 28, 36, "by Dec 3"),
        ),
        due("2026-12-03"),
        area_id=2,
        project_id=10,
        priority=2,
    ),
    # Names match loosely: case, spaces, and dashes are ignored.
    Case(
        "Ship it #side-projects /done",
        "Ship it",
        (Token(PROJECT, 8, 22, "#side-projects"), Token(STATUS, 23, 28, "/done")),
        project_id=11,
        status="done",
    ),
    Case(
        "Ship it #SideProjects",
        "Ship it",
        (Token(PROJECT, 8, 21, "#SideProjects"),),
        project_id=11,
    ),
    # Only known status words are statuses.
    Case(
        "Check /etc/hosts /todo",
        "Check /etc/hosts",
        (Token(STATUS, 17, 22, "/todo"),),
        status="todo",
    ),
    Case("Open /later", "Open /later"),
    # A repeated label is one label with two tokens.
    Case(
        "Run @health 5k @health",
        "Run 5k",
        (Token(LABEL, 4, 11, "@health"), Token(LABEL, 15, 22, "@health")),
        label_ids=(20,),
    ),
    Case(
        "Buy stamps @errand, then mail #home.",
        "Buy stamps, then mail.",
        (Token(LABEL, 11, 18, "@errand"), Token(PROJECT, 30, 35, "#home")),
        area_id=1,
        label_ids=(21,),
    ),
]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.line)
def test_quick_add(case: Case) -> None:
    result = parse_quick_add(case.line, ctx("sat"))
    assert result.title == case.title
    assert result.tokens == case.tokens
    assert result.due == case.due
    rec = result.recurrence
    assert (rec.rrule if rec else None, rec.mode if rec else None) == (
        case.rrule,
        case.mode,
    )
    assert (result.area_id, result.project_id) == (case.area_id, case.project_id)
    assert result.unknown_project == case.unknown_project
    assert (result.label_ids, result.unknown_labels) == (
        case.label_ids,
        case.unknown_labels,
    )
    assert (result.priority, result.status) == (case.priority, case.status)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.line)
def test_expected_offsets_point_at_the_token_text(case: Case) -> None:
    """Guards the hand-counted offsets in CASES themselves."""
    for token in case.tokens:
        assert case.line[token.start : token.end] == token.text


def test_recurrence_carries_time_start_and_text() -> None:
    result = parse_quick_add("Water plants every 3 days starting tomorrow at 9am #home", ctx("sat"))
    rec = result.recurrence
    assert rec is not None
    assert (rec.dtstart, rec.time, rec.text) == (
        d("2026-11-22"),
        t("09:00"),
        "every 3 days at 9am",
    )


def test_a_time_alone_rolls_to_tomorrow_once_it_has_passed() -> None:
    # 10:00 on Saturday: 9am has passed, 5pm has not.
    assert parse_quick_add("Standup 9am", ctx("sat")).due == due("2026-11-22", "09:00")
    assert parse_quick_add("Standup 5pm", ctx("sat")).due == due("2026-11-21", "17:00")


def test_empty_line() -> None:
    result = parse_quick_add("   ", ctx("sat"))
    assert (result.title, result.tokens, result.due) == ("", (), None)
