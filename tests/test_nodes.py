from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from src.contracts.core import EntityIdPrefix, generate_prefixed_id
from src.contracts.outputs import (
    DraftingOutput,
    KnowledgePolicyOutput,
    QaHandoffOutput,
    TriageOutput,
)
from src.db.base import Base
from src.db.repositories import build_repository_bundle
from src.db.models import Ticket, TicketRun
from src.db.session import build_engine, create_session_factory, session_scope
from src.orchestration.nodes_ticket import TicketNodes
from src.orchestration.state import build_ticket_run_state
from src.rag.provider import KnowledgeAnswer
from src.tickets.message_log import MessageLogService
from src.tickets.state_machine import TicketStateService


class FakeGmailClient:
    def __init__(self, emails: list[dict] | None = None) -> None:
        self._emails = emails or []
        self.created_drafts: list[tuple[Email, str]] = []

    def fetch_unanswered_emails(self, max_results=None):
        return list(self._emails)

    def create_draft_reply(self, initial_email, reply_text):
        self.created_drafts.append((initial_email, reply_text))
        return {"id": "draft_001"}

    def send_reply(self, initial_email, reply_text):
        return {"id": "sent_001"}


class FakeKnowledgeProvider:
    def answer_questions(self, questions):
        return [
            KnowledgeAnswer(question=question, answer=f"answer for {question}")
            for question in questions
        ]


class FakePolicyProvider:
    def get_policy(self, category=None):
        return f"policy for {category or 'default'}"


class FakeTicketStore:
    def ping(self):
        return True

    def session_scope(self):
        raise AssertionError("session_scope should not be used in this test")


class FakeAgents:
    def __init__(self) -> None:
        self.categorize_email = SimpleNamespace(
            invoke=lambda _: SimpleNamespace(category=SimpleNamespace(value="product_enquiry"))
        )
        self.triage_email = SimpleNamespace(
            invoke=lambda _: TriageOutput(
                primary_route="knowledge_request",
                secondary_routes=[],
                tags=[],
                response_strategy="answer",
                multi_intent=False,
                intent_confidence=0.91,
                priority="medium",
                needs_clarification=False,
                needs_escalation=False,
                routing_reason="Customer asks about product usage.",
            )
        )
        self.design_rag_queries = SimpleNamespace(
            invoke=lambda _: SimpleNamespace(queries=["pricing", "annual billing"])
        )
        self.email_writer = SimpleNamespace(
            invoke=lambda payload: SimpleNamespace(
                email=f"draft based on {payload['email_information']}"
            )
        )
        self.email_proofreader = SimpleNamespace(
            invoke=lambda _: SimpleNamespace(send=True, feedback="looks good")
        )

    def triage_email_with_rules(self, *, subject, email, context=None):
        return SimpleNamespace(
            output=TriageOutput(
                primary_route="knowledge_request",
                secondary_routes=[],
                tags=[],
                response_strategy="answer",
                multi_intent=False,
                intent_confidence=0.91,
                priority="medium",
                needs_clarification=False,
                needs_escalation=False,
                routing_reason="Customer asks about product usage.",
            )
        )

    def knowledge_policy_agent_detailed(
        self,
        *,
        primary_route,
        response_strategy,
        normalized_email,
        knowledge_answers=None,
        policy_notes="",
        knowledge_confidence=None,
        needs_escalation=False,
    ):
        return SimpleNamespace(
            output=self.knowledge_policy_agent(
                primary_route=primary_route,
                response_strategy=response_strategy,
                normalized_email=normalized_email,
                knowledge_answers=knowledge_answers,
                policy_notes=policy_notes,
                knowledge_confidence=knowledge_confidence,
                needs_escalation=needs_escalation,
            ),
            llm_invocation=None,
            fallback_used=True,
            guardrails_adjusted=False,
        )

    def knowledge_policy_agent(
        self,
        *,
        primary_route,
        response_strategy,
        normalized_email,
        knowledge_answers=None,
        policy_notes="",
        knowledge_confidence=None,
        needs_escalation=False,
    ):
        answers = knowledge_answers or []
        return KnowledgePolicyOutput(
            queries=[item["question"] for item in answers],
            knowledge_summary="\n".join(item["answer"] for item in answers)
            or "fallback knowledge summary",
            citations=[],
            knowledge_confidence=knowledge_confidence if knowledge_confidence is not None else 0.9,
            risk_level="high" if needs_escalation else "low",
            allowed_actions=["answer_question"],
            disallowed_actions=[],
            policy_notes=policy_notes or "policy for default",
        )

    def drafting_agent(
        self,
        *,
        customer_email,
        subject,
        primary_route,
        response_strategy,
        normalized_email,
        knowledge_summary,
        policy_notes,
        rewrite_guidance=None,
    ):
        return DraftingOutput(
            draft_text=f"Hello,\n\n{knowledge_summary or policy_notes}\n\nBest regards",
            draft_rationale="deterministic drafting for tests",
            applied_response_strategy=response_strategy,
        )

    def drafting_agent_detailed(
        self,
        *,
        customer_email,
        subject,
        primary_route,
        response_strategy,
        normalized_email,
        knowledge_summary,
        policy_notes,
        rewrite_guidance=None,
        allowed_actions=None,
        disallowed_actions=None,
    ):
        return SimpleNamespace(
            output=self.drafting_agent(
                customer_email=customer_email,
                subject=subject,
                primary_route=primary_route,
                response_strategy=response_strategy,
                normalized_email=normalized_email,
                knowledge_summary=knowledge_summary,
                policy_notes=policy_notes,
                rewrite_guidance=rewrite_guidance,
            ),
            llm_invocation=None,
            fallback_used=True,
            guardrails_adjusted=False,
        )

    def qa_handoff_agent(
        self,
        *,
        primary_route,
        draft_text,
        knowledge_confidence,
        needs_escalation,
        rewrite_count,
        policy_notes,
    ):
        return QaHandoffOutput(
            approved=not needs_escalation,
            issues=["risk_requires_human_review"] if needs_escalation else [],
            rewrite_guidance=[],
            quality_scores={"clarity": 4.0},
            escalate=needs_escalation,
            reason="deterministic qa for tests",
            human_handoff_summary="needs human review" if needs_escalation else None,
        )

    def qa_handoff_agent_detailed(
        self,
        *,
        primary_route,
        draft_text,
        knowledge_confidence,
        needs_escalation,
        rewrite_count,
        policy_notes,
    ):
        return SimpleNamespace(
            output=self.qa_handoff_agent(
                primary_route=primary_route,
                draft_text=draft_text,
                knowledge_confidence=knowledge_confidence,
                needs_escalation=needs_escalation,
                rewrite_count=rewrite_count,
                policy_notes=policy_notes,
            ),
            llm_invocation=None,
            fallback_used=True,
            guardrails_adjusted=False,
        )


class FakeServices:
    def __init__(self, gmail_client):
        self.gmail_client = gmail_client
        self.knowledge_provider = FakeKnowledgeProvider()
        self.policy_provider = FakePolicyProvider()
        self.ticket_store = FakeTicketStore()


def test_route_ticket_prioritizes_escalation_and_policy_secondary_intent():
    nodes = TicketNodes(
        agents=FakeAgents(),
        service_container=FakeServices(FakeGmailClient()),
    )

    assert (
        nodes.route_ticket(
            {
                "primary_route": "knowledge_request",
                "secondary_routes": ["commercial_policy_request"],
                "needs_escalation": True,
                "needs_clarification": False,
            }
        )
        == "escalate_to_human"
    )
    assert (
        nodes.route_ticket(
            {
                "primary_route": "knowledge_request",
                "secondary_routes": ["commercial_policy_request"],
                "needs_escalation": False,
                "needs_clarification": False,
            }
        )
        == "policy_check"
    )
    assert (
        nodes.route_ticket(
            {
                "primary_route": "unrelated",
                "secondary_routes": [],
                "needs_escalation": True,
                "needs_clarification": False,
            }
        )
        == "escalate_to_human"
    )


@contextmanager
def _build_ticket_execution_nodes(sample_email_payload, *, triage_output: TriageOutput):
    class TicketExecutionAgents(FakeAgents):
        def triage_email_with_rules(self, *, subject, email, context=None):
            return SimpleNamespace(output=triage_output, escalation_reasons=[])

    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    with session_scope(session_factory) as session:
        ticket = Ticket(
            ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
            source_thread_id="thread-node-test",
            source_message_id=sample_email_payload["messageId"],
            gmail_thread_id="thread-node-test",
            customer_id="cust_email_customer_example_com",
            customer_email="customer@example.com",
            customer_email_raw='"Customer" <customer@example.com>',
            subject=sample_email_payload["subject"],
            latest_message_excerpt=sample_email_payload["body"],
            business_status="new",
            processing_status="running",
            priority="medium",
            secondary_routes=[],
            tags=[],
            multi_intent=False,
            needs_clarification=False,
            needs_escalation=False,
            risk_reasons=[],
            lease_owner="worker-1",
            lease_expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
            current_run_id="run-node-test",
        )
        run = TicketRun(
            run_id="run-node-test",
            ticket_id=ticket.ticket_id,
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type="manual_api",
            status="running",
            started_at=datetime.now(timezone.utc),
            attempt_index=1,
        )
        session.add(ticket)
        session.add(run)
        session.flush()
        message_log = MessageLogService(session)
        message_log.ingest_inbound_email(
            SimpleNamespace(
                source_channel="gmail",
                source_thread_id="thread-node-test",
                source_message_id=sample_email_payload["messageId"],
                sender_email_raw=sample_email_payload["sender"],
                subject=sample_email_payload["subject"],
                body_text=sample_email_payload["body"],
                message_timestamp=datetime.now(timezone.utc),
                references=sample_email_payload["references"],
                attachments=[],
            )
        )
        session.flush()
        repositories = build_repository_bundle(session)
        state_service = TicketStateService(session, repositories=repositories)
        nodes = TicketNodes(
            agents=TicketExecutionAgents(),
            service_container=FakeServices(FakeGmailClient()),
            session=session,
            repositories=repositories,
            state_service=state_service,
            message_log=message_log,
            run=run,
            worker_id="worker-1",
        )
        yield nodes, ticket, run, session


def test_ticket_execution_nodes_route_knowledge_request_to_gmail_draft(sample_email_payload):
    triage_output = TriageOutput(
        primary_route="knowledge_request",
        secondary_routes=[],
        tags=[],
        response_strategy="answer",
        multi_intent=False,
        intent_confidence=0.91,
        priority="medium",
        needs_clarification=False,
        needs_escalation=False,
        routing_reason="Knowledge request.",
    )
    with _build_ticket_execution_nodes(sample_email_payload, triage_output=triage_output) as (
        nodes,
        ticket,
        run,
        session,
    ):
        state = build_ticket_run_state(
            ticket_id=ticket.ticket_id,
            business_status=ticket.business_status,
            processing_status=ticket.processing_status,
            ticket_version=ticket.version,
            trace_id=run.trace_id,
            run_id=run.run_id,
        )
        state.update(nodes.load_ticket_context(state))
        state.update(nodes.load_memory(state))
        state.update(nodes.triage_ticket(state))
        assert nodes.route_ticket(state) == "knowledge_lookup"
        state.update(nodes.knowledge_lookup(state))
        state.update(nodes.draft_reply(state))
        state.update(nodes.qa_review(state))
        assert nodes.route_after_qa(state) == "create_gmail_draft"
        state.update(nodes.create_gmail_draft(state))
        state.update(nodes.collect_case_context(state))
        state.update(nodes.extract_memory_updates(state))
        state.update(nodes.validate_memory_updates(state))

        assert state["final_action"] == "create_draft"
        assert state["business_status"] == "draft_created"
        assert state["memory_updates"]["customer_id"] == ticket.customer_id
        assert state["memory_updates"]["historical_case_ref"]["outcome"] == "draft_created"


def test_triage_ticket_updates_routing_fields_without_retriaging_state():
    triage_output = TriageOutput(
        primary_route="knowledge_request",
        secondary_routes=[],
        tags=[],
        response_strategy="answer",
        multi_intent=False,
        intent_confidence=0.91,
        priority="medium",
        needs_clarification=False,
        needs_escalation=False,
        routing_reason="Knowledge request.",
    )
    payload = {
        "messageId": "<product-enquiry@test.local>",
        "sender": '"Customer" <customer@example.com>',
        "subject": "How do I enable SSO?",
        "body": "We are on the pro plan. Where do I enable SSO?",
        "references": None,
    }
    with _build_ticket_execution_nodes(payload, triage_output=triage_output) as (
        nodes,
        ticket,
        run,
        session,
    ):
        ticket.business_status = "triaged"
        session.flush()
        state = build_ticket_run_state(
            ticket_id=ticket.ticket_id,
            business_status="triaged",
            processing_status=ticket.processing_status,
            ticket_version=ticket.version,
            trace_id=run.trace_id,
            run_id=run.run_id,
        )
        state.update(nodes.load_ticket_context(state))
        state.update(nodes.load_memory(state))

        result = nodes.triage_ticket(state)

        assert result["business_status"] == "triaged"
        assert result["primary_route"] == "knowledge_request"
        assert result["routing_reason"] == "Knowledge request."


def test_ticket_execution_nodes_route_high_risk_case_to_human_review(sample_email_payload):
    triage_output = TriageOutput(
        primary_route="commercial_policy_request",
        secondary_routes=[],
        tags=["refund_request"],
        response_strategy="policy_constrained",
        multi_intent=False,
        intent_confidence=0.91,
        priority="high",
        needs_clarification=False,
        needs_escalation=True,
        routing_reason="Refund requests require manual review.",
    )
    with _build_ticket_execution_nodes(sample_email_payload, triage_output=triage_output) as (
        nodes,
        ticket,
        run,
        session,
    ):
        state = build_ticket_run_state(
            ticket_id=ticket.ticket_id,
            business_status=ticket.business_status,
            processing_status=ticket.processing_status,
            ticket_version=ticket.version,
            trace_id=run.trace_id,
            run_id=run.run_id,
        )
        state.update(nodes.load_ticket_context(state))
        state.update(nodes.load_memory(state))
        state.update(nodes.triage_ticket(state))
        assert nodes.route_ticket(state) == "policy_check"
        state.update(nodes.policy_check(state))
        assert nodes.route_after_knowledge(state) == "escalate_to_human"
        state.update(nodes.escalate_to_human(state))
        state.update(nodes.collect_case_context(state))
        state.update(nodes.extract_memory_updates(state))
        state.update(nodes.validate_memory_updates(state))

        assert state["business_status"] == "awaiting_human_review"
        assert state["final_action"] == "handoff_to_human"
        assert "needs_escalation" in state["memory_updates"]["risk_tags_to_add"]


def test_ticket_execution_nodes_route_policy_secondary_intent_to_policy_check(
    sample_email_payload,
):
    triage_output = TriageOutput(
        primary_route="knowledge_request",
        secondary_routes=["commercial_policy_request"],
        tags=["billing_question", "needs_escalation"],
        response_strategy="answer",
        multi_intent=True,
        intent_confidence=0.84,
        priority="high",
        needs_clarification=False,
        needs_escalation=True,
        routing_reason="The main ask is product guidance, but the email also includes a billing dispute.",
    )
    with _build_ticket_execution_nodes(sample_email_payload, triage_output=triage_output) as (
        nodes,
        ticket,
        run,
        session,
    ):
        state = build_ticket_run_state(
            ticket_id=ticket.ticket_id,
            business_status=ticket.business_status,
            processing_status=ticket.processing_status,
            ticket_version=ticket.version,
            trace_id=run.trace_id,
            run_id=run.run_id,
        )
        state.update(nodes.load_ticket_context(state))
        state.update(nodes.load_memory(state))
        state.update(nodes.triage_ticket(state))

        assert nodes.route_ticket(state) == "escalate_to_human"


def test_ticket_execution_nodes_route_unrelated_escalation_to_human(sample_email_payload):
    triage_output = TriageOutput(
        primary_route="unrelated",
        secondary_routes=[],
        tags=["needs_escalation"],
        response_strategy="acknowledgement",
        multi_intent=False,
        intent_confidence=0.42,
        priority="medium",
        needs_clarification=False,
        needs_escalation=True,
        routing_reason="The intent is unclear, so a human should review it instead of auto-closing.",
    )
    with _build_ticket_execution_nodes(sample_email_payload, triage_output=triage_output) as (
        nodes,
        ticket,
        run,
        session,
    ):
        state = build_ticket_run_state(
            ticket_id=ticket.ticket_id,
            business_status=ticket.business_status,
            processing_status=ticket.processing_status,
            ticket_version=ticket.version,
            trace_id=run.trace_id,
            run_id=run.run_id,
        )
        state.update(nodes.load_ticket_context(state))
        state.update(nodes.load_memory(state))
        state.update(nodes.triage_ticket(state))

        assert nodes.route_ticket(state) == "escalate_to_human"


def test_ticket_execution_nodes_route_technical_issue_to_clarification(sample_email_payload):
    triage_output = TriageOutput(
        primary_route="technical_issue",
        secondary_routes=[],
        tags=["needs_clarification"],
        response_strategy="troubleshooting",
        multi_intent=False,
        intent_confidence=0.88,
        priority="medium",
        needs_clarification=True,
        needs_escalation=False,
        routing_reason="Diagnostics are incomplete.",
    )
    with _build_ticket_execution_nodes(sample_email_payload, triage_output=triage_output) as (
        nodes,
        ticket,
        run,
        session,
    ):
        state = build_ticket_run_state(
            ticket_id=ticket.ticket_id,
            business_status=ticket.business_status,
            processing_status=ticket.processing_status,
            ticket_version=ticket.version,
            trace_id=run.trace_id,
            run_id=run.run_id,
        )
        state.update(nodes.load_ticket_context(state))
        state.update(nodes.load_memory(state))
        state.update(nodes.triage_ticket(state))

        assert nodes.route_ticket(state) == "clarify_request"
        state.update(nodes.clarify_request(state))
        state.update(nodes.collect_case_context(state))
        state.update(nodes.extract_memory_updates(state))
        state.update(nodes.validate_memory_updates(state))

        assert state["business_status"] == "awaiting_customer_input"
        assert state["final_action"] == "request_clarification"
        assert state["clarification_history"][0]["source"] == "clarify_request"
        assert state["memory_updates"]["historical_case_ref"]["outcome"] == "awaiting_customer_input"
