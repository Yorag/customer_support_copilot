from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core_schema import SourceChannel, to_api_timestamp


def _serialize_datetime(value: datetime) -> str:
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return to_api_timestamp(normalized)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        use_enum_values=True,
        extra="forbid",
        populate_by_name=True,
    )


def _require_non_blank(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank.")
    return normalized


class ErrorPayload(ApiModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ErrorResponse(ApiModel):
    error: ErrorPayload


class IngestEmailRequest(ApiModel):
    source_channel: str = Field(default=SourceChannel.GMAIL.value)
    source_thread_id: str
    source_message_id: str
    sender_email_raw: str
    subject: str
    body_text: str
    message_timestamp: datetime
    references: Optional[str] = None
    attachments: List[Dict[str, Any]] = Field(default_factory=list)

    @field_validator("source_channel")
    @classmethod
    def validate_source_channel(cls, value: str) -> str:
        if value != SourceChannel.GMAIL.value:
            raise ValueError("source_channel must be `gmail` in V1.")
        return value


class IngestEmailResponse(ApiModel):
    ticket_id: str
    created: bool
    business_status: str
    processing_status: str
    version: int


class RunTicketRequest(ApiModel):
    ticket_version: int = Field(ge=1)
    trigger_type: str = Field(default="manual_api")
    force_retry: bool = False


class RunTicketResponse(ApiModel):
    ticket_id: str
    run_id: str
    trace_id: str
    processing_status: str


class ApproveTicketRequest(ApiModel):
    ticket_version: int = Field(ge=1)
    draft_id: str
    comment: Optional[str] = None

    @field_validator("draft_id")
    @classmethod
    def validate_draft_id(cls, value: str) -> str:
        return _require_non_blank(value, field_name="draft_id")


class EditAndApproveTicketRequest(ApiModel):
    ticket_version: int = Field(ge=1)
    draft_id: str
    comment: Optional[str] = None
    edited_content_text: str

    @field_validator("draft_id", "edited_content_text")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        return _require_non_blank(value, field_name=info.field_name)


class RewriteTicketRequest(ApiModel):
    ticket_version: int = Field(ge=1)
    draft_id: str
    comment: Optional[str] = None
    rewrite_reasons: List[str] = Field(default_factory=list)

    @field_validator("draft_id")
    @classmethod
    def validate_draft_id(cls, value: str) -> str:
        return _require_non_blank(value, field_name="draft_id")

    @field_validator("rewrite_reasons")
    @classmethod
    def validate_rewrite_reasons(cls, value: List[str]) -> List[str]:
        if not value:
            raise ValueError("rewrite_reasons must contain at least one reason.")
        return [
            _require_non_blank(item, field_name="rewrite_reasons")
            for item in value
        ]


class EscalateTicketRequest(ApiModel):
    ticket_version: int = Field(ge=1)
    comment: Optional[str] = None
    target_queue: str

    @field_validator("target_queue")
    @classmethod
    def validate_target_queue(cls, value: str) -> str:
        return _require_non_blank(value, field_name="target_queue")


class CloseTicketRequest(ApiModel):
    ticket_version: int = Field(ge=1)
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return _require_non_blank(value, field_name="reason")


class TicketActionResponse(ApiModel):
    ticket_id: str
    review_id: Optional[str] = None
    business_status: str
    processing_status: str
    version: int


class TicketSummary(ApiModel):
    ticket_id: str
    business_status: str
    processing_status: str
    priority: str
    primary_route: Optional[str] = None
    multi_intent: bool
    tags: List[str]
    version: int


class TicketRunSummary(ApiModel):
    run_id: str
    trace_id: str
    status: str
    final_action: Optional[str] = None


class TicketDraftSummary(ApiModel):
    draft_id: str
    qa_status: str


class TicketSnapshotResponse(ApiModel):
    ticket: TicketSummary
    latest_run: Optional[TicketRunSummary] = None
    latest_draft: Optional[TicketDraftSummary] = None


class TraceEventResponse(ApiModel):
    event_id: str
    event_type: str
    event_name: str
    node_name: Optional[str] = None
    start_time: str
    end_time: Optional[str] = None
    latency_ms: Optional[int] = None
    status: str
    metadata: Optional[Dict[str, Any]] = None

    @classmethod
    def from_record(cls, *, event) -> "TraceEventResponse":
        return cls(
            event_id=event.event_id,
            event_type=event.event_type,
            event_name=event.event_name,
            node_name=event.node_name,
            start_time=_serialize_datetime(event.start_time),
            end_time=(
                _serialize_datetime(event.end_time) if event.end_time is not None else None
            ),
            latency_ms=event.latency_ms,
            status=event.status,
            metadata=event.event_metadata,
        )


class TicketTraceResponse(ApiModel):
    ticket_id: str
    run_id: str
    trace_id: str
    latency_metrics: Optional[Dict[str, Any]] = None
    resource_metrics: Optional[Dict[str, Any]] = None
    response_quality: Optional[Dict[str, Any]] = None
    trajectory_evaluation: Optional[Dict[str, Any]] = None
    events: List[TraceEventResponse]


class CustomerMemoryResponse(ApiModel):
    customer_id: str
    profile: Dict[str, Any]
    risk_tags: List[str]
    business_flags: Dict[str, Any]
    historical_case_refs: List[Dict[str, Any]]
    version: int


class MetricsWindow(ApiModel):
    from_: str = Field(alias="from")
    to: str


class MetricsSummaryResponse(ApiModel):
    window: MetricsWindow
    latency: Dict[str, Any]
    resources: Dict[str, Any]
    response_quality: Dict[str, Any]
    trajectory_evaluation: Dict[str, Any]
