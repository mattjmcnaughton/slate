"""workspaces: every owned row belongs to one workspace; every id is a UUID

Slate had no meaningful data when this landed (approved reset), so instead of a
backfill this drops the single-user tables and recreates them scoped by
workspace, with composite (id, workspace_id) foreign keys so the database
refuses links across workspaces. Users sign in again and get a new account.

Revision ID: 0004_workspaces
Revises: 0003_uuids
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import slate.models

revision: str = "0004_workspaces"
down_revision: str | None = "0003_uuids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = slate.models.UTCDateTime(timezone=True)
OLD = ("task_labels", "activity", "comments", "tasks", "labels", "projects", "areas")


def _owned(name: str, *cols: sa.Column, extra: tuple = ()) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(32)),
        sa.Column("source_id", sa.String(128)),
        *cols,
        sa.UniqueConstraint("id", "workspace_id", name=f"uq_{name}_id_workspace"),
        sa.UniqueConstraint("workspace_id", "source", "source_id", name=f"uq_{name}_source"),
        *extra,
    )
    op.create_index(f"ix_{name}_workspace_id", name, ["workspace_id"])


def _ref(col: str, target: str, name: str, ondelete: str | None = None) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [col, "workspace_id"],
        [f"{target}.id", f"{target}.workspace_id"],
        name=name,
        ondelete=ondelete,
    )


def upgrade() -> None:
    for name in (*OLD, "settings", "users"):
        op.drop_table(name)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("issuer", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("last_login_at", TS, nullable=False),
        sa.UniqueConstraint("issuer", "subject"),
    )
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("next_task_number", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False, unique=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("last_used_at", TS),
        sa.Column("revoked_at", TS),
    )
    op.create_index("ix_api_keys_user", "api_keys", ["user_id"])

    _owned(
        "areas",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("color", sa.String(16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
    )
    _owned(
        "projects",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("area_id", sa.Uuid()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("target_date", sa.Date()),
        sa.Column("color", sa.String(16)),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        extra=(_ref("area_id", "areas", "fk_projects_area"),),
    )
    _owned(
        "labels",
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("color", sa.String(16), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
    )
    _owned(
        "tasks",
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Uuid()),
        sa.Column("area_id", sa.Uuid()),
        sa.Column("parent_id", sa.Uuid()),
        sa.Column("due_date", sa.Date()),
        sa.Column("due_time", sa.Time()),
        sa.Column("recurrence_rrule", sa.String(500)),
        sa.Column("recurrence_mode", sa.String(32)),
        sa.Column("recurrence_dtstart", sa.Date()),
        sa.Column("recurrence_time", sa.Time()),
        sa.Column("recurrence_text", sa.String(200)),
        sa.Column("completed_runs", sa.Integer(), nullable=False),
        sa.Column("completed_at", TS),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        extra=(
            sa.UniqueConstraint("workspace_id", "number", name="uq_tasks_number"),
            _ref("project_id", "projects", "fk_tasks_project"),
            _ref("area_id", "areas", "fk_tasks_area"),
            _ref("parent_id", "tasks", "fk_tasks_parent", "CASCADE"),
        ),
    )
    op.create_index("ix_tasks_due_date", "tasks", ["workspace_id", "due_date"])
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
    op.create_index("ix_tasks_parent_id", "tasks", ["parent_id"])
    op.create_table(
        "task_labels",
        sa.Column("task_id", sa.Uuid(), primary_key=True),
        sa.Column("label_id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        _ref("task_id", "tasks", "fk_task_labels_task", "CASCADE"),
        _ref("label_id", "labels", "fk_task_labels_label", "CASCADE"),
    )
    _owned(
        "comments",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        extra=(_ref("task_id", "tasks", "fk_comments_task", "CASCADE"),),
    )
    op.create_index("ix_comments_task", "comments", ["task_id"])
    op.create_table(
        "activity",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        _ref("task_id", "tasks", "fk_activity_task", "CASCADE"),
    )
    op.create_index("ix_activity_task", "activity", ["task_id"])


def downgrade() -> None:
    raise NotImplementedError("0004_workspaces reset the data; there is nothing to go back to")
