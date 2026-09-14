"""pool_snapshots table for historical pool charts

Revision ID: 004
Revises: 003
Create Date: 2026-09-14 17:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, Sequence[str], None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pool_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("total_proxies", sa.Integer(), nullable=False),
        sa.Column("healthy", sa.Integer(), nullable=False),
        sa.Column("degraded", sa.Integer(), nullable=False),
        sa.Column("dead", sa.Integer(), nullable=False),
        sa.Column("new", sa.Integer(), nullable=False),
        sa.Column("checking", sa.Integer(), nullable=False),
        sa.Column("disabled", sa.Integer(), nullable=False),
        sa.Column("in_cooldown", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pool_snapshots_recorded_at", "pool_snapshots", ["recorded_at"])


def downgrade() -> None:
    op.drop_index("ix_pool_snapshots_recorded_at", table_name="pool_snapshots")
    op.drop_table("pool_snapshots")
