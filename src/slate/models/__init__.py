"""SQLAlchemy models. Portable column types only, so SQLite and Postgres both work."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """Aware UTC datetimes on every backend (SQLite drops the zone otherwise)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


TS = UTCDateTime()


class SourceMixin:
    source: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[str | None] = mapped_column(String(128))


class AreaRow(SourceMixin, Base):
    __tablename__ = "areas"
    __table_args__ = (UniqueConstraint("source", "source_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[UUID] = mapped_column(Uuid, unique=True)
    name: Mapped[str] = mapped_column(String(200))
    color: Mapped[str] = mapped_column(String(16))
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(TS)
    updated_at: Mapped[datetime] = mapped_column(TS)


class ProjectRow(SourceMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("source", "source_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[UUID] = mapped_column(Uuid, unique=True)
    name: Mapped[str] = mapped_column(String(200))
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16))
    description: Mapped[str] = mapped_column(Text, default="")
    target_date: Mapped[date | None] = mapped_column(Date)
    color: Mapped[str | None] = mapped_column(String(16))
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(TS)
    updated_at: Mapped[datetime] = mapped_column(TS)


class LabelRow(SourceMixin, Base):
    __tablename__ = "labels"
    __table_args__ = (UniqueConstraint("source", "source_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[UUID] = mapped_column(Uuid, unique=True)
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(TS)
    updated_at: Mapped[datetime] = mapped_column(TS)


class TaskRow(SourceMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("source", "source_id"),
        Index("ix_tasks_due_date", "due_date"),
        Index("ix_tasks_project_id", "project_id"),
        Index("ix_tasks_parent_id", "parent_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[UUID] = mapped_column(Uuid, unique=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16))
    priority: Mapped[int] = mapped_column(Integer, default=0)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id", ondelete="SET NULL"))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    due_date: Mapped[date | None] = mapped_column(Date)
    due_time: Mapped[time | None] = mapped_column(Time)
    recurrence_rrule: Mapped[str | None] = mapped_column(String(500))
    recurrence_mode: Mapped[str | None] = mapped_column(String(32))
    recurrence_dtstart: Mapped[date | None] = mapped_column(Date)
    recurrence_time: Mapped[time | None] = mapped_column(Time)
    recurrence_text: Mapped[str | None] = mapped_column(String(200))
    completed_runs: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(TS)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(TS)
    updated_at: Mapped[datetime] = mapped_column(TS)


class TaskLabelRow(Base):
    __tablename__ = "task_labels"
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    label_id: Mapped[int] = mapped_column(
        ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True
    )


class CommentRow(SourceMixin, Base):
    __tablename__ = "comments"
    __table_args__ = (UniqueConstraint("source", "source_id"), Index("ix_comments_task", "task_id"))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[UUID] = mapped_column(Uuid, unique=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS)
    updated_at: Mapped[datetime] = mapped_column(TS)


class ActivityRow(Base):
    __tablename__ = "activity"
    __table_args__ = (Index("ix_activity_task", "task_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS)


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("issuer", "subject"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[UUID] = mapped_column(Uuid, unique=True)
    issuer: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(TS)
    last_login_at: Mapped[datetime] = mapped_column(TS)


class SettingsRow(Base):
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timezone: Mapped[str] = mapped_column(String(64))
