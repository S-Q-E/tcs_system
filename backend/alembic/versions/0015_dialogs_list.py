"""Cache last-message summary on conversation state (step 9C)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_dialogs_list"
down_revision = "0014_notify_dedupe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tcs_crm_conversation_state",
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tcs_crm_conversation_state",
        sa.Column("last_message_direction", sa.Text(), nullable=True),
    )
    op.add_column(
        "tcs_crm_conversation_state",
        sa.Column("last_message_preview", sa.Text(), nullable=True),
    )
    # tcs_* tables are owned by the bot and may be absent (fresh database):
    # guard the backfill the same way 0009 and 0022 do.
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'tcs_messages') THEN "
            "UPDATE tcs_crm_conversation_state s SET"
            " last_message_at = m.created_at,"
            " last_message_direction = m.direction,"
            " last_message_preview = LEFT(m.content, 200)"
            " FROM (SELECT DISTINCT ON (whatsapp_id) whatsapp_id, direction,"
            " content, created_at FROM tcs_messages"
            " ORDER BY whatsapp_id, created_at DESC, id DESC) m"
            " WHERE m.whatsapp_id = s.whatsapp_id; "
            "END IF; END $$"
        )
    )


def downgrade() -> None:
    op.drop_column("tcs_crm_conversation_state", "last_message_preview")
    op.drop_column("tcs_crm_conversation_state", "last_message_direction")
    op.drop_column("tcs_crm_conversation_state", "last_message_at")
