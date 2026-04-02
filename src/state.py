from __future__ import annotations

from typing import Annotated, Any, Optional

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from .core_schema import (
    ResponseStrategy,
    SourceChannel,
    TicketBusinessStatus,
    TicketPriority,
    TicketProcessingStatus,
    TicketRoute,
)


class Email(BaseModel):
    id: str = Field(..., description="Unique identifier of the email")
    threadId: str = Field(..., description="Thread identifier of the email")
    messageId: str = Field(..., description="Message identifier of the email")
    references: str = Field(..., description="References of the email")
    sender: str = Field(..., description="Email address of the sender")
    subject: str = Field(..., description="Subject line of the email")
    body: str = Field(..., description="Body content of the email")


class GraphState(TypedDict, total=False):
    # Base ticket/run fields
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

    # Input fields
    raw_email: Optional[Email]
    normalized_email: str
    attachments: list[dict[str, Any]]

    # Routing fields
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

    # Knowledge fields
    queries: list[str]
    knowledge_summary: str
    retrieval_results: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    knowledge_confidence: Optional[float]
    policy_notes: str
    allowed_actions: list[str]
    disallowed_actions: list[str]
    knowledge_policy_result: Optional[dict[str, Any]]

    # Memory fields
    thread_summary: Optional[str]
    customer_profile: Optional[dict[str, Any]]
    historical_cases: list[dict[str, Any]]
    case_context: Optional[dict[str, Any]]
    memory_update_candidates: Optional[dict[str, Any]]
    memory_updates: Optional[dict[str, Any]]

    # Draft and review fields
    draft_versions: list[dict[str, Any]]
    qa_feedback: Optional[dict[str, Any]]
    applied_response_strategy: Optional[str]
    rewrite_count: int
    approval_status: Optional[str]
    escalation_reason: Optional[str]
    final_action: Optional[str]
    human_handoff_summary: Optional[str]
    qa_result: Optional[dict[str, Any]]

    # Observability fields
    trace_id: Optional[str]
    trace_events: list[dict[str, Any]]
    latency_metrics: dict[str, Any]
    resource_metrics: dict[str, Any]
    response_quality: Optional[dict[str, Any]]
    trajectory_evaluation: Optional[dict[str, Any]]
    extra_metrics: dict[str, Any]

    # Concurrency and recovery fields
    claimed_by: Optional[str]
    claimed_at: Optional[str]
    lease_until: Optional[str]
    retry_count: int
    last_error: Optional[dict[str, Any]]
    side_effect_records: dict[str, Any]
    idempotency_keys: dict[str, str]

    # Transitional compatibility fields for the existing tutorial graph
    pending_emails: list[Email]
    emails: list[Email]
    current_email: Optional[Email]
    email_category: Optional[str]
    triage_result: Optional[dict[str, Any]]
    generated_email: str
    rag_queries: list[str]
    retrieved_documents: str
    writer_messages: Annotated[list[str], add_messages]
    sendable: bool
    trials: int


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
        "policy_notes": "",
        "allowed_actions": [],
        "disallowed_actions": [],
        "knowledge_policy_result": None,
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
        "trace_id": None,
        "trace_events": [],
        "latency_metrics": {},
        "resource_metrics": {},
        "response_quality": None,
        "trajectory_evaluation": None,
        "extra_metrics": {},
        "claimed_by": None,
        "claimed_at": None,
        "lease_until": None,
        "retry_count": 0,
        "last_error": None,
        "side_effect_records": {},
        "idempotency_keys": {},
        "pending_emails": [],
        "emails": [],
        "current_email": None,
        "email_category": None,
        "triage_result": None,
        "generated_email": "",
        "rag_queries": [],
        "retrieved_documents": "",
        "writer_messages": [],
        "sendable": False,
        "trials": 0,
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
    pending_emails: list[Email | dict[str, Any]] | None = None,
    trace_id: str | None = None,
    run_id: str | None = None,
    trigger_type: str | None = None,
    triggered_by: str | None = None,
) -> GraphState:
    state = build_initial_graph_state()
    normalized_pending_emails = [coerce_email(item) for item in pending_emails or []]
    active_email = coerce_email(raw_email) if raw_email is not None else None

    if active_email is None and normalized_pending_emails:
        active_email = normalized_pending_emails[-1]

    if active_email is not None:
        state.update(
            {
                "raw_email": active_email,
                "current_email": active_email,
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
            "pending_emails": normalized_pending_emails,
            "emails": list(normalized_pending_emails),
        }
    )
    return state


def coerce_email(payload: Email | dict[str, Any]) -> Email:
    if isinstance(payload, Email):
        return payload
    return Email(**payload)


def get_active_email(state: GraphState) -> Email:
    active_email = state.get("raw_email") or state.get("current_email")
    if active_email is not None:
        return active_email

    pending_emails = state.get("pending_emails", [])
    if pending_emails:
        return pending_emails[-1]

    raise KeyError("GraphState does not contain an active email.")


def set_active_email(state: GraphState, email: Email | dict[str, Any] | None) -> GraphState:
    normalized_email = coerce_email(email) if email is not None else None
    updates: GraphState = {
        "raw_email": normalized_email,
        "current_email": normalized_email,
        "normalized_email": normalized_email.body if normalized_email else "",
        "thread_id": normalized_email.threadId if normalized_email else "",
    }
    return updates


def pop_pending_email(state: GraphState) -> Email | None:
    pending_emails = state.get("pending_emails", [])
    if not pending_emails:
        return None
    return pending_emails.pop()
