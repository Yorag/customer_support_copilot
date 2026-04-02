from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from statistics import mean
from typing import Any, Iterable
from uuid import UUID, uuid5

from langsmith import Client
from langsmith.run_trees import RunTree

from src.config import get_settings
from src.core_schema import (
    EntityIdPrefix,
    RunFinalAction,
    TicketBusinessStatus,
    TicketRoute,
    TraceEventStatus,
    TraceEventType,
    generate_prefixed_id,
    utc_now,
)
from src.db.models import Ticket, TicketRun, TraceEvent


_LANGSMITH_NAMESPACE = UUID("12345678-1234-5678-1234-567812345678")
_REQUIRED_ROUTE_TEMPLATES: dict[str, list[str]] = {
    TicketRoute.KNOWLEDGE_REQUEST.value: [
        "triage",
        "knowledge_lookup",
        "draft_reply",
        "qa_review",
        "create_gmail_draft",
    ],
    "technical_issue_clarify": [
        "triage",
        "clarify_request",
        "create_gmail_draft",
        "awaiting_customer_input",
    ],
    TicketRoute.TECHNICAL_ISSUE.value: [
        "triage",
        "knowledge_lookup",
        "draft_reply",
        "qa_review",
        "create_gmail_draft",
    ],
    "commercial_policy_request_high_risk": [
        "triage",
        "policy_check",
        "customer_history_lookup",
        "escalate_to_human",
    ],
    TicketRoute.COMMERCIAL_POLICY_REQUEST.value: [
        "triage",
        "policy_check",
        "customer_history_lookup",
        "draft_reply",
        "qa_review",
        "create_gmail_draft",
    ],
    TicketRoute.FEEDBACK_INTAKE.value: [
        "triage",
        "draft_reply",
        "qa_review",
        "create_gmail_draft",
    ],
    TicketRoute.UNRELATED.value: [
        "triage",
        "close_ticket",
    ],
}
_TRAJECTORY_PENALTIES = {
    "missing_required_node": 1.5,
    "wrong_order": 1.0,
    "missed_escalation": 2.0,
    "missed_clarification": 2.0,
    "unexpected_auto_draft": 1.5,
}
_TRAJECTORY_NODE_SET = {
    node
    for route in _REQUIRED_ROUTE_TEMPLATES.values()
    for node in route
    if node != "awaiting_customer_input"
}


def _duration_ms(start: datetime, end: datetime) -> int:
    return max(0, int((end - start).total_seconds() * 1000))


def _uuid_from_prefixed_id(value: str) -> UUID:
    return uuid5(_LANGSMITH_NAMESPACE, value)


@dataclass(frozen=True)
class JudgeResult:
    relevance: int
    correctness: int
    intent_alignment: int
    clarity: int
    reason: str

    @property
    def overall_score(self) -> float:
        return round(
            (
                self.relevance
                + self.correctness
                + self.intent_alignment
                + self.clarity
            )
            / 4,
            2,
        )

    def as_response_quality(self) -> dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "subscores": {
                "relevance": self.relevance,
                "correctness": self.correctness,
                "intent_alignment": self.intent_alignment,
                "clarity": self.clarity,
            },
            "reason": self.reason,
        }


class JudgeSchemaError(ValueError):
    pass


def validate_judge_output(payload: dict[str, Any]) -> JudgeResult:
    required_keys = {
        "relevance",
        "correctness",
        "intent_alignment",
        "clarity",
        "reason",
    }
    actual_keys = set(payload.keys())
    if actual_keys != required_keys:
        raise JudgeSchemaError(
            "Judge output must use fixed keys "
            f"{sorted(required_keys)}, got {sorted(actual_keys)}."
        )

    numeric_fields = ("relevance", "correctness", "intent_alignment", "clarity")
    normalized: dict[str, Any] = {}
    for field in numeric_fields:
        value = payload[field]
        if not isinstance(value, int) or value < 1 or value > 5:
            raise JudgeSchemaError(f"Judge field `{field}` must be an integer in [1, 5].")
        normalized[field] = value

    reason = str(payload["reason"]).strip()
    if not reason:
        raise JudgeSchemaError("Judge field `reason` must not be blank.")

    return JudgeResult(reason=reason, **normalized)


class ResponseQualityJudge:
    def evaluate(
        self,
        *,
        email_subject: str | None,
        email_body: str | None,
        draft_text: str | None,
        evidence_summary: str | None,
        policy_summary: str | None,
        primary_route: str | None,
        final_action: str | None,
    ) -> dict[str, Any]:
        draft = (draft_text or "").strip()
        body = (email_body or "").strip()
        route = primary_route or TicketRoute.UNRELATED.value
        action = final_action or RunFinalAction.NO_OP.value

        relevance = 5 if draft else 1
        correctness = 4
        intent_alignment = 4
        clarity = 4
        reasons: list[str] = []

        if not draft:
            relevance = correctness = intent_alignment = clarity = 1
            reasons.append("No customer-facing draft was produced.")
        else:
            reasons.append("Draft exists and can be evaluated against the run outcome.")

        if route == TicketRoute.COMMERCIAL_POLICY_REQUEST.value:
            correctness = 5 if "policy" in ((draft + " " + (policy_summary or "")).lower()) else 3
            reasons.append("Commercial-policy replies are checked for explicit policy boundaries.")
        elif route == TicketRoute.TECHNICAL_ISSUE.value and action == RunFinalAction.REQUEST_CLARIFICATION.value:
            detail_text = (draft + " " + body).lower()
            coverage = sum(
                phrase in detail_text
                for phrase in ("error", "steps", "environment", "expected")
            )
            correctness = 5 if coverage >= 3 else 4 if coverage >= 2 else 3
            intent_alignment = correctness
            reasons.append("Clarification drafts are checked for required troubleshooting asks.")
        elif route == TicketRoute.UNRELATED.value:
            clarity = 5 if len(draft) < 240 else 4
            reasons.append("Out-of-scope replies should stay concise and avoid over-committing.")

        if evidence_summary and route in {
            TicketRoute.KNOWLEDGE_REQUEST.value,
            TicketRoute.TECHNICAL_ISSUE.value,
        }:
            correctness = min(5, correctness + 1)
            reasons.append("Knowledge or troubleshooting evidence is available.")

        if len(draft) < 40 and draft:
            clarity = min(clarity, 3)
            reasons.append("Draft is short and may not be sufficiently clear.")

        result = validate_judge_output(
            {
                "relevance": relevance,
                "correctness": correctness,
                "intent_alignment": intent_alignment,
                "clarity": clarity,
                "reason": " ".join(reasons),
            }
        )
        return result.as_response_quality()


class LangSmithTraceClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._enabled = bool(settings.langsmith.tracing_enabled and settings.langsmith.api_key)
        self._project = settings.langsmith.project
        self._client = (
            Client(
                api_key=settings.langsmith.api_key,
                api_url=settings.langsmith.endpoint,
            )
            if self._enabled
            else None
        )

    def create_root_run(
        self,
        *,
        run: TicketRun,
        ticket: Ticket,
        inputs: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> RunTree | None:
        if self._client is None:
            return None
        root = RunTree(
            id=_uuid_from_prefixed_id(run.trace_id),
            trace_id=_uuid_from_prefixed_id(run.trace_id),
            name="ticket_run",
            run_type="chain",
            start_time=run.started_at,
            inputs=inputs,
            extra={
                "metadata": {
                    "trace_id": run.trace_id,
                    "run_id": run.run_id,
                    "ticket_id": ticket.ticket_id,
                    **(metadata or {}),
                }
            },
            tags=["customer-support-copilot", "ticket-run"],
            project_name=self._project,
            ls_client=self._client,
        )
        try:
            root.post()
        except Exception:
            return None
        return root

    def create_child_run(
        self,
        *,
        parent: RunTree | None,
        event: TraceEvent,
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
    ) -> RunTree | None:
        if parent is None:
            return None
        run_type = _langsmith_run_type_for_event(event.event_type)
        child = parent.create_child(
            name=event.event_name,
            run_type=run_type,
            run_id=_uuid_from_prefixed_id(event.event_id),
            start_time=event.start_time,
            end_time=event.end_time,
            inputs=inputs or {},
            outputs=outputs,
            extra={
                "metadata": {
                    "trace_id": event.trace_id,
                    "run_id": event.run_id,
                    "ticket_id": event.ticket_id,
                    "event_type": event.event_type,
                    "node_name": event.node_name,
                    "status": event.status,
                    **(event.event_metadata or {}),
                }
            },
            tags=[f"event:{event.event_type}"],
        )
        try:
            child.post()
        except Exception:
            return None
        return child

    def finalize_run(
        self,
        *,
        root: RunTree | None,
        ended_at: datetime,
        outputs: dict[str, Any],
        error: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        if root is None:
            return
        root.end_time = ended_at
        root.outputs = outputs
        root.error = error
        existing_extra = dict(root.extra or {})
        metadata = dict(existing_extra.get("metadata") or {})
        metadata.update(extra_metadata or {})
        root.extra = {**existing_extra, "metadata": metadata}
        try:
            root.patch()
        except Exception:
            return


def _langsmith_run_type_for_event(event_type: str) -> str:
    if event_type == TraceEventType.LLM_CALL.value:
        return "llm"
    if event_type == TraceEventType.TOOL_CALL.value:
        return "tool"
    return "chain"


class TraceRecorder:
    def __init__(self, *, repositories, langsmith_client: LangSmithTraceClient | None = None) -> None:
        self._repositories = repositories
        self._langsmith = langsmith_client or LangSmithTraceClient()
        self._root_run: RunTree | None = None
        self._child_runs: dict[str, RunTree] = {}

    def start_run(
        self,
        *,
        ticket: Ticket,
        run: TicketRun,
        inputs: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._root_run = self._langsmith.create_root_run(
            run=run,
            ticket=ticket,
            inputs=inputs,
            metadata=metadata,
        )

    def finalize_run(
        self,
        *,
        run: TicketRun,
        ticket: Ticket,
        error: str | None = None,
    ) -> None:
        self._langsmith.finalize_run(
            root=self._root_run,
            ended_at=run.ended_at or utc_now(),
            outputs={
                "ticket_id": ticket.ticket_id,
                "run_id": run.run_id,
                "trace_id": run.trace_id,
                "status": run.status,
                "final_action": run.final_action,
                "latency_metrics": run.latency_metrics,
                "resource_metrics": run.resource_metrics,
                "response_quality": run.response_quality,
                "trajectory_evaluation": run.trajectory_evaluation,
            },
            error=error,
            extra_metadata={
                "final_node": run.final_node,
                "ticket_business_status": ticket.business_status,
                "ticket_processing_status": ticket.processing_status,
            },
        )

    def record_event(
        self,
        *,
        run: TicketRun,
        ticket: Ticket,
        event_type: str,
        event_name: str,
        node_name: str | None,
        start_time: datetime,
        end_time: datetime,
        status: str,
        metadata: dict[str, Any] | None = None,
        event_id: str | None = None,
        outputs: dict[str, Any] | None = None,
    ) -> TraceEvent:
        event = TraceEvent(
            event_id=event_id or generate_prefixed_id(EntityIdPrefix.TRACE),
            trace_id=run.trace_id,
            run_id=run.run_id,
            ticket_id=ticket.ticket_id,
            event_type=event_type,
            event_name=event_name,
            node_name=node_name,
            start_time=start_time,
            end_time=end_time,
            latency_ms=_duration_ms(start_time, end_time),
            status=status,
            event_metadata=metadata,
        )
        self._repositories.trace_events.add(event)
        child = self._langsmith.create_child_run(
            parent=self._root_run,
            event=event,
            inputs=metadata or {},
            outputs=outputs,
        )
        if child is not None:
            self._child_runs[event.event_id] = child
        return event

    @contextmanager
    def node_span(
        self,
        *,
        run: TicketRun,
        ticket: Ticket,
        node_name: str,
        metadata: dict[str, Any] | None = None,
    ):
        started_at = utc_now()
        try:
            yield
        except Exception as exc:
            self.record_event(
                run=run,
                ticket=ticket,
                event_type=TraceEventType.NODE.value,
                event_name=node_name,
                node_name=node_name,
                start_time=started_at,
                end_time=utc_now(),
                status=TraceEventStatus.FAILED.value,
                metadata={**(metadata or {}), "error_message": str(exc)},
            )
            raise
        else:
            self.record_event(
                run=run,
                ticket=ticket,
                event_type=TraceEventType.NODE.value,
                event_name=node_name,
                node_name=node_name,
                start_time=started_at,
                end_time=utc_now(),
                status=TraceEventStatus.SUCCEEDED.value,
                metadata=metadata,
            )

    def record_decision(
        self,
        *,
        run: TicketRun,
        ticket: Ticket,
        event_name: str,
        node_name: str,
        metadata: dict[str, Any],
    ) -> TraceEvent:
        now = utc_now()
        return self.record_event(
            run=run,
            ticket=ticket,
            event_type=TraceEventType.DECISION.value,
            event_name=event_name,
            node_name=node_name,
            start_time=now,
            end_time=now,
            status=TraceEventStatus.SUCCEEDED.value,
            metadata=metadata,
        )

    def record_tool_call(
        self,
        *,
        run: TicketRun,
        ticket: Ticket,
        event_name: str,
        node_name: str,
        tool_name: str,
        input_ref: str,
        output_ref: str,
        start_time: datetime,
        end_time: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> TraceEvent:
        payload = {
            "tool_name": tool_name,
            "input_ref": input_ref,
            "output_ref": output_ref,
            **(metadata or {}),
        }
        return self.record_event(
            run=run,
            ticket=ticket,
            event_type=TraceEventType.TOOL_CALL.value,
            event_name=event_name,
            node_name=node_name,
            start_time=start_time,
            end_time=end_time,
            status=TraceEventStatus.SUCCEEDED.value,
            metadata=payload,
        )

    def record_llm_call(
        self,
        *,
        run: TicketRun,
        ticket: Ticket,
        event_name: str,
        node_name: str,
        model: str,
        start_time: datetime,
        end_time: datetime,
        prompt_tokens: int,
        completion_tokens: int,
        metadata: dict[str, Any] | None = None,
    ) -> TraceEvent:
        total_tokens = prompt_tokens + completion_tokens
        payload = {
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            **(metadata or {}),
        }
        return self.record_event(
            run=run,
            ticket=ticket,
            event_type=TraceEventType.LLM_CALL.value,
            event_name=event_name,
            node_name=node_name,
            start_time=start_time,
            end_time=end_time,
            status=TraceEventStatus.SUCCEEDED.value,
            metadata=payload,
        )

    def list_run_events(self, run_id: str) -> list[TraceEvent]:
        events = self._repositories.trace_events.list_by_run(run_id)
        events.sort(key=lambda item: (item.start_time, item.created_at, item.event_id))
        return events

    def build_latency_metrics(self, *, run: TicketRun) -> dict[str, Any]:
        events = self.list_run_events(run.run_id)
        end_to_end_ms = _duration_ms(run.started_at, run.ended_at or utc_now())

        node_events = [event for event in events if event.event_type == TraceEventType.NODE.value]
        llm_events = [
            event for event in events if event.event_type == TraceEventType.LLM_CALL.value
        ]
        tool_events = [
            event for event in events if event.event_type == TraceEventType.TOOL_CALL.value
        ]

        node_groups: dict[str, list[int]] = {}
        for event in node_events:
            if event.event_name == "run_ticket":
                continue
            if event.latency_ms is None:
                continue
            key = event.node_name or event.event_name
            node_groups.setdefault(key, []).append(event.latency_ms)

        node_latencies = {
            key: round(mean(values), 3)
            for key, values in sorted(node_groups.items())
            if values
        }
        slowest_node = None
        if node_latencies:
            slowest_node = max(node_latencies.items(), key=lambda item: item[1])[0]

        slowest_call = None
        for event in events:
            if event.latency_ms is None:
                continue
            if slowest_call is None or event.latency_ms > slowest_call["latency_ms"]:
                slowest_call = {
                    "event_name": event.event_name,
                    "latency_ms": event.latency_ms,
                }

        return {
            "end_to_end_ms": end_to_end_ms,
            "slowest_node": slowest_node,
            "slowest_call": slowest_call,
            "node_latencies": node_latencies,
            "llm_call_latencies": {
                event.event_name: event.latency_ms
                for event in llm_events
                if event.latency_ms is not None
            },
            "tool_call_latencies": {
                event.event_name: event.latency_ms
                for event in tool_events
                if event.latency_ms is not None
            },
        }

    def build_resource_metrics(self, *, run: TicketRun) -> dict[str, Any]:
        events = self.list_run_events(run.run_id)
        llm_events = [
            event for event in events if event.event_type == TraceEventType.LLM_CALL.value
        ]
        tool_events = [
            event for event in events if event.event_type == TraceEventType.TOOL_CALL.value
        ]

        prompt_tokens_total = 0
        completion_tokens_total = 0
        for event in llm_events:
            metadata = event.event_metadata or {}
            prompt_tokens_total += int(metadata.get("prompt_tokens", 0) or 0)
            completion_tokens_total += int(metadata.get("completion_tokens", 0) or 0)

        return {
            "prompt_tokens_total": prompt_tokens_total,
            "completion_tokens_total": completion_tokens_total,
            "total_tokens": prompt_tokens_total + completion_tokens_total,
            "llm_call_count": len(llm_events),
            "tool_call_count": len(tool_events),
        }


def estimate_token_usage(*, text: str, multiplier: float = 1.0) -> int:
    normalized = (text or "").strip()
    if not normalized:
        return 0
    return max(1, int(len(normalized.split()) * multiplier))


def build_trajectory_evaluation(
    *,
    ticket: Ticket,
    final_action: str | None,
    events: Iterable[TraceEvent],
) -> dict[str, Any]:
    actual_route = [
        event.node_name or event.event_name
        for event in events
        if event.event_type == TraceEventType.NODE.value
        and event.status == TraceEventStatus.SUCCEEDED.value
        and (event.node_name or event.event_name) != "run_ticket"
        and (event.node_name or event.event_name) in _TRAJECTORY_NODE_SET
    ]
    expected_template_key = _select_expected_template_key(
        ticket=ticket,
        final_action=final_action,
    )
    expected_route = list(_REQUIRED_ROUTE_TEMPLATES[expected_template_key])
    violations: list[dict[str, str]] = []

    for required_node in expected_route:
        if required_node == "awaiting_customer_input":
            if ticket.business_status != TicketBusinessStatus.AWAITING_CUSTOMER_INPUT.value:
                violations.append(
                    {
                        "type": "missing_required_node",
                        "message": "The run should end in awaiting_customer_input for clarification cases.",
                    }
                )
            continue
        if required_node not in actual_route:
            violations.append(
                {
                    "type": "missing_required_node",
                    "message": f"Required node `{required_node}` is missing from the actual route.",
                }
            )

    ordered_required = [node for node in expected_route if node in actual_route]
    actual_positions = [actual_route.index(node) for node in ordered_required]
    if actual_positions != sorted(actual_positions):
        violations.append(
            {
                "type": "wrong_order",
                "message": "Observed node order does not match the expected route template.",
            }
        )

    if ticket.needs_escalation and "escalate_to_human" not in actual_route:
        violations.append(
            {
                "type": "missed_escalation",
                "message": "The run should escalate but did not route to escalate_to_human.",
            }
        )
    if ticket.needs_clarification and "clarify_request" not in actual_route:
        violations.append(
            {
                "type": "missed_clarification",
                "message": "The run should request clarification but did not route to clarify_request.",
            }
        )
    if (
        ticket.primary_route == TicketRoute.COMMERCIAL_POLICY_REQUEST.value
        and "create_gmail_draft" in actual_route
        and ticket.needs_escalation
    ):
        violations.append(
            {
                "type": "unexpected_auto_draft",
                "message": "The run created a draft instead of escalating a high-risk policy request.",
            }
        )

    score = 5.0
    for violation in violations:
        score -= _TRAJECTORY_PENALTIES[violation["type"]]
    score = max(0.0, round(score, 2))

    return {
        "score": score,
        "expected_route": expected_route,
        "actual_route": actual_route,
        "violations": violations,
    }


def _select_expected_template_key(*, ticket: Ticket, final_action: str | None) -> str:
    if ticket.primary_route == TicketRoute.TECHNICAL_ISSUE.value and (
        ticket.needs_clarification
        or final_action == RunFinalAction.REQUEST_CLARIFICATION.value
    ):
        return "technical_issue_clarify"
    if ticket.primary_route == TicketRoute.COMMERCIAL_POLICY_REQUEST.value and (
        ticket.needs_escalation
        or final_action == RunFinalAction.HANDOFF_TO_HUMAN.value
    ):
        return "commercial_policy_request_high_risk"
    return ticket.primary_route or TicketRoute.UNRELATED.value
