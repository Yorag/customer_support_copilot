from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from src.contracts.core import EntityIdPrefix, generate_prefixed_id
from src.db.base import Base
from src.db.models import Ticket, TicketMessage, TicketRun
from src.db.session import build_engine, create_session_factory, session_scope
from src.tools.ticket_store import SqlAlchemyTicketStore


def _build_ticket_and_run():
    ticket = Ticket(
        ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
        source_thread_id="thread-msg-001",
        source_message_id="msg-root-001",
        gmail_thread_id="gmail-thread-msg-001",
        customer_email="liwei@example.com",
        customer_email_raw='"Li Wei" <liwei@example.com>',
        subject="Hello",
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


def test_ticket_message_persists_with_required_fields():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    ticket, run = _build_ticket_and_run()

    with session_scope(session_factory) as session:
        session.add(ticket)
        session.add(run)
        session.flush()
        session.add(
            TicketMessage(
                ticket_message_id=generate_prefixed_id(EntityIdPrefix.TICKET_MESSAGE),
                ticket_id=ticket.ticket_id,
                run_id=run.run_id,
                source_thread_id=ticket.source_thread_id,
                source_message_id="msg-inbound-001",
                gmail_thread_id=ticket.gmail_thread_id,
                direction="inbound",
                message_type="customer_email",
                sender_email="liwei@example.com",
                recipient_emails=["support@example.com"],
                subject="Hello",
                body_text="Need help",
                customer_visible=True,
                message_timestamp=datetime.now(timezone.utc),
            )
        )

    with session_scope(session_factory) as session:
        row = session.query(TicketMessage).one()

    assert row.ticket_message_id.startswith("tm_")
    assert row.source_channel == "gmail"
    assert row.direction == "inbound"
    assert row.message_type == "customer_email"


def test_ticket_message_unique_source_message_is_enforced():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    ticket, run = _build_ticket_and_run()

    with pytest.raises(IntegrityError):
        with session_scope(session_factory) as session:
            session.add(ticket)
            session.add(run)
            session.flush()
            for idx in range(2):
                session.add(
                    TicketMessage(
                        ticket_message_id=generate_prefixed_id(
                            EntityIdPrefix.TICKET_MESSAGE
                        ),
                        ticket_id=ticket.ticket_id,
                        run_id=run.run_id,
                        source_thread_id=ticket.source_thread_id,
                        source_message_id="msg-inbound-dup",
                        gmail_thread_id=ticket.gmail_thread_id,
                        direction="inbound",
                        message_type="customer_email",
                        sender_email="liwei@example.com",
                        recipient_emails=["support@example.com"],
                        customer_visible=True,
                        message_timestamp=datetime.now(timezone.utc),
                    )
                )


def test_ticket_message_validates_direction_and_recipients():
    with pytest.raises(ValueError):
        TicketMessage(
            ticket_message_id=generate_prefixed_id(EntityIdPrefix.TICKET_MESSAGE),
            ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
            source_thread_id="thread",
            source_message_id="msg",
            gmail_thread_id="gmail-thread",
            direction="unsupported",
            message_type="customer_email",
            recipient_emails=["support@example.com"],
            customer_visible=True,
            message_timestamp=datetime.now(timezone.utc),
        )

    with pytest.raises(ValueError):
        TicketMessage(
            ticket_message_id=generate_prefixed_id(EntityIdPrefix.TICKET_MESSAGE),
            ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
            source_thread_id="thread",
            source_message_id="msg",
            gmail_thread_id="gmail-thread",
            direction="inbound",
            message_type="customer_email",
            recipient_emails=["", "support@example.com"],
            customer_visible=True,
            message_timestamp=datetime.now(timezone.utc),
        )


def test_ticket_message_repository_can_lookup_by_source_message_id():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    store = SqlAlchemyTicketStore(engine=engine)
    ticket, run = _build_ticket_and_run()
    ticket_message_id = generate_prefixed_id(EntityIdPrefix.TICKET_MESSAGE)

    with store.session_scope() as session:
        repositories = store.repositories(session)
        repositories.tickets.add(ticket)
        repositories.ticket_runs.add(run)
        session.flush()
        repositories.ticket_messages.add(
            TicketMessage(
                ticket_message_id=ticket_message_id,
                ticket_id=ticket.ticket_id,
                run_id=run.run_id,
                source_thread_id=ticket.source_thread_id,
                source_message_id="msg-source-lookup",
                gmail_thread_id=ticket.gmail_thread_id,
                direction="outbound_draft",
                message_type="reply_draft",
                sender_email="support@example.com",
                recipient_emails=["liwei@example.com"],
                customer_visible=True,
                message_timestamp=datetime.now(timezone.utc),
            )
        )
        session.flush()

        assert repositories.ticket_messages.get(ticket_message_id) is not None
        assert (
            repositories.ticket_messages.get_by_source_message_id("msg-source-lookup")
            is not None
        )
        assert len(repositories.ticket_messages.list_by_ticket(ticket.ticket_id)) == 1
