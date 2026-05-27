"""Drop financial automation tables.

The finan migration brought two domain-specific tables that backed the
removed `financial_record_store` / `financial_bill_store` / `record_store`
step types. With those handlers and their service layer gone, the tables
are orphan storage that we drop here.

Revision ID: 0101
Revises: 0100
Create Date: 2026-05-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0101"
down_revision: Union[str, None] = "0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


_LEGACY_CONFIG_KEYS = (
    "financial_automation_template", "financial_provider", "financial_unit_id",
    "financial_asset", "financial_address", "financial_customer_code",
    "financial_delivery_location", "financial_username_field", "financial_password_field",
    "financial_browser_timeout_ms", "financial_notification_enabled",
    "financial_notification_recipient", "financial_notification_agent_id",
    "financial_password_vault_integration_id", "financial_password_vault_provider",
    "financial_password_vault_vault_id", "financial_password_vault_vault_name",
    "financial_password_vault_item_id", "financial_password_vault_item_title",
    "financial_password_vault_field_name", "financial_password_vault_reference",
    "financial_parser_mode", "financial_record_kind", "financial_automation_key",
    "financial_subject_key", "financial_record", "financial_record_handle",
    "financial_record_handle_path", "financial_record_source_step",
    "financial_record_dedupe_key", "financial_record_key_fields",
    "financial_record_payload", "financial_source_step", "financial_dedupe_key",
    "financial_notify_on_update", "financial_bill_handle", "financial_bill_source_step",
    "financial_bill_source", "financial_bill",
    "parser_mode", "record_kind", "record_provider", "record_unit", "record_asset",
    "record_address", "record_automation_key", "record_source_step", "record_dedupe_key",
    "emit_record_handle", "emit_raw_handle", "emit_raw_bill_handle",
    "emit_financial_record_handle", "issue_record_handle", "raw_bill_handle",
)


def _strip_legacy_keys_from_flow_node_configs() -> None:
    """Strip the finan-migration keys from every flow_node.config_json blob.

    The keys are no longer in FlowStepConfig and no handler reads them, but they
    can still echo back through the API because `extra='allow'` lets unknown
    keys round-trip. Cleaning them once at migration time keeps the JSON shape
    consistent with the schema.
    """
    bind = op.get_bind()
    operands = " ".join(f"- :k{i}" for i in range(len(_LEGACY_CONFIG_KEYS)))
    params = {f"k{i}": key for i, key in enumerate(_LEGACY_CONFIG_KEYS)}
    likes = " OR ".join(
        f"config_json LIKE :like{i}" for i in range(len(_LEGACY_CONFIG_KEYS))
    )
    likes_params = {f"like{i}": f"%{key}%" for i, key in enumerate(_LEGACY_CONFIG_KEYS)}
    sql = sa.text(
        f"UPDATE flow_node "
        f"SET config_json = (config_json::jsonb {operands})::text "
        f"WHERE {likes}"
    )
    bind.execute(sql, {**params, **likes_params})


def upgrade() -> None:
    _strip_legacy_keys_from_flow_node_configs()

    if _has_table("financial_automation_record"):
        for index_name in (
            "idx_financial_automation_record_period",
            "idx_financial_automation_record_provider",
            "idx_financial_automation_record_tenant_type",
            "ix_financial_automation_record_provider",
            "ix_financial_automation_record_automation_key",
            "ix_financial_automation_record_record_type",
            "ix_financial_automation_record_tenant_id",
        ):
            if index_name in _indexes("financial_automation_record"):
                op.drop_index(index_name, table_name="financial_automation_record")
        op.drop_table("financial_automation_record")

    if _has_table("financial_utility_bill"):
        for index_name in (
            "idx_financial_utility_bill_due_date",
            "idx_financial_utility_bill_tenant_provider",
            "ix_financial_utility_bill_automation_key",
            "ix_financial_utility_bill_tenant_id",
        ):
            if index_name in _indexes("financial_utility_bill"):
                op.drop_index(index_name, table_name="financial_utility_bill")
        op.drop_table("financial_utility_bill")


def downgrade() -> None:
    # No-op: the column definitions and model classes have been removed.
    # Restoring the tables would require reverting code as well; downgrade
    # only exists to keep alembic happy if someone walks back the history.
    pass
