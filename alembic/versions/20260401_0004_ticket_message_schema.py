from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260401_0004"
down_revision = "20260401_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticket_messages",
        sa.Column("ticket_message_id", sa.String(length=64), nullable=False),
        sa.Column("ticket_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("draft_id", sa.String(length=64), nullable=True),
        sa.Column("source_channel", sa.String(length=32), nullable=False, server_default="gmail"),
        sa.Column("source_thread_id", sa.String(length=255), nullable=False),
        sa.Column("source_message_id", sa.String(length=255), nullable=False),
        sa.Column("gmail_thread_id", sa.String(length=255), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("message_type", sa.String(length=64), nullable=False),
        sa.Column("sender_email", sa.String(length=320), nullable=True),
        sa.Column("recipient_emails", sa.JSON(), nullable=False),
        sa.Column("subject", sa.String(length=998), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("reply_to_source_message_id", sa.String(length=255), nullable=True),
        sa.Column("customer_visible", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("message_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_channel = 'gmail'",
            name="ck_ticket_messages_source_channel",
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.ticket_id"]),
        sa.ForeignKeyConstraint(["run_id"], ["ticket_runs.run_id"]),
        sa.ForeignKeyConstraint(["draft_id"], ["draft_artifacts.draft_id"]),
        sa.PrimaryKeyConstraint("ticket_message_id"),
        sa.UniqueConstraint(
            "source_channel",
            "source_message_id",
            name="uq_ticket_messages_source_message",
        ),
    )
    op.create_index("ix_ticket_messages_ticket_id", "ticket_messages", ["ticket_id"], unique=False)
    op.create_index("ix_ticket_messages_run_id", "ticket_messages", ["run_id"], unique=False)
    op.create_index("ix_ticket_messages_draft_id", "ticket_messages", ["draft_id"], unique=False)
    op.create_index(
        "ix_ticket_messages_message_timestamp",
        "ticket_messages",
        ["message_timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ticket_messages_message_timestamp", table_name="ticket_messages")
    op.drop_index("ix_ticket_messages_draft_id", table_name="ticket_messages")
    op.drop_index("ix_ticket_messages_run_id", table_name="ticket_messages")
    op.drop_index("ix_ticket_messages_ticket_id", table_name="ticket_messages")
    op.drop_table("ticket_messages")
