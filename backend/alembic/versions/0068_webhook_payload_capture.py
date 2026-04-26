"""Add webhook_payload_capture ringbuffer table.

Revision ID: 0068
Revises: 0067
Create Date: 2026-04-26

Wave 1 of the Triggers↔Flows Unification (release/0.7.0).

Stores the last N (default 5) inbound payloads per webhook integration
for schema inference in the Flow editor's Source-step variable
autocomplete. The ringbuffer is enforced application-side in
``routes_webhook_inbound.py`` after dispatch — DELETE the rows older
than the 5th most recent for the same ``(tenant_id, webhook_id)``.

Wave 5 wires this into the frontend's DynamicSourceFieldsProvider so
``{{source.payload.<inferred>}}`` autocomplete reflects what the
endpoint actually received in the last 5 deliveries.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0068"
down_revision: Union[str, None] = "0067"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade() -> None:
    if not _has_table("webhook_payload_capture"):
        op.create_table(
            "webhook_payload_capture",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "tenant_id",
                sa.String(length=50),
                sa.ForeignKey("tenant.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "webhook_id",
                sa.Integer(),
                sa.ForeignKey("webhook_integration.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "captured_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
            # payload truncated to ~64KB application-side at write time;
            # raw text not parsed at write — read-side does JSON.parse.
            sa.Column("payload_json", sa.Text(), nullable=False),
            # minimally redacted (auth/cookie headers stripped); nullable.
            sa.Column("headers_json", sa.Text(), nullable=True),
            sa.Column("dedupe_key", sa.String(length=512), nullable=True),
        )

    indexes = _indexes("webhook_payload_capture")
    if "ix_webhook_payload_capture_recent" not in indexes:
        op.create_index(
            "ix_webhook_payload_capture_recent",
            "webhook_payload_capture",
            ["tenant_id", "webhook_id", "captured_at"],
        )


def downgrade() -> None:
    if _has_table("webhook_payload_capture"):
        if "ix_webhook_payload_capture_recent" in _indexes("webhook_payload_capture"):
            op.drop_index(
                "ix_webhook_payload_capture_recent",
                table_name="webhook_payload_capture",
            )
        op.drop_table("webhook_payload_capture")
