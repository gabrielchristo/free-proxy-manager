"""restore unique proxy identity on protocol+host+port

Revision ID: 008
Revises: 007
Create Date: 2026-09-15 00:30:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "008"
down_revision: Union[str, Sequence[str], None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("proxies") as batch_op:
        batch_op.drop_constraint("uq_proxy_identity", type_="unique")
        batch_op.create_unique_constraint(
            "uq_proxy_identity",
            ["protocol", "host", "port"],
        )


def downgrade() -> None:
    with op.batch_alter_table("proxies") as batch_op:
        batch_op.drop_constraint("uq_proxy_identity", type_="unique")
        batch_op.create_unique_constraint("uq_proxy_identity", ["host", "port"])
