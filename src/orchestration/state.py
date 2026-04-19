from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from src.contracts.core import (
    SourceChannel,
    TicketBusinessStatus,
    TicketPriority,
    TicketProcessingStatus,
    to_api_timestamp,
)


class Email(BaseModel):
    id: str = Field(..., description="Unique identifier of the email")
    threadId: str = Field(..., description="Thread identifier of the email")
    messageId: str = Field(..., description="Message identifier of the email")
    references: str = Field(..., description="References of the email")
    sender: str = Field(..., description="Email address of the sender")
    subject: str = Field(..., description="Subject line of the email")
    body: str = Field(..., description="Body content of the email")


class EmailPayload(TypedDict):
    id: str
    threadId: str
    messageId: str
    references: str
    sender: str
    subject: str
    body: str


class ClarificationHistoryEntry(TypedDict):
    question: str
    asked_at: str
    source: str


class CheckpointMetadata(TypedDict):
    thread_id: str
    checkpoint_ns: str
    last_checkpoint_node: Optional[str]
    last_checkpoint_at: Optional[str]


class ClaimProjection(TypedDict):
    claimed_by: Optional[str]
    claimed_at: Optional[str]
    lease_until: Optional[str]


class GraphState(TypedDict, total=False):
    ticket_id: str
    channel: str
    customer_id: Optional[str]
    thread_id: str
    business_status: str
    processing_status: str
    ticket_version: int
    ticket_created_at: Optional[str]
    ticket_updated_at: Optional[str]
    run_id: Optional[str]
    trigger_type: Optional[str]
    triggered_by: Optional[str]
    current_node: Optional[str]
    clarification_history: list[ClarificationHistoryEntry]
    resume_count: int
    checkpoint_metadata: CheckpointMetadata
    raw_email: Optional[EmailPayload]
    normalized_email: str
    attachments: list[dict[str, Any]]
    primary_route: Optional[str]
    secondary_routes: list[str]
    tags: list[str]
    response_strategy: Optional[str]
    multi_intent: bool
    intent_confidence: Optional[float]
    priority: str
    needs_clarification: bool
    needs_escalation: bool
    routing_reason: Optional[str]
    queries: list[str]
    knowledge_summary: str
    retrieval_results: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    knowledge_confidence: Optional[float]
    retrieval_hit: bool
    policy_notes: str
    allowed_actions: list[str]
    disallowed_actions: list[str]
    thread_summary: Optional[str]
    customer_profile: Optional[dict[str, Any]]
    historical_cases: list[dict[str, Any]]
    case_context: Optional[dict[str, Any]]
    memory_update_candidates: Optional[dict[str, Any]]
    memory_updates: Optional[dict[str, Any]]
    draft_versions: list[dict[str, Any]]
    qa_feedback: Optional[dict[str, Any]]
    applied_response_strategy: Optional[str]
    rewrite_count: int
    approval_status: Optional[str]
    escalation_reason: Optional[str]
    final_action: Optional[str]
    human_handoff_summary: Optional[str]
    qa_result: Optional[dict[str, Any]]
    manual_draft_guidance: list[str]
    trace_id: Optional[str]
    latency_metrics: dict[str, Any]
    resource_metrics: dict[str, Any]
    response_quality: Optional[dict[str, Any]]
    trajectory_evaluation: Optional[dict[str, Any]]
    claimed_by: Optional[str]
    claimed_at: Optional[str]
    lease_until: Optional[str]
    retry_count: int
    last_error: Optional[dict[str, Any]]
    side_effect_records: dict[str, Any]
    idempotency_keys: dict[str, str]


def build_initial_graph_state() -> GraphState:
    return {
        "channel": SourceChannel.GMAIL.value,
        "customer_id": None,
        "thread_id": "",
        "business_status": TicketBusinessStatus.NEW.value,
        "processing_status": TicketProcessingStatus.QUEUED.value,
        "ticket_version": 1,
        "ticket_created_at": None,
        "ticket_updated_at": None,
        "run_id": None,
        "trigger_type": None,
        "triggered_by": None,
        "current_node": None,
        "clarification_history": [],
        "resume_count": 0,
        "checkpoint_metadata": _build_checkpoint_metadata(),
        "raw_email": None,
        "normalized_email": "",
        "attachments": [],
        "primary_route": None,
        "secondary_routes": [],
        "tags": [],
        "response_strategy": None,
        "multi_intent": False,
        "intent_confidence": None,
        "priority": TicketPriority.MEDIUM.value,
        "needs_clarification": False,
        "needs_escalation": False,
        "routing_reason": None,
        "queries": [],
        "knowledge_summary": "",
        "retrieval_results": [],
        "citations": [],
        "knowledge_confidence": None,
        "retrieval_hit": True,
        "policy_notes": "",
        "allowed_actions": [],
        "disallowed_actions": [],
        "thread_summary": None,
        "customer_profile": None,
        "historical_cases": [],
        "case_context": None,
        "memory_update_candidates": None,
        "memory_updates": None,
        "draft_versions": [],
        "qa_feedback": None,
        "applied_response_strategy": None,
        "rewrite_count": 0,
        "approval_status": None,
        "escalation_reason": None,
        "final_action": None,
        "human_handoff_summary": None,
        "qa_result": None,
        "manual_draft_guidance": [],
        "trace_id": None,
        "latency_metrics": {},
        "resource_metrics": {},
        "response_quality": None,
        "trajectory_evaluation": None,
        "claimed_by": None,
        "claimed_at": None,
        "lease_until": None,
        "retry_count": 0,
        "last_error": None,
        "side_effect_records": {},
        "idempotency_keys": {},
    }


def build_ticket_run_state(
    *,
    raw_email: Email | dict[str, Any] | None = None,
    ticket_id: str = "",
    customer_id: str | None = None,
    business_status: TicketBusinessStatus | str = TicketBusinessStatus.NEW,
    processing_status: TicketProcessingStatus | str = TicketProcessingStatus.QUEUED,
    ticket_version: int = 1,
    priority: TicketPriority | str = TicketPriority.MEDIUM,
    trace_id: str | None = None,
    run_id: str | None = None,
    trigger_type: str | None = None,
    triggered_by: str | None = None,
    claimed_by: str | None = None,
    claimed_at: str | None = None,
    lease_until: str | None = None,
) -> GraphState:
    state = build_initial_graph_state()
    active_email = coerce_email(raw_email) if raw_email is not None else None

    if active_email is not None:
        state.update(
            {
                "raw_email": serialize_email(active_email),
                "normalized_email": active_email.body,
                "thread_id": active_email.threadId,
            }
        )

    state.update(
        {
            "ticket_id": ticket_id,
            "customer_id": customer_id,
            "business_status": TicketBusinessStatus(business_status).value,
            "processing_status": TicketProcessingStatus(processing_status).value,
            "ticket_version": ticket_version,
            "priority": TicketPriority(priority).value,
            "trace_id": trace_id,
            "run_id": run_id,
            "trigger_type": trigger_type,
            "triggered_by": triggered_by,
            "claimed_by": claimed_by,
            "claimed_at": claimed_at,
            "lease_until": lease_until,
            "checkpoint_metadata": _build_checkpoint_metadata(
                ticket_id=ticket_id,
                run_id=run_id,
            ),
        }
    )
    return state


def coerce_email(payload: Email | dict[str, Any]) -> Email:
    if isinstance(payload, Email):
        return payload
    return Email(**payload)


def serialize_email(payload: Email | dict[str, Any]) -> EmailPayload:
    return coerce_email(payload).model_dump(mode="json")


def get_active_email(state: GraphState) -> Email:
    active_email = state.get("raw_email")
    if active_email is not None:
        return coerce_email(active_email)

    raise KeyError("GraphState does not contain an active email.")


def set_active_email(state: GraphState, email: Email | dict[str, Any] | None) -> GraphState:
    normalized_email = coerce_email(email) if email is not None else None
    serialized = serialize_email(normalized_email) if normalized_email else None
    return {
        "raw_email": serialized,
        "normalized_email": normalized_email.body if normalized_email else "",
        "thread_id": normalized_email.threadId if normalized_email else "",
    }


def build_claim_projection(
    *,
    lease_owner: str | None = None,
    lease_expires_at: datetime | str | None = None,
    current_run_id: str | None = None,
    run_id: str | None = None,
    run_started_at: datetime | str | None = None,
) -> ClaimProjection:
    claimed_at = None
    if current_run_id and run_id and current_run_id == run_id and run_started_at is not None:
        claimed_at = _serialize_timestamp_like(run_started_at)

    return {
        "claimed_by": lease_owner,
        "claimed_at": claimed_at,
        "lease_until": _serialize_timestamp_like(lease_expires_at),
    }


def _build_checkpoint_metadata(
    *,
    ticket_id: str | None = None,
    run_id: str | None = None,
    last_checkpoint_node: str | None = None,
    last_checkpoint_at: str | None = None,
) -> CheckpointMetadata:
    normalized_ticket_id = (ticket_id or "").strip()
    normalized_run_id = (run_id or "").strip()
    return {
        "thread_id": normalized_ticket_id,
        "checkpoint_ns": normalized_run_id,
        "last_checkpoint_node": last_checkpoint_node,
        "last_checkpoint_at": last_checkpoint_at,
    }


def _serialize_timestamp_like(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return to_api_timestamp(normalized)


__all__ = [
    "CheckpointMetadata",
    "ClaimProjection",
    "ClarificationHistoryEntry",
    "Email",
    "EmailPayload",
    "GraphState",
    "build_claim_projection",
    "build_initial_graph_state",
    "build_ticket_run_state",
    "coerce_email",
    "get_active_email",
    "serialize_email",
    "set_active_email",
]

