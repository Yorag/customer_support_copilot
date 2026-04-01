from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    event,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates

from src.core_schema import (
    DraftQaStatus,
    DraftType,
    HumanReviewAction,
    INITIAL_VERSION,
    MemoryEventType,
    MemorySourceStage,
    MessageDirection,
    MessageType,
    ResponseStrategy,
    RunFinalAction,
    RunStatus,
    RunTriggerType,
    SourceChannel,
    TicketBusinessStatus,
    TicketPriority,
    TicketProcessingStatus,
    TicketRoute,
    TicketTag,
    TraceEventStatus,
    TraceEventType,
    ensure_timezone_aware,
    normalize_ticket_routing,
    validate_source_channel,
)

from .base import Base


JSON_FIELD = JSON().with_variant(JSONB(), "postgresql")


def _enum_values(enum_cls) -> tuple[str, ...]:
    return tuple(item.value for item in enum_cls)


def _ensure_allowed_value(
    value: str | None,
    *,
    field_name: str,
    allowed_values: tuple[str, ...],
    nullable: bool = False,
) -> str | None:
    if value is None:
        if nullable:
            return None
        raise ValueError(f"{field_name} is required.")

    if value not in allowed_values:
        allowed_text = ", ".join(allowed_values)
        raise ValueError(
            f"Unsupported {field_name} `{value}`. Allowed values: {allowed_text}."
        )

    return value


def _ensure_fixed_object_keys(
    value: dict[str, Any] | None,
    *,
    field_name: str,
    required_keys: set[str],
) -> dict[str, Any] | None:
    if value is None:
        return None

    actual_keys = set(value.keys())
    if actual_keys != required_keys:
        expected_text = ", ".join(sorted(required_keys))
        actual_text = ", ".join(sorted(actual_keys))
        raise ValueError(
            f"{field_name} must use fixed keys [{expected_text}], got [{actual_text}]."
        )

    return value


def _ensure_trace_metadata_keys(
    *,
    event_type: str,
    metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    required_keys_by_type = {
        TraceEventType.LLM_CALL.value: {
            "model",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        },
        TraceEventType.TOOL_CALL.value: {"tool_name", "input_ref", "output_ref"},
        TraceEventType.DECISION.value: {
            "primary_route",
            "response_strategy",
            "needs_clarification",
            "needs_escalation",
            "final_action",
        },
    }
    required_keys = required_keys_by_type.get(event_type)
    if required_keys is None or metadata is None:
        return metadata

    missing = sorted(required_keys.difference(metadata.keys()))
    if missing:
        missing_text = ", ".join(missing)
        raise ValueError(
            f"metadata for event_type `{event_type}` is missing required keys: "
            f"{missing_text}."
        )

    return metadata


def _ensure_required_string_list(
    value: list[str] | None,
    *,
    field_name: str,
) -> list[str]:
    if value is None:
        raise ValueError(f"{field_name} is required.")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field_name} must be a list of non-empty strings.")
    return value


class AppMetadata(Base):
    """Generic bootstrap table for infrastructure-level metadata."""

    __tablename__ = "app_metadata"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint(
            "source_channel",
            "source_thread_id",
            "is_active",
            name="uq_tickets_source_thread_active",
        ),
        UniqueConstraint(
            "gmail_thread_id",
            "is_active",
            name="uq_tickets_gmail_thread_active",
        ),
        CheckConstraint("source_channel = 'gmail'", name="ck_tickets_source_channel"),
        CheckConstraint("reopen_count >= 0", name="ck_tickets_reopen_count"),
        CheckConstraint("version >= 1", name="ck_tickets_version"),
        CheckConstraint(
            "intent_confidence IS NULL OR "
            "(intent_confidence >= 0 AND intent_confidence <= 1)",
            name="ck_tickets_intent_confidence",
        ),
    )

    ticket_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_channel: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SourceChannel.GMAIL.value,
        server_default=SourceChannel.GMAIL.value,
    )
    source_thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    gmail_thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    gmail_draft_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    customer_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    customer_email: Mapped[str] = mapped_column(String(320), nullable=False)
    customer_email_raw: Mapped[str] = mapped_column(String(512), nullable=False)
    subject: Mapped[str] = mapped_column(String(998), nullable=False)
    latest_message_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_status: Mapped[str] = mapped_column(String(64), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[str] = mapped_column(String(32), nullable=False)
    primary_route: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    secondary_routes: Mapped[list[str]] = mapped_column(
        JSON_FIELD,
        nullable=False,
        default=list,
    )
    tags: Mapped[list[str]] = mapped_column(JSON_FIELD, nullable=False, default=list)
    response_strategy: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    multi_intent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    needs_clarification: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    needs_escalation: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    intent_confidence: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(4, 3),
        nullable=True,
    )
    routing_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risk_reasons: Mapped[list[str]] = mapped_column(
        JSON_FIELD,
        nullable=False,
        default=list,
    )
    current_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    lease_owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reopen_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=INITIAL_VERSION,
        server_default=str(INITIAL_VERSION),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    @validates("source_channel")
    def _validate_source_channel(self, key: str, value: str) -> str:
        return validate_source_channel(value).value

    @validates("business_status")
    def _validate_business_status(self, key: str, value: str) -> str:
        return _ensure_allowed_value(
            value,
            field_name=key,
            allowed_values=_enum_values(TicketBusinessStatus),
        )

    @validates("processing_status")
    def _validate_processing_status(self, key: str, value: str) -> str:
        return _ensure_allowed_value(
            value,
            field_name=key,
            allowed_values=_enum_values(TicketProcessingStatus),
        )

    @validates("priority")
    def _validate_priority(self, key: str, value: str) -> str:
        return _ensure_allowed_value(
            value,
            field_name=key,
            allowed_values=_enum_values(TicketPriority),
        )

    @validates("primary_route")
    def _validate_primary_route(self, key: str, value: str | None) -> str | None:
        return _ensure_allowed_value(
            value,
            field_name=key,
            allowed_values=_enum_values(TicketRoute),
            nullable=True,
        )

    @validates("response_strategy")
    def _validate_response_strategy(self, key: str, value: str | None) -> str | None:
        return _ensure_allowed_value(
            value,
            field_name=key,
            allowed_values=_enum_values(ResponseStrategy),
            nullable=True,
        )

    @validates("version")
    def _validate_version(self, key: str, value: int) -> int:
        if value < INITIAL_VERSION:
            raise ValueError(f"{key} must be >= {INITIAL_VERSION}.")
        return value

    @validates("reopen_count")
    def _validate_reopen_count(self, key: str, value: int) -> int:
        if value < 0:
            raise ValueError(f"{key} must be >= 0.")
        return value

    @validates("intent_confidence")
    def _validate_intent_confidence(
        self,
        key: str,
        value: Decimal | None,
    ) -> Decimal | None:
        if value is None:
            return value
        if value < 0 or value > 1:
            raise ValueError(f"{key} must be between 0 and 1.")
        return value

    @validates("lease_expires_at", "created_at", "updated_at", "closed_at")
    def _validate_datetimes(
        self,
        key: str,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return value
        return ensure_timezone_aware(value)

Index("ix_tickets_created_at", Ticket.created_at)
Index("ix_tickets_customer_id", Ticket.customer_id)
Index("ix_tickets_current_run_id", Ticket.current_run_id)
Index("ix_tickets_processing_status", Ticket.processing_status)
Index("ix_tickets_business_status", Ticket.business_status)


class TicketRun(Base):
    __tablename__ = "ticket_runs"
    __table_args__ = (
        CheckConstraint("attempt_index >= 1", name="ck_ticket_runs_attempt_index"),
    )

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tickets.ticket_id"),
        nullable=False,
        index=True,
    )
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False)
    triggered_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    final_action: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    final_node: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    attempt_index: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latency_metrics: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON_FIELD,
        nullable=True,
    )
    resource_metrics: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON_FIELD,
        nullable=True,
    )
    response_quality: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON_FIELD,
        nullable=True,
    )
    trajectory_evaluation: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON_FIELD,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    @validates("trigger_type")
    def _validate_trigger_type(self, key: str, value: str) -> str:
        return _ensure_allowed_value(
            value,
            field_name=key,
            allowed_values=_enum_values(RunTriggerType),
        )

    @validates("status")
    def _validate_status(self, key: str, value: str) -> str:
        return _ensure_allowed_value(
            value,
            field_name=key,
            allowed_values=_enum_values(RunStatus),
        )

    @validates("final_action")
    def _validate_final_action(self, key: str, value: str | None) -> str | None:
        return _ensure_allowed_value(
            value,
            field_name=key,
            allowed_values=_enum_values(RunFinalAction),
            nullable=True,
        )

    @validates("attempt_index")
    def _validate_attempt_index(self, key: str, value: int) -> int:
        if value < 1:
            raise ValueError(f"{key} must be >= 1.")
        return value

    @validates("started_at", "ended_at", "created_at", "updated_at")
    def _validate_datetimes(
        self,
        key: str,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return value
        return ensure_timezone_aware(value)

    @validates("response_quality")
    def _validate_response_quality(
        self,
        key: str,
        value: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        return _ensure_fixed_object_keys(
            value,
            field_name=key,
            required_keys={"overall_score", "subscores", "reason"},
        )

    @validates("trajectory_evaluation")
    def _validate_trajectory_evaluation(
        self,
        key: str,
        value: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        return _ensure_fixed_object_keys(
            value,
            field_name=key,
            required_keys={"score", "expected_route", "actual_route", "violations"},
        )


Index("ix_ticket_runs_started_at", TicketRun.started_at)


class DraftArtifact(Base):
    __tablename__ = "draft_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "ticket_id",
            "run_id",
            "version_index",
            name="uq_draft_artifacts_ticket_run_version",
        ),
        CheckConstraint("version_index >= 1", name="ck_draft_artifacts_version_index"),
    )

    draft_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tickets.ticket_id"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ticket_runs.run_id"),
        nullable=False,
        index=True,
    )
    version_index: Mapped[int] = mapped_column(Integer, nullable=False)
    draft_type: Mapped[str] = mapped_column(String(64), nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_evidence_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qa_status: Mapped[str] = mapped_column(String(32), nullable=False)
    qa_feedback: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON_FIELD,
        nullable=True,
    )
    gmail_draft_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("draft_type")
    def _validate_draft_type(self, key: str, value: str) -> str:
        return _ensure_allowed_value(
            value,
            field_name=key,
            allowed_values=_enum_values(DraftType),
        )

    @validates("qa_status")
    def _validate_qa_status(self, key: str, value: str) -> str:
        return _ensure_allowed_value(
            value,
            field_name=key,
            allowed_values=_enum_values(DraftQaStatus),
        )

    @validates("version_index")
    def _validate_version_index(self, key: str, value: int) -> int:
        if value < 1:
            raise ValueError(f"{key} must be >= 1.")
        return value

    @validates("created_at")
    def _validate_created_at(self, key: str, value: datetime) -> datetime:
        return ensure_timezone_aware(value)


Index("ix_draft_artifacts_created_at", DraftArtifact.created_at)


class HumanReview(Base):
    __tablename__ = "human_reviews"

    review_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tickets.ticket_id"),
        nullable=False,
        index=True,
    )
    draft_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("draft_artifacts.draft_id"),
        nullable=True,
        index=True,
    )
    reviewer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    edited_content_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    edited_content_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_rewrite_reason: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON_FIELD,
        nullable=True,
    )
    target_queue: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ticket_version_at_review: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("action")
    def _validate_action(self, key: str, value: str) -> str:
        return _ensure_allowed_value(
            value,
            field_name=key,
            allowed_values=_enum_values(HumanReviewAction),
        )

    @validates("ticket_version_at_review")
    def _validate_ticket_version_at_review(self, key: str, value: int) -> int:
        if value < INITIAL_VERSION:
            raise ValueError(f"{key} must be >= {INITIAL_VERSION}.")
        return value

    @validates("created_at")
    def _validate_created_at(self, key: str, value: datetime) -> datetime:
        return ensure_timezone_aware(value)


Index("ix_human_reviews_created_at", HumanReview.created_at)


class TraceEvent(Base):
    __tablename__ = "trace_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ticket_runs.run_id"),
        nullable=False,
        index=True,
    )
    ticket_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tickets.ticket_id"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    event_name: Mapped[str] = mapped_column(String(255), nullable=False)
    node_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    event_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata",
        JSON_FIELD,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("event_type")
    def _validate_event_type(self, key: str, value: str) -> str:
        return _ensure_allowed_value(
            value,
            field_name=key,
            allowed_values=_enum_values(TraceEventType),
        )

    @validates("status")
    def _validate_status(self, key: str, value: str) -> str:
        return _ensure_allowed_value(
            value,
            field_name=key,
            allowed_values=_enum_values(TraceEventStatus),
        )

    @validates("start_time", "end_time", "created_at")
    def _validate_datetimes(
        self,
        key: str,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return value
        return ensure_timezone_aware(value)

Index("ix_trace_events_start_time", TraceEvent.start_time)


class CustomerMemoryProfile(Base):
    __tablename__ = "customer_memory_profiles"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_customer_memory_profiles_version"),
    )

    customer_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    primary_email: Mapped[str] = mapped_column(String(320), nullable=False)
    alias_emails: Mapped[list[str]] = mapped_column(JSON_FIELD, nullable=False, default=list)
    profile: Mapped[dict[str, Any]] = mapped_column(JSON_FIELD, nullable=False)
    risk_tags: Mapped[list[str]] = mapped_column(JSON_FIELD, nullable=False, default=list)
    business_flags: Mapped[dict[str, Any]] = mapped_column(JSON_FIELD, nullable=False)
    historical_case_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_FIELD,
        nullable=False,
        default=list,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=INITIAL_VERSION,
        server_default=str(INITIAL_VERSION),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    @validates("customer_id", "primary_email")
    def _validate_required_strings(self, key: str, value: str) -> str:
        if value is None or not value.strip():
            raise ValueError(f"{key} is required.")
        return value.strip()

    @validates("alias_emails", "risk_tags")
    def _validate_string_lists(self, key: str, value: list[str]) -> list[str]:
        return _ensure_required_string_list(value, field_name=key)

    @validates("profile")
    def _validate_profile(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        if value is None:
            raise ValueError(f"{key} is required.")
        return _ensure_fixed_object_keys(
            value,
            field_name=key,
            required_keys={
                "name",
                "account_tier",
                "preferred_language",
                "preferred_tone",
            },
        ) or {}

    @validates("business_flags")
    def _validate_business_flags(
        self,
        key: str,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        if value is None:
            raise ValueError(f"{key} is required.")
        return _ensure_fixed_object_keys(
            value,
            field_name=key,
            required_keys={
                "high_value_customer",
                "refund_dispute_history",
                "requires_manual_approval",
            },
        ) or {}

    @validates("historical_case_refs")
    def _validate_historical_case_refs(
        self,
        key: str,
        value: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if value is None:
            raise ValueError(f"{key} is required.")
        if any(not isinstance(item, dict) for item in value):
            raise ValueError(f"{key} must be a list of JSON objects.")
        return value

    @validates("version")
    def _validate_version(self, key: str, value: int) -> int:
        if value < INITIAL_VERSION:
            raise ValueError(f"{key} must be >= {INITIAL_VERSION}.")
        return value

    @validates("created_at", "updated_at")
    def _validate_datetimes(
        self,
        key: str,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return value
        return ensure_timezone_aware(value)


Index("ix_customer_memory_profiles_updated_at", CustomerMemoryProfile.updated_at)


class CustomerMemoryEvent(Base):
    __tablename__ = "customer_memory_events"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_customer_memory_events_idempotency_key",
        ),
    )

    memory_event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("customer_memory_profiles.customer_id"),
        nullable=False,
        index=True,
    )
    ticket_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tickets.ticket_id"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("ticket_runs.run_id"),
        nullable=False,
        index=True,
    )
    source_stage: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_FIELD, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("customer_id", "idempotency_key")
    def _validate_required_strings(self, key: str, value: str) -> str:
        if value is None or not value.strip():
            raise ValueError(f"{key} is required.")
        return value.strip()

    @validates("source_stage")
    def _validate_source_stage(self, key: str, value: str) -> str:
        return _ensure_allowed_value(
            value,
            field_name=key,
            allowed_values=_enum_values(MemorySourceStage),
        )

    @validates("event_type")
    def _validate_event_type(self, key: str, value: str) -> str:
        return _ensure_allowed_value(
            value,
            field_name=key,
            allowed_values=_enum_values(MemoryEventType),
        )

    @validates("payload")
    def _validate_payload(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        if value is None:
            raise ValueError(f"{key} is required.")
        return value

    @validates("created_at")
    def _validate_created_at(self, key: str, value: datetime) -> datetime:
        return ensure_timezone_aware(value)


Index("ix_customer_memory_events_created_at", CustomerMemoryEvent.created_at)


class TicketMessage(Base):
    __tablename__ = "ticket_messages"
    __table_args__ = (
        UniqueConstraint(
            "source_channel",
            "source_message_id",
            name="uq_ticket_messages_source_message",
        ),
        CheckConstraint(
            "source_channel = 'gmail'",
            name="ck_ticket_messages_source_channel",
        ),
    )

    ticket_message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tickets.ticket_id"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("ticket_runs.run_id"),
        nullable=True,
        index=True,
    )
    draft_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("draft_artifacts.draft_id"),
        nullable=True,
        index=True,
    )
    source_channel: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SourceChannel.GMAIL.value,
        server_default=SourceChannel.GMAIL.value,
    )
    source_thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    gmail_thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    message_type: Mapped[str] = mapped_column(String(64), nullable=False)
    sender_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    recipient_emails: Mapped[list[str]] = mapped_column(
        JSON_FIELD,
        nullable=False,
        default=list,
    )
    subject: Mapped[Optional[str]] = mapped_column(String(998), nullable=True)
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reply_to_source_message_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    customer_visible: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    message_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    message_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata",
        JSON_FIELD,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @validates("source_channel")
    def _validate_source_channel(self, key: str, value: str) -> str:
        return validate_source_channel(value).value

    @validates("direction")
    def _validate_direction(self, key: str, value: str) -> str:
        return _ensure_allowed_value(
            value,
            field_name=key,
            allowed_values=_enum_values(MessageDirection),
        )

    @validates("message_type")
    def _validate_message_type(self, key: str, value: str) -> str:
        return _ensure_allowed_value(
            value,
            field_name=key,
            allowed_values=_enum_values(MessageType),
        )

    @validates("recipient_emails")
    def _validate_recipient_emails(self, key: str, value: list[str]) -> list[str]:
        return _ensure_required_string_list(value, field_name=key)

    @validates("message_timestamp", "created_at")
    def _validate_datetimes(
        self,
        key: str,
        value: datetime,
    ) -> datetime:
        return ensure_timezone_aware(value)


Index("ix_ticket_messages_message_timestamp", TicketMessage.message_timestamp)


def _normalize_ticket_routing_fields(target: Ticket) -> None:
    selection = normalize_ticket_routing(
        source_channel=target.source_channel or SourceChannel.GMAIL.value,
        primary_route=target.primary_route,
        secondary_routes=target.secondary_routes or [],
        tags=target.tags or [],
        multi_intent=bool(target.multi_intent),
    )
    target.source_channel = selection.source_channel.value
    target.secondary_routes = [route.value for route in selection.secondary_routes]
    target.tags = [tag.value for tag in selection.tags]


def _validate_trace_event_metadata(target: TraceEvent) -> None:
    target.event_metadata = _ensure_trace_metadata_keys(
        event_type=target.event_type,
        metadata=target.event_metadata,
    )


@event.listens_for(Ticket, "before_insert")
@event.listens_for(Ticket, "before_update")
def _ticket_before_persist(mapper, connection, target: Ticket) -> None:
    _normalize_ticket_routing_fields(target)


@event.listens_for(TraceEvent, "before_insert")
@event.listens_for(TraceEvent, "before_update")
def _trace_event_before_persist(mapper, connection, target: TraceEvent) -> None:
    _validate_trace_event_metadata(target)


ALL_TICKET_BUSINESS_STATUSES = _enum_values(TicketBusinessStatus)
ALL_TICKET_PROCESSING_STATUSES = _enum_values(TicketProcessingStatus)
ALL_TICKET_PRIORITIES = _enum_values(TicketPriority)
ALL_TICKET_ROUTES = _enum_values(TicketRoute)
ALL_TICKET_TAGS = _enum_values(TicketTag)
ALL_RESPONSE_STRATEGIES = _enum_values(ResponseStrategy)
ALL_RUN_TRIGGER_TYPES = _enum_values(RunTriggerType)
ALL_RUN_STATUSES = _enum_values(RunStatus)
ALL_RUN_FINAL_ACTIONS = _enum_values(RunFinalAction)
ALL_DRAFT_TYPES = _enum_values(DraftType)
ALL_DRAFT_QA_STATUSES = _enum_values(DraftQaStatus)
ALL_HUMAN_REVIEW_ACTIONS = _enum_values(HumanReviewAction)
ALL_TRACE_EVENT_TYPES = _enum_values(TraceEventType)
ALL_TRACE_EVENT_STATUSES = _enum_values(TraceEventStatus)
ALL_MEMORY_SOURCE_STAGES = _enum_values(MemorySourceStage)
ALL_MEMORY_EVENT_TYPES = _enum_values(MemoryEventType)
