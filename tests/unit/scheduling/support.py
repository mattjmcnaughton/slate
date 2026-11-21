"""Shared fixtures for the scheduling tests.

Every expected value in these tests was worked out by hand from the calendar
(and, for elapsed-time cases, the America/New_York DST rules), never copied
from the parser's output.

    October 2026          November 2026         December 2026
    Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su
              1  2  3  4                     1      1  2  3  4  5  6
     5  6  7  8  9 10 11   2  3  4  5  6  7  8   7  8  9 10 11 12 13
    12 13 14 15 16 17 18   9 10 11 12 13 14 15  14 15 16 17 18 19 20
    19 20 21 22 23 24 25  16 17 18 19 20 21 22  21 22 23 24 25 26 27
    26 27 28 29 30 31     23 24 25 26 27 28 29  28 29 30 31
                          30

    January 2027          February 2027         March 2027
    Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su  Mo Tu We Th Fr Sa Su
                 1  2  3   1  2  3  4  5  6  7   1  2  3  4  5  6  7
     4  5  6  7  8  9 10   8  9 10 11 12 13 14   8  9 10 11 12 13 14
    11 12 13 14 15 16 17  15 16 17 18 19 20 21  15 16 17 18 19 20 21
    18 19 20 21 22 23 24  22 23 24 25 26 27 28  22 23 24 25 26 27 28
    25 26 27 28 29 30 31                        29 30 31

DST in New York ends on Sun 2026-11-01 (02:00 EDT becomes 01:00 EST) and starts
on Sun 2027-03-14 (02:00 EST becomes 03:00 EDT). 2028 is a leap year; its
Feb 29 is a Tuesday.
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from slate.scheduling import EntityRef, ParseContext

NY = ZoneInfo("America/New_York")

NOWS = {
    "sat": datetime(2026, 11, 21, 10, 0, tzinfo=NY),  # a Saturday morning
    "sun": datetime(2026, 11, 22, 15, 0, tzinfo=NY),  # a Sunday afternoon
    "wed": datetime(2026, 11, 18, 8, 0, tzinfo=NY),  # midweek
    "nye": datetime(2026, 12, 31, 18, 0, tzinfo=NY),  # Thursday, year end
    "jan31": datetime(2027, 1, 31, 9, 0, tzinfo=NY),  # Sunday, month end
    "fall": datetime(2026, 10, 31, 23, 30, tzinfo=NY),  # Sat, night before DST ends
    "spring": datetime(2027, 3, 13, 23, 30, tzinfo=NY),  # Sat, night before DST
    "leap": datetime(2028, 2, 29, 12, 0, tzinfo=NY),  # Tuesday, leap day
}

AREAS = (EntityRef(1, "Home"), EntityRef(2, "Work"), EntityRef(3, "Garden"))
PROJECTS = (
    EntityRef(10, "Taxes"),
    EntityRef(11, "Side Projects", aliases=("side-projects",)),
    EntityRef(12, "Garden"),
)
LABELS = (EntityRef(20, "health"), EntityRef(21, "errand"))


def ctx(now: str = "sat") -> ParseContext:
    return ParseContext(now=NOWS[now], areas=AREAS, projects=PROJECTS, labels=LABELS)


def d(iso: str) -> date:
    return date.fromisoformat(iso)


def t(clock: str | None) -> time | None:
    return time.fromisoformat(clock) if clock is not None else None
