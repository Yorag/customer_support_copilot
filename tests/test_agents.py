from __future__ import annotations

from langchain_core.runnables import RunnableLambda

from src.agents import Agents
from src.structure_outputs import TriageOutput
from src.triage import TriageDecisionService


class FakeLLM:
    def with_structured_output(self, schema):
        if schema is TriageOutput:
            return RunnableLambda(
                lambda _: TriageOutput(
                    primary_route="knowledge_request",
                    secondary_routes=[],
                    tags=[],
                    response_strategy="answer",
                    multi_intent=False,
                    intent_confidence=0.91,
                    priority="medium",
                    needs_clarification=False,
                    needs_escalation=False,
                    routing_reason="Customer asks how to use a supported capability.",
                )
            )

        return RunnableLambda(
            lambda _: schema.model_validate(
                {
                    "category": "product_enquiry",
                }
                if schema.__name__ == "CategorizeEmailOutput"
                else {
                    "queries": ["how does it work?"],
                }
                if schema.__name__ == "RAGQueriesOutput"
                else {
                    "email": "draft",
                }
                if schema.__name__ == "WriterOutput"
                else {
                    "feedback": "ok",
                    "send": True,
                }
            )
        )


def test_agents_triage_email_uses_structured_output_chain(monkeypatch):
    monkeypatch.setattr("src.agents.build_chat_model", lambda temperature=0.1: FakeLLM())

    agents = Agents()
    result = agents.triage_email.invoke(
        {
            "subject": "SSO support",
            "email": "Does the professional plan support SSO?",
        }
    )

    assert result.primary_route.value == "knowledge_request"
    assert result.response_strategy.value == "answer"


def test_agents_triage_email_with_rules_delegates_to_service(monkeypatch):
    monkeypatch.setattr("src.agents.build_chat_model", lambda temperature=0.1: FakeLLM())
    service = TriageDecisionService()
    agents = Agents(triage_service=service)

    decision = agents.triage_email_with_rules(
        subject="Upgrade error and charge",
        email="I was charged twice when upgrading and the page failed.",
    )

    assert decision.output.primary_route.value == "commercial_policy_request"


def test_agents_knowledge_policy_role_outputs_deterministic_contract(monkeypatch):
    monkeypatch.setattr("src.agents.build_chat_model", lambda temperature=0.1: FakeLLM())
    agents = Agents()

    result = agents.knowledge_policy_agent(
        primary_route="knowledge_request",
        response_strategy="answer",
        normalized_email="How do I configure SSO?",
        knowledge_answers=[
            {"question": "How do I configure SSO?", "answer": "Use the SSO settings page."}
        ],
        policy_notes="No special policy constraints.",
    )

    assert result.knowledge_confidence == 0.9
    assert result.allowed_actions == ["answer_question"]
    assert "SSO settings page" in result.knowledge_summary


def test_agents_drafting_role_uses_selected_strategy(monkeypatch):
    monkeypatch.setattr("src.agents.build_chat_model", lambda temperature=0.1: FakeLLM())
    agents = Agents()

    result = agents.drafting_agent(
        customer_email="liwei@example.com",
        subject="Refund review",
        primary_route="commercial_policy_request",
        response_strategy="policy_constrained",
        normalized_email="I need a refund because I was charged twice.",
        knowledge_summary="No extra knowledge.",
        policy_notes="Do not promise refunds.",
    )

    assert result.applied_response_strategy.value == "policy_constrained"
    assert "policy" in result.draft_text.lower()


def test_agents_qa_handoff_role_escalates_when_risk_requires_manual_review(monkeypatch):
    monkeypatch.setattr("src.agents.build_chat_model", lambda temperature=0.1: FakeLLM())
    agents = Agents()

    result = agents.qa_handoff_agent(
        primary_route="commercial_policy_request",
        draft_text="Hello,\n\nWe received your request.\n\nBest regards",
        knowledge_confidence=0.85,
        needs_escalation=True,
        rewrite_count=1,
        policy_notes="Do not promise refunds.",
    )

    assert result.approved is False
    assert result.escalate is True
    assert result.human_handoff_summary is not None
