from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core_schema import ResponseStrategy, TicketPriority, TicketRoute, TicketTag
from src.structure_outputs import TriageOutput


def test_triage_output_matches_spec_example_and_syncs_tags():
    output = TriageOutput(
        primary_route="commercial_policy_request",
        secondary_routes=[],
        tags=["billing_question", "refund_request"],
        response_strategy="policy_constrained",
        multi_intent=False,
        intent_confidence=0.93,
        priority="high",
        needs_clarification=False,
        needs_escalation=True,
        routing_reason=" The customer requests a refund for a billing issue, which requires policy-constrained handling. ",
    )

    assert output.primary_route is TicketRoute.COMMERCIAL_POLICY_REQUEST
    assert output.response_strategy is ResponseStrategy.POLICY_CONSTRAINED
    assert output.priority is TicketPriority.HIGH
    assert output.tags == [
        TicketTag.BILLING_QUESTION,
        TicketTag.REFUND_REQUEST,
        TicketTag.NEEDS_ESCALATION,
    ]
    assert output.routing_reason == (
        "The customer requests a refund for a billing issue, "
        "which requires policy-constrained handling."
    )


def test_triage_output_adds_multi_intent_and_deduplicates_tags_and_routes():
    output = TriageOutput(
        primary_route="commercial_policy_request",
        secondary_routes=["technical_issue", "technical_issue"],
        tags=["billing_question", "multi_intent", "needs_escalation", "needs_escalation"],
        response_strategy="policy_constrained",
        multi_intent=True,
        intent_confidence=0.88,
        priority="critical",
        needs_clarification=False,
        needs_escalation=True,
        routing_reason="Billing dispute with a separate technical failure.",
    )

    assert output.secondary_routes == [TicketRoute.TECHNICAL_ISSUE]
    assert output.tags == [
        TicketTag.BILLING_QUESTION,
        TicketTag.MULTI_INTENT,
        TicketTag.NEEDS_ESCALATION,
    ]


def test_triage_output_rejects_secondary_routes_when_not_multi_intent():
    with pytest.raises(ValidationError):
        TriageOutput(
            primary_route="knowledge_request",
            secondary_routes=["technical_issue"],
            tags=[],
            response_strategy="answer",
            multi_intent=False,
            intent_confidence=0.91,
            priority="medium",
            needs_clarification=False,
            needs_escalation=False,
            routing_reason="The message mostly asks a product question.",
        )


def test_triage_output_rejects_needs_clarification_for_non_technical_route():
    with pytest.raises(ValidationError):
        TriageOutput(
            primary_route="knowledge_request",
            secondary_routes=[],
            tags=["needs_clarification"],
            response_strategy="answer",
            multi_intent=False,
            intent_confidence=0.87,
            priority="medium",
            needs_clarification=True,
            needs_escalation=False,
            routing_reason="Customer asks how SSO works.",
        )


def test_triage_output_rejects_low_confidence_without_escalation():
    with pytest.raises(ValidationError):
        TriageOutput(
            primary_route="feedback_intake",
            secondary_routes=[],
            tags=["general_feedback"],
            response_strategy="acknowledgement",
            multi_intent=False,
            intent_confidence=0.45,
            priority="medium",
            needs_clarification=False,
            needs_escalation=False,
            routing_reason="The message is ambiguous feedback with weak routing confidence.",
        )


def test_triage_output_rejects_mismatched_response_strategy():
    with pytest.raises(ValidationError):
        TriageOutput(
            primary_route="technical_issue",
            secondary_routes=[],
            tags=[],
            response_strategy="answer",
            multi_intent=False,
            intent_confidence=0.91,
            priority="high",
            needs_clarification=False,
            needs_escalation=False,
            routing_reason="The user reports a login failure after following the guide.",
        )


def test_triage_output_rejects_when_boolean_tag_sync_would_exceed_tag_limit():
    with pytest.raises(ValidationError):
        TriageOutput(
            primary_route="technical_issue",
            secondary_routes=[],
            tags=[
                "feature_request",
                "complaint",
                "general_feedback",
                "billing_question",
                "refund_request",
            ],
            response_strategy="troubleshooting",
            multi_intent=False,
            intent_confidence=0.92,
            priority="critical",
            needs_clarification=False,
            needs_escalation=True,
            routing_reason="The message already contains the maximum number of tags before escalation.",
        )
