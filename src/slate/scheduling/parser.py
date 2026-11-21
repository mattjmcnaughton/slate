"""Quick-add and schedule parsing.

``parse_schedule`` reads a whole string as one schedule phrase with the grammar
in ``grammar.py``. ``parse_quick_add`` finds the tokens in a line of free text:

1. Sigils: ``#project``, ``@label``, ``p1``..``p4``, ``/status``.
2. Schedule phrases anywhere in what is left. A phrase that could be ordinary
   title text ("sun", "12/3", "weekly") only counts at the end of the line.
   When several phrases qualify, the one at the end of the line wins, then one
   at the start, then a recurrence over a date, then the rightmost; the others
   stay in the title. A time written apart from its date ("Standup 9am with
   the team tomorrow") is combined with it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import timedelta
from typing import TYPE_CHECKING

from dateutil.relativedelta import relativedelta

from slate.scheduling.grammar import Grammar, Phrase, RuleSpec
from slate.scheduling.lexer import Tok, lex
from slate.scheduling.recurrence import (
    WEEKDAY_CODES,
    describe_rule,
    first_on_or_after,
    month_day_fields,
    year_day_fields,
)
from slate.scheduling.types import (
    Due,
    EntityRef,
    ParseContext,
    QuickAddResult,
    Recurrence,
    RecurrenceMode,
    ScheduleResult,
    Token,
    TokenKind,
)

if TYPE_CHECKING:
    from datetime import date, datetime

STATUS_WORDS = {
    "backlog": "backlog",
    "todo": "todo",
    "doing": "in_progress",
    "in-progress": "in_progress",
    "in_progress": "in_progress",
    "inprogress": "in_progress",
    "progress": "in_progress",
    "done": "done",
    "canceled": "canceled",
    "cancelled": "canceled",
}

# A sigil stands alone: after whitespace, and before whitespace or closing
# punctuation, so "a@b.com", "C#", and "/usr/bin" are left alone.
_SIGIL = re.compile(
    r"(?<!\S)(?:#(?P<project>[\w-]+)|@(?P<label>[\w-]+)|/(?P<status>[\w-]+)"
    r"|(?P<priority>p[1-4]))(?=[.,;:!?)]*(?:\s|$))",
    re.IGNORECASE,
)
_PRIORITY = {"1": 1, "2": 2, "3": 3, "4": 0}
_SPAN = {
    "day": lambda n: relativedelta(days=n),
    "week": lambda n: relativedelta(weeks=n),
    "month": lambda n: relativedelta(months=n),
    "quarter": lambda n: relativedelta(months=3 * n),
    "year": lambda n: relativedelta(years=n),
}
_ARTICLES = ("the", "a", "an")
_CLOSERS = ".,;:!?"


def _norm(s: str) -> str:
    return re.sub(r"[\W_]+", "", s.casefold())


def _match(name: str, refs: tuple[EntityRef, ...]) -> EntityRef | None:
    key = _norm(name)
    for ref in refs:
        if key in {_norm(ref.name), *(_norm(a) for a in ref.aliases)}:
            return ref
    return None


# Schedules


def _by_parts(spec: RuleSpec, anchor: date) -> dict[str, str]:
    """The BY* parts of a fixed rule; a rule that names no day ("every month")
    takes it from ``anchor``."""
    bymonth, bymonthday = spec.bymonth, spec.bymonthday
    byday, bysetpos = spec.byday, spec.bysetpos
    if spec.unit_only:
        if spec.freq == "WEEKLY":
            byday = (WEEKDAY_CODES[anchor.weekday()],)
        elif spec.freq == "MONTHLY":
            bymonthday, bysetpos = month_day_fields([anchor.day])
        elif spec.freq == "YEARLY":
            bymonth = anchor.month
            bymonthday, bysetpos = year_day_fields(anchor.month, anchor.day)
    parts: dict[str, str] = {}
    if bymonth is not None:
        parts["BYMONTH"] = str(bymonth)
    if bymonthday:
        parts["BYMONTHDAY"] = ",".join(map(str, bymonthday))
    if byday:
        parts["BYDAY"] = ",".join(byday)
    if bysetpos is not None:
        parts["BYSETPOS"] = str(bysetpos)
    return parts


def _join(parts: dict[str, str]) -> str:
    return ";".join(f"{key}={value}" for key, value in parts.items())


def _build(spec: RuleSpec, today: date) -> tuple[Due, Recurrence] | None:
    """Anchor a parsed rule to its start date.

    ``dtstart`` is the rule's first date on or after the start date (today
    unless "starting ..." was given), which also fixes the phase of "every
    other Friday". Returns None when the rule has no dates, as in "every day
    until yesterday".
    """
    anchor = spec.start or today
    parts = {"FREQ": spec.freq}
    if spec.interval > 1:
        parts["INTERVAL"] = str(spec.interval)
    if spec.after_completion:
        mode = RecurrenceMode.AFTER_COMPLETION
        dtstart = anchor
    else:
        mode = RecurrenceMode.FIXED
        by = _by_parts(spec, anchor)
        parts |= by
        every_period = Recurrence(_join({"FREQ": spec.freq, **by}), mode, anchor)
        first = first_on_or_after(every_period, anchor)
        if first is None:
            return None
        dtstart = first
    until = spec.until
    if until is None and spec.span is not None:
        n, unit = spec.span
        until = dtstart + _SPAN[unit](n) - timedelta(days=1)
    if spec.count is not None:
        parts["COUNT"] = str(spec.count)
    elif until is not None:
        parts["UNTIL"] = until.strftime("%Y%m%d")
    rrule = _join(parts)
    text = describe_rule(rrule, mode, spec.at)
    rec = Recurrence(rrule, mode, dtstart, spec.at, text)
    due = first_on_or_after(rec, max(today, dtstart))
    return (Due(due, spec.at), rec) if due is not None else None


def _resolve(phrase: Phrase, now: datetime) -> tuple[Due, Recurrence | None] | None:
    today = now.date()
    if phrase.rule is not None:
        return _build(phrase.rule, today)
    if phrase.day is not None:
        return Due(phrase.day, phrase.at), None
    if phrase.at is None:
        return None
    # A time alone means its next occurrence.
    later_today = phrase.at > now.time()
    return Due(today if later_today else today + timedelta(days=1), phrase.at), None


def parse_schedule(text: str, ctx: ParseContext) -> ScheduleResult:
    stripped = text.strip()
    if not stripped:
        return ScheduleResult(error="Empty schedule")
    toks = lex(text)
    phrase = Grammar(toks, ctx.now).phrase_at(0)
    if phrase is None or any(tok.kind != "sym" for tok in toks[phrase.end :]):
        return ScheduleResult(error=f"Could not understand “{stripped}”")
    resolved = _resolve(phrase, ctx.now)
    if resolved is None:
        return ScheduleResult(error=f"No dates match “{stripped}”")
    due, rec = resolved
    return ScheduleResult(due=due, recurrence=rec)


# Quick add


@dataclass
class _Fields:
    area_id: int | None = None
    project_id: int | None = None
    unknown_project: str | None = None
    label_ids: list[int] = field(default_factory=list)
    unknown_labels: list[str] = field(default_factory=list)
    priority: int | None = None
    status: str | None = None
    tokens: list[Token] = field(default_factory=list)


def _read_sigils(text: str, ctx: ParseContext) -> _Fields:
    fields = _Fields()
    for m in _SIGIL.finditer(text):
        kind = m.lastgroup
        raw = m.group(0)
        name = raw[1:]
        unresolved = False
        if kind == "project":
            project = _match(name, ctx.projects)
            area = None if project else _match(name, ctx.areas)
            if project:
                fields.project_id = project.id
            elif area:
                fields.area_id = area.id
            elif not _norm(name) or name.isdigit():
                continue  # "#123" is an issue number, not a new project
            else:
                fields.unknown_project = name
                unresolved = True
            token_kind = TokenKind.PROJECT
        elif kind == "label":
            label = _match(name, ctx.labels)
            if label:
                if label.id not in fields.label_ids:
                    fields.label_ids.append(label.id)
            elif not _norm(name):
                continue
            else:
                if name not in fields.unknown_labels:
                    fields.unknown_labels.append(name)
                unresolved = True
            token_kind = TokenKind.LABEL
        elif kind == "status":
            status = STATUS_WORDS.get(name.lower())
            if status is None:
                continue
            fields.status = status
            token_kind = TokenKind.STATUS
        else:
            fields.priority = _PRIORITY[raw[1]]
            token_kind = TokenKind.PRIORITY
        fields.tokens.append(Token(token_kind, m.start(), m.end(), raw, unresolved))
    return fields


def _filler(toks: list[Tok]) -> bool:
    return all(tok.kind in ("stop", "sym") for tok in toks)


def _rank(phrase: Phrase, toks: list[Tok]) -> tuple[int, bool, int]:
    """Higher wins: the end of the line, then the start, then a recurrence,
    then the rightmost."""
    if _filler(toks[phrase.end :]):
        place = 2
    elif _filler(toks[: phrase.start]):
        place = 1
    else:
        place = 0
    return place, phrase.rule is not None, phrase.start


def _accepted(phrase: Phrase, toks: list[Tok]) -> bool:
    """A weak phrase counts only at the end of the line, and not after an
    article ("Relax in the sun")."""
    if not phrase.weak:
        return True
    if not _filler(toks[phrase.end :]):
        return False
    before = toks[phrase.start - 1] if phrase.start else None
    return not (before and before.kind == "word" and before.text in _ARTICLES)


def _time_only(phrase: Phrase) -> bool:
    return phrase.rule is None and phrase.day is None


def _has_time(phrase: Phrase) -> bool:
    return phrase.at is not None or (
        phrase.rule is not None and phrase.rule.at is not None
    )


def _find_schedule(
    text: str, toks: list[Tok], now: datetime
) -> tuple[Due | None, Recurrence | None, list[Token]]:
    grammar = Grammar(toks, now)
    found: list[Phrase] = []
    i = 0
    while i < len(toks):
        phrase = grammar.phrase_at(i)
        if phrase is None:
            i += 1
            continue
        i = phrase.end
        if _accepted(phrase, toks) and _resolve(phrase, now) is not None:
            found.append(phrase)
    if not found:
        return None, None, []

    def rank(phrase: Phrase) -> tuple[int, bool, int]:
        return _rank(phrase, toks)

    main = max(found, key=rank)
    # A time and a date written apart belong together.
    others = [phrase for phrase in found if phrase is not main]
    if _time_only(main):
        partners = [p for p in others if not _time_only(p) and not _has_time(p)]
    elif not _has_time(main):
        partners = [p for p in others if _time_only(p)]
    else:
        partners = []
    partner = max(partners, key=rank, default=None)
    used = [main]
    merged = main
    if partner is not None:
        used.append(partner)
        clock, body = (main, partner) if _time_only(main) else (partner, main)
        if body.rule is not None:
            merged = replace(body, rule=replace(body.rule, at=clock.at))
        else:
            merged = replace(body, at=clock.at)
    resolved = _resolve(merged, now)
    if resolved is None:
        return None, None, []
    tokens = []
    for phrase in used:
        start, end = toks[phrase.start].start, toks[phrase.end - 1].end
        kind = TokenKind.RECURRENCE if phrase.rule is not None else TokenKind.DATE
        tokens.append(Token(kind, start, end, text[start:end]))
    return resolved[0], resolved[1], tokens


def _title(text: str, tokens: list[Token]) -> str:
    """``text`` without the tokens, whitespace collapsed. Punctuation that
    followed a removed token closes up: "Call mom tomorrow." -> "Call mom."."""
    kept = ""
    pos = 0
    for token in tokens:
        kept += text[pos : token.start]
        pos = token.end
        if text[pos : pos + 1] in _CLOSERS and text[pos : pos + 1]:
            kept = kept.rstrip()
            if not kept and text[pos] != "!" and text[pos] != "?":
                pos += 1  # "Tomorrow, call mom": nothing left for the comma
        else:
            kept += " "
    kept += text[pos:]
    return re.sub(r"\s+", " ", kept).strip()


def parse_quick_add(text: str, ctx: ParseContext) -> QuickAddResult:
    fields = _read_sigils(text, ctx)
    toks = lex(text, [(token.start, token.end) for token in fields.tokens])
    due, recurrence, schedule_tokens = _find_schedule(text, toks, ctx.now)
    tokens = sorted([*fields.tokens, *schedule_tokens], key=lambda token: token.start)
    return QuickAddResult(
        title=_title(text, tokens),
        due=due,
        recurrence=recurrence,
        area_id=fields.area_id,
        project_id=fields.project_id,
        unknown_project=fields.unknown_project,
        label_ids=tuple(fields.label_ids),
        unknown_labels=tuple(fields.unknown_labels),
        priority=fields.priority,
        status=fields.status,
        tokens=tuple(tokens),
    )
