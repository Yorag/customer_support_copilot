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
    thread_seed = generate_prefixed_id(EntityIdPrefix.TICKET)
    ticket = Ticket(
        ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
        source_thread_id=f"gmail-thread-{thread_seed}",
        source_message_id=f"<root-{thread_seed}@gmail.com>",
        gmail_thread_id=f"gmail-thread-{thread_seed}",
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


def _seed_review_ticket(
    store: SqlAlchemyTicketStore,
    *,
    business_status: str = "awaiting_human_review",
    processing_status: str = "waiting_external",
    version: int = 7,
    primary_route: str = "commercial_policy_request",
    draft_qa_status: str = "pending",
) -> tuple[Ticket, str, DraftArtifact]:
    ticket = _create_ticket(
        store,
        business_status=business_status,
        processing_status=processing_status,
        version=version,
        primary_route=primary_route,
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
                resource_metrics={
                    "total_tokens": 120,
                    "llm_call_count": 1,
                    "tool_call_count": 0,
                },
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
                    "expected_route": primary_route,
                    "actual_route": primary_route,
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
            qa_status=draft_qa_status,
        )
        session.add(draft)
        session.flush()
        session.expunge(draft)
    return ticket, run_id, draft


def _seed_customer_memory_profile(store: SqlAlchemyTicketStore) -> None:
    with store.session_scope() as session:
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
    assert "prompt_tokens_total" in trace_payload["resource_metrics"]
    assert "node_latencies" in trace_payload["latency_metrics"]


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


def test_approve_and_close_update_memory_and_metrics_queries():
    app, store = _build_app()
    client = TestClient(app)

    ticket, _, draft = _seed_review_ticket(store)
    _seed_customer_memory_profile(store)

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
    assert "review_id" in approve.json()

    close = client.post(
        f"/tickets/{ticket.ticket_id}/close",
        json={"ticket_version": 8, "reason": "draft_sent_manually"},
        headers={"X-Actor-Id": "reviewer-1"},
    )
    assert close.status_code == 200
    assert close.json()["business_status"] == "closed"
    assert "review_id" not in close.json()

    with store.session_scope() as session:
        latest_human_action_run = (
            session.query(TicketRun)
            .filter(TicketRun.ticket_id == ticket.ticket_id, TicketRun.trigger_type == "human_action")
            .order_by(TicketRun.started_at.desc(), TicketRun.created_at.desc())
            .first()
        )
        assert latest_human_action_run is not None
        assert latest_human_action_run.triggered_by == "reviewer-1"

    memory = client.get("/customers/cust_email_liwei_example_com/memory")
    assert memory.status_code == 200
    memory_payload = memory.json()
    assert memory_payload["customer_id"] == "cust_email_liwei_example_com"
    assert memory_payload["profile"] == {
        "name": "Li Wei",
        "account_tier": "pro",
        "preferred_language": "en",
        "preferred_tone": "direct",
    }
    assert memory_payload["risk_tags"] == [
        "policy_sensitive_case",
        "refund_dispute_history",
    ]
    assert memory_payload["business_flags"] == {
        "high_value_customer": False,
        "refund_dispute_history": True,
        "requires_manual_approval": True,
    }
    assert memory_payload["version"] == 4
    assert any(
        item["ticket_id"] == ticket.ticket_id for item in memory_payload["historical_case_refs"]
    )

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


def test_edit_and_approve_returns_review_and_creates_new_draft_version():
    app, store = _build_app()
    client = TestClient(app)
    ticket, _, draft = _seed_review_ticket(store)

    response = client.post(
        f"/tickets/{ticket.ticket_id}/edit-and-approve",
        json={
            "ticket_version": 7,
            "draft_id": draft.draft_id,
            "comment": "Softened the refund wording.",
            "edited_content_text": "Hello, we have received your request and will review it.",
        },
        headers={"X-Actor-Id": "reviewer-2"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["business_status"] == "approved"
    assert payload["processing_status"] == "completed"
    assert "review_id" in payload

    with store.session_scope() as session:
        drafts = (
            session.query(DraftArtifact)
            .filter(DraftArtifact.ticket_id == ticket.ticket_id)
            .order_by(DraftArtifact.version_index.asc())
            .all()
        )
        assert len(drafts) == 2
        assert drafts[-1].version_index == 2
        assert drafts[-1].content_text == (
            "Hello, we have received your request and will review it."
        )


def test_rewrite_and_escalate_follow_contract_states():
    app, store = _build_app()
    client = TestClient(app)
    ticket, _, draft = _seed_review_ticket(store)

    rewrite = client.post(
        f"/tickets/{ticket.ticket_id}/rewrite",
        json={
            "ticket_version": 7,
            "draft_id": draft.draft_id,
            "comment": "Do not imply refund approval before confirmation.",
            "rewrite_reasons": [
                "over_committed_refund_outcome",
                "policy_wording_too_strong",
            ],
        },
        headers={"X-Actor-Id": "reviewer-3"},
    )

    assert rewrite.status_code == 200
    rewrite_payload = rewrite.json()
    assert rewrite_payload["business_status"] == "rejected"
    assert rewrite_payload["processing_status"] == "queued"
    assert "review_id" in rewrite_payload

    triaged_ticket = _create_ticket(
        store,
        business_status="triaged",
        processing_status="completed",
        version=4,
        primary_route="technical_issue",
        subject="Security concern",
        latest_message_excerpt="Possible token exposure.",
    )
    escalate = client.post(
        f"/tickets/{triaged_ticket.ticket_id}/escalate",
        json={
            "ticket_version": 4,
            "comment": "Security implication needs specialist review.",
            "target_queue": "security_support",
        },
        headers={"X-Actor-Id": "reviewer-4"},
    )

    assert escalate.status_code == 200
    escalate_payload = escalate.json()
    assert escalate_payload["business_status"] == "escalated"
    assert escalate_payload["processing_status"] == "waiting_external"
    assert "review_id" in escalate_payload


def test_manual_actions_require_actor_header():
    app, store = _build_app()
    client = TestClient(app)
    ticket, _, draft = _seed_review_ticket(store)

    response = client.post(
        f"/tickets/{ticket.ticket_id}/approve",
        json={
            "ticket_version": 7,
            "draft_id": draft.draft_id,
            "comment": "Looks good.",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["details"] == {"header": "X-Actor-Id"}


def test_manual_action_rejects_duplicate_idempotency_key():
    app, store = _build_app()
    client = TestClient(app)
    ticket, _, draft = _seed_review_ticket(store)

    request_body = {
        "ticket_version": 7,
        "draft_id": draft.draft_id,
        "comment": "Policy wording looks safe.",
    }
    headers = {
        "X-Actor-Id": "reviewer-1",
        "Idempotency-Key": "manual-approve-001",
    }

    first = client.post(f"/tickets/{ticket.ticket_id}/approve", json=request_body, headers=headers)
    second = client.post(f"/tickets/{ticket.ticket_id}/approve", json=request_body, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_request"


def test_manual_action_request_validation_rejects_blank_fields():
    app, store = _build_app()
    client = TestClient(app)
    ticket, _, draft = _seed_review_ticket(store)

    rewrite = client.post(
        f"/tickets/{ticket.ticket_id}/rewrite",
        json={
            "ticket_version": 7,
            "draft_id": draft.draft_id,
            "rewrite_reasons": [],
        },
        headers={"X-Actor-Id": "reviewer-3"},
    )
    assert rewrite.status_code == 422
    assert rewrite.json()["error"]["code"] == "validation_error"

    edit = client.post(
        f"/tickets/{ticket.ticket_id}/edit-and-approve",
        json={
            "ticket_version": 7,
            "draft_id": draft.draft_id,
            "edited_content_text": "   ",
        },
        headers={"X-Actor-Id": "reviewer-2"},
    )
    assert edit.status_code == 422
    assert edit.json()["error"]["code"] == "validation_error"

    escalate_ticket = _create_ticket(
        store,
        business_status="triaged",
        processing_status="completed",
        version=4,
        primary_route="technical_issue",
    )
    escalate = client.post(
        f"/tickets/{escalate_ticket.ticket_id}/escalate",
        json={
            "ticket_version": 4,
            "target_queue": "  ",
        },
        headers={"X-Actor-Id": "reviewer-4"},
    )
    assert escalate.status_code == 422
    assert escalate.json()["error"]["code"] == "validation_error"

    approved_ticket = _create_ticket(
        store,
        business_status="approved",
        processing_status="completed",
        version=8,
        primary_route="commercial_policy_request",
    )
    close = client.post(
        f"/tickets/{approved_ticket.ticket_id}/close",
        json={"ticket_version": 8, "reason": "  "},
        headers={"X-Actor-Id": "reviewer-5"},
    )
    assert close.status_code == 422
    assert close.json()["error"]["code"] == "validation_error"
