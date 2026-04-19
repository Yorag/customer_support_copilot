from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.contracts.core import SourceChannel, to_api_timestamp


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


class RetryTicketRequest(ApiModel):
    ticket_version: int = Field(ge=1)


class RunTicketResponse(ApiModel):
    ticket_id: str
    run_id: str
    trace_id: str
    processing_status: str


class GenerateDraftRequest(ApiModel):
    ticket_version: int = Field(ge=1)
    mode: Literal["create", "regenerate"] = "create"
    source_draft_id: Optional[str] = None
    comment: Optional[str] = None
    rewrite_guidance: List[str] = Field(default_factory=list)

    @field_validator("source_draft_id")
    @classmethod
    def validate_source_draft_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _require_non_blank(value, field_name="source_draft_id")

    @field_validator("rewrite_guidance")
    @classmethod
    def validate_rewrite_guidance(cls, value: List[str]) -> List[str]:
        return [
            _require_non_blank(item, field_name="rewrite_guidance")
            for item in value
        ]


class ApproveTicketRequest(ApiModel):
    ticket_version: int = Field(ge=1)
    draft_id: str
    comment: Optional[str] = None

    @field_validator("draft_id")
    @classmethod
    def validate_draft_id(cls, value: str) -> str:
        return _require_non_blank(value, field_name="draft_id")


class SaveDraftRequest(ApiModel):
    ticket_version: int = Field(ge=1)
    draft_id: str
    comment: Optional[str] = None
    edited_content_text: str

    @field_validator("draft_id", "edited_content_text")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        return _require_non_blank(value, field_name=info.field_name)


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
    claimed_by: Optional[str] = None
    claimed_at: Optional[str] = None
    lease_until: Optional[str] = None
    priority: str
    primary_route: Optional[str] = None
    multi_intent: bool
    tags: List[str]
    version: int


class EvaluationSummaryRef(ApiModel):
    status: Literal["not_available", "partial", "complete"]
    trace_id: str
    has_response_quality: bool
    response_quality_overall_score: Optional[float] = None
    has_trajectory_evaluation: bool
    trajectory_score: Optional[float] = None
    trajectory_violation_count: Optional[int] = None


class TicketRunSummary(ApiModel):
    run_id: str
    trace_id: str
    status: str
    final_action: Optional[str] = None
    evaluation_summary_ref: EvaluationSummaryRef


class TicketDraftSummary(ApiModel):
    draft_id: str
    qa_status: str


class PaginatedResponse(ApiModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class TicketListItem(ApiModel):
    ticket_id: str
    customer_id: Optional[str] = None
    customer_email_raw: str
    subject: str
    business_status: str
    processing_status: str
    priority: str
    primary_route: Optional[str] = None
    multi_intent: bool
    version: int
    updated_at: str
    latest_run: Optional[TicketRunSummary] = None
    latest_draft: Optional[TicketDraftSummary] = None


class TicketListResponse(PaginatedResponse):
    items: List[TicketListItem]


class TicketRunHistoryItem(ApiModel):
    run_id: str
    trace_id: str
    trigger_type: str
    triggered_by: Optional[str] = None
    status: str
    final_action: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    attempt_index: int
    is_human_action: bool
    evaluation_summary_ref: EvaluationSummaryRef


class TicketRunsResponse(PaginatedResponse):
    ticket_id: str
    items: List[TicketRunHistoryItem]


class TicketDraftDetail(ApiModel):
    draft_id: str
    run_id: str
    version_index: int
    draft_type: str
    qa_status: str
    content_text: str
    source_evidence_summary: Optional[str] = None
    gmail_draft_id: Optional[str] = None
    created_at: str


class TicketDraftsResponse(ApiModel):
    ticket_id: str
    items: List[TicketDraftDetail]


class TicketMessage(ApiModel):
    ticket_message_id: str
    run_id: Optional[str] = None
    draft_id: Optional[str] = None
    source_message_id: str
    direction: str
    message_type: str
    sender_email: Optional[str] = None
    recipient_emails: List[str] = Field(default_factory=list)
    subject: Optional[str] = None
    body_text: Optional[str] = None
    reply_to_source_message_id: Optional[str] = None
    customer_visible: bool
    message_timestamp: str
    metadata: Optional[Dict[str, Any]] = None


class TicketSnapshotResponse(ApiModel):
    ticket: TicketSummary
    latest_run: Optional[TicketRunSummary] = None
    latest_draft: Optional[TicketDraftSummary] = None
    messages: List[TicketMessage] = Field(default_factory=list)


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


class GmailScanPreviewRequest(ApiModel):
    max_results: Optional[int] = Field(default=None, ge=1, le=100)


class GmailScanRequest(ApiModel):
    max_results: Optional[int] = Field(default=None, ge=1, le=100)
    enqueue: bool = True


class GmailScanPreviewItem(ApiModel):
    source_thread_id: str
    source_message_id: Optional[str] = None
    sender_email_raw: str
    subject: str
    skip_reason: Optional[str] = None


class GmailScanPreviewSummary(ApiModel):
    candidate_threads: int = Field(ge=0)
    skipped_existing_draft_threads: int = Field(ge=0)
    skipped_self_sent_threads: int = Field(ge=0)


class GmailScanPreviewResponse(ApiModel):
    gmail_enabled: bool
    requested_max_results: int = Field(ge=1)
    summary: GmailScanPreviewSummary
    items: List[GmailScanPreviewItem]


class GmailScanItem(ApiModel):
    source_thread_id: str
    ticket_id: Optional[str] = None
    created_ticket: bool
    queued_run_id: Optional[str] = None


class GmailScanSummary(ApiModel):
    fetched_threads: int = Field(ge=0)
    ingested_tickets: int = Field(ge=0)
    queued_runs: int = Field(ge=0)
    skipped_existing_draft_threads: int = Field(ge=0)
    skipped_self_sent_threads: int = Field(ge=0)
    errors: int = Field(ge=0)


class GmailScanResponse(ApiModel):
    scan_id: str
    status: Literal["accepted"]
    gmail_enabled: bool
    requested_max_results: int = Field(ge=1)
    enqueue: bool
    summary: GmailScanSummary
    items: List[GmailScanItem]


class OpsStatusGmail(ApiModel):
    enabled: bool
    account_email: Optional[str] = None
    last_scan_at: Optional[str] = None
    last_scan_status: Optional[str] = None


class OpsStatusWorker(ApiModel):
    healthy: Optional[bool] = None
    worker_count: Optional[int] = Field(default=None, ge=0)
    last_heartbeat_at: Optional[str] = None


class OpsStatusQueue(ApiModel):
    queued_runs: int = Field(ge=0)
    running_runs: int = Field(ge=0)
    waiting_external_tickets: int = Field(ge=0)
    error_tickets: int = Field(ge=0)


class OpsStatusDependencies(ApiModel):
    database: str
    gmail: str
    llm: str
    checkpointing: str


class OpsStatusRecentFailure(ApiModel):
    ticket_id: str
    run_id: str
    trace_id: str
    error_code: Optional[str] = None
    occurred_at: Optional[str] = None


class OpsStatusResponse(ApiModel):
    gmail: OpsStatusGmail
    worker: OpsStatusWorker
    queue: OpsStatusQueue
    dependencies: OpsStatusDependencies
    recent_failure: Optional[OpsStatusRecentFailure] = None


class TestEmailRequest(ApiModel):
    sender_email_raw: str
    subject: str
    body_text: str
    references: Optional[str] = None
    auto_enqueue: bool = True
    scenario_label: Optional[str] = None

    @field_validator("sender_email_raw", "subject", "body_text")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        return _require_non_blank(value, field_name=info.field_name)


class TestEmailTicketResult(ApiModel):
    ticket_id: str
    created: bool
    business_status: str
    processing_status: str
    version: int


class TestEmailRunResult(ApiModel):
    run_id: str
    trace_id: str
    processing_status: str


class TestEmailMetadata(ApiModel):
    scenario_label: Optional[str] = None
    auto_enqueue: bool
    source_channel: str


class TestEmailResponse(ApiModel):
    ticket: TestEmailTicketResult
    run: Optional[TestEmailRunResult] = None
    test_metadata: TestEmailMetadata
