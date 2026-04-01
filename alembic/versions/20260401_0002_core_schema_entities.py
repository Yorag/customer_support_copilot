from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260401_0002"
down_revision = "20260331_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("ticket_id", sa.String(length=64), nullable=False),
        sa.Column("source_channel", sa.String(length=32), nullable=False, server_default="gmail"),
        sa.Column("source_thread_id", sa.String(length=255), nullable=False),
        sa.Column("source_message_id", sa.String(length=255), nullable=False),
        sa.Column("gmail_thread_id", sa.String(length=255), nullable=False),
        sa.Column("gmail_draft_id", sa.String(length=255), nullable=True),
        sa.Column("customer_id", sa.String(length=255), nullable=True),
        sa.Column("customer_email", sa.String(length=320), nullable=False),
        sa.Column("customer_email_raw", sa.String(length=512), nullable=False),
        sa.Column("subject", sa.String(length=998), nullable=False),
        sa.Column("latest_message_excerpt", sa.Text(), nullable=True),
        sa.Column("business_status", sa.String(length=64), nullable=False),
        sa.Column("processing_status", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("primary_route", sa.String(length=64), nullable=True),
        sa.Column("secondary_routes", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("response_strategy", sa.String(length=64), nullable=True),
        sa.Column("multi_intent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("needs_clarification", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("needs_escalation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("intent_confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("routing_reason", sa.Text(), nullable=True),
        sa.Column("risk_reasons", sa.JSON(), nullable=False),
        sa.Column("current_run_id", sa.String(length=64), nullable=True),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=128), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("reopen_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("source_channel = 'gmail'", name="ck_tickets_source_channel"),
        sa.CheckConstraint("reopen_count >= 0", name="ck_tickets_reopen_count"),
        sa.CheckConstraint("version >= 1", name="ck_tickets_version"),
        sa.CheckConstraint(
            "intent_confidence IS NULL OR (intent_confidence >= 0 AND intent_confidence <= 1)",
            name="ck_tickets_intent_confidence",
        ),
        sa.PrimaryKeyConstraint("ticket_id"),
        sa.UniqueConstraint(
            "source_channel",
            "source_thread_id",
            "is_active",
            name="uq_tickets_source_thread_active",
        ),
        sa.UniqueConstraint(
            "gmail_thread_id",
            "is_active",
            name="uq_tickets_gmail_thread_active",
        ),
    )
    op.create_index("ix_tickets_created_at", "tickets", ["created_at"], unique=False)
    op.create_index("ix_tickets_customer_id", "tickets", ["customer_id"], unique=False)
    op.create_index("ix_tickets_current_run_id", "tickets", ["current_run_id"], unique=False)
    op.create_index("ix_tickets_processing_status", "tickets", ["processing_status"], unique=False)
    op.create_index("ix_tickets_business_status", "tickets", ["business_status"], unique=False)

    op.create_table(
        "ticket_runs",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("ticket_id", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("triggered_by", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("final_action", sa.String(length=64), nullable=True),
        sa.Column("final_node", sa.String(length=255), nullable=True),
        sa.Column("attempt_index", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("latency_metrics", sa.JSON(), nullable=True),
        sa.Column("resource_metrics", sa.JSON(), nullable=True),
        sa.Column("response_quality", sa.JSON(), nullable=True),
        sa.Column("trajectory_evaluation", sa.JSON(), nullable=True),
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
        sa.CheckConstraint("attempt_index >= 1", name="ck_ticket_runs_attempt_index"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.ticket_id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index("ix_ticket_runs_ticket_id", "ticket_runs", ["ticket_id"], unique=False)
    op.create_index("ix_ticket_runs_trace_id", "ticket_runs", ["trace_id"], unique=False)
    op.create_index("ix_ticket_runs_started_at", "ticket_runs", ["started_at"], unique=False)

    op.create_table(
        "draft_artifacts",
        sa.Column("draft_id", sa.String(length=64), nullable=False),
        sa.Column("ticket_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("version_index", sa.Integer(), nullable=False),
        sa.Column("draft_type", sa.String(length=64), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("content_html", sa.Text(), nullable=True),
        sa.Column("source_evidence_summary", sa.Text(), nullable=True),
        sa.Column("qa_status", sa.String(length=32), nullable=False),
        sa.Column("qa_feedback", sa.JSON(), nullable=True),
        sa.Column("gmail_draft_id", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("version_index >= 1", name="ck_draft_artifacts_version_index"),
        sa.ForeignKeyConstraint(["run_id"], ["ticket_runs.run_id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.ticket_id"]),
        sa.PrimaryKeyConstraint("draft_id"),
        sa.UniqueConstraint(
            "ticket_id",
            "run_id",
            "version_index",
            name="uq_draft_artifacts_ticket_run_version",
        ),
    )
    op.create_index("ix_draft_artifacts_ticket_id", "draft_artifacts", ["ticket_id"], unique=False)
    op.create_index("ix_draft_artifacts_run_id", "draft_artifacts", ["run_id"], unique=False)
    op.create_index("ix_draft_artifacts_created_at", "draft_artifacts", ["created_at"], unique=False)

    op.create_table(
        "human_reviews",
        sa.Column("review_id", sa.String(length=64), nullable=False),
        sa.Column("ticket_id", sa.String(length=64), nullable=False),
        sa.Column("draft_id", sa.String(length=64), nullable=True),
        sa.Column("reviewer_id", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("edited_content_text", sa.Text(), nullable=True),
        sa.Column("edited_content_html", sa.Text(), nullable=True),
        sa.Column("requested_rewrite_reason", sa.JSON(), nullable=True),
        sa.Column("target_queue", sa.String(length=255), nullable=True),
        sa.Column("ticket_version_at_review", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["draft_id"], ["draft_artifacts.draft_id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.ticket_id"]),
        sa.PrimaryKeyConstraint("review_id"),
    )
    op.create_index("ix_human_reviews_ticket_id", "human_reviews", ["ticket_id"], unique=False)
    op.create_index("ix_human_reviews_draft_id", "human_reviews", ["draft_id"], unique=False)
    op.create_index("ix_human_reviews_created_at", "human_reviews", ["created_at"], unique=False)

    op.create_table(
        "trace_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("ticket_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("event_name", sa.String(length=255), nullable=False),
        sa.Column("node_name", sa.String(length=255), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["ticket_runs.run_id"]),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.ticket_id"]),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_trace_events_trace_id", "trace_events", ["trace_id"], unique=False)
    op.create_index("ix_trace_events_run_id", "trace_events", ["run_id"], unique=False)
    op.create_index("ix_trace_events_ticket_id", "trace_events", ["ticket_id"], unique=False)
    op.create_index("ix_trace_events_start_time", "trace_events", ["start_time"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_trace_events_start_time", table_name="trace_events")
    op.drop_index("ix_trace_events_ticket_id", table_name="trace_events")
    op.drop_index("ix_trace_events_run_id", table_name="trace_events")
    op.drop_index("ix_trace_events_trace_id", table_name="trace_events")
    op.drop_table("trace_events")

    op.drop_index("ix_human_reviews_created_at", table_name="human_reviews")
    op.drop_index("ix_human_reviews_draft_id", table_name="human_reviews")
    op.drop_index("ix_human_reviews_ticket_id", table_name="human_reviews")
    op.drop_table("human_reviews")

    op.drop_index("ix_draft_artifacts_created_at", table_name="draft_artifacts")
    op.drop_index("ix_draft_artifacts_run_id", table_name="draft_artifacts")
    op.drop_index("ix_draft_artifacts_ticket_id", table_name="draft_artifacts")
    op.drop_table("draft_artifacts")

    op.drop_index("ix_ticket_runs_started_at", table_name="ticket_runs")
    op.drop_index("ix_ticket_runs_trace_id", table_name="ticket_runs")
    op.drop_index("ix_ticket_runs_ticket_id", table_name="ticket_runs")
    op.drop_table("ticket_runs")

    op.drop_index("ix_tickets_business_status", table_name="tickets")
    op.drop_index("ix_tickets_processing_status", table_name="tickets")
    op.drop_index("ix_tickets_current_run_id", table_name="tickets")
    op.drop_index("ix_tickets_customer_id", table_name="tickets")
    op.drop_index("ix_tickets_created_at", table_name="tickets")
    op.drop_table("tickets")
