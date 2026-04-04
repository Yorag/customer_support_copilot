from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.contracts.core import (
    ResponseStrategy,
    TicketPriority,
    TicketRoute,
    TicketTag,
)
from src.triage import TriageContext, TriageDecisionService


SAMPLES_PATH = Path(__file__).resolve().parent / "samples" / "triage_cases.json"


def _load_triage_cases() -> list[dict]:
    return json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _load_triage_cases(), ids=lambda case: case["name"])
def test_triage_service_matches_sample_cases(case: dict):
    service = TriageDecisionService()

    decision = service.evaluate(
        subject=case["subject"],
        body=case["body"],
    )

    output = decision.output
    expected = case["expected"]

    assert output.primary_route.value == expected["primary_route"]
    assert [route.value for route in output.secondary_routes] == expected.get(
        "secondary_routes",
        [],
    )
    assert output.response_strategy.value == expected["response_strategy"]

    if "multi_intent" in expected:
        assert output.multi_intent is expected["multi_intent"]
    if "needs_clarification" in expected:
        assert output.needs_clarification is expected["needs_clarification"]
    if "needs_escalation" in expected:
        assert output.needs_escalation is expected["needs_escalation"]
    if "tags_contains" in expected:
        tag_values = {tag.value for tag in output.tags}
        assert set(expected["tags_contains"]).issubset(tag_values)


def test_conflict_priority_prefers_commercial_over_technical_and_knowledge():
    service = TriageDecisionService()

    decision = service.evaluate(
        subject="Billing issue and SSO problem",
        body=(
            "Why was I charged twice this month? I also followed the SSO docs and login failed "
            "for our workspace with an error page."
        ),
    )

    assert decision.selected_rule == "R3"
    assert decision.output.primary_route is TicketRoute.COMMERCIAL_POLICY_REQUEST
    assert decision.output.secondary_routes == [TicketRoute.TECHNICAL_ISSUE]
    assert decision.output.multi_intent is True


def test_priority_escalates_for_high_value_customer_and_repeat_replies():
    service = TriageDecisionService()

    decision = service.evaluate(
        subject="Login failed again",
        body=(
            "I tried to configure SSO for our workspace and login failed again with an error. "
            "I expected the team to sign in successfully."
        ),
        context=TriageContext(
            is_high_value_customer=True,
            recent_customer_replies_72h=2,
        ),
    )

    assert decision.output.primary_route is TicketRoute.TECHNICAL_ISSUE
    assert decision.output.priority is TicketPriority.CRITICAL
    assert any("High-value customer" in reason for reason in decision.priority_reasons)
    assert any("Repeated replies" in reason for reason in decision.priority_reasons)


def test_low_confidence_for_weak_unrelated_signal_forces_escalation():
    service = TriageDecisionService()

    decision = service.evaluate(
        subject="Hello",
        body="Please help.",
    )

    assert decision.output.primary_route is TicketRoute.UNRELATED
    assert decision.output.intent_confidence < 0.60
    assert decision.output.needs_escalation is True
    assert TicketTag.NEEDS_ESCALATION in decision.output.tags


def test_clarification_only_applies_to_technical_issue():
    service = TriageDecisionService()

    technical = service.evaluate(
        subject="The product is broken",
        body="The app failed.",
    )
    feedback = service.evaluate(
        subject="Bad experience",
        body="The new report page is frustrating and hard to use.",
    )

    assert technical.output.primary_route is TicketRoute.TECHNICAL_ISSUE
    assert technical.output.needs_clarification is True
    assert TicketTag.NEEDS_CLARIFICATION in technical.output.tags
    assert feedback.output.primary_route is TicketRoute.FEEDBACK_INTAKE
    assert feedback.output.needs_clarification is False


def test_escalation_triggers_for_manual_approval_and_knowledge_gap():
    service = TriageDecisionService()

    decision = service.evaluate(
        subject="Need a definitive answer about a legal term",
        body="Does your contract guarantee specific data residency and legal indemnity?",
        context=TriageContext(
            requires_manual_approval=True,
            knowledge_evidence_sufficient=False,
        ),
    )

    assert decision.output.primary_route is TicketRoute.COMMERCIAL_POLICY_REQUEST
    assert decision.output.needs_escalation is True
    assert TicketTag.NEEDS_ESCALATION in decision.output.tags
    assert any("manual approval" in reason for reason in decision.escalation_reasons)


def test_response_strategy_mapping_stays_consistent_with_primary_route():
    service = TriageDecisionService()

    decision = service.evaluate(
        subject="How do I use webhooks?",
        body="How do I configure webhooks for my workspace?",
    )

    assert decision.output.primary_route is TicketRoute.KNOWLEDGE_REQUEST
    assert decision.output.response_strategy is ResponseStrategy.ANSWER
