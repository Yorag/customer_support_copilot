from __future__ import annotations

from typing import Iterable

from src.contracts.core import (
    RunFinalAction,
    TicketBusinessStatus,
    TicketRoute,
    TraceEventStatus,
    TraceEventType,
)
from src.db.models import Ticket, TraceEvent


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


def build_trajectory_evaluation(
    *,
    ticket: Ticket,
    final_action: str | None,
    events: Iterable[TraceEvent],
) -> dict[str, object]:
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
                        "message": (
                            "The run should end in awaiting_customer_input for "
                            "clarification cases."
                        ),
                    }
                )
            continue
        if required_node not in actual_route:
            violations.append(
                {
                    "type": "missing_required_node",
                    "message": (
                        f"Required node `{required_node}` is missing from the actual route."
                    ),
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
                "message": (
                    "The run should request clarification but did not route to "
                    "clarify_request."
                ),
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
                "message": (
                    "The run created a draft instead of escalating a high-risk "
                    "policy request."
                ),
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


__all__ = [
    "_REQUIRED_ROUTE_TEMPLATES",
    "_TRAJECTORY_NODE_SET",
    "_TRAJECTORY_PENALTIES",
    "_select_expected_template_key",
    "build_trajectory_evaluation",
]
