"""Recurrence math: when a repeating task is due next, and its future runs.

Rules the app relies on (decided in the v1 scope):

- FIXED: completing a run moves the task to the first occurrence strictly after
  both the current due date and today. Missed runs are skipped, not replayed.
- AFTER_COMPLETION: the next date is the completion date plus one interval.
- When the series has ended (UNTIL passed or COUNT used up), ``next_due``
  returns None and the app marks the task done for good.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from dateutil.rrule import rrulestr

from slate.scheduling.types import Recurrence, RecurrenceMode


def _rule(rec: Recurrence):
    start = datetime.combine(rec.dtstart, datetime.min.time())
    return rrulestr(rec.rrule, dtstart=start)


def _parts(rec: Recurrence) -> dict[str, str]:
    return dict(p.split("=", 1) for p in rec.rrule.split(";") if "=" in p)


def _step(rec: Recurrence, frm: date) -> date:
    parts = _parts(rec)
    n = int(parts.get("INTERVAL", "1"))
    freq = parts.get("FREQ", "DAILY")
    delta = {
        "DAILY": relativedelta(days=n),
        "WEEKLY": relativedelta(weeks=n),
        "MONTHLY": relativedelta(months=n),
        "YEARLY": relativedelta(years=n),
    }.get(freq, relativedelta(days=n))
    return frm + delta


def _within_bounds(rec: Recurrence, candidate: date, completed_runs: int) -> bool:
    parts = _parts(rec)
    if "UNTIL" in parts:
        until = datetime.strptime(parts["UNTIL"][:8], "%Y%m%d").date()
        if candidate > until:
            return False
    return not ("COUNT" in parts and completed_runs >= int(parts["COUNT"]))


def next_due(
    rec: Recurrence,
    *,
    current_due: date,
    completed_on: date,
    today: date,
    completed_runs: int = 0,
) -> date | None:
    """The due date after completing the run due on ``current_due``.

    ``completed_runs`` counts runs completed so far, including this one; it
    bounds COUNT for AFTER_COMPLETION rules.
    """
    if rec.mode is RecurrenceMode.AFTER_COMPLETION:
        candidate = _step(rec, completed_on)
        return candidate if _within_bounds(rec, candidate, completed_runs) else None
    floor = max(current_due, today)
    nxt = _rule(rec).after(datetime.combine(floor, datetime.max.time()))
    return nxt.date() if nxt else None


def occurrences(rec: Recurrence, *, start: date, end: date) -> list[date]:
    """Dates of a FIXED series in [start, end], inclusive.

    AFTER_COMPLETION series cannot be projected, so this returns [].
    """
    if rec.mode is RecurrenceMode.AFTER_COMPLETION:
        return []
    lo = datetime.combine(start, datetime.min.time())
    hi = datetime.combine(end, datetime.max.time())
    return [d.date() for d in _rule(rec).between(lo, hi, inc=True)]


def first_on_or_after(rec: Recurrence, day: date) -> date | None:
    """The first occurrence on or after ``day`` (for setting the initial due)."""
    if rec.mode is RecurrenceMode.AFTER_COMPLETION:
        return max(rec.dtstart, day)
    nxt = _rule(rec).after(datetime.combine(day, datetime.min.time()) - timedelta(seconds=1))
    return nxt.date() if nxt else None


def describe(rec: Recurrence) -> str:
    """A human description of the rule."""
    return rec.text or rec.rrule
