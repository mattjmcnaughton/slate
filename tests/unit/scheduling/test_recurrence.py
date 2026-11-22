"""Recurrence math: next_due, occurrences, first_on_or_after, describe."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from slate.scheduling import (
    Recurrence,
    RecurrenceMode,
    describe,
    first_on_or_after,
    next_due,
    occurrences,
    parse_schedule,
)

from .support import NY, ctx, d

FIXED = RecurrenceMode.FIXED
AFTER = RecurrenceMode.AFTER_COMPLETION
DAY_31 = "FREQ=MONTHLY;BYMONTHDAY=28,29,30,31;BYSETPOS=-1"
DAY_30 = "FREQ=MONTHLY;BYMONTHDAY=28,29,30;BYSETPOS=-1"
LEAP_DAY = "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=28,29;BYSETPOS=-1"


def fixed(rrule: str, dtstart: str) -> Recurrence:
    return Recurrence(rrule, FIXED, d(dtstart))


def after(rrule: str, dtstart: str = "2026-11-21") -> Recurrence:
    return Recurrence(rrule, AFTER, d(dtstart))


def complete_on_time(rec: Recurrence, due: str, runs: int) -> list[str | None]:
    """Complete each run on its due date; return the due dates that follow."""
    out: list[str | None] = []
    current = d(due)
    for _ in range(runs):
        nxt = next_due(rec, current_due=current, completed_on=current, today=current)
        out.append(nxt.isoformat() if nxt else None)
        if nxt is None:
            break
        current = nxt
    return out


# (rule, dtstart, first due, the due dates after completing each run on time)
SERIES = [
    ("FREQ=DAILY", "2026-11-21", "2026-11-21", ["2026-11-22", "2026-11-23"]),
    # Across the year boundary
    ("FREQ=DAILY", "2026-12-30", "2026-12-30", ["2026-12-31", "2027-01-01"]),
    (
        "FREQ=WEEKLY;BYDAY=TH",
        "2026-12-24",
        "2026-12-24",
        ["2026-12-31", "2027-01-07"],
    ),
    (
        "FREQ=WEEKLY;BYDAY=MO,TH",
        "2026-11-23",
        "2026-11-23",
        ["2026-11-26", "2026-11-30", "2026-12-03"],
    ),
    # Every other Friday keeps its phase from dtstart.
    (
        "FREQ=WEEKLY;INTERVAL=2;BYDAY=FR",
        "2026-11-27",
        "2026-11-27",
        ["2026-12-11", "2026-12-25", "2027-01-08"],
    ),
    # A week runs Monday to Sunday: Thu Nov 19, then Tue and Thu two weeks on.
    (
        "FREQ=WEEKLY;INTERVAL=2;BYDAY=TU,TH",
        "2026-11-19",
        "2026-11-19",
        ["2026-12-01", "2026-12-03", "2026-12-15", "2026-12-17"],
    ),
    # "every 31st" lands on the last day of shorter months.
    (
        DAY_31,
        "2027-01-31",
        "2027-01-31",
        ["2027-02-28", "2027-03-31", "2027-04-30", "2027-05-31"],
    ),
    (DAY_31, "2028-01-31", "2028-01-31", ["2028-02-29", "2028-03-31"]),
    (DAY_30, "2027-01-30", "2027-01-30", ["2027-02-28", "2027-03-30", "2027-04-30"]),
    (DAY_30, "2028-01-30", "2028-01-30", ["2028-02-29", "2028-03-30"]),
    (
        "FREQ=MONTHLY;INTERVAL=2;BYMONTHDAY=28,29,30,31;BYSETPOS=-1",
        "2026-12-31",
        "2026-12-31",
        ["2027-02-28", "2027-04-30", "2027-06-30", "2027-08-31"],
    ),
    (
        "FREQ=MONTHLY;BYMONTHDAY=15,-1",
        "2027-01-31",
        "2027-01-31",
        ["2027-02-15", "2027-02-28", "2027-03-15", "2027-03-31"],
    ),
    (
        "FREQ=MONTHLY;BYMONTHDAY=-1",
        "2027-12-31",
        "2027-12-31",
        ["2028-01-31", "2028-02-29", "2028-03-31"],
    ),
    # An explicit BYMONTHDAY=31 keeps its RFC 5545 meaning: short months skip.
    (
        "FREQ=MONTHLY;BYMONTHDAY=31",
        "2027-01-31",
        "2027-01-31",
        ["2027-03-31", "2027-05-31"],
    ),
    # A rule that leaves the day to dtstart is clamped, not skipped.
    ("FREQ=MONTHLY", "2027-01-31", "2027-01-31", ["2027-02-28", "2027-03-31"]),
    ("FREQ=MONTHLY", "2026-11-15", "2026-11-15", ["2026-12-15", "2027-01-15"]),
    ("FREQ=YEARLY", "2028-02-29", "2028-02-29", ["2029-02-28", "2030-02-28"]),
    ("FREQ=YEARLY", "2026-12-31", "2026-12-31", ["2027-12-31", "2028-12-31"]),
    # Feb 29: Feb 28 in other years, Feb 29 again in 2032.
    (
        LEAP_DAY,
        "2028-02-29",
        "2028-02-29",
        ["2029-02-28", "2030-02-28", "2031-02-28", "2032-02-29"],
    ),
    # Last Fridays: Nov 27, Dec 25, Jan 29, Feb 26.
    (
        "FREQ=MONTHLY;BYDAY=-1FR",
        "2026-11-27",
        "2026-11-27",
        ["2026-12-25", "2027-01-29", "2027-02-26"],
    ),
    # Third Wednesdays: Dec 16, Jan 20, Feb 17.
    (
        "FREQ=MONTHLY;BYDAY=3WE",
        "2026-12-16",
        "2026-12-16",
        ["2027-01-20", "2027-02-17"],
    ),
    # Fifth Fridays skip months with only four: Jan 29, then Apr 30 2027.
    ("FREQ=MONTHLY;BYDAY=5FR", "2027-01-29", "2027-01-29", ["2027-04-30"]),
    # Last workdays: Mon Nov 30, Thu Dec 31, Fri Jan 29.
    (
        "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1",
        "2026-11-30",
        "2026-11-30",
        ["2026-12-31", "2027-01-29"],
    ),
    (
        "FREQ=YEARLY;BYMONTH=1;BYMONTHDAY=1",
        "2027-01-01",
        "2027-01-01",
        ["2028-01-01", "2029-01-01"],
    ),
    # UNTIL is inclusive, and the series then ends.
    (
        "FREQ=DAILY;UNTIL=20261123",
        "2026-11-21",
        "2026-11-21",
        ["2026-11-22", "2026-11-23", None],
    ),
    # COUNT counts runs from dtstart.
    (
        "FREQ=DAILY;COUNT=3",
        "2026-11-21",
        "2026-11-21",
        ["2026-11-22", "2026-11-23", None],
    ),
    (
        "FREQ=WEEKLY;BYDAY=SA;UNTIL=20270101",
        "2026-11-21",
        "2026-11-21",
        ["2026-11-28", "2026-12-05", "2026-12-12", "2026-12-19", "2026-12-26", None],
    ),
]


@pytest.mark.parametrize(("rrule", "dtstart", "due", "following"), SERIES)
def test_fixed_series(rrule: str, dtstart: str, due: str, following: list) -> None:
    rec = fixed(rrule, dtstart)
    first = first_on_or_after(rec, d(dtstart))
    assert first == d(due)
    assert complete_on_time(rec, due, len(following)) == following


# (rule, dtstart, current due, completed on = today, next due)
LATE_AND_EARLY = [
    # Late: jump past today with no catch-up.
    ("FREQ=DAILY", "2026-11-01", "2026-11-10", "2026-11-21", "2026-11-22"),
    ("FREQ=WEEKLY;BYDAY=MO,TH", "2026-11-23", "2026-11-23", "2026-12-02", "2026-12-03"),
    # Late, and today is itself an occurrence: the next one is after today.
    ("FREQ=WEEKLY;BYDAY=MO", "2026-11-23", "2026-11-23", "2026-11-30", "2026-12-07"),
    ("FREQ=DAILY;INTERVAL=3", "2026-11-21", "2026-11-21", "2026-11-28", "2026-11-30"),
    (DAY_31, "2027-01-31", "2027-01-31", "2027-04-10", "2027-04-30"),
    (LEAP_DAY, "2028-02-29", "2028-02-29", "2031-06-01", "2032-02-29"),
    ("FREQ=MONTHLY;BYDAY=-1FR", "2026-11-27", "2026-11-27", "2026-12-25", "2027-01-29"),
    # Late past the end of the series
    ("FREQ=DAILY;UNTIL=20261130", "2026-11-21", "2026-11-25", "2026-11-30", None),
    (
        "FREQ=DAILY;UNTIL=20261130",
        "2026-11-21",
        "2026-11-25",
        "2026-11-29",
        "2026-11-30",
    ),
    # Skipped runs use up a fixed rule's COUNT: runs are Nov 21 to 25.
    ("FREQ=DAILY;COUNT=5", "2026-11-21", "2026-11-21", "2026-11-24", "2026-11-25"),
    ("FREQ=DAILY;COUNT=5", "2026-11-21", "2026-11-21", "2026-11-25", None),
    # Early: the next run is after the one just completed, not the same one.
    ("FREQ=WEEKLY;BYDAY=FR", "2026-11-27", "2026-11-27", "2026-11-25", "2026-12-04"),
    ("FREQ=DAILY", "2026-11-21", "2026-11-30", "2026-11-21", "2026-12-01"),
    # A run moved off the schedule by hand (due Wed) returns to the schedule.
    ("FREQ=WEEKLY;BYDAY=MO", "2026-11-23", "2026-11-25", "2026-11-25", "2026-11-30"),
]


@pytest.mark.parametrize(("rrule", "dtstart", "current", "today", "expected"), LATE_AND_EARLY)
def test_fixed_next_due_is_after_both_the_old_due_date_and_today(
    rrule: str, dtstart: str, current: str, today: str, expected: str | None
) -> None:
    got = next_due(
        fixed(rrule, dtstart),
        current_due=d(current),
        completed_on=d(today),
        today=d(today),
    )
    assert got == (d(expected) if expected else None)


# (rule, completed on, completed runs, next due)
AFTER_COMPLETION = [
    ("FREQ=DAILY", "2026-11-21", 1, "2026-11-22"),
    ("FREQ=DAILY;INTERVAL=3", "2026-11-25", 1, "2026-11-28"),
    ("FREQ=DAILY;INTERVAL=3", "2026-12-30", 1, "2027-01-02"),
    ("FREQ=WEEKLY;INTERVAL=2", "2026-11-21", 1, "2026-12-05"),
    ("FREQ=MONTHLY", "2026-11-21", 1, "2026-12-21"),
    ("FREQ=MONTHLY", "2027-01-31", 1, "2027-02-28"),
    ("FREQ=MONTHLY;INTERVAL=3", "2026-11-30", 1, "2027-02-28"),
    ("FREQ=YEARLY", "2028-02-29", 1, "2029-02-28"),
    ("FREQ=YEARLY", "2026-12-31", 1, "2027-12-31"),
    # UNTIL is inclusive.
    ("FREQ=DAILY;INTERVAL=3;UNTIL=20261125", "2026-11-22", 1, "2026-11-25"),
    ("FREQ=DAILY;INTERVAL=3;UNTIL=20261125", "2026-11-23", 1, None),
    # COUNT is the number of completed runs.
    ("FREQ=DAILY;COUNT=2", "2026-11-21", 1, "2026-11-22"),
    ("FREQ=DAILY;COUNT=2", "2026-11-22", 2, None),
]


@pytest.mark.parametrize(("rrule", "done", "runs", "expected"), AFTER_COMPLETION)
def test_after_completion_counts_from_the_completion_date(
    rrule: str, done: str, runs: int, expected: str | None
) -> None:
    got = next_due(
        after(rrule),
        # The old due date does not matter, early or late.
        current_due=d("2026-11-21"),
        completed_on=d(done),
        today=d(done),
        completed_runs=runs,
    )
    assert got == (d(expected) if expected else None)


def test_occurrences_are_inclusive_and_bounded() -> None:
    rec = fixed("FREQ=WEEKLY;BYDAY=MO,TH", "2026-11-23")
    mon_thu = [d("2026-11-23"), d("2026-11-26"), d("2026-11-30"), d("2026-12-03")]
    assert occurrences(rec, start=d("2026-11-21"), end=d("2026-12-06")) == mon_thu
    assert occurrences(rec, start=d("2026-11-23"), end=d("2026-12-03")) == mon_thu
    assert occurrences(rec, start=d("2026-11-24"), end=d("2026-11-25")) == []
    assert occurrences(rec, start=d("2026-11-26"), end=d("2026-11-26")) == [d("2026-11-26")]
    # Nothing before dtstart, and nothing for an inverted range.
    assert occurrences(rec, start=d("2026-11-01"), end=d("2026-11-22")) == []
    assert occurrences(rec, start=d("2026-12-06"), end=d("2026-11-21")) == []


def test_occurrences_stop_at_until_and_count() -> None:
    until = fixed("FREQ=DAILY;UNTIL=20261123", "2026-11-21")
    count = fixed("FREQ=DAILY;COUNT=3", "2026-11-21")
    three = [d("2026-11-21"), d("2026-11-22"), d("2026-11-23")]
    assert occurrences(until, start=d("2026-11-01"), end=d("2026-12-31")) == three
    assert occurrences(count, start=d("2026-11-01"), end=d("2026-12-31")) == three
    assert occurrences(count, start=d("2026-11-23"), end=d("2026-12-31")) == three[2:]


def test_occurrences_project_fixed_rules_only() -> None:
    rec = after("FREQ=DAILY;INTERVAL=3")
    assert occurrences(rec, start=d("2026-11-21"), end=d("2026-12-21")) == []


def test_occurrences_across_month_ends_and_the_year_boundary() -> None:
    rec = fixed(DAY_31, "2026-10-31")
    assert occurrences(rec, start=d("2026-10-31"), end=d("2027-03-31")) == [
        d("2026-10-31"),
        d("2026-11-30"),
        d("2026-12-31"),
        d("2027-01-31"),
        d("2027-02-28"),
        d("2027-03-31"),
    ]


def test_first_on_or_after() -> None:
    weekly = fixed("FREQ=WEEKLY;BYDAY=MO", "2026-11-23")
    assert first_on_or_after(weekly, d("2026-11-01")) == d("2026-11-23")
    assert first_on_or_after(weekly, d("2026-11-23")) == d("2026-11-23")
    assert first_on_or_after(weekly, d("2026-11-24")) == d("2026-11-30")
    ended = fixed("FREQ=DAILY;UNTIL=20261123", "2026-11-21")
    assert first_on_or_after(ended, d("2026-11-23")) == d("2026-11-23")
    assert first_on_or_after(ended, d("2026-11-24")) is None
    floating = after("FREQ=DAILY;INTERVAL=3;UNTIL=20261130", "2026-11-21")
    assert first_on_or_after(floating, d("2026-11-01")) == d("2026-11-21")
    assert first_on_or_after(floating, d("2026-11-25")) == d("2026-11-25")
    assert first_on_or_after(floating, d("2026-12-01")) is None


def test_until_with_a_time_or_zone_suffix_is_read_as_a_date() -> None:
    for until in ("20261123T000000Z", "20261123T235959"):
        rec = fixed(f"FREQ=DAILY;UNTIL={until}", "2026-11-21")
        assert complete_on_time(rec, "2026-11-22", 2) == ["2026-11-23", None]


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _month_index(day: date) -> int:
    return day.year * 12 + day.month


def _last_day(day: date) -> bool:
    return (day + timedelta(days=1)).month != day.month


# Old series, each with its own definition of "is this day a run?", so a wrong
# shortcut through years of history shows up as a different list.
OLD_SERIES = [
    (
        "FREQ=DAILY;INTERVAL=3",
        date(2015, 1, 6),
        lambda day, start: (day - start).days % 3 == 0,
    ),
    (
        "FREQ=WEEKLY;INTERVAL=2;BYDAY=TU,TH",
        date(2015, 1, 8),  # a Thursday
        lambda day, start: (
            day.weekday() in (1, 3) and (_week_start(day) - _week_start(start)).days % 14 == 0
        ),
    ),
    (
        "FREQ=WEEKLY;INTERVAL=3",
        date(2015, 1, 9),  # a Friday
        lambda day, start: (day - start).days % 21 == 0,
    ),
    (DAY_31, date(2015, 1, 31), lambda day, start: _last_day(day)),
    (
        # Day left to dtstart: the 30th, or the last day of February.
        "FREQ=MONTHLY",
        date(2015, 1, 30),
        lambda day, start: day.day == 30 or (day.month == 2 and _last_day(day)),
    ),
    (
        "FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=15",
        date(2015, 2, 15),
        lambda day, start: day.day == 15 and (_month_index(day) - _month_index(start)) % 3 == 0,
    ),
    (
        "FREQ=MONTHLY;INTERVAL=2;BYDAY=-1FR",
        date(2015, 1, 30),
        lambda day, start: (
            day.weekday() == 4
            and (day + timedelta(days=7)).month != day.month
            and (_month_index(day) - _month_index(start)) % 2 == 0
        ),
    ),
    (
        LEAP_DAY,
        date(2016, 2, 29),
        lambda day, start: day.month == 2 and _last_day(day),
    ),
    (
        "FREQ=YEARLY;INTERVAL=2",
        date(2016, 2, 29),
        lambda day, start: day.month == 2 and _last_day(day) and (day.year - start.year) % 2 == 0,
    ),
    (
        # The day (29) comes from dtstart, the month from the rule.
        "FREQ=YEARLY;BYMONTH=3",
        date(2016, 2, 29),
        lambda day, start: (day.month, day.day) == (3, 29),
    ),
    (
        "FREQ=YEARLY;INTERVAL=3;BYMONTH=12;BYMONTHDAY=31",
        date(2015, 12, 31),
        lambda day, start: (day.month, day.day) == (12, 31) and (day.year - start.year) % 3 == 0,
    ),
]


@pytest.mark.parametrize(("rrule", "dtstart", "is_run"), OLD_SERIES)
def test_old_series_keep_their_phase(rrule: str, dtstart: date, is_run) -> None:
    rec = Recurrence(rrule, FIXED, dtstart)
    lo, hi = date(2026, 10, 1), date(2032, 3, 31)
    days = [lo + timedelta(days=n) for n in range((hi - lo).days + 1)]
    expected = [day for day in days if is_run(day, dtstart)]
    assert expected
    assert occurrences(rec, start=lo, end=hi) == expected
    assert first_on_or_after(rec, lo) == expected[0]
    for current, following in list(zip(expected, expected[1:], strict=False))[:5]:
        got = next_due(rec, current_due=current, completed_on=current, today=current)
        assert got == following


@pytest.mark.parametrize(
    ("now", "run", "following"),
    [
        # Clocks go back on Nov 1 2026 and forward on Mar 14 2027.
        ("fall", "2026-10-31", ["2026-11-01", "2026-11-02"]),
        ("spring", "2027-03-13", ["2027-03-14", "2027-03-15"]),
    ],
)
def test_a_daily_7am_stays_at_7am_across_a_dst_change(
    now: str, run: str, following: list[str]
) -> None:
    result = parse_schedule("every day at 7am", ctx(now))
    rec = result.recurrence
    assert rec is not None
    assert result.due is not None
    assert (result.due.date, result.due.time) == (d(run), time(7))
    assert complete_on_time(rec, run, 2) == following
    assert occurrences(rec, start=d(run), end=d(following[-1])) == [
        d(run),
        *(d(day) for day in following),
    ]
    assert rec.time == time(7)
    # The wall clock holds at 07:00 while the UTC offset moves by an hour.
    moments = [datetime.combine(d(day), time(7), NY) for day in (run, following[-1])]
    assert [moment.hour for moment in moments] == [7, 7]
    offsets = [moment.utcoffset() for moment in moments]
    assert offsets[0] != offsets[1]
    assert moments[1] - moments[0] == timedelta(days=2)  # wall-clock days


# (rule, mode, time, description)
DESCRIPTIONS = [
    ("FREQ=DAILY", FIXED, None, "every day"),
    ("FREQ=WEEKLY", FIXED, None, "every week"),
    ("FREQ=WEEKLY;INTERVAL=2", FIXED, None, "every 2 weeks"),
    ("FREQ=WEEKLY;BYDAY=MO,TH", FIXED, time(7), "every Mon, Thu at 7am"),
    (
        "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
        FIXED,
        time(17, 30),
        "every weekday at 5:30pm",
    ),
    (
        "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,TU,WE,TH,FR",
        FIXED,
        None,
        "every 2 weeks on Mon, Tue, Wed, Thu, Fri",
    ),
    ("FREQ=MONTHLY;BYMONTHDAY=-1", FIXED, None, "every last day"),
    ("FREQ=MONTHLY;BYMONTHDAY=1,15", FIXED, None, "every 1st, 15th"),
    ("FREQ=MONTHLY;BYMONTHDAY=22", FIXED, None, "every 22nd"),
    ("FREQ=MONTHLY;BYMONTHDAY=23", FIXED, None, "every 23rd"),
    ("FREQ=MONTHLY;BYMONTHDAY=11", FIXED, None, "every 11th"),
    (DAY_31, FIXED, None, "every 31st"),
    (DAY_30, FIXED, None, "every 30th"),
    ("FREQ=MONTHLY;BYDAY=-1FR", FIXED, None, "every last Fri"),
    ("FREQ=MONTHLY;BYDAY=+2TU", FIXED, None, "every 2nd Tue"),
    ("FREQ=MONTHLY;INTERVAL=3;BYDAY=1MO", FIXED, None, "every 3 months on the 1st Mon"),
    ("FREQ=YEARLY;BYMONTH=1;BYMONTHDAY=1", FIXED, None, "every Jan 1"),
    (LEAP_DAY, FIXED, None, "every Feb 29"),
    (
        "FREQ=DAILY;UNTIL=20270630",
        FIXED,
        time(0),
        "every day at 12am until Jun 30, 2027",
    ),
    ("FREQ=DAILY;COUNT=10", FIXED, None, "every day for 10 times"),
    ("RRULE:freq=daily;interval=2", FIXED, None, "every 2 days"),
    ("FREQ=DAILY;INTERVAL=3", AFTER, None, "every! 3 days"),
    ("FREQ=MONTHLY", AFTER, time(9), "every! month at 9am"),
    # No words for these: the rule itself is shown.
    ("FREQ=HOURLY", FIXED, None, "FREQ=HOURLY"),
    ("FREQ=MONTHLY;BYDAY=MO", FIXED, None, "FREQ=MONTHLY;BYDAY=MO"),
    ("FREQ=YEARLY;BYWEEKNO=20", FIXED, None, "FREQ=YEARLY;BYWEEKNO=20"),
    ("nonsense", FIXED, None, "nonsense"),
]


@pytest.mark.parametrize(("rrule", "mode", "at", "expected"), DESCRIPTIONS)
def test_describe_without_text(
    rrule: str, mode: RecurrenceMode, at: time | None, expected: str
) -> None:
    rec = Recurrence(rrule, mode, d("2026-11-21"), at)
    assert describe(rec) == expected


def test_describe_prefers_the_stored_text() -> None:
    rec = Recurrence("FREQ=DAILY", FIXED, d("2026-11-21"), text="every day, forever")
    assert describe(rec) == "every day, forever"
