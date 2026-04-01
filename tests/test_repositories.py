from __future__ import annotations

from datetime import datetime, timezone

from src.core_schema import EntityIdPrefix, generate_prefixed_id
from src.db.base import Base
from src.db.models import CustomerMemoryProfile, Ticket, TicketRun
from src.db.session import build_engine
from src.tools.ticket_store import SqlAlchemyTicketStore


def _build_ticket(ticket_id: str, gmail_thread_id: str) -> Ticket:
    return Ticket(
        ticket_id=ticket_id,
        source_thread_id=gmail_thread_id,
        source_message_id=f"msg-{gmail_thread_id}",
        gmail_thread_id=gmail_thread_id,
        customer_email="liwei@example.com",
        customer_email_raw='"Li Wei" <liwei@example.com>',
        subject="Need help",
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


def test_ticket_store_repositories_bundle_supports_core_entities():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    store = SqlAlchemyTicketStore(engine=engine)

    ticket_id = generate_prefixed_id(EntityIdPrefix.TICKET)
    run_id = generate_prefixed_id(EntityIdPrefix.RUN)
    customer_id = "cust_email_liwei_example_com"

    with store.session_scope() as session:
        repositories = store.repositories(session)

        repositories.tickets.add(_build_ticket(ticket_id, "gmail-thread-001"))
        repositories.ticket_runs.add(
            TicketRun(
                run_id=run_id,
                ticket_id=ticket_id,
                trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
                trigger_type="manual_api",
                status="running",
                started_at=datetime.now(timezone.utc),
                attempt_index=1,
            )
        )
        repositories.customer_memory_profiles.add(
            CustomerMemoryProfile(
                customer_id=customer_id,
                primary_email="liwei@example.com",
                alias_emails=["support+cn@example.com"],
                profile={
                    "name": "Li Wei",
                    "account_tier": "enterprise",
                    "preferred_language": "zh-CN",
                    "preferred_tone": "direct",
                },
                risk_tags=[],
                business_flags={
                    "high_value_customer": True,
                    "refund_dispute_history": False,
                    "requires_manual_approval": False,
                },
                historical_case_refs=[],
            )
        )
        session.flush()

        assert repositories.tickets.get(ticket_id) is not None
        assert (
            repositories.tickets.get_active_by_gmail_thread_id("gmail-thread-001")
            is not None
        )
        assert repositories.ticket_runs.get(run_id) is not None
        assert repositories.customer_memory_profiles.get(customer_id) is not None


def test_repositories_list_entities_by_scope():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    store = SqlAlchemyTicketStore(engine=engine)

    ticket_id = generate_prefixed_id(EntityIdPrefix.TICKET)
    run_id = generate_prefixed_id(EntityIdPrefix.RUN)

    with store.session_scope() as session:
        repositories = store.repositories(session)
        repositories.tickets.add(_build_ticket(ticket_id, "gmail-thread-002"))
        repositories.ticket_runs.add(
            TicketRun(
                run_id=run_id,
                ticket_id=ticket_id,
                trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
                trigger_type="manual_api",
                status="running",
                started_at=datetime.now(timezone.utc),
                attempt_index=1,
            )
        )
        session.flush()

        assert len(repositories.tickets.list_all()) == 1
        assert len(repositories.ticket_runs.list_by_ticket(ticket_id)) == 1
