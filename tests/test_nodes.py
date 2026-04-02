from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from src.nodes import Nodes
from src.core_schema import EntityIdPrefix, generate_prefixed_id
from src.db.base import Base
from src.db.repositories import build_repository_bundle
from src.db.models import Ticket, TicketRun
from src.db.session import build_engine, create_session_factory, session_scope
from src.state import Email, build_ticket_run_state
from src.tools.types import KnowledgeAnswer
from src.structure_outputs import (
    DraftingOutput,
    KnowledgePolicyOutput,
    QaHandoffOutput,
    TriageOutput,
)
from src.message_log import MessageLogService
from src.ticket_state_machine import TicketStateService


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


class FakeServices:
    def __init__(self, gmail_client):
        self.gmail_client = gmail_client
        self.knowledge_provider = FakeKnowledgeProvider()
        self.policy_provider = FakePolicyProvider()
        self.ticket_store = FakeTicketStore()


def test_load_new_emails_uses_gmail_provider(sample_email_payload):
    gmail_client = FakeGmailClient(emails=[sample_email_payload])
    nodes = Nodes(agents=FakeAgents(), service_container=FakeServices(gmail_client))

    result = nodes.load_new_emails({})

    assert len(result["pending_emails"]) == 1
    assert result["emails"][0].subject == "Pricing question"
    assert result["raw_email"].subject == "Pricing question"


def test_retrieve_from_rag_uses_knowledge_provider():
    nodes = Nodes(
        agents=FakeAgents(),
        service_container=FakeServices(FakeGmailClient()),
    )

    result = nodes.retrieve_from_rag({"rag_queries": ["pricing", "billing"]})

    assert "pricing" in result["retrieved_documents"]
    assert "answer for billing" in result["retrieved_documents"]


def test_create_draft_response_uses_gmail_provider(sample_email_payload):
    gmail_client = FakeGmailClient()
    nodes = Nodes(agents=FakeAgents(), service_container=FakeServices(gmail_client))
    email = Email(**sample_email_payload)

    result = nodes.create_draft_response(
        build_ticket_run_state(raw_email=email) | {"generated_email": "Here is the answer"}
    )

    assert result["retrieved_documents"] == ""
    assert result["trials"] == 0
    assert result["applied_response_strategy"] is None
    assert gmail_client.created_drafts == [(email, "Here is the answer")]


def test_triage_email_returns_structured_output_and_legacy_category(sample_email_payload):
    gmail_client = FakeGmailClient(emails=[sample_email_payload])
    nodes = Nodes(agents=FakeAgents(), service_container=FakeServices(gmail_client))

    result = nodes.triage_email(
        build_ticket_run_state(pending_emails=[Email(**sample_email_payload)])
    )

    assert result["current_email"].subject == "Pricing question"
    assert result["raw_email"].subject == "Pricing question"
    assert result["triage_result"]["primary_route"] == "knowledge_request"
    assert result["primary_route"] == "knowledge_request"
    assert result["email_category"] == "product_enquiry"


def test_route_email_based_on_triage_uses_primary_route():
    nodes = Nodes(
        agents=FakeAgents(),
        service_container=FakeServices(FakeGmailClient()),
    )

    assert (
        nodes.route_email_based_on_triage(
            {"triage_result": {"primary_route": "knowledge_request"}}
        )
        == "product related"
    )
    assert (
        nodes.route_email_based_on_triage(
            {"triage_result": {"primary_route": "unrelated"}}
        )
        == "unrelated"
    )
    assert (
        nodes.route_email_based_on_triage(
            {"triage_result": {"primary_route": "feedback_intake"}}
        )
        == "not product related"
    )


def test_write_draft_email_updates_ticket_run_draft_fields(sample_email_payload):
    nodes = Nodes(
        agents=FakeAgents(),
        service_container=FakeServices(FakeGmailClient()),
    )
    state = build_ticket_run_state(raw_email=sample_email_payload)
    state.update(
        {
            "email_category": "product_enquiry",
            "retrieved_documents": "knowledge summary",
            "draft_versions": [],
        }
    )

    result = nodes.write_draft_email(state)

    assert result["trials"] == 1
    assert result["rewrite_count"] == 1
    assert result["draft_versions"][0]["version_index"] == 1
    assert "draft based on" in result["generated_email"]


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
        nodes = Nodes(
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
        result = nodes.create_gmail_draft(state)

        assert result["final_action"] == "create_draft"
        assert result["business_status"] == "draft_created"


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
        result = nodes.escalate_to_human(state)

        assert result["business_status"] == "awaiting_human_review"
        assert result["final_action"] == "handoff_to_human"


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
        result = nodes.clarify_request(state)

        assert result["business_status"] == "awaiting_customer_input"
        assert result["final_action"] == "request_clarification"
