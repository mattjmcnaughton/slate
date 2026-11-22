"""Recurrence math: when a repeating task is due next, and its future runs.

Rules the app relies on (decided in the v1 scope):

- FIXED: completing a run moves the task to the first occurrence strictly after
  both the current due date and today. Missed runs are skipped, not replayed.
- AFTER_COMPLETION: the next date is the completion date plus one interval.
- When the series has ended (UNTIL passed or COUNT used up), ``next_due``
  returns None and the app marks the task done for good.

Everything here works on local calendar dates. A rule's wall-clock time is
stored beside it and never enters the math, so a DST change cannot shift it.

Month ends: the parser writes "every 31st" as the standard RRULE
``BYMONTHDAY=28,29,30,31;BYSETPOS=-1`` (the last of those days that exists), so
it lands on the last day of shorter months. An explicit ``BYMONTHDAY=31`` keeps
its RFC 5545 meaning and skips them. A rule that leaves the day to DTSTART
(``FREQ=MONTHLY`` from the 31st, ``FREQ=YEARLY`` from Feb 29) is read the
clamped way, because RFC 5545 would silently skip those months and years.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING

from dateutil.relativedelta import relativedelta
from dateutil.rrule import rrulestr

from slate.scheduling.types import RecurrenceMode

if TYPE_CHECKING:
    from collections.abc import Iterable

    from slate.scheduling.types import Recurrence

WEEKDAY_CODES = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
WORKDAY_CODES = WEEKDAY_CODES[:5]
MONTH_NAMES = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

_WEEKDAY_NAMES = dict(
    zip(WEEKDAY_CODES, ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"), strict=True)
)
_UNIT_NAMES = {"DAILY": "day", "WEEKLY": "week", "MONTHLY": "month", "YEARLY": "year"}
# BY* parts that pick the day within a period; without one, DTSTART picks it.
_DAY_RULES = ("BYMONTHDAY", "BYDAY", "BYYEARDAY", "BYWEEKNO", "BYSETPOS")
_BY_RULES = ("BYMONTH", "BYMONTHDAY", "BYDAY", "BYSETPOS")
# Rules made only of these parts can be projected from a later DTSTART.
_SKIPPABLE = frozenset({"FREQ", "INTERVAL", "UNTIL", "WKST", *_BY_RULES})
_DESCRIBABLE = frozenset({"FREQ", "INTERVAL", "UNTIL", "COUNT", *_BY_RULES})
_NTH_WEEKDAY = re.compile(r"\+?(-1|[1-5])(MO|TU|WE|TH|FR|SA|SU)")


def _parts(rrule: str) -> dict[str, str]:
    body = rrule.strip()
    if body[:6].upper() == "RRULE:":
        body = body[6:]
    parts: dict[str, str] = {}
    for item in body.split(";"):
        key, sep, value = item.partition("=")
        if sep:
            parts[key.strip().upper()] = value.strip().upper()
    return parts


def _interval(parts: dict[str, str]) -> int:
    return max(1, int(parts.get("INTERVAL", "1")))


def _until(parts: dict[str, str]) -> date | None:
    if "UNTIL" not in parts:
        return None
    return datetime.strptime(parts["UNTIL"][:8], "%Y%m%d").date()


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time.min)


def month_day_fields(days: Iterable[int]) -> tuple[tuple[int, ...], int | None]:
    """BYMONTHDAY and BYSETPOS for days of the month, clamped to short months.

    One day past the 28th becomes "the last of 28..day that exists". In a list,
    only the 31st can be clamped (as -1, the last day); a 29th or 30th in a
    list is skipped in a February that lacks it.
    """
    unique = set(days)
    if len(unique) == 1:
        (day,) = unique
        if day > 28:
            return tuple(range(28, day + 1)), -1
        return (day,), None
    if 31 in unique:
        unique = (unique - {31}) | {-1}
    return tuple(sorted(unique, key=lambda d: (d < 0, d))), None


def year_day_fields(month: int, day: int) -> tuple[tuple[int, ...], int | None]:
    """BYMONTHDAY and BYSETPOS for a day of the year; Feb 29 falls on Feb 28
    in a year without one."""
    if (month, day) == (2, 29):
        return (28, 29), -1
    return (day,), None


def _explicit(rec: Recurrence) -> dict[str, str]:
    """The rule's parts with a date-only UNTIL and no fragile implicit day."""
    parts = _parts(rec.rrule)
    if "UNTIL" in parts:
        parts["UNTIL"] = parts["UNTIL"][:8]
    start = rec.dtstart
    if any(key in parts for key in _DAY_RULES):
        return parts
    freq = parts.get("FREQ")
    if freq == "MONTHLY" and start.day > 28:
        days, setpos = month_day_fields([start.day])
        parts["BYMONTHDAY"] = ",".join(map(str, days))
        parts["BYSETPOS"] = str(setpos)
    elif (
        freq == "YEARLY"
        and (start.month, start.day) == (2, 29)
        and parts.get("BYMONTH", "2") == "2"
    ):
        days, setpos = year_day_fields(2, 29)
        parts.update(BYMONTH="2", BYMONTHDAY=",".join(map(str, days)), BYSETPOS=str(setpos))
    return parts


def _later_start(parts: dict[str, str], start: date, lo: date) -> date:
    """A DTSTART closer to ``lo`` that yields the same dates on or after ``lo``.

    dateutil walks a series from DTSTART, which gets slow for a daily task that
    is years old. Moving DTSTART forward by whole intervals keeps the phase.
    """
    if lo <= start or not parts.keys() <= _SKIPPABLE:
        return start
    n = _interval(parts)
    freq = parts.get("FREQ")
    if freq == "DAILY":
        periods = (lo - start).days // n - 1
        moved = start + timedelta(days=periods * n)
    elif freq == "WEEKLY":
        periods = (lo - start).days // (7 * n) - 1
        moved = start + timedelta(weeks=periods * n)
    elif freq == "MONTHLY":
        periods = ((lo.year - start.year) * 12 + lo.month - start.month) // n - 1
        moved = start + relativedelta(months=periods * n)
    elif freq == "YEARLY":
        periods = (lo.year - start.year) // n - 1
        moved = start + relativedelta(years=periods * n)
    else:
        return start
    if periods <= 0:
        return start
    # relativedelta clamps Jan 31 to Feb 28; that is only safe when the rule
    # names its own day and does not read it from DTSTART.
    if moved.day != start.day and not any(key in parts for key in _DAY_RULES):
        return start
    return moved


def _series(rec: Recurrence, lo: date):
    """The dateutil rule for ``rec``, valid for dates on or after ``lo``."""
    parts = _explicit(rec)
    # COUNT is counted from DTSTART, so a counted series cannot be moved.
    start = rec.dtstart if "COUNT" in parts else _later_start(parts, rec.dtstart, lo)
    text = ";".join(f"{key}={value}" for key, value in parts.items())
    return rrulestr(text, dtstart=_midnight(start))


def _step(parts: dict[str, str], frm: date) -> date:
    n = _interval(parts)
    freq = parts.get("FREQ", "DAILY")
    delta = {
        "DAILY": relativedelta(days=n),
        "WEEKLY": relativedelta(weeks=n),
        "MONTHLY": relativedelta(months=n),
        "YEARLY": relativedelta(years=n),
    }.get(freq, relativedelta(days=n))
    return frm + delta


def _within_bounds(parts: dict[str, str], candidate: date, completed_runs: int) -> bool:
    until = _until(parts)
    if until is not None and candidate > until:
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
    bounds COUNT for AFTER_COMPLETION rules. A FIXED rule's COUNT is counted on
    the calendar from ``dtstart``, as in RFC 5545, so skipped runs use it up.
    """
    if rec.mode is RecurrenceMode.AFTER_COMPLETION:
        parts = _parts(rec.rrule)
        candidate = _step(parts, completed_on)
        return candidate if _within_bounds(parts, candidate, completed_runs) else None
    floor = max(current_due, today)
    nxt = _series(rec, floor).after(_midnight(floor))
    return nxt.date() if nxt else None


def occurrences(rec: Recurrence, *, start: date, end: date) -> list[date]:
    """Dates of a FIXED series in [start, end], inclusive.

    AFTER_COMPLETION series cannot be projected, so this returns [].
    """
    if rec.mode is RecurrenceMode.AFTER_COMPLETION or end < start:
        return []
    found = _series(rec, start).between(_midnight(start), _midnight(end), inc=True)
    return [d.date() for d in found]


def first_on_or_after(rec: Recurrence, day: date) -> date | None:
    """The first occurrence on or after ``day`` (for setting the initial due)."""
    if rec.mode is RecurrenceMode.AFTER_COMPLETION:
        candidate = max(rec.dtstart, day)
        until = _until(_parts(rec.rrule))
        return None if until is not None and candidate > until else candidate
    nxt = _series(rec, day).after(_midnight(day), inc=True)
    return nxt.date() if nxt else None


def ordinal(n: int) -> str:
    """1 -> "1st", 22 -> "22nd"."""
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def format_time(at: time) -> str:
    """07:00 -> "7am", 17:30 -> "5:30pm", 12:00 -> "12pm"."""
    hour = at.hour % 12 or 12
    suffix = "am" if at.hour < 12 else "pm"
    return f"{hour}{suffix}" if at.minute == 0 else f"{hour}:{at.minute:02d}{suffix}"


def format_date(day: date) -> str:
    """2027-06-30 -> "Jun 30, 2027"."""
    return f"{MONTH_NAMES[day.month - 1]} {day.day}, {day.year}"


def _weekday_names(value: str, *, allow_weekday: bool) -> str | None:
    codes = tuple(value.split(","))
    if any(code not in _WEEKDAY_NAMES for code in codes):
        return None
    if allow_weekday and codes == WORKDAY_CODES:
        return "weekday"
    return ", ".join(_WEEKDAY_NAMES[code] for code in codes)


def _nth_weekdays(value: str) -> str | None:
    """ "1MO,3MO" -> "1st, 3rd Mon"; "-1FR" -> "last Fri"."""
    pairs = []
    for code in value.split(","):
        m = _NTH_WEEKDAY.fullmatch(code)
        if m is None:
            return None
        pairs.append((int(m.group(1)), m.group(2)))
    nths = list(dict.fromkeys(n for n, _ in pairs))
    days = list(dict.fromkeys(day for _, day in pairs))
    if sorted(pairs) != sorted((n, day) for n in nths for day in days):
        return None
    which = ", ".join("last" if n == -1 else ordinal(n) for n in nths)
    return f"{which} {', '.join(_WEEKDAY_NAMES[day] for day in days)}"


def _month_part(by: dict[str, str]) -> str | None:
    """What a monthly rule lands on: "15th", "last Fri", "last day"."""
    days, weekdays, setpos = by.get("BYMONTHDAY"), by.get("BYDAY"), by.get("BYSETPOS")
    if weekdays and not days:
        if setpos is None:
            return _nth_weekdays(weekdays)
        if tuple(weekdays.split(",")) == WORKDAY_CODES and setpos in ("1", "-1"):
            return "first workday" if setpos == "1" else "last workday"
        return None
    if not days or weekdays:
        return None
    values = [int(v) for v in days.split(",")]
    if setpos is not None:
        clamped = setpos == "-1" and len(values) > 1 and values[-1] <= 31
        if clamped and values == list(range(28, values[-1] + 1)):
            return ordinal(values[-1])
        return None
    if any(v != -1 and not 1 <= v <= 31 for v in values):
        return None
    return ", ".join("last day" if v == -1 else ordinal(v) for v in values)


def _year_part(by: dict[str, str]) -> str | None:
    """What a yearly rule lands on: "Jan 1"."""
    if "BYDAY" in by or "BYMONTH" not in by or "BYMONTHDAY" not in by:
        return None
    if "," in by["BYMONTH"] or not 1 <= int(by["BYMONTH"]) <= 12:
        return None
    month = MONTH_NAMES[int(by["BYMONTH"]) - 1]
    if "BYSETPOS" in by:
        leap_day = (by["BYMONTH"], by["BYMONTHDAY"], by["BYSETPOS"])
        return "Feb 29" if leap_day == ("2", "28,29", "-1") else None
    if "," in by["BYMONTHDAY"] or not 1 <= int(by["BYMONTHDAY"]) <= 31:
        return None
    return f"{month} {int(by['BYMONTHDAY'])}"


def _cadence(parts: dict[str, str], *, spacing_only: bool) -> str | None:
    """The part after "every": "3 days", "Mon, Thu", "2 months on the 15th"."""
    freq = parts.get("FREQ", "")
    unit = _UNIT_NAMES.get(freq)
    if unit is None or not parts.keys() <= _DESCRIBABLE:
        return None
    n = _interval(parts)
    spacing = unit if n == 1 else f"{n} {unit}s"
    by = {key: parts[key] for key in _BY_RULES if key in parts}
    if spacing_only or not by:
        return spacing
    if freq == "WEEKLY" and by.keys() == {"BYDAY"}:
        what = _weekday_names(by["BYDAY"], allow_weekday=n == 1)
        joined = f"{spacing} on {what}"
    elif freq == "MONTHLY" and "BYMONTH" not in by:
        what = _month_part(by)
        joined = f"{spacing} on the {what}"
    elif freq == "YEARLY":
        what = _year_part(by)
        joined = f"{spacing} on {what}"
    else:
        return None
    if what is None:
        return None
    return what if n == 1 else joined


def describe_rule(rrule: str, mode: RecurrenceMode, at: time | None = None) -> str:
    """A normalized description of a rule, such as "every Mon, Thu at 7am".

    ``parse_schedule`` reads the result back to the same rule. A rule this
    function has no words for is returned as its RRULE.
    """
    after = mode is RecurrenceMode.AFTER_COMPLETION
    try:
        parts = _parts(rrule)
        cadence = _cadence(parts, spacing_only=after)
        if cadence is None:
            return rrule
        text = f"every! {cadence}" if after else f"every {cadence}"
        if at is not None:
            text += f" at {format_time(at)}"
        if "COUNT" in parts:
            text += f" for {int(parts['COUNT'])} times"
        until = _until(parts)
        if until is not None:
            text += f" until {format_date(until)}"
    except ValueError:
        return rrule
    return text


def describe(rec: Recurrence) -> str:
    """A human description of the rule."""
    return rec.text or describe_rule(rec.rrule, rec.mode, rec.time)
