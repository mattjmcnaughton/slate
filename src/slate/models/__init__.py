"""SQLAlchemy models. Portable column types only, so SQLite and Postgres both work.

Every id is a UUID. Everything a person owns belongs to one workspace, and every
reference between owned rows carries ``workspace_id`` in a composite foreign key,
so the database itself refuses a link across workspaces. Deletes that should
clear a reference (an area's projects, a project's tasks) are done by the
repositories, since a composite SET NULL would also clear ``workspace_id``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
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


def _owned(table: str, *extra: Any) -> tuple:
    """Constraints every workspace-owned table shares."""
    return (
        UniqueConstraint("id", "workspace_id", name=f"uq_{table}_id_workspace"),
        UniqueConstraint("workspace_id", "source", "source_id", name=f"uq_{table}_source"),
        *extra,
    )


def _ref(cols: str, target: str, name: str, ondelete: str | None = None) -> ForeignKeyConstraint:
    """Composite foreign key ``(<cols>, workspace_id)`` -> ``<target>(id, workspace_id)``."""
    return ForeignKeyConstraint(
        [cols, "workspace_id"],
        [f"{target}.id", f"{target}.workspace_id"],
        name=name,
        ondelete=ondelete,
    )


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("issuer", "subject"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    issuer: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(TS)
    last_login_at: Mapped[datetime] = mapped_column(TS)


class WorkspaceRow(Base):
    __tablename__ = "workspaces"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    # Unique: one workspace per user for now. Sharing would add a members table.
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64))
    next_task_number: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(TS)


class ApiKeyRow(Base):
    __tablename__ = "api_keys"
    __table_args__ = (Index("ix_api_keys_user", "user_id"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(TS)
    last_used_at: Mapped[datetime | None] = mapped_column(TS)
    revoked_at: Mapped[datetime | None] = mapped_column(TS)


class OwnedMixin:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[str | None] = mapped_column(String(128))


class AreaRow(OwnedMixin, Base):
    __tablename__ = "areas"
    __table_args__ = _owned("areas")
    name: Mapped[str] = mapped_column(String(200))
    color: Mapped[str] = mapped_column(String(16))
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(TS)
    updated_at: Mapped[datetime] = mapped_column(TS)


class ProjectRow(OwnedMixin, Base):
    __tablename__ = "projects"
    __table_args__ = _owned("projects", _ref("area_id", "areas", "fk_projects_area"))
    name: Mapped[str] = mapped_column(String(200))
    area_id: Mapped[UUID | None] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(16))
    description: Mapped[str] = mapped_column(Text, default="")
    target_date: Mapped[date | None] = mapped_column(Date)
    color: Mapped[str | None] = mapped_column(String(16))
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(TS)
    updated_at: Mapped[datetime] = mapped_column(TS)


class LabelRow(OwnedMixin, Base):
    __tablename__ = "labels"
    __table_args__ = _owned("labels")
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(TS)
    updated_at: Mapped[datetime] = mapped_column(TS)


class TaskRow(OwnedMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = _owned(
        "tasks",
        UniqueConstraint("workspace_id", "number", name="uq_tasks_number"),
        _ref("project_id", "projects", "fk_tasks_project"),
        _ref("area_id", "areas", "fk_tasks_area"),
        _ref("parent_id", "tasks", "fk_tasks_parent", "CASCADE"),
        Index("ix_tasks_due_date", "workspace_id", "due_date"),
        Index("ix_tasks_project_id", "project_id"),
        Index("ix_tasks_parent_id", "parent_id"),
    )
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16))
    priority: Mapped[int] = mapped_column(Integer, default=0)
    project_id: Mapped[UUID | None] = mapped_column(Uuid)
    area_id: Mapped[UUID | None] = mapped_column(Uuid)
    parent_id: Mapped[UUID | None] = mapped_column(Uuid)
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
    __table_args__ = (
        _ref("task_id", "tasks", "fk_task_labels_task", "CASCADE"),
        _ref("label_id", "labels", "fk_task_labels_label", "CASCADE"),
    )
    task_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    label_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid)


class CommentRow(OwnedMixin, Base):
    __tablename__ = "comments"
    __table_args__ = _owned(
        "comments",
        _ref("task_id", "tasks", "fk_comments_task", "CASCADE"),
        Index("ix_comments_task", "task_id"),
    )
    task_id: Mapped[UUID] = mapped_column(Uuid)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS)
    updated_at: Mapped[datetime] = mapped_column(TS)


class ActivityRow(Base):
    __tablename__ = "activity"
    __table_args__ = (
        _ref("task_id", "tasks", "fk_activity_task", "CASCADE"),
        Index("ix_activity_task", "task_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid)
    task_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS)
