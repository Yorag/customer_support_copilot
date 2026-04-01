from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from src.core_schema import EntityIdPrefix, generate_prefixed_id
from src.db.base import Base
from src.db.models import DraftArtifact, HumanReview, Ticket, TicketRun, TraceEvent
from src.db.session import build_engine, create_session_factory, session_scope


def _build_ticket(**overrides):
    payload = {
        "ticket_id": generate_prefixed_id(EntityIdPrefix.TICKET),
        "source_thread_id": "thread-001",
        "source_message_id": "msg-001",
        "gmail_thread_id": "gmail-thread-001",
        "customer_email": "liwei@example.com",
        "customer_email_raw": '"Li Wei" <liwei@example.com>',
        "subject": "Need help with login",
        "business_status": "new",
        "processing_status": "queued",
        "priority": "high",
        "secondary_routes": [],
        "tags": [],
        "multi_intent": False,
        "needs_clarification": False,
        "needs_escalation": False,
        "risk_reasons": [],
    }
    payload.update(overrides)
    return Ticket(**payload)


def test_core_entity_tables_are_created():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    table_names = set(inspect(engine).get_table_names())

    assert {
        "app_metadata",
        "tickets",
        "ticket_runs",
        "draft_artifacts",
        "human_reviews",
        "trace_events",
    }.issubset(table_names)


def test_ticket_defaults_and_sync_rules_persist():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        session.add(
            _build_ticket(
                primary_route="commercial_policy_request",
                secondary_routes=["technical_issue"],
                tags=["billing_question"],
                multi_intent=True,
                response_strategy="policy_constrained",
                intent_confidence=Decimal("0.912"),
            )
        )

    with session_scope(session_factory) as session:
        row = session.query(Ticket).one()

    assert row.source_channel == "gmail"
    assert row.version == 1
    assert row.reopen_count == 0
    assert row.is_active is True
    assert row.secondary_routes == ["technical_issue"]
    assert row.tags == ["billing_question", "multi_intent"]


def test_ticket_unique_active_thread_constraint_is_enforced():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with pytest.raises(IntegrityError):
        with session_scope(session_factory) as session:
            session.add(_build_ticket())
            session.add(
                _build_ticket(
                    ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
                    source_message_id="msg-002",
                )
            )


def test_ticket_run_requires_fixed_response_quality_keys():
    with pytest.raises(ValueError):
        TicketRun(
            run_id=generate_prefixed_id(EntityIdPrefix.RUN),
            ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type="manual_api",
            status="running",
            started_at=datetime.now(timezone.utc),
            attempt_index=1,
            response_quality={"score": 1},
        )


def test_trace_event_requires_minimum_metadata_keys_for_decisions():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    ticket = _build_ticket(ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET))
    run = TicketRun(
        run_id=generate_prefixed_id(EntityIdPrefix.RUN),
        ticket_id=ticket.ticket_id,
        trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
        trigger_type="manual_api",
        status="running",
        started_at=datetime.now(timezone.utc),
        attempt_index=1,
    )

    with pytest.raises(ValueError):
        with session_scope(session_factory) as session:
            session.add(ticket)
            session.add(run)
            session.add(
                TraceEvent(
                    event_id=generate_prefixed_id(EntityIdPrefix.MEMORY_EVENT),
                    trace_id=run.trace_id,
                    run_id=run.run_id,
                    ticket_id=ticket.ticket_id,
                    event_type="decision",
                    event_name="route_selected",
                    start_time=datetime.now(timezone.utc),
                    status="succeeded",
                    event_metadata={"primary_route": "technical_issue"},
                )
            )


def test_related_entities_can_be_persisted_end_to_end():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    ticket = _build_ticket(
        ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
        source_thread_id="thread-002",
        source_message_id="msg-010",
        gmail_thread_id="gmail-thread-002",
        business_status="awaiting_human_review",
        processing_status="waiting_external",
        priority="critical",
        primary_route="commercial_policy_request",
        secondary_routes=["technical_issue"],
        tags=["billing_question"],
        multi_intent=True,
        needs_escalation=True,
        response_strategy="policy_constrained",
        risk_reasons=["refund_amount_involved"],
    )
    run = TicketRun(
        run_id=generate_prefixed_id(EntityIdPrefix.RUN),
        ticket_id=ticket.ticket_id,
        trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
        trigger_type="manual_api",
        status="running",
        started_at=datetime.now(timezone.utc),
        attempt_index=1,
        response_quality={
            "overall_score": 0.91,
            "subscores": {},
            "reason": "good enough",
        },
        trajectory_evaluation={
            "score": 0.95,
            "expected_route": "commercial_policy_request",
            "actual_route": "commercial_policy_request",
            "violations": [],
        },
    )
    draft = DraftArtifact(
        draft_id=generate_prefixed_id(EntityIdPrefix.DRAFT),
        ticket_id=ticket.ticket_id,
        run_id=run.run_id,
        version_index=1,
        draft_type="reply",
        content_text="We are reviewing the refund request.",
        qa_status="pending",
    )
    review = HumanReview(
        review_id=generate_prefixed_id(EntityIdPrefix.REVIEW),
        ticket_id=ticket.ticket_id,
        draft_id=draft.draft_id,
        reviewer_id="agent-1",
        action="approve",
        ticket_version_at_review=1,
    )
    trace_event = TraceEvent(
        event_id=generate_prefixed_id(EntityIdPrefix.MEMORY_EVENT),
        trace_id=run.trace_id,
        run_id=run.run_id,
        ticket_id=ticket.ticket_id,
        event_type="decision",
        event_name="route_selected",
        start_time=datetime.now(timezone.utc),
        status="succeeded",
        event_metadata={
            "primary_route": "commercial_policy_request",
            "response_strategy": "policy_constrained",
            "needs_clarification": False,
            "needs_escalation": True,
            "final_action": "handoff_to_human",
        },
    )

    with session_scope(session_factory) as session:
        session.add(ticket)
        session.add(run)
        session.flush()
        session.add(draft)
        session.flush()
        session.add(review)
        session.add(trace_event)

    with session_scope(session_factory) as session:
        assert session.query(Ticket).count() == 1
        assert session.query(TicketRun).count() == 1
        assert session.query(DraftArtifact).count() == 1
        assert session.query(HumanReview).count() == 1
        assert session.query(TraceEvent).count() == 1
