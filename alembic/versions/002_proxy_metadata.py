"""proxy metadata fields

Revision ID: 002
Revises: 001
Create Date: 2026-09-13 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, Sequence[str], None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("proxies") as batch_op:
        batch_op.add_column(sa.Column("city", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("isp", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("asn", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("org", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("ssl", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("source_latency_ms", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("source_uptime_percent", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("source_speed", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("source_last_checked", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("last_error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("metadata", sa.JSON(), nullable=True))

    with op.batch_alter_table("proxy_source_links") as batch_op:
        batch_op.add_column(sa.Column("source_metadata", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("proxy_source_links") as batch_op:
        batch_op.drop_column("source_metadata")

    with op.batch_alter_table("proxies") as batch_op:
        batch_op.drop_column("metadata")
        batch_op.drop_column("last_error")
        batch_op.drop_column("source_last_checked")
        batch_op.drop_column("source_speed")
        batch_op.drop_column("source_uptime_percent")
        batch_op.drop_column("source_latency_ms")
        batch_op.drop_column("ssl")
        batch_op.drop_column("org")
        batch_op.drop_column("asn")
        batch_op.drop_column("isp")
        batch_op.drop_column("city")
