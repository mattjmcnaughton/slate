"""users table, keyed by identity provider (issuer, subject)

Revision ID: 0002_users
Revises: 7a92e1837ca3
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import slate.models

revision: str = "0002_users"
down_revision: str | None = "7a92e1837ca3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("issuer", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("created_at", slate.models.UTCDateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", slate.models.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issuer", "subject"),
    )


def downgrade() -> None:
    op.drop_table("users")
