from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from src.core_schema import (
    EntityIdPrefix,
    build_customer_identity,
    generate_prefixed_id,
    normalize_email_address,
)
from src.db.base import Base
from src.db.models import CustomerMemoryEvent, CustomerMemoryProfile, Ticket, TicketRun
from src.db.session import build_engine, create_session_factory, session_scope


def _build_ticket_and_run():
    ticket = Ticket(
        ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
        source_thread_id="thread-100",
        source_message_id="msg-100",
        gmail_thread_id="gmail-thread-100",
        customer_email="liwei@example.com",
        customer_email_raw='"Li Wei" <liwei@example.com>',
        subject="Need account help",
        business_status="new",
        processing_status="queued",
        priority="medium",
        secondary_routes=[],
        tags=[],
        multi_intent=False,
        needs_clarification=False,
        needs_escalation=False,
        risk_reasons=[],
    )
    run = TicketRun(
        run_id=generate_prefixed_id(EntityIdPrefix.RUN),
        ticket_id=ticket.ticket_id,
        trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
        trigger_type="manual_api",
        status="running",
        started_at=datetime.now(timezone.utc),
        attempt_index=1,
    )
    return ticket, run


def test_normalize_email_address_extracts_and_normalizes_sender():
    assert (
        normalize_email_address(' "Li Wei" <LiWei+VIP@Example.com> ')
        == "liwei+vip@example.com"
    )
    assert normalize_email_address("not-an-email") is None


def test_build_customer_identity_uses_alias_map():
    identity = build_customer_identity(
        '"Li Wei" <support+cn@example.com>',
        alias_map={"support+cn@example.com": "liwei@example.com"},
    )

    assert identity is not None
    assert identity.normalized_email == "liwei@example.com"
    assert identity.customer_id == "cust_email_liwei_example_com"


def test_build_customer_identity_returns_none_for_unreliable_email():
    assert build_customer_identity("invalid-email") is None
    assert build_customer_identity(None) is None


def test_customer_memory_profile_requires_fixed_keys():
    with pytest.raises(ValueError):
        CustomerMemoryProfile(
            customer_id="cust_email_liwei_example_com",
            primary_email="liwei@example.com",
            alias_emails=["support@example.com"],
            profile={"name": "Li Wei"},
            risk_tags=[],
            business_flags={
                "high_value_customer": True,
                "refund_dispute_history": False,
                "requires_manual_approval": False,
            },
            historical_case_refs=[],
        )


def test_customer_memory_entities_persist_end_to_end():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    ticket, run = _build_ticket_and_run()
    profile = CustomerMemoryProfile(
        customer_id="cust_email_liwei_example_com",
        primary_email="liwei@example.com",
        alias_emails=["support+cn@example.com"],
        profile={
            "name": "Li Wei",
            "account_tier": "enterprise",
            "preferred_language": "zh-CN",
            "preferred_tone": "direct",
        },
        risk_tags=["refund_dispute_history"],
        business_flags={
            "high_value_customer": True,
            "refund_dispute_history": True,
            "requires_manual_approval": False,
        },
        historical_case_refs=[
            {
                "ticket_id": "t_legacy_001",
                "summary": "Previous billing dispute",
            }
        ],
    )
    event = CustomerMemoryEvent(
        memory_event_id=generate_prefixed_id(EntityIdPrefix.MEMORY_EVENT),
        customer_id=profile.customer_id,
        ticket_id=ticket.ticket_id,
        run_id=run.run_id,
        source_stage="close_ticket",
        event_type="historical_case_append",
        payload={"summary": "Resolved refund dispute"},
        idempotency_key="ticket-close-1",
    )

    with session_scope(session_factory) as session:
        session.add(ticket)
        session.add(run)
        session.add(profile)
        session.flush()
        session.add(event)

    with session_scope(session_factory) as session:
        assert session.query(CustomerMemoryProfile).count() == 1
        assert session.query(CustomerMemoryEvent).count() == 1


def test_customer_memory_event_cannot_be_written_without_customer_profile():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    ticket, run = _build_ticket_and_run()

    with pytest.raises(IntegrityError):
        with session_scope(session_factory) as session:
            session.add(ticket)
            session.add(run)
            session.add(
                CustomerMemoryEvent(
                    memory_event_id=generate_prefixed_id(EntityIdPrefix.MEMORY_EVENT),
                    customer_id="cust_email_missing_example_com",
                    ticket_id=ticket.ticket_id,
                    run_id=run.run_id,
                    source_stage="close_ticket",
                    event_type="profile_update",
                    payload={"preferred_language": "en"},
                    idempotency_key="missing-profile",
                )
            )
