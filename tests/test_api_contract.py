from __future__ import annotations

from datetime import datetime, timedelta, timezone
from tempfile import mkstemp
from os import close

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import get_container
from src.bootstrap.container import ServiceContainer
from src.contracts.core import EntityIdPrefix, generate_prefixed_id
from src.contracts.outputs import (
    DraftingOutput,
    KnowledgePolicyOutput,
    QaHandoffOutput,
    TriageOutput,
)
from src.db.base import Base
from src.db.models import CustomerMemoryProfile, DraftArtifact, Ticket, TicketRun
from src.db.session import build_engine, create_session_factory
from src.orchestration.checkpointing import build_test_checkpointer
from src.tools.ticket_store import SqlAlchemyTicketStore


class FakeResponseQualityJudge:
    def __init__(self, *, should_fail: bool = False) -> None:
        self._should_fail = should_fail

    def evaluate(
        self,
        *,
        email_subject,
        email_body,
        draft_text,
        evidence_summary,
        policy_summary,
        primary_route,
        final_action,
    ):
        if self._should_fail:
            return type(
                "JudgeEval",
                (),
                {
                    "response_quality": None,
                    "llm_metadata": {
                        "model": "fake-judge-model",
                        "provider": "openai-compatible",
                        "prompt_tokens": 9,
                        "completion_tokens": 0,
                        "total_tokens": 9,
                        "token_source": "estimated",
                        "request_id": "req_judge_fail",
                        "finish_reason": None,
                        "prompt_version": "response_quality_judge_v1",
                        "judge_name": "response_quality_judge",
                        "judge_status": "failed",
                        "error_message": "judge timeout",
                        "raw_text": None,
                        "latency_ms": 12,
                    },
                },
            )()
        return type(
            "JudgeEval",
            (),
            {
                "response_quality": {
                    "overall_score": 4.25,
                    "subscores": {
                        "relevance": 5,
                        "correctness": 4,
                        "intent_alignment": 4,
                        "clarity": 4,
                    },
                    "reason": "Judge accepted the draft.",
                },
                "llm_metadata": {
                    "model": "fake-judge-model",
                    "provider": "openai-compatible",
                    "prompt_tokens": 9,
                    "completion_tokens": 5,
                    "total_tokens": 14,
                    "token_source": "provider_actual",
                    "request_id": "req_judge_ok",
                    "finish_reason": "stop",
                    "prompt_version": "response_quality_judge_v1",
                    "judge_name": "response_quality_judge",
                    "judge_status": "succeeded",
                    "latency_ms": 12,
                },
            },
        )()


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


class FakeApiAgents:
    def triage_email_with_rules_detailed(self, *, subject, email, context=None):
        normalized = f"{subject or ''}\n{email}".lower()
        if "refund" in normalized or "charged twice" in normalized:
            output = TriageOutput(
                primary_route="commercial_policy_request",
                secondary_routes=[],
                tags=["needs_escalation"],
                response_strategy="policy_constrained",
                multi_intent=False,
                intent_confidence=0.91,
                priority="high",
                needs_clarification=False,
                needs_escalation=True,
                routing_reason="Refund disputes require manual review.",
            )
        elif "error" in normalized or "failed" in normalized:
            output = TriageOutput(
                primary_route="technical_issue",
                secondary_routes=[],
                tags=["needs_clarification"],
                response_strategy="troubleshooting",
                multi_intent=False,
                intent_confidence=0.88,
                priority="medium",
                needs_clarification=True,
                needs_escalation=False,
                routing_reason="Technical issue is missing diagnostic detail.",
            )
        else:
            output = TriageOutput(
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
        return type(
            "Decision",
            (),
            {
                "output": output,
                "selected_rule": "fake_runtime",
                "matched_rules": ("fake_runtime",),
                "escalation_reasons": (),
                "llm_invocation": None,
            },
        )()

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
            draft_rationale="deterministic drafting for api tests",
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
            reason="deterministic qa for api tests",
            human_handoff_summary="needs human review" if needs_escalation else None,
        )


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
        agents_factory=lambda: FakeApiAgents(),
        response_quality_judge_factory=lambda: FakeResponseQualityJudge(),
        gmail_client_factory=lambda: FakeApiGmailClient(),
        knowledge_provider_factory=lambda: FakeApiKnowledgeProvider(),
        policy_provider_factory=lambda: FakeApiPolicyProvider(),
        ticket_store_factory=lambda: store,
        checkpointer_factory=build_test_checkpointer,
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
                    "prompt_tokens_total": 90,
                    "completion_tokens_total": 30,
                    "total_tokens": 120,
                    "llm_call_count": 1,
                    "tool_call_count": 0,
                    "actual_token_call_count": 1,
                    "estimated_token_call_count": 0,
                    "unavailable_token_call_count": 0,
                    "token_coverage_ratio": 1.0,
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


def test_run_ticket_enqueues_run_without_sync_execution():
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
    assert payload["processing_status"] == "queued"

    snapshot = client.get(f"/tickets/{ticket.ticket_id}")
    assert snapshot.status_code == 200
    snapshot_payload = snapshot.json()
    assert snapshot_payload["ticket"]["business_status"] == "triaged"
    assert snapshot_payload["ticket"]["processing_status"] == "queued"
    assert snapshot_payload["ticket"]["claimed_by"] is None
    assert snapshot_payload["ticket"]["claimed_at"] is None
    assert snapshot_payload["ticket"]["lease_until"] is None
    assert snapshot_payload["latest_run"]["trace_id"] == payload["trace_id"]
    assert snapshot_payload["latest_run"]["status"] == "queued"
    assert "events" not in snapshot_payload["latest_run"]
    assert "latency_metrics" not in snapshot_payload["latest_run"]
    assert "resource_metrics" not in snapshot_payload["latest_run"]
    assert "response_quality" not in snapshot_payload["latest_run"]
    assert "trajectory_evaluation" not in snapshot_payload["latest_run"]
    assert snapshot_payload["latest_run"]["evaluation_summary_ref"] == {
        "status": "not_available",
        "trace_id": payload["trace_id"],
        "has_response_quality": False,
        "response_quality_overall_score": None,
        "has_trajectory_evaluation": False,
        "trajectory_score": None,
        "trajectory_violation_count": None,
    }
    assert snapshot_payload["latest_draft"] is None

    with store.session_scope() as session:
        persisted_run = session.get(TicketRun, payload["run_id"])
        assert persisted_run is not None
        assert persisted_run.status == "queued"
        assert persisted_run.started_at is None
        assert persisted_run.ended_at is None
        assert persisted_run.response_quality is None
        assert persisted_run.trajectory_evaluation is None


def test_run_ticket_rejects_when_ticket_already_has_queued_run():
    app, store = _build_app()
    client = TestClient(app)
    ticket = _create_ticket(store, business_status="triaged", processing_status="queued", version=2)

    with store.session_scope() as session:
        queued_run = TicketRun(
            run_id=generate_prefixed_id(EntityIdPrefix.RUN),
            ticket_id=ticket.ticket_id,
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type="manual_api",
            status="queued",
            attempt_index=1,
        )
        session.add(queued_run)
        persisted_ticket = session.get(Ticket, ticket.ticket_id)
        assert persisted_ticket is not None
        persisted_ticket.current_run_id = queued_run.run_id

    response = client.post(
        f"/tickets/{ticket.ticket_id}/run",
        json={
            "ticket_version": 2,
            "trigger_type": "manual_api",
            "force_retry": False,
        },
        headers={"X-Actor-Id": "api-user", "X-Request-Id": "req-queued-conflict"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state_transition"


def test_get_ticket_trace_supports_explicit_run_selection():
    app, store = _build_app()
    client = TestClient(app)

    ticket, first_run_id, _ = _seed_review_ticket(store)

    with store.session_scope() as session:
        session.add(
            TicketRun(
                run_id=generate_prefixed_id(EntityIdPrefix.RUN),
                ticket_id=ticket.ticket_id,
                trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
                trigger_type="manual_api",
                status="succeeded",
                started_at=datetime.now(timezone.utc),
                ended_at=datetime.now(timezone.utc) + timedelta(seconds=2),
                final_action="create_draft",
                attempt_index=2,
                latency_metrics={"end_to_end_ms": 2400, "slowest_node": "draft_reply"},
                resource_metrics={
                    "prompt_tokens_total": 180,
                    "completion_tokens_total": 60,
                    "total_tokens": 240,
                    "llm_call_count": 2,
                    "tool_call_count": 1,
                    "actual_token_call_count": 0,
                    "estimated_token_call_count": 1,
                    "unavailable_token_call_count": 1,
                    "token_coverage_ratio": 0.0,
                },
                response_quality={
                    "overall_score": 3.9,
                    "subscores": {
                        "relevance": 3.9,
                        "correctness": 3.8,
                        "intent_alignment": 4.0,
                        "clarity": 3.9,
                    },
                    "reason": "follow-up run",
                },
                trajectory_evaluation={
                    "score": 4.1,
                    "expected_route": "commercial_policy_request",
                    "actual_route": "commercial_policy_request",
                    "violations": [],
                },
            )
        )

    latest_trace = client.get(f"/tickets/{ticket.ticket_id}/trace")
    assert latest_trace.status_code == 200
    assert latest_trace.json()["run_id"] != first_run_id

    explicit_trace = client.get(
        f"/tickets/{ticket.ticket_id}/trace",
        params={"run_id": first_run_id},
    )
    assert explicit_trace.status_code == 200
    explicit_payload = explicit_trace.json()
    assert explicit_payload["run_id"] == first_run_id
    assert explicit_payload["trace_id"].startswith("trace_")
    assert explicit_payload["latency_metrics"]["end_to_end_ms"] == 1000


def test_get_ticket_trace_rejects_run_id_from_other_ticket():
    app, store = _build_app()
    client = TestClient(app)

    first_ticket, _, _ = _seed_review_ticket(store)
    second_ticket, other_run_id, _ = _seed_review_ticket(store)

    response = client.get(
        f"/tickets/{first_ticket.ticket_id}/trace",
        params={"run_id": other_run_id},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert response.json()["error"]["details"] == {
        "ticket_id": first_ticket.ticket_id,
        "run_id": other_run_id,
    }


def test_ticket_snapshot_returns_null_latest_run_when_no_runs_exist():
    app, store = _build_app()
    client = TestClient(app)

    ticket = _create_ticket(store, business_status="new", processing_status="queued", version=1)

    response = client.get(f"/tickets/{ticket.ticket_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_run"] is None


def test_ticket_snapshot_returns_partial_eval_summary_when_only_trajectory_exists():
    app, store = _build_app()
    client = TestClient(app)

    ticket = _create_ticket(
        store,
        business_status="draft_created",
        processing_status="completed",
        version=2,
        primary_route="technical_issue",
    )
    run_id = generate_prefixed_id(EntityIdPrefix.RUN)
    trace_id = generate_prefixed_id(EntityIdPrefix.TRACE)
    with store.session_scope() as session:
        session.add(
            TicketRun(
                run_id=run_id,
                ticket_id=ticket.ticket_id,
                trace_id=trace_id,
                trigger_type="manual_api",
                status="succeeded",
                started_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                ended_at=datetime.now(timezone.utc),
                final_action="create_draft",
                attempt_index=1,
                response_quality=None,
                trajectory_evaluation={
                    "score": 4.0,
                    "expected_route": "technical_issue",
                    "actual_route": "technical_issue",
                    "violations": ["missing_required_diagnostic_step"],
                },
            )
        )

    response = client.get(f"/tickets/{ticket.ticket_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_run"]["evaluation_summary_ref"] == {
        "status": "partial",
        "trace_id": trace_id,
        "has_response_quality": False,
        "response_quality_overall_score": None,
        "has_trajectory_evaluation": True,
        "trajectory_score": 4.0,
        "trajectory_violation_count": 1,
    }


def test_ticket_snapshot_returns_not_available_eval_summary_for_running_run():
    app, store = _build_app()
    client = TestClient(app)

    ticket = _create_ticket(store, business_status="triaged", processing_status="running", version=2)
    run_id = generate_prefixed_id(EntityIdPrefix.RUN)
    trace_id = generate_prefixed_id(EntityIdPrefix.TRACE)
    with store.session_scope() as session:
        session.add(
            TicketRun(
                run_id=run_id,
                ticket_id=ticket.ticket_id,
                trace_id=trace_id,
                trigger_type="manual_api",
                status="running",
                started_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                ended_at=None,
                final_action=None,
                attempt_index=1,
                response_quality=None,
                trajectory_evaluation=None,
            )
        )

    response = client.get(f"/tickets/{ticket.ticket_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_run"]["evaluation_summary_ref"] == {
        "status": "not_available",
        "trace_id": trace_id,
        "has_response_quality": False,
        "response_quality_overall_score": None,
        "has_trajectory_evaluation": False,
        "trajectory_score": None,
        "trajectory_violation_count": None,
    }


def test_ticket_snapshot_projects_current_claim_fields():
    app, store = _build_app()
    client = TestClient(app)

    ticket = _create_ticket(
        store,
        business_status="triaged",
        processing_status="running",
        version=3,
        primary_route="technical_issue",
    )
    current_run_id = generate_prefixed_id(EntityIdPrefix.RUN)
    other_run_id = generate_prefixed_id(EntityIdPrefix.RUN)
    lease_until = datetime(2026, 4, 3, 2, 5, tzinfo=timezone.utc)
    started_at = datetime(2026, 4, 3, 2, 0, tzinfo=timezone.utc)
    with store.session_scope() as session:
        current_run = TicketRun(
            run_id=current_run_id,
            ticket_id=ticket.ticket_id,
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type="manual_api",
            status="running",
            started_at=started_at,
            created_at=started_at - timedelta(minutes=30),
            attempt_index=1,
        )
        latest_finished = TicketRun(
            run_id=other_run_id,
            ticket_id=ticket.ticket_id,
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type="manual_api",
            status="succeeded",
            started_at=started_at - timedelta(minutes=10),
            ended_at=started_at - timedelta(minutes=9),
            final_action="create_draft",
            attempt_index=2,
            created_at=started_at - timedelta(minutes=20),
            response_quality={
                "overall_score": 4.0,
                "subscores": {
                    "relevance": 4.0,
                    "correctness": 4.0,
                    "intent_alignment": 4.0,
                    "clarity": 4.0,
                },
                "reason": "ok",
            },
            trajectory_evaluation={
                "score": 4.0,
                "expected_route": "technical_issue",
                "actual_route": "technical_issue",
                "violations": [],
            },
        )
        session.add(current_run)
        session.add(latest_finished)
        persisted_ticket = session.get(Ticket, ticket.ticket_id)
        assert persisted_ticket is not None
        persisted_ticket.current_run_id = current_run_id
        persisted_ticket.lease_owner = "worker-9"
        persisted_ticket.lease_expires_at = lease_until

    response = client.get(f"/tickets/{ticket.ticket_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ticket"]["claimed_by"] == "worker-9"
    assert payload["ticket"]["claimed_at"] == "2026-04-03T02:00:00+00:00"
    assert payload["ticket"]["lease_until"] == "2026-04-03T02:05:00+00:00"
    assert payload["latest_run"]["run_id"] == other_run_id


def test_ticket_snapshot_selects_latest_run_by_created_at_then_run_id():
    app, store = _build_app()
    client = TestClient(app)

    ticket = _create_ticket(
        store,
        business_status="draft_created",
        processing_status="completed",
        version=2,
        primary_route="technical_issue",
    )
    shared_created_at = datetime.now(timezone.utc)
    with store.session_scope() as session:
        older_started_later = TicketRun(
            run_id="run_00000000000000000000000001",
            ticket_id=ticket.ticket_id,
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type="manual_api",
            status="succeeded",
            started_at=shared_created_at + timedelta(minutes=5),
            ended_at=shared_created_at + timedelta(minutes=6),
            final_action="create_draft",
            attempt_index=1,
            created_at=shared_created_at,
            response_quality={
                "overall_score": 3.5,
                "subscores": {
                    "relevance": 3.5,
                    "correctness": 3.5,
                    "intent_alignment": 3.5,
                    "clarity": 3.5,
                },
                "reason": "older created_at",
            },
            trajectory_evaluation={
                "score": 3.0,
                "expected_route": "technical_issue",
                "actual_route": "technical_issue",
                "violations": [],
            },
        )
        newer_created = TicketRun(
            run_id="run_00000000000000000000000002",
            ticket_id=ticket.ticket_id,
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type="manual_api",
            status="succeeded",
            started_at=shared_created_at,
            ended_at=shared_created_at + timedelta(minutes=1),
            final_action="create_draft",
            attempt_index=2,
            created_at=shared_created_at,
            response_quality=None,
            trajectory_evaluation={
                "score": 4.2,
                "expected_route": "technical_issue",
                "actual_route": "technical_issue",
                "violations": [],
            },
        )
        session.add(older_started_later)
        session.add(newer_created)

    response = client.get(f"/tickets/{ticket.ticket_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_run"]["run_id"] == "run_00000000000000000000000002"
    assert payload["latest_run"]["evaluation_summary_ref"]["status"] == "partial"


def test_run_ticket_only_queues_high_risk_case():
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
    assert run.json()["processing_status"] == "queued"
    snapshot = client.get(f"/tickets/{ticket_id}")
    assert snapshot.json()["ticket"]["business_status"] == "triaged"
    assert snapshot.json()["ticket"]["processing_status"] == "queued"
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


def test_metrics_summary_filters_by_route():
    app, store = _build_app()
    client = TestClient(app)

    _seed_review_ticket(store, primary_route="commercial_policy_request")
    _seed_review_ticket(store, primary_route="technical_issue")

    now = datetime.now(timezone.utc)
    response = client.get(
        "/metrics/summary",
        params={
            "from": (now - timedelta(days=1)).isoformat(),
            "to": (now + timedelta(days=1)).isoformat(),
            "route": "technical_issue",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["latency"]["p50_ms"] == 1000.0
    assert payload["resources"]["avg_total_tokens"] == 120.0
    assert payload["resources"]["avg_actual_token_call_count"] == 1.0
    assert payload["resources"]["avg_estimated_token_call_count"] == 0.0
    assert payload["resources"]["avg_unavailable_token_call_count"] == 0.0
    assert payload["resources"]["avg_token_coverage_ratio"] == 1.0
    assert payload["trajectory_evaluation"]["avg_score"] == 4.8


def test_metrics_summary_rejects_invalid_route():
    app, _ = _build_app()
    client = TestClient(app)

    now = datetime.now(timezone.utc)
    response = client.get(
        "/metrics/summary",
        params={
            "from": (now - timedelta(days=1)).isoformat(),
            "to": now.isoformat(),
            "route": "unknown_route",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["details"]["query"] == "route"


def test_metrics_summary_rejects_inverted_time_window():
    app, _ = _build_app()
    client = TestClient(app)

    now = datetime.now(timezone.utc)
    response = client.get(
        "/metrics/summary",
        params={
            "from": now.isoformat(),
            "to": (now - timedelta(days=1)).isoformat(),
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["details"] == {"query": ["from", "to"]}


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
