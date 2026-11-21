"""Quick-add and schedule parsing.

PLACEHOLDER: this is a deliberately small implementation so the rest of the app
can be built against the real interface. It understands "#name", "@label",
"p1".."p4", "/status", "today", "tomorrow", ISO dates, and "every day|week|
month|year". The full grammar replaces this module.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from slate.scheduling.recurrence import first_on_or_after
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

STATUS_WORDS = {
    "backlog": "backlog",
    "todo": "todo",
    "doing": "in_progress",
    "in-progress": "in_progress",
    "progress": "in_progress",
    "done": "done",
    "canceled": "canceled",
    "cancelled": "canceled",
}

_FREQ = {"day": "DAILY", "week": "WEEKLY", "month": "MONTHLY", "year": "YEARLY"}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _match(name: str, refs: tuple[EntityRef, ...]) -> EntityRef | None:
    key = _norm(name)
    for ref in refs:
        if key in {_norm(ref.name), *(_norm(a) for a in ref.aliases)}:
            return ref
    return None


def parse_schedule(text: str, ctx: ParseContext) -> ScheduleResult:
    today = ctx.now.date()
    t = text.strip().lower()
    if not t:
        return ScheduleResult(error="Empty schedule")
    m = re.fullmatch(r"every(!)?\s+(day|week|month|year)", t)
    if m:
        rec = Recurrence(
            rrule=f"FREQ={_FREQ[m.group(2)]}",
            mode=RecurrenceMode.AFTER_COMPLETION if m.group(1) else RecurrenceMode.FIXED,
            dtstart=today,
            text=f"every{m.group(1) or ''} {m.group(2)}",
        )
        first = first_on_or_after(rec, today)
        return ScheduleResult(due=Due(first) if first else None, recurrence=rec)
    if t == "today":
        return ScheduleResult(due=Due(today))
    if t == "tomorrow":
        return ScheduleResult(due=Due(today + timedelta(days=1)))
    try:
        return ScheduleResult(due=Due(date.fromisoformat(t)))
    except ValueError:
        return ScheduleResult(error=f"Could not understand “{text.strip()}”")


_TOKEN = re.compile(
    r"(?P<project>#[\w-]+)|(?P<label>@[\w-]+)|(?P<priority>\bp[1-4]\b)"
    r"|(?P<status>/[\w-]+)|(?P<sched>\bevery!?\s+(?:day|week|month|year)\b"
    r"|\btoday\b|\btomorrow\b|\b\d{4}-\d{2}-\d{2}\b)",
    re.IGNORECASE,
)


def parse_quick_add(text: str, ctx: ParseContext) -> QuickAddResult:
    tokens: list[Token] = []
    fields: dict = {"label_ids": [], "unknown_labels": []}
    for m in _TOKEN.finditer(text):
        kind = m.lastgroup
        raw = m.group(0)
        unresolved = False
        if kind == "project":
            ref = _match(raw[1:], ctx.projects)
            area = None if ref else _match(raw[1:], ctx.areas)
            if ref:
                fields["project_id"] = ref.id
            elif area:
                fields["area_id"] = area.id
            else:
                fields["unknown_project"] = raw[1:]
                unresolved = True
            tokens.append(Token(TokenKind.PROJECT, m.start(), m.end(), raw, unresolved))
        elif kind == "label":
            ref = _match(raw[1:], ctx.labels)
            if ref:
                fields["label_ids"].append(ref.id)
            else:
                fields["unknown_labels"].append(raw[1:])
                unresolved = True
            tokens.append(Token(TokenKind.LABEL, m.start(), m.end(), raw, unresolved))
        elif kind == "priority":
            fields["priority"] = {1: 1, 2: 2, 3: 3, 4: 0}[int(raw[1])]
            tokens.append(Token(TokenKind.PRIORITY, m.start(), m.end(), raw))
        elif kind == "status":
            status = STATUS_WORDS.get(raw[1:].lower())
            if status is None:
                continue
            fields["status"] = status
            tokens.append(Token(TokenKind.STATUS, m.start(), m.end(), raw))
        else:
            res = parse_schedule(raw, ctx)
            if res.error:
                continue
            fields["due"] = res.due
            fields["recurrence"] = res.recurrence
            k = TokenKind.RECURRENCE if res.recurrence else TokenKind.DATE
            tokens.append(Token(k, m.start(), m.end(), raw))
    title = text
    for tok in sorted(tokens, key=lambda t: t.start, reverse=True):
        title = title[: tok.start] + " " + title[tok.end :]
    title = re.sub(r"\s+", " ", title).strip()
    return QuickAddResult(
        title=title,
        due=fields.get("due"),
        recurrence=fields.get("recurrence"),
        area_id=fields.get("area_id"),
        project_id=fields.get("project_id"),
        unknown_project=fields.get("unknown_project"),
        label_ids=tuple(fields["label_ids"]),
        unknown_labels=tuple(fields["unknown_labels"]),
        priority=fields.get("priority"),
        status=fields.get("status"),
        tokens=tuple(tokens),
    )
