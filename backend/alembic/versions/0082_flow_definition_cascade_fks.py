"""Add ON DELETE CASCADE to flow_node, flow_run, flow_node_run FKs.

The trigger-delete cascade safety net in 0081 fails when a system-owned
FlowDefinition is deleted because flow_node and flow_run still reference it
with NO ACTION. This migration upgrades those FKs to CASCADE so deleting a
flow_definition row also removes its child flow_node + flow_run + flow_node_run
rows. case_memory.flow_run_id stays SET NULL (cases survive flow run deletion
intentionally — long-term memory shouldn't disappear when a flow is removed).

Combined with 0081, the cascade chain is:
  trigger (webhook/email/jira/github) DELETE
    -> trg_*_cascade_delete BEFORE trigger fires
       -> fn_cascade_trigger_delete()
          -> DELETE flow_definition (system-owned, no other binding refs)
             -> CASCADE: flow_node + flow_run -> flow_node_run

Revision ID: 0082
Revises: 0081
Create Date: 2026-05-03
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0082"
down_revision: Union[str, None] = "0081"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # flow_node -> flow_definition: NO ACTION -> CASCADE
    op.execute("ALTER TABLE flow_node DROP CONSTRAINT flow_node_flow_definition_id_fkey;")
    op.execute(
        "ALTER TABLE flow_node ADD CONSTRAINT flow_node_flow_definition_id_fkey "
        "FOREIGN KEY (flow_definition_id) REFERENCES flow_definition(id) ON DELETE CASCADE;"
    )

    # flow_run -> flow_definition: NO ACTION -> CASCADE
    op.execute("ALTER TABLE flow_run DROP CONSTRAINT flow_run_flow_definition_id_fkey;")
    op.execute(
        "ALTER TABLE flow_run ADD CONSTRAINT flow_run_flow_definition_id_fkey "
        "FOREIGN KEY (flow_definition_id) REFERENCES flow_definition(id) ON DELETE CASCADE;"
    )

    # flow_node_run -> flow_node: NO ACTION -> CASCADE
    op.execute("ALTER TABLE flow_node_run DROP CONSTRAINT flow_node_run_flow_node_id_fkey;")
    op.execute(
        "ALTER TABLE flow_node_run ADD CONSTRAINT flow_node_run_flow_node_id_fkey "
        "FOREIGN KEY (flow_node_id) REFERENCES flow_node(id) ON DELETE CASCADE;"
    )

    # flow_node_run -> flow_run: NO ACTION -> CASCADE
    op.execute("ALTER TABLE flow_node_run DROP CONSTRAINT flow_node_run_flow_run_id_fkey;")
    op.execute(
        "ALTER TABLE flow_node_run ADD CONSTRAINT flow_node_run_flow_run_id_fkey "
        "FOREIGN KEY (flow_run_id) REFERENCES flow_run(id) ON DELETE CASCADE;"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE flow_node_run DROP CONSTRAINT flow_node_run_flow_run_id_fkey;")
    op.execute(
        "ALTER TABLE flow_node_run ADD CONSTRAINT flow_node_run_flow_run_id_fkey "
        "FOREIGN KEY (flow_run_id) REFERENCES flow_run(id);"
    )
    op.execute("ALTER TABLE flow_node_run DROP CONSTRAINT flow_node_run_flow_node_id_fkey;")
    op.execute(
        "ALTER TABLE flow_node_run ADD CONSTRAINT flow_node_run_flow_node_id_fkey "
        "FOREIGN KEY (flow_node_id) REFERENCES flow_node(id);"
    )
    op.execute("ALTER TABLE flow_run DROP CONSTRAINT flow_run_flow_definition_id_fkey;")
    op.execute(
        "ALTER TABLE flow_run ADD CONSTRAINT flow_run_flow_definition_id_fkey "
        "FOREIGN KEY (flow_definition_id) REFERENCES flow_definition(id);"
    )
    op.execute("ALTER TABLE flow_node DROP CONSTRAINT flow_node_flow_definition_id_fkey;")
    op.execute(
        "ALTER TABLE flow_node ADD CONSTRAINT flow_node_flow_definition_id_fkey "
        "FOREIGN KEY (flow_definition_id) REFERENCES flow_definition(id);"
    )
