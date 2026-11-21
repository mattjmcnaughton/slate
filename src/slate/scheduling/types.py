"""Value types shared by the parser, the recurrence engine, and the app."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import StrEnum


class RecurrenceMode(StrEnum):
    # The schedule is fixed to the calendar: "every Monday".
    FIXED = "fixed"
    # The next date counts from the day the task is completed: "every! 3 days".
    AFTER_COMPLETION = "after_completion"


@dataclass(frozen=True)
class Recurrence:
    """A repeat rule.

    ``rrule`` is an RFC 5545 RRULE value without the ``RRULE:`` prefix, such as
    ``FREQ=WEEKLY;BYDAY=MO,TH`` or ``FREQ=MONTHLY;BYMONTHDAY=-1``. It may carry
    ``INTERVAL``, ``UNTIL`` (a date, ``YYYYMMDD``), and ``COUNT``. ``dtstart`` is
    the first date the series may land on. In AFTER_COMPLETION mode only FREQ and
    INTERVAL are meaningful for spacing; UNTIL and COUNT still bound the series.

    ``time`` is a local wall-clock time in the user's time zone, or None for an
    all-day task. ``text`` is the normalized human description, such as
    "every Mon, Thu at 7am".
    """

    rrule: str
    mode: RecurrenceMode
    dtstart: date
    time: time | None = None
    text: str = ""


@dataclass(frozen=True)
class Due:
    """A due date with an optional local time. No time zone: dates are local."""

    date: date
    time: time | None = None


class TokenKind(StrEnum):
    DATE = "date"  # a one-off date or time: "tomorrow 5pm"
    RECURRENCE = "recurrence"  # "every weekday 7am"
    PROJECT = "project"  # "#home" (resolved to an area or a project)
    LABEL = "label"  # "@errand"
    PRIORITY = "priority"  # "p1"
    STATUS = "status"  # "/doing"


@dataclass(frozen=True)
class Token:
    """A span of the input that the parser consumed, for live highlighting."""

    kind: TokenKind
    start: int  # character offset, inclusive
    end: int  # character offset, exclusive
    text: str  # the raw substring
    # Set when the token names something that does not exist, such as an
    # unknown "#name"; the UI offers to create it.
    unresolved: bool = False


@dataclass(frozen=True)
class EntityRef:
    """An area, project, or label the parser may resolve "#name" / "@name" to."""

    id: int
    name: str
    # Extra names that also match, such as a slug ("side-projects").
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParseContext:
    """Everything the parser needs besides the text.

    ``now`` must be timezone-aware and already in the user's time zone; the
    parser reads ``now.date()`` as "today".
    """

    now: datetime
    areas: tuple[EntityRef, ...] = ()
    projects: tuple[EntityRef, ...] = ()
    labels: tuple[EntityRef, ...] = ()


@dataclass(frozen=True)
class ScheduleResult:
    """The result of parsing a date or schedule phrase on its own.

    Exactly one of ``due`` (a one-off) or ``recurrence`` is set on success. For
    a recurrence, ``due`` is also set to its first occurrence on or after today.
    ``error`` is a short human message when the text could not be understood.
    """

    due: Due | None = None
    recurrence: Recurrence | None = None
    error: str | None = None


@dataclass(frozen=True)
class QuickAddResult:
    """The result of parsing a quick-add line such as "Pay rent every 1st #home p1".

    ``title`` is the input with every consumed token removed and whitespace
    collapsed. ``priority`` uses the app's scale: 0 none, 1 urgent, 2 high,
    3 medium, 4 low. ``p1``..``p3`` map to 1..3 and ``p4`` maps to 0, as in
    Todoist; "low" has no shortcut. ``status`` is one of the task status values
    ("backlog", "todo", "in_progress", "done", "canceled") or None.
    ``unknown_project`` holds the name from an unresolved "#name".
    """

    title: str
    due: Due | None = None
    recurrence: Recurrence | None = None
    area_id: int | None = None
    project_id: int | None = None
    unknown_project: str | None = None
    label_ids: tuple[int, ...] = ()
    unknown_labels: tuple[str, ...] = ()
    priority: int | None = None
    status: str | None = None
    tokens: tuple[Token, ...] = field(default_factory=tuple)
