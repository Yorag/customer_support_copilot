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
