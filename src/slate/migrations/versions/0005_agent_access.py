"""agent access: agent settings on workspaces, pending changes, sidebar messages

Additive. Agent settings live on the workspace (one per user for now), off by
default and in suggest mode.

Revision ID: 0005_agent_access
Revises: 0004_workspaces
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import slate.models

revision: str = "0005_agent_access"
down_revision: str | None = "0004_workspaces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = slate.models.UTCDateTime(timezone=True)


def upgrade() -> None:
    with op.batch_alter_table("workspaces") as b:
        b.add_column(
            sa.Column("agent_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        b.add_column(
            sa.Column("agent_mode", sa.String(16), nullable=False, server_default="suggest")
        )
        b.add_column(sa.Column("agent_instructions", sa.Text(), nullable=False, server_default=""))
    op.create_table(
        "pending_changes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tool", sa.String(64), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column(
            "created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("result", sa.JSON()),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("resolved_at", TS),
        sa.UniqueConstraint("id", "workspace_id", name="uq_pending_changes_id_workspace"),
    )
    op.create_index("ix_pending_changes_status", "pending_changes", ["workspace_id", "status"])
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("image_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pending_change_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index(
        "ix_agent_messages_user", "agent_messages", ["workspace_id", "user_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("agent_messages")
    op.drop_table("pending_changes")
    with op.batch_alter_table("workspaces") as b:
        b.drop_column("agent_instructions")
        b.drop_column("agent_mode")
        b.drop_column("agent_enabled")
