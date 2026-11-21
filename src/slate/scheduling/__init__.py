"""Natural-language scheduling: quick-add parsing and recurrence math.

This package is pure: no I/O, no database, no global clock. Every function takes
the reference time explicitly so results are deterministic and testable.

The public API is re-exported here; the rest of the app imports only from
``slate.scheduling``.
"""

from slate.scheduling.parser import parse_quick_add, parse_schedule
from slate.scheduling.recurrence import (
    describe,
    first_on_or_after,
    next_due,
    occurrences,
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

__all__ = [
    "Due",
    "EntityRef",
    "ParseContext",
    "QuickAddResult",
    "Recurrence",
    "RecurrenceMode",
    "ScheduleResult",
    "Token",
    "TokenKind",
    "describe",
    "first_on_or_after",
    "next_due",
    "occurrences",
    "parse_quick_add",
    "parse_schedule",
]
