from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260401_0003"
down_revision = "20260401_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_memory_profiles",
        sa.Column("customer_id", sa.String(length=255), nullable=False),
        sa.Column("primary_email", sa.String(length=320), nullable=False),
        sa.Column("alias_emails", sa.JSON(), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("risk_tags", sa.JSON(), nullable=False),
        sa.Column("business_flags", sa.JSON(), nullable=False),
        sa.Column("historical_case_refs", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("version >= 1", name="ck_customer_memory_profiles_version"),
        sa.PrimaryKeyConstraint("customer_id"),
    )
    op.create_index(
        "ix_customer_memory_profiles_updated_at",
        "customer_memory_profiles",
        ["updated_at"],
        unique=False,
    )

    op.create_table(
        "customer_memory_events",
        sa.Column("memory_event_id", sa.String(length=64), nullable=False),
        sa.Column("customer_id", sa.String(length=255), nullable=False),
        sa.Column("ticket_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("source_stage", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customer_memory_profiles.customer_id"],
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.ticket_id"]),
        sa.ForeignKeyConstraint(["run_id"], ["ticket_runs.run_id"]),
        sa.PrimaryKeyConstraint("memory_event_id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_customer_memory_events_idempotency_key",
        ),
    )
    op.create_index(
        "ix_customer_memory_events_customer_id",
        "customer_memory_events",
        ["customer_id"],
        unique=False,
    )
    op.create_index(
        "ix_customer_memory_events_ticket_id",
        "customer_memory_events",
        ["ticket_id"],
        unique=False,
    )
    op.create_index(
        "ix_customer_memory_events_run_id",
        "customer_memory_events",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_customer_memory_events_created_at",
        "customer_memory_events",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_memory_events_created_at",
        table_name="customer_memory_events",
    )
    op.drop_index(
        "ix_customer_memory_events_run_id",
        table_name="customer_memory_events",
    )
    op.drop_index(
        "ix_customer_memory_events_ticket_id",
        table_name="customer_memory_events",
    )
    op.drop_index(
        "ix_customer_memory_events_customer_id",
        table_name="customer_memory_events",
    )
    op.drop_table("customer_memory_events")

    op.drop_index(
        "ix_customer_memory_profiles_updated_at",
        table_name="customer_memory_profiles",
    )
    op.drop_table("customer_memory_profiles")
