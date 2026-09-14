"""dedupe proxies by host+port and normalize IP hosts

Revision ID: 005
Revises: 004
Create Date: 2026-09-14 22:45:00.000000

"""

from __future__ import annotations

import ipaddress
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, Sequence[str], None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUS_RANK = {
    "HEALTHY": 6,
    "DEGRADED": 5,
    "NEW": 4,
    "CHECKING": 3,
    "DEAD": 2,
    "DISABLED": 1,
}


def _normalize_host(host: str) -> str:
    cleaned = host.strip()
    if not cleaned:
        return cleaned

    if re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", cleaned):
        parts = cleaned.split(".")
        if len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
            return ".".join(str(int(part)) for part in parts)

    try:
        return str(ipaddress.ip_address(cleaned))
    except ValueError:
        return cleaned.lower().rstrip(".")


def _prefer_protocol(existing: str, incoming: str) -> str:
    rank = {"https": 2, "http": 1}
    if rank.get(incoming.lower(), 0) > rank.get(existing.lower(), 0):
        return incoming.lower()
    return existing.lower()


def upgrade() -> None:
    connection = op.get_bind()

    rows = connection.execute(
        sa.text(
            "SELECT id, host, port, protocol, status, success_count, failure_count, "
            "consecutive_failures, score, last_success, last_seen "
            "FROM proxies ORDER BY id"
        )
    ).mappings().all()

    normalized_rows = []
    for row in rows:
        normalized_rows.append(
            {
                **row,
                "normalized_host": _normalize_host(row["host"]),
            }
        )

    for row in normalized_rows:
        if row["normalized_host"] != row["host"]:
            connection.execute(
                sa.text("UPDATE proxies SET host = :host WHERE id = :id"),
                {"host": row["normalized_host"], "id": row["id"]},
            )
            row["host"] = row["normalized_host"]

    groups: dict[tuple[str, int], list[dict]] = {}
    for row in normalized_rows:
        key = (row["host"], row["port"])
        groups.setdefault(key, []).append(row)

    for (_host, _port), members in groups.items():
        if len(members) <= 1:
            continue

        members.sort(
            key=lambda item: (
                -STATUS_RANK.get(item["status"], 0),
                -(item["success_count"] or 0),
                item["id"],
            )
        )
        keeper = members[0]
        keeper_id = keeper["id"]
        keeper_protocol = keeper["protocol"]

        for duplicate in members[1:]:
            dup_id = duplicate["id"]
            keeper_protocol = _prefer_protocol(keeper_protocol, duplicate["protocol"])

            links = connection.execute(
                sa.text("SELECT id, source_id FROM proxy_source_links WHERE proxy_id = :proxy_id"),
                {"proxy_id": dup_id},
            ).mappings().all()

            for link in links:
                existing = connection.execute(
                    sa.text(
                        "SELECT id FROM proxy_source_links "
                        "WHERE proxy_id = :proxy_id AND source_id = :source_id"
                    ),
                    {"proxy_id": keeper_id, "source_id": link["source_id"]},
                ).first()
                if existing:
                    connection.execute(
                        sa.text("DELETE FROM proxy_source_links WHERE id = :id"),
                        {"id": link["id"]},
                    )
                else:
                    connection.execute(
                        sa.text(
                            "UPDATE proxy_source_links SET proxy_id = :keeper_id WHERE id = :id"
                        ),
                        {"keeper_id": keeper_id, "id": link["id"]},
                    )

            connection.execute(
                sa.text("DELETE FROM proxies WHERE id = :id"),
                {"id": dup_id},
            )

        connection.execute(
            sa.text("UPDATE proxies SET protocol = :protocol WHERE id = :id"),
            {"protocol": keeper_protocol, "id": keeper_id},
        )

    with op.batch_alter_table("proxies") as batch_op:
        batch_op.drop_constraint("uq_proxy_identity")
        batch_op.create_unique_constraint("uq_proxy_identity", ["host", "port"])


def downgrade() -> None:
    with op.batch_alter_table("proxies") as batch_op:
        batch_op.drop_constraint("uq_proxy_identity")
        batch_op.create_unique_constraint("uq_proxy_identity", ["protocol", "host", "port"])
