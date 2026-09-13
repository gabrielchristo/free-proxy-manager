"""proxy was_dead flag for recheck deprioritization

Revision ID: 003
Revises: 002
Create Date: 2026-09-13 07:45:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, Sequence[str], None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("proxies") as batch_op:
        batch_op.add_column(
            sa.Column(
                "was_dead",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    op.execute(
        sa.text(
            "UPDATE proxies SET was_dead = 1 "
            "WHERE status = 'DEAD' OR cooldown_level > 0"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("proxies") as batch_op:
        batch_op.drop_column("was_dead")
