from __future__ import annotations

from datetime import datetime, timedelta, timezone
from tempfile import mkstemp
from os import close

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import get_container
from src.core_schema import EntityIdPrefix, generate_prefixed_id
from src.db.base import Base
from src.db.models import CustomerMemoryProfile, DraftArtifact, Ticket, TicketRun
from src.db.session import build_engine, create_session_factory
from src.tools.service_container import ServiceContainer
from src.tools.ticket_store import SqlAlchemyTicketStore


class FakeApiGmailClient:
    def create_draft_reply(self, initial_email, reply_text):
        return {"id": "gmail-draft-test"}


class FakeApiKnowledgeProvider:
    def answer_questions(self, questions):
        return [
            type("Answer", (), {"question": question, "answer": f"answer for {question}"})()
            for question in questions
        ]


class FakeApiPolicyProvider:
    def get_policy(self, category=None):
        return f"policy for {category or 'default'}"


def _build_app():
    fd, path = mkstemp(suffix=".db")
    close(fd)
    engine = build_engine(f"sqlite+pysqlite:///{path}")
    Base.metadata.create_all(engine)
    store = SqlAlchemyTicketStore(
        engine=engine,
        session_factory=create_session_factory(engine),
    )
    app = create_app()
    app.dependency_overrides[get_container] = lambda: ServiceContainer(
        gmail_client_factory=lambda: FakeApiGmailClient(),
        knowledge_provider_factory=lambda: FakeApiKnowledgeProvider(),
        policy_provider_factory=lambda: FakeApiPolicyProvider(),
        ticket_store_factory=lambda: store,
    )
    return app, store


def _create_ticket(
    store: SqlAlchemyTicketStore,
    *,
    business_status: str = "new",
    processing_status: str = "queued",
    version: int = 1,
    primary_route: str | None = None,
    subject: str = "How do I configure SSO?",
    latest_message_excerpt: str = "How do I configure SSO for my workspace?",
) -> Ticket:
    ticket = Ticket(
        ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
        source_thread_id="gmail-thread-api",
        source_message_id="<root-api@gmail.com>",
        gmail_thread_id="gmail-thread-api",
        customer_id="cust_email_liwei_example_com",
        customer_email="liwei@example.com",
        customer_email_raw='"Li Wei" <liwei@example.com>',
        subject=subject,
        latest_message_excerpt=latest_message_excerpt,
        business_status=business_status,
        processing_status=processing_status,
        priority="medium",
        primary_route=primary_route,
        secondary_routes=[],
        tags=[],
        multi_intent=False,
        needs_clarification=False,
        needs_escalation=False,
        risk_reasons=[],
        version=version,
    )
    with store.session_scope() as session:
        session.add(ticket)
    return ticket


def test_ingest_email_creates_ticket_and_snapshot():
    app, store = _build_app()
    client = TestClient(app)

    response = client.post(
        "/tickets/ingest-email",
        json={
            "source_channel": "gmail",
            "source_thread_id": "thread-001",
            "source_message_id": "<msg-001@gmail.com>",
            "sender_email_raw": '"Li Wei" <liwei@example.com>',
            "subject": "Need refund for duplicate charge",
            "body_text": "I was charged twice this month.",
            "message_timestamp": "2026-03-31T20:55:00+08:00",
            "references": "<prev1@gmail.com>",
            "attachments": [{"filename": "invoice.pdf"}],
        },
        headers={"Idempotency-Key": "ingest-001"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["created"] is True
    assert payload["business_status"] == "new"
    assert payload["processing_status"] == "queued"

    snapshot = client.get(f"/tickets/{payload['ticket_id']}")
    assert snapshot.status_code == 200
    assert snapshot.json()["ticket"]["version"] == 1


def test_ingest_email_rejects_duplicate_idempotency_key():
    app, store = _build_app()
    client = TestClient(app)
    body = {
        "source_channel": "gmail",
        "source_thread_id": "thread-dup",
        "source_message_id": "<msg-dup@gmail.com>",
        "sender_email_raw": '"Li Wei" <liwei@example.com>',
        "subject": "Hello",
        "body_text": "Need help",
        "message_timestamp": "2026-03-31T20:55:00+08:00",
        "attachments": [],
    }

    first = client.post(
        "/tickets/ingest-email",
        json=body,
        headers={"Idempotency-Key": "dup-key"},
    )
    second = client.post(
        "/tickets/ingest-email",
        json=body,
        headers={"Idempotency-Key": "dup-key"},
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_request"


def test_run_ticket_creates_run_trace_and_draft_created_status():
    app, store = _build_app()
    client = TestClient(app)

    ticket = _create_ticket(store, business_status="new", processing_status="queued", version=1)

    response = client.post(
        f"/tickets/{ticket.ticket_id}/run",
        json={
            "ticket_version": 1,
            "trigger_type": "manual_api",
            "force_retry": False,
        },
        headers={"X-Actor-Id": "api-user", "X-Request-Id": "req-001"},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["ticket_id"] == ticket.ticket_id
    assert payload["processing_status"] == "completed"

    snapshot = client.get(f"/tickets/{ticket.ticket_id}")
    assert snapshot.status_code == 200
    snapshot_payload = snapshot.json()
    assert snapshot_payload["ticket"]["business_status"] == "draft_created"
    assert snapshot_payload["latest_run"]["trace_id"] == payload["trace_id"]
    assert snapshot_payload["latest_draft"]["qa_status"] == "passed"

    trace = client.get(f"/tickets/{ticket.ticket_id}/trace")
    assert trace.status_code == 200
    trace_payload = trace.json()
    assert trace_payload["run_id"] == payload["run_id"]
    assert trace_payload["trace_id"] == payload["trace_id"]
    assert len(trace_payload["events"]) >= 2


def test_run_ticket_routes_high_risk_case_to_human_review():
    app, store = _build_app()
    client = TestClient(app)

    response = client.post(
        "/tickets/ingest-email",
        json={
            "source_channel": "gmail",
            "source_thread_id": "thread-high-risk",
            "source_message_id": "<msg-risk@gmail.com>",
            "sender_email_raw": '"Li Wei" <liwei@example.com>',
            "subject": "Need refund for duplicate charge",
            "body_text": "I need a refund because I was charged twice.",
            "message_timestamp": "2026-03-31T20:55:00+08:00",
            "attachments": [],
        },
    )
    ticket_id = response.json()["ticket_id"]

    run = client.post(
        f"/tickets/{ticket_id}/run",
        json={
            "ticket_version": 1,
            "trigger_type": "manual_api",
            "force_retry": False,
        },
        headers={"X-Actor-Id": "api-user", "X-Request-Id": "req-risk"},
    )

    assert run.status_code == 202
    snapshot = client.get(f"/tickets/{ticket_id}")
    assert snapshot.json()["ticket"]["business_status"] == "awaiting_human_review"
    assert snapshot.json()["latest_draft"] is None


def test_manual_actions_and_memory_and_metrics_queries():
    app, store = _build_app()
    client = TestClient(app)

    ticket = _create_ticket(
        store,
        business_status="awaiting_human_review",
        processing_status="waiting_external",
        version=7,
        primary_route="commercial_policy_request",
        subject="Need refund review",
        latest_message_excerpt="I need a refund because I was charged twice.",
    )
    run_id = generate_prefixed_id(EntityIdPrefix.RUN)
    with store.session_scope() as session:
        session.add(
            TicketRun(
                run_id=run_id,
                ticket_id=ticket.ticket_id,
                trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
                trigger_type="manual_api",
                status="succeeded",
                started_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                ended_at=datetime.now(timezone.utc),
                final_action="handoff_to_human",
                attempt_index=1,
                latency_metrics={"end_to_end_ms": 1000, "slowest_node": "triage"},
                resource_metrics={"total_tokens": 120, "llm_call_count": 1, "tool_call_count": 0},
                response_quality={
                    "overall_score": 4.5,
                    "subscores": {
                        "relevance": 4.5,
                        "correctness": 4.5,
                        "intent_alignment": 4.5,
                        "clarity": 4.5,
                    },
                    "reason": "ok",
                },
                trajectory_evaluation={
                    "score": 4.8,
                    "expected_route": "commercial_policy_request",
                    "actual_route": "commercial_policy_request",
                    "violations": [],
                },
            )
        )
        session.flush()
        draft = DraftArtifact(
            draft_id=generate_prefixed_id(EntityIdPrefix.DRAFT),
            ticket_id=ticket.ticket_id,
            run_id=run_id,
            version_index=1,
            draft_type="reply",
            content_text="Draft body",
            qa_status="pending",
        )
        session.add(draft)
        session.add(
            CustomerMemoryProfile(
                customer_id="cust_email_liwei_example_com",
                primary_email="liwei@example.com",
                alias_emails=["liwei@example.com"],
                profile={
                    "name": "Li Wei",
                    "account_tier": "pro",
                    "preferred_language": "en",
                    "preferred_tone": "direct",
                },
                risk_tags=["refund_dispute_history"],
                business_flags={
                    "high_value_customer": False,
                    "refund_dispute_history": True,
                    "requires_manual_approval": True,
                },
                historical_case_refs=[
                    {"ticket_id": "t_old", "summary": "Duplicate charge dispute."}
                ],
                version=3,
            )
        )

    approve = client.post(
        f"/tickets/{ticket.ticket_id}/approve",
        json={
            "ticket_version": 7,
            "draft_id": draft.draft_id,
            "comment": "Policy wording looks safe.",
        },
        headers={"X-Actor-Id": "reviewer-1"},
    )
    assert approve.status_code == 200
    assert approve.json()["business_status"] == "approved"

    close = client.post(
        f"/tickets/{ticket.ticket_id}/close",
        json={"ticket_version": 8, "reason": "draft_sent_manually"},
    )
    assert close.status_code == 200
    assert close.json()["business_status"] == "closed"

    memory = client.get("/customers/cust_email_liwei_example_com/memory")
    assert memory.status_code == 200
    assert memory.json()["version"] == 3

    now = datetime.now(timezone.utc)
    metrics = client.get(
        "/metrics/summary",
        params={
            "from": (now - timedelta(days=1)).isoformat(),
            "to": (now + timedelta(days=1)).isoformat(),
            "route": "commercial_policy_request",
        },
    )
    assert metrics.status_code == 200
    assert metrics.json()["latency"]["p50_ms"] == 1000.0
