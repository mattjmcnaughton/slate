"""The schedule grammar: a hand-written recursive-descent parser over tokens.

``Grammar.phrase_at(i)`` reads the longest schedule phrase that starts at token
``i``. In outline (``[x]`` optional, ``|`` alternatives)::

    phrase     := recurrence | one_off | time recurrence
    recurrence := ("every" | "each") ["!"] pattern modifier*
                | adverb modifier*                    daily, weekly, monthly, ...
                | "after" count unit modifier*        after 2 weeks
                | count unit "after" "done"           3 days after done
    pattern    := ["other" | count | ordinal] unit ["on" day_spec]
                | "weekday" | "weekend" | ["other"] weekdays
                | month day | day ["of"] month        every Jan 1
                | ordinals [weekdays | "day" | "workday"] ["of the month"]
                | "morning" | "afternoon" | "evening" | "night"
    modifier   := ["at"] time
                | ("starting" | "from") date
                | ("until" | "through" | "ending") (date | month [year])
                | "for" count unit | "for" count "times"
                | "after" "done"
    one_off    := ["on" | "by" | "due"] date [[","] time] | time [["on"] date]
    date       := today | tonight | tomorrow | yesterday | [this | next] weekday
                | this weekend | next (weekend | week | month | year)
                | "in" count unit | end of (month | year) | eom | eoy
                | month day [[","] year] | day ["of"] month [[","] year]
                | M/D[/Y] | YYYY-MM-DD | ["the"] ordinal
    time       := H[:MM] (am | pm) | HH:MM | noon | midnight | part of day

Dates are resolved against ``now`` as they are read. A recurrence comes back
as a ``RuleSpec``; the parser module turns it into a ``Recurrence``.

A phrase is ``weak`` when it could easily be ordinary title text ("sun",
"12/3", "weekly", "15th", "noon", "after 2 weeks"). Quick add only accepts a
weak phrase at the end of the line.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING

from dateutil.relativedelta import relativedelta

from slate.scheduling.recurrence import (
    WEEKDAY_CODES,
    WORKDAY_CODES,
    month_day_fields,
    year_day_fields,
)

if TYPE_CHECKING:
    from slate.scheduling.lexer import Tok

_FULL_WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
WEEKDAYS: dict[str, int] = {
    **{name: i for i, name in enumerate(_FULL_WEEKDAYS)},
    **{name[:3]: i for i, name in enumerate(_FULL_WEEKDAYS)},
    "tues": 1,
    "weds": 2,
    "thur": 3,
    "thurs": 3,
}
_FULL_MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
MONTHS: dict[str, int] = {
    **{name: i for i, name in enumerate(_FULL_MONTHS, start=1)},
    **{name[:3]: i for i, name in enumerate(_FULL_MONTHS, start=1)},
    "sept": 9,
}
# The longest each month gets; Feb 29 is valid, Feb 30 never is.
_MONTH_LENGTHS = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
UNITS = {
    "day": "day",
    "days": "day",
    "week": "week",
    "weeks": "week",
    "wk": "week",
    "wks": "week",
    "month": "month",
    "months": "month",
    "quarter": "quarter",
    "quarters": "quarter",
    "year": "year",
    "years": "year",
    "yr": "year",
    "yrs": "year",
}
_CLOCK_UNITS = {
    "hour": "hours",
    "hours": "hours",
    "hr": "hours",
    "hrs": "hours",
    "minute": "minutes",
    "minutes": "minutes",
    "min": "minutes",
    "mins": "minutes",
}
_FREQ = {"day": "DAILY", "week": "WEEKLY", "month": "MONTHLY", "year": "YEARLY"}
_ADVERBS = {
    "daily": ("day", 1),
    "weekly": ("week", 1),
    "biweekly": ("week", 2),
    "fortnightly": ("week", 2),
    "monthly": ("month", 1),
    "quarterly": ("quarter", 1),
    "yearly": ("year", 1),
    "annually": ("year", 1),
}
_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_ORDINAL_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
# Todoist's times for a part of the day.
PARTS_OF_DAY = {
    "morning": time(9),
    "afternoon": time(12),
    "evening": time(19),
    "night": time(22),
}
_TOMORROW = ("tomorrow", "tmrw", "tmr", "tmw")
_STARTING = ("starting", "starts", "from", "beginning")
_UNTIL = ("until", "till", "til", "through", "thru", "ending", "ends")
_DONE = ("done", "completion", "completing", "completed", "complete", "finishing")
_MIN_YEAR, _MAX_YEAR = 1970, 2199
_MAX_COUNT = 999
_OPENERS = frozenset("([{<\"'“‘,;")
_JOINERS = frozenset("-_/@#$%&+=*~^\\'’")


@dataclass
class RuleSpec:
    """A recurrence as written, before it is anchored to a start date."""

    freq: str
    interval: int = 1
    bymonth: int | None = None
    bymonthday: tuple[int, ...] = ()
    byday: tuple[str, ...] = ()
    bysetpos: int | None = None
    # "every 2 weeks" with no day named: the day comes from the start date, and
    # only such a rule can count from completion ("every! 2 weeks").
    unit_only: bool = False
    after_completion: bool = False
    at: time | None = None
    start: date | None = None
    until: date | None = None
    span: tuple[int, str] | None = None  # "for 6 weeks"
    count: int | None = None


@dataclass
class Phrase:
    """A schedule phrase covering tokens [start, end).

    A one-off has ``day`` and maybe ``at``, or only ``at`` ("9am"); a recurrence
    has ``rule``.
    """

    start: int
    end: int
    day: date | None = None
    at: time | None = None
    rule: RuleSpec | None = None
    weak: bool = False


@dataclass(frozen=True)
class _Date:
    day: date
    end: int
    at: time | None = None
    weak: bool = False


@dataclass(frozen=True)
class _Time:
    at: time
    end: int
    weak: bool = False


def _safe_date(year: int, month: int, day: int) -> date | None:
    """The date, or None when it does not exist or its year is not plausible
    (which also keeps date arithmetic far from date.max)."""
    if not _MIN_YEAR <= year <= _MAX_YEAR:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _to_24h(hour: int, meridiem: str) -> int | None:
    if not 1 <= hour <= 12:
        return None
    return hour % 12 + (12 if meridiem == "pm" else 0)


def _spacing(unit: str, n: int) -> RuleSpec:
    """A rule for every ``n`` units with no day named."""
    if unit == "quarter":
        unit, n = "month", 3 * n
    return RuleSpec(_FREQ[unit], interval=n, unit_only=True)


class Grammar:
    def __init__(self, toks: list[Tok], now: datetime) -> None:
        self.toks = toks
        self.now = now
        self.today = now.date()
        self._limit = len(toks)

    def phrase_at(self, i: int) -> Phrase | None:
        """The longest phrase starting at token ``i`` that is not part of a
        larger word, such as "today" in "today-ish" or "5pm" in "5pm-6pm"."""
        if not self._starts_cleanly(i):
            return None
        try:
            while self._limit > i:
                phrase = self._phrase(i)
                if phrase is None or self._ends_cleanly(phrase.end):
                    return phrase
                # Back off: retry without the token that ran into other text.
                self._limit = phrase.end - 1
            return None
        finally:
            self._limit = len(self.toks)

    # Token access

    def _tok(self, i: int) -> Tok | None:
        return self.toks[i] if 0 <= i < self._limit else None

    def _word(self, i: int) -> str | None:
        tok = self._tok(i)
        return tok.text if tok is not None and tok.kind == "word" else None

    def _is(self, i: int, *words: str) -> bool:
        return self._word(i) in words

    def _sym(self, i: int, char: str) -> bool:
        tok = self._tok(i)
        return tok is not None and tok.kind == "sym" and tok.text == char

    def _starts_cleanly(self, i: int) -> bool:
        tok = self.toks[i]
        if not tok.glued:
            return True
        prev = self.toks[i - 1]
        return prev.kind == "sym" and prev.text in _OPENERS

    def _ends_cleanly(self, end: int) -> bool:
        if end >= len(self.toks) or not self.toks[end].glued:
            return True
        nxt = self.toks[end]
        if nxt.kind != "sym" or nxt.text in _JOINERS:
            return False
        if nxt.text in ".:" and end + 1 < len(self.toks):
            after = self.toks[end + 1]
            return not (after.glued and after.kind != "sym")
        return True

    # Small pieces

    def _count(self, i: int, *, articles: bool = False) -> tuple[int, int] | None:
        """A count at ``i`` as (value, next index): "3", "two", and "a"/"an"."""
        tok = self._tok(i)
        if tok is None:
            return None
        if tok.kind == "num" and len(tok.text) <= 3 and int(tok.text) >= 1:
            return int(tok.text), i + 1  # at most _MAX_COUNT
        if tok.kind == "word":
            if tok.text in _NUMBER_WORDS:
                return _NUMBER_WORDS[tok.text], i + 1
            if articles and tok.text in ("a", "an"):
                return 1, i + 1
        return None

    def _unit(self, i: int, n: int = 1) -> str | None:
        """The unit at ``i`` for a count of ``n``. A quarter is 3 months, so
        its count is capped to keep the month count a readable count."""
        unit = UNITS.get(self._word(i) or "")
        return None if unit == "quarter" and n > _MAX_COUNT // 3 else unit

    def _weekday(self, i: int) -> int | None:
        word = self._word(i)
        if word is None:
            return None
        if word.endswith("s") and word[:-1] in _FULL_WEEKDAYS:
            word = word[:-1]
        return WEEKDAYS.get(word)

    def _separator(self, i: int) -> int:
        """The index after a list separator at ``i`` (",", "and", "&", ", and",
        "/"), or ``i`` when there is none."""
        j = i + 1 if self._sym(i, ",") else i
        if self._is(j, "and") or self._sym(j, "&") or (j == i and self._sym(j, "/")):
            j += 1
        return j

    def _weekday_list(self, i: int) -> tuple[tuple[str, ...], int] | None:
        """Weekdays at ``i`` as sorted BYDAY codes: "Mon, Thu", "sat and sun"."""
        first = self._weekday(i)
        if first is None:
            return None
        days = {first}
        j = i + 1
        while True:
            k = self._separator(j)
            nxt = self._weekday(k) if k > j else None
            if nxt is None:
                break
            days.add(nxt)
            j = k + 1
        return tuple(WEEKDAY_CODES[d] for d in sorted(days)), j

    def _ordinal(self, i: int) -> tuple[int, bool] | None:
        """An ordinal at ``i`` as (value, written as a word): "15th", "third",
        and "last" (-1)."""
        tok = self._tok(i)
        if tok is None:
            return None
        if tok.kind == "ord":
            value = int(tok.text[:-2])
            return (value, False) if 1 <= value <= 31 else None
        if tok.kind == "word":
            if tok.text == "last":
                return -1, True
            if tok.text in _ORDINAL_WORDS:
                return _ORDINAL_WORDS[tok.text], True
        return None

    def _day_number(self, i: int) -> int | None:
        """A day of the month at ``i``: "3" or "3rd", but not the 3 of "3pm"."""
        tok = self._tok(i)
        if tok is None or tok.kind not in ("num", "ord"):
            return None
        if tok.kind == "ord":
            value = int(tok.text[:-2])
        else:
            nxt = self._tok(i + 1)
            if len(tok.text) > 2 or (
                nxt is not None and nxt.kind == "word" and (nxt.glued or nxt.text in ("am", "pm"))
            ):
                return None
            value = int(tok.text)
        return value if 1 <= value <= 31 else None

    def _year(self, i: int) -> tuple[int, int] | None:
        """An optional ", 2027" or "2027" at ``i`` as (year, next index)."""
        j = i + 1 if self._sym(i, ",") else i
        tok = self._tok(j)
        if tok is None or tok.kind != "num" or len(tok.text) != 4:
            return None
        nxt = self._tok(j + 1)
        if nxt is not None and nxt.glued and nxt.kind == "word":
            return None
        year = int(tok.text)
        return (year, j + 1) if _MIN_YEAR <= year <= _MAX_YEAR else None

    # Dates

    def _next_month_day(self, month: int, day: int) -> date | None:
        """The next such date on or after today (Feb 29: the next leap year)."""
        for year in range(self.today.year, self.today.year + 9):
            candidate = _safe_date(year, month, day)
            if candidate is not None and candidate >= self.today:
                return candidate
        return None

    def _resolve(self, month: int, day: int, end: int) -> _Date | None:
        """A month and day, with the year that may follow at ``end``."""
        found = self._year(end)
        if found is not None:
            resolved = _safe_date(found[0], month, day)
            end = found[1]
        else:
            resolved = self._next_month_day(month, day)
        return _Date(resolved, end) if resolved is not None else None

    def _month_first(self, i: int) -> _Date | None:
        month = MONTHS.get(self._word(i) or "")
        day = self._day_number(i + 1)
        if month is None or day is None:
            return None
        return self._resolve(month, day, i + 2)

    def _day_first(self, i: int) -> _Date | None:
        day = self._day_number(i)
        if day is None:
            return None
        j = i + 2 if self._is(i + 1, "of") else i + 1
        month = MONTHS.get(self._word(j) or "")
        return self._resolve(month, day, j + 1) if month is not None else None

    def _slash(self, i: int) -> _Date | None:
        fields = [int(part) for part in self.toks[i].text.split("/")]
        if len(fields) == 2:
            resolved = self._next_month_day(fields[0], fields[1])
        else:
            year = fields[2] + 2000 if fields[2] < 100 else fields[2]
            resolved = _safe_date(year, fields[0], fields[1])
        if resolved is None:
            return None
        return _Date(resolved, i + 1, weak=len(fields) == 2)

    def _bare_ordinal(self, i: int) -> _Date | None:
        """ "15th": the next 15th on or after today."""
        tok = self._tok(i)
        if tok is None or tok.kind != "ord":
            return None
        day = int(tok.text[:-2])
        first = self.today.replace(day=1)
        for months in range(13):
            month = first + relativedelta(months=months)
            candidate = _safe_date(month.year, month.month, day)
            if candidate is not None and candidate >= self.today:
                return _Date(candidate, i + 1, weak=True)
        return None

    def _next_monday(self) -> date:
        return self.today + timedelta(days=7 - self.today.weekday())

    def _relative(self, i: int) -> _Date | None:
        """ "in 3 days", "in 2 weeks", "in an hour"."""
        found = self._count(i + 1, articles=True)
        if found is None:
            return None
        n, j = found
        word = self._word(j) or ""
        unit = UNITS.get(word)
        if unit is not None:
            delta = {
                "day": relativedelta(days=n),
                "week": relativedelta(weeks=n),
                "month": relativedelta(months=n),
                "quarter": relativedelta(months=3 * n),
                "year": relativedelta(years=n),
            }[unit]
            return _Date(self.today + delta, j + 1)
        if word in _CLOCK_UNITS:
            # Elapsed time, not wall-clock arithmetic, so a DST change in
            # between is accounted for.
            elapsed = timedelta(**{_CLOCK_UNITS[word]: n})
            if self.now.tzinfo is None:
                then = self.now + elapsed
            else:
                then = (self.now.astimezone(UTC) + elapsed).astimezone(self.now.tzinfo)
            return _Date(then.date(), j + 1, at=time(then.hour, then.minute))
        return None

    def _date(self, i: int) -> _Date | None:
        tok = self._tok(i)
        if tok is None:
            return None
        if tok.kind == "iso":
            year, month, day = (int(part) for part in tok.text.split("-"))
            resolved = _safe_date(year, month, day)
            return _Date(resolved, i + 1) if resolved is not None else None
        if tok.kind == "slash":
            return self._slash(i)
        if tok.kind in ("num", "ord"):
            return self._day_first(i) or self._bare_ordinal(i)
        if tok.kind != "word":
            return None
        word = tok.text
        today = self.today
        if word == "today":
            return _Date(today, i + 1)
        if word == "tonight":
            return _Date(today, i + 1, at=PARTS_OF_DAY["night"])
        if word in _TOMORROW:
            return _Date(today + timedelta(days=1), i + 1)
        if word == "yesterday":
            return _Date(today - timedelta(days=1), i + 1)
        if word == "the":
            if self._is(i + 1, "day"):
                return self._date(i + 1)
            return self._day_first(i + 1) or self._bare_ordinal(i + 1)
        if word == "day" and self._is(i + 1, "after") and self._is(i + 2, *_TOMORROW):
            return _Date(today + timedelta(days=2), i + 3)
        if word == "this":
            return self._this(i + 1)
        if word == "next":
            return self._next(i + 1)
        if word == "in":
            return self._relative(i)
        if word in ("eom", "eoy"):
            return _Date(self._end_of("month" if word == "eom" else "year"), i + 1)
        if word == "end" and self._is(i + 1, "of"):
            j = i + 3 if self._is(i + 2, "the", "this") else i + 2
            if self._is(j, "month", "year"):
                return _Date(self._end_of(self._word(j) or ""), j + 1)
            return None
        weekday = WEEKDAYS.get(word)
        if weekday is not None:
            ahead = (weekday - today.weekday()) % 7 or 7
            weak = word not in _FULL_WEEKDAYS
            return _Date(today + timedelta(days=ahead), i + 1, weak=weak)
        return self._month_first(i)

    def _end_of(self, unit: str) -> date:
        if unit == "year":
            return self.today.replace(month=12, day=31)
        return self.today + relativedelta(day=31)

    def _this(self, i: int) -> _Date | None:
        """What follows "this": a part of today, the weekend, or a weekday."""
        word = self._word(i) or ""
        today = self.today
        if word in ("morning", "afternoon", "evening"):
            return _Date(today, i + 1, at=PARTS_OF_DAY[word])
        if word == "weekend":
            ahead = max(0, 5 - today.weekday())
            return _Date(today + timedelta(days=ahead), i + 1)
        weekday = WEEKDAYS.get(word)
        if weekday is None:
            return None
        ahead = (weekday - today.weekday()) % 7
        return _Date(today + timedelta(days=ahead), i + 1)

    def _next(self, i: int) -> _Date | None:
        """What follows "next": a day of next Mon-Sun week, or the next period."""
        word = self._word(i)
        today = self.today
        if word == "week":
            return _Date(self._next_monday(), i + 1)
        if word == "weekend":
            return _Date(self._next_monday() + timedelta(days=5), i + 1)
        if word == "month":
            return _Date(today + relativedelta(months=1, day=1), i + 1)
        if word == "year":
            return _Date(date(today.year + 1, 1, 1), i + 1)
        weekday = WEEKDAYS.get(word or "")
        if weekday is None:
            return None
        return _Date(self._next_monday() + timedelta(days=weekday), i + 1)

    def _month_end(self, i: int) -> _Date | None:
        """ "June" or "June 2027" as a bound: the last day of that month."""
        month = MONTHS.get(self._word(i) or "")
        if month is None:
            return None
        found = self._year(i + 1)
        if found is not None:
            year, end = found
        else:
            end = i + 1
            passed = month < self.today.month
            year = self.today.year + (1 if passed else 0)
        return _Date(date(year, month, 1) + relativedelta(day=31), end)

    # Times

    def _time(self, i: int, *, bare_hour: bool = False, parts: bool = False) -> _Time | None:
        """A time at ``i``. ``bare_hour`` allows "at 7" (24-hour: 07:00);
        ``parts`` allows "morning", "evening", and so on."""
        lead = self._is(i, "at")
        j = i + 1 if lead else i
        tok = self._tok(j)
        if tok is None:
            return None
        meridiem = self._word(j + 1) if self._is(j + 1, "am", "pm") else None
        if tok.kind == "clock":
            hour, minute = (int(part) for part in tok.text.split(":"))
            if minute > 59:
                return None
            if meridiem is not None:
                hour24 = _to_24h(hour, meridiem)
                return None if hour24 is None else _Time(time(hour24, minute), j + 2)
            if hour > 23:
                return None
            return _Time(time(hour, minute), j + 1, weak=not lead)
        if tok.kind == "num" and len(tok.text) <= 2:
            hour = int(tok.text)
            if meridiem is not None:
                hour24 = _to_24h(hour, meridiem)
                return None if hour24 is None else _Time(time(hour24), j + 2)
            nxt = self._tok(j + 1)
            glued = nxt is not None and nxt.glued and nxt.kind != "sym"
            if lead and bare_hour and hour <= 23 and not glued:
                return _Time(time(hour), j + 1)
            return None
        if tok.kind != "word":
            return None
        if tok.text in ("noon", "midday"):
            return _Time(time(12), j + 1, weak=not lead)
        if tok.text == "midnight":
            return _Time(time(0), j + 1, weak=not lead)
        if parts and not lead:
            k = j + 2 if self._is(j, "in") and self._is(j + 1, "the") else j
            part = PARTS_OF_DAY.get(self._word(k) or "")
            if part is not None:
                return _Time(part, k + 1)
        return None

    # One-off dates

    def _one_off(self, i: int) -> Phrase | None:
        j = i
        lead = self._word(i) if self._is(i, "on", "by", "due") else None
        if lead is not None:
            j += 1
            if lead == "due" and self._is(j, "on", "by"):
                j += 1
        found = self._date(j)
        if found is not None:
            at, end = found.at, found.end
            weak = found.weak and lead is None
            after = self._time(end + 1 if self._sym(end, ",") else end, bare_hour=True, parts=True)
            if after is not None:
                at, end, weak = after.at, after.end, weak and after.weak
            return Phrase(i, end, day=found.day, at=at, weak=weak)
        if lead == "on":
            return None
        clock = self._time(j)
        if clock is None:
            return None
        weak = clock.weak and lead is None
        # "5pm tomorrow", "5pm on Friday"
        found = self._date(clock.end + 1 if self._is(clock.end, "on") else clock.end)
        if found is not None:
            weak = weak and found.weak
            return Phrase(i, found.end, day=found.day, at=clock.at, weak=weak)
        return Phrase(i, clock.end, at=clock.at, weak=weak)

    # Recurrences

    def _unit_rule(self, unit: str, n: int, i: int) -> tuple[RuleSpec, int]:
        """A rule for every ``n`` units, with the "on ..." that may follow at
        ``i``: "on Tue", "on the 15th", "on Jan 1"."""
        spec = _spacing(unit, n)
        n = spec.interval
        if not self._is(i, "on"):
            return spec, i
        if unit == "week":
            days = self._weekday_list(i + 1)
            if days is not None:
                return RuleSpec("WEEKLY", interval=n, byday=days[0]), days[1]
        else:
            which = self._yearly if unit == "year" else self._monthly
            named = which(i + 1)
            if named is not None:
                return replace(named[0], interval=n), named[1]
        return spec, i

    def _interval(self, i: int) -> tuple[RuleSpec, int] | None:
        """ "day", "3 days", "other week", "2 weeks on Tue", "other Fri"."""
        n, j = 1, i
        counted = self._count(i)
        nth = self._ordinal(i)
        if self._is(i, "other"):
            n, j = 2, i + 1
            days = self._weekday_list(j)
            if days is not None:
                return RuleSpec("WEEKLY", interval=2, byday=days[0]), days[1]
        elif counted is not None:
            n, j = counted
        elif nth is not None and nth[0] > 1:
            # "every 2nd week" is every 2 weeks, but "every 2nd day of the
            # month" is a day of the month.
            if self._is(i + 1, "day") and self._of_month(i + 2) > i + 2:
                return None
            n, j = nth[0], i + 1
        unit = self._unit(j, n)
        if unit is None:
            return None
        return self._unit_rule(unit, n, j + 1)

    def _named_days(self, i: int) -> tuple[RuleSpec, int] | None:
        if self._is(i, "weekday", "weekdays", "workday", "workdays"):
            return RuleSpec("WEEKLY", byday=WORKDAY_CODES), i + 1
        if self._is(i, "weekend", "weekends"):
            return RuleSpec("WEEKLY", byday=("SA",)), i + 1
        days = self._weekday_list(i)
        if days is None:
            return None
        return RuleSpec("WEEKLY", byday=days[0]), days[1]

    def _yearly(self, i: int) -> tuple[RuleSpec, int] | None:
        """A day of the year: "Jan 1", "1 Jan", "1st of January"."""
        j = i + 1 if self._is(i, "the") else i
        month = MONTHS.get(self._word(j) or "")
        if month is not None:
            day, end = self._day_number(j + 1), j + 2
        else:
            day = self._day_number(j)
            k = j + 2 if self._is(j + 1, "of") else j + 1
            month, end = MONTHS.get(self._word(k) or ""), k + 1
        if month is None or day is None or day > _MONTH_LENGTHS[month - 1]:
            return None
        days, setpos = year_day_fields(month, day)
        spec = RuleSpec("YEARLY", bymonth=month, bymonthday=days, bysetpos=setpos)
        return spec, end

    def _of_month(self, i: int) -> int:
        """The index after an optional "of the month" at ``i``."""
        of_month = (
            self._is(i, "of")
            and self._is(i + 1, "the", "each", "every")
            and self._is(i + 2, "month")
        )
        return i + 3 if of_month else i

    def _monthly(self, i: int) -> tuple[RuleSpec, int] | None:
        """A day of the month: "15th", "1st and 15th", "3rd Wednesday",
        "last Fri", "last day", "first workday"."""
        j = i + 1 if self._is(i, "the") else i
        nths: list[int] = []
        worded = False
        while True:
            found = self._ordinal(j)
            if found is None:
                break
            nths.append(found[0])
            worded = worded or found[1]
            j += 1
            k = self._separator(j)
            if k == j or self._ordinal(k) is None:
                break
            j = k
        if not nths:
            return None
        days = self._weekday_list(j)
        if days is not None:
            if any(n > 5 for n in nths):
                return None
            ordered = sorted(set(nths), key=lambda n: (n < 0, n))
            codes = tuple(f"{n}{code}" for n in ordered for code in days[0])
            return RuleSpec("MONTHLY", byday=codes), self._of_month(days[1])
        if self._is(j, "workday", "weekday") and nths in ([1], [-1]):
            spec = RuleSpec("MONTHLY", byday=WORKDAY_CODES, bysetpos=nths[0])
            return spec, self._of_month(j + 1)
        if self._is(j, "day"):
            j += 1
        elif worded:
            # "every second" and "every last" alone are not schedules.
            return None
        bymonthday, bysetpos = month_day_fields(nths)
        spec = RuleSpec("MONTHLY", bymonthday=bymonthday, bysetpos=bysetpos)
        return spec, self._of_month(j)

    def _part_of_day(self, i: int) -> tuple[RuleSpec, int] | None:
        part = PARTS_OF_DAY.get(self._word(i) or "")
        return (RuleSpec("DAILY", at=part), i + 1) if part is not None else None

    def _modifiers(self, spec: RuleSpec, start: int, i: int) -> Phrase:
        """The time and bounds after a pattern, in any order, each once."""
        j = i
        while True:
            if spec.at is None:
                clock = self._time(j, bare_hour=True, parts=True)
                if clock is not None:
                    spec.at, j = clock.at, clock.end
                    continue
            word = self._word(j)
            k = j + 2 if self._is(j + 1, "on") else j + 1
            if word in _STARTING and spec.start is None:
                found = self._date(k)
                if found is not None:
                    spec.start, j = found.day, found.end
                    continue
            if word in _UNTIL and spec.until is None:
                found = self._date(k) or self._month_end(k)
                if found is not None:
                    spec.until, j = found.day, found.end
                    continue
            if word == "after" and spec.unit_only and self._is(j + 1, *_DONE):
                spec.after_completion, j = True, j + 2
                continue
            if word == "for" and spec.span is None and spec.count is None:
                counted = self._count(j + 1, articles=True)
                if counted is not None:
                    n, k = counted
                    unit = self._unit(k)
                    if self._is(k, "times", "time"):
                        spec.count, j = n, k + 1
                        continue
                    if unit is not None:
                        spec.span, j = (n, unit), k + 1
                        continue
            return Phrase(start, j, rule=spec)

    def _every(self, i: int) -> Phrase | None:
        if not self._is(i, "every", "each"):
            return None
        j = i + 1
        bang = self._tok(j)
        after_completion = self._sym(j, "!") and bang is not None and bang.glued
        if after_completion:
            j += 1
        found = (
            self._interval(j)
            or self._named_days(j)
            or self._yearly(j)
            or self._monthly(j)
            or self._part_of_day(j)
        )
        if found is None:
            return None
        spec, j = found
        # "every! Monday" has no interval to count from completion; a fixed
        # rule already moves to the Monday after the completion date.
        spec.after_completion = after_completion and spec.unit_only
        return self._modifiers(spec, i, j)

    def _adverb(self, i: int) -> Phrase | None:
        entry = _ADVERBS.get(self._word(i) or "")
        if entry is None:
            return None
        spec, j = self._unit_rule(*entry, i + 1)
        phrase = self._modifiers(spec, i, j)
        phrase.weak = phrase.end == i + 1
        return phrase

    def _after(self, i: int) -> Phrase | None:
        """ "after 2 weeks" and "3 days after done"."""
        leading = self._is(i, "after")
        counted = self._count(i + 1 if leading else i, articles=True)
        if counted is None:
            return None
        n, j = counted
        unit = self._unit(j, n)
        if unit is None:
            return None
        j += 1
        if not leading:
            if not (self._is(j, "after") and self._is(j + 1, *_DONE)):
                return None
            j += 2
        spec = _spacing(unit, n)
        spec.after_completion = True
        phrase = self._modifiers(spec, i, j)
        phrase.weak = leading and phrase.end == j
        return phrase

    def _phrase(self, i: int) -> Phrase | None:
        phrase = self._every(i) or self._after(i) or self._adverb(i) or self._one_off(i)
        if phrase is not None and phrase.rule is None and phrase.day is None:
            # A time before the rule: "7am every weekday".
            rest = self._every(phrase.end) or self._adverb(phrase.end)
            if rest is not None and rest.rule is not None and rest.rule.at is None:
                rest.rule.at = phrase.at
                return replace(rest, start=i, weak=False)
        return phrase
