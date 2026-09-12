"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-22 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "proxy_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("last_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("proxies_found", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "proxies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("protocol", sa.String(length=20), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("anonymity", sa.String(length=50), nullable=True),
        sa.Column("status", sa.Enum("NEW", "CHECKING", "HEALTHY", "DEGRADED", "DEAD", "DISABLED", name="proxystatus"), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("connect_time_ms", sa.Float(), nullable=True),
        sa.Column("last_http_status", sa.Integer(), nullable=True),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cooldown_level", sa.Integer(), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("protocol", "host", "port", name="uq_proxy_identity"),
    )

    op.create_table(
        "proxy_source_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("proxy_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["proxy_id"], ["proxies.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["proxy_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proxy_id", "source_id", name="uq_proxy_source_link"),
    )


def downgrade() -> None:
    op.drop_table("proxy_source_links")
    op.drop_table("proxies")
    op.drop_table("proxy_sources")
