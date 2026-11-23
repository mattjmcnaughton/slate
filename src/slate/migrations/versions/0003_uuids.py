"""public uuid next to the integer id on every entity table

Integer ids stay the primary and foreign keys; uuids are what URLs show.
Existing rows get a fresh uuid4.

Revision ID: 0003_uuids
Revises: 0002_users
Create Date: 2026-11-23
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_uuids"
down_revision: str | None = "0002_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("areas", "projects", "labels", "tasks", "comments", "users")


def upgrade() -> None:
    conn = op.get_bind()
    for name in TABLES:
        with op.batch_alter_table(name) as batch:
            batch.add_column(sa.Column("uuid", sa.Uuid(), nullable=True))
        table = sa.table(name, sa.column("id", sa.Integer()), sa.column("uuid", sa.Uuid()))
        for (row_id,) in conn.execute(sa.select(table.c.id)).all():
            conn.execute(table.update().where(table.c.id == row_id).values(uuid=uuid.uuid4()))
        with op.batch_alter_table(name) as batch:
            batch.alter_column("uuid", existing_type=sa.Uuid(), nullable=False)
            batch.create_unique_constraint(f"uq_{name}_uuid", ["uuid"])


def downgrade() -> None:
    for name in TABLES:
        with op.batch_alter_table(name) as batch:
            batch.drop_constraint(f"uq_{name}_uuid", type_="unique")
            batch.drop_column("uuid")
