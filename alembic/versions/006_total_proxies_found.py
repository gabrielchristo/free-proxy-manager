"""add total_proxies_found to proxy_sources

Revision ID: 006
Revises: 005
Create Date: 2026-09-14 23:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, Sequence[str], None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("proxy_sources") as batch_op:
        batch_op.add_column(
            sa.Column(
                "total_proxies_found",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )

    op.execute(
        sa.text(
            """
            UPDATE proxy_sources
            SET total_proxies_found = (
                SELECT COUNT(*)
                FROM proxy_source_links
                WHERE proxy_source_links.source_id = proxy_sources.id
            )
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("proxy_sources") as batch_op:
        batch_op.drop_column("total_proxies_found")
