"""Injectable clocks. Code never calls ``datetime.now()`` directly."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """The current instant, timezone-aware, in UTC."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """A clock that only moves when told to. Used by tests and seeded dev mode."""

    def __init__(self, at: datetime) -> None:
        if at.tzinfo is None:
            raise ValueError("FixedClock needs an aware datetime")
        self._at = at.astimezone(UTC)

    def now(self) -> datetime:
        return self._at

    def advance(self, **kwargs: float) -> None:
        self._at += timedelta(**kwargs)

    def set(self, at: datetime) -> None:
        self._at = at.astimezone(UTC)
