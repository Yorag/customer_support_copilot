from __future__ import annotations

from langchain_core.runnables import RunnableLambda

from src.agents import Agents
from src.core_schema import TicketRoute
from src.structure_outputs import TriageOutput
from src.triage import TriageContext, TriageDecisionService


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
            "is_high_value_customer": "false",
            "recent_customer_replies_72h": 0,
            "requires_manual_approval": "false",
            "qa_failure_count": 0,
            "knowledge_evidence_sufficient": "true",
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

    assert decision.selected_rule == "R3"
    assert "llm_structured_output" in decision.matched_rules
    assert decision.output.primary_route.value == "commercial_policy_request"


def test_agents_triage_email_with_rules_prefers_llm_when_safe(monkeypatch):
    monkeypatch.setattr("src.agents.build_chat_model", lambda temperature=0.1: FakeLLM())
    agents = Agents(triage_service=TriageDecisionService())

    decision = agents.triage_email_with_rules(
        subject="SSO support",
        email="How do I configure SSO for my workspace and where is the setup guide?",
    )

    assert decision.selected_rule == "llm_structured_output"
    assert decision.matched_rules[0] == "llm_structured_output"
    assert decision.output.primary_route is TicketRoute.KNOWLEDGE_REQUEST
    assert decision.output.needs_escalation is False


class MisclassifyingLLM(FakeLLM):
    def with_structured_output(self, schema):
        if schema is TriageOutput:
            return RunnableLambda(
                lambda _: TriageOutput(
                    primary_route="knowledge_request",
                    secondary_routes=[],
                    tags=[],
                    response_strategy="answer",
                    multi_intent=False,
                    intent_confidence=0.88,
                    priority="medium",
                    needs_clarification=False,
                    needs_escalation=False,
                    routing_reason="The customer appears to ask a product question.",
                )
            )
        return super().with_structured_output(schema)


def test_agents_triage_email_with_rules_overrides_llm_for_high_risk_policy(monkeypatch):
    monkeypatch.setattr("src.agents.build_chat_model", lambda temperature=0.1: MisclassifyingLLM())
    agents = Agents(triage_service=TriageDecisionService())

    decision = agents.triage_email_with_rules(
        subject="重复扣费申请退款",
        email="我们这个月被重复扣费了两次，请立即退款并说明处理时效。",
    )

    assert decision.selected_rule == "R3"
    assert "llm_structured_output" in decision.matched_rules
    assert decision.output.primary_route is TicketRoute.COMMERCIAL_POLICY_REQUEST
    assert decision.output.needs_escalation is True


class EscalatingKnowledgeLLM(FakeLLM):
    def with_structured_output(self, schema):
        if schema is TriageOutput:
            return RunnableLambda(
                lambda _: TriageOutput(
                    primary_route="knowledge_request",
                    secondary_routes=[],
                    tags=["needs_escalation"],
                    response_strategy="answer",
                    multi_intent=False,
                    intent_confidence=0.92,
                    priority="medium",
                    needs_clarification=False,
                    needs_escalation=True,
                    routing_reason="The customer is asking about product capabilities.",
                )
            )
        return super().with_structured_output(schema)


def test_agents_triage_email_with_rules_keeps_escalation_deterministic(monkeypatch):
    monkeypatch.setattr("src.agents.build_chat_model", lambda temperature=0.1: EscalatingKnowledgeLLM())
    agents = Agents(triage_service=TriageDecisionService())

    decision = agents.triage_email_with_rules(
        subject="API 速率限制说明",
        email="想确认一下工作区 API token 的速率限制是多少，触发限流后应该怎么重试？",
    )

    assert decision.output.primary_route is TicketRoute.KNOWLEDGE_REQUEST
    assert decision.selected_rule == "llm_structured_output"
    assert decision.output.needs_escalation is True
    assert "LLM triage requested escalation." in decision.escalation_reasons


class ConservativeKnowledgeLLM(FakeLLM):
    def with_structured_output(self, schema):
        if schema is TriageOutput:
            return RunnableLambda(
                lambda _: TriageOutput(
                    primary_route="knowledge_request",
                    secondary_routes=[],
                    tags=["needs_escalation"],
                    response_strategy="answer",
                    multi_intent=False,
                    intent_confidence=0.59,
                    priority="medium",
                    needs_clarification=False,
                    needs_escalation=True,
                    routing_reason="The product question is understood, but low confidence requires escalation.",
                )
            )
        return super().with_structured_output(schema)


def test_agents_triage_email_with_rules_preserves_safe_llm_conservatism(monkeypatch):
    monkeypatch.setattr("src.agents.build_chat_model", lambda temperature=0.1: ConservativeKnowledgeLLM())
    agents = Agents(triage_service=TriageDecisionService())

    decision = agents.triage_email_with_rules(
        subject="SSO support",
        email="How do I configure SSO for my workspace and where is the setup guide?",
    )

    assert decision.selected_rule == "llm_structured_output"
    assert decision.output.primary_route is TicketRoute.KNOWLEDGE_REQUEST
    assert decision.output.needs_clarification is False
    assert decision.output.needs_escalation is True
    assert "LLM triage requested escalation." in decision.escalation_reasons


def test_agents_triage_email_with_rules_keeps_manual_approval_guardrail(monkeypatch):
    monkeypatch.setattr("src.agents.build_chat_model", lambda temperature=0.1: FakeLLM())
    agents = Agents(triage_service=TriageDecisionService())

    decision = agents.triage_email_with_rules(
        subject="SSO support",
        email="How do I configure SSO for my workspace and where is the setup guide?",
        context=TriageContext(requires_manual_approval=True),
    )

    assert decision.selected_rule == "R1"
    assert "llm_structured_output" in decision.matched_rules
    assert decision.output.primary_route is TicketRoute.KNOWLEDGE_REQUEST
    assert decision.output.needs_escalation is True
    assert any("manual approval" in reason for reason in decision.escalation_reasons)


class FailingLLM:
    def with_structured_output(self, schema):
        return RunnableLambda(lambda _: (_ for _ in ()).throw(RuntimeError("llm unavailable")))


def test_agents_triage_email_with_rules_falls_back_to_rules_when_llm_fails(monkeypatch):
    monkeypatch.setattr("src.agents.build_chat_model", lambda temperature=0.1: FailingLLM())
    agents = Agents(triage_service=TriageDecisionService())

    decision = agents.triage_email_with_rules(
        subject="重复扣费申请退款",
        email="我们这个月被重复扣费了两次，请立即退款并说明处理时效。",
    )

    assert decision.selected_rule == "fallback_rule_service"
    assert decision.output.primary_route is TicketRoute.COMMERCIAL_POLICY_REQUEST
    assert decision.output.needs_escalation is True


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
