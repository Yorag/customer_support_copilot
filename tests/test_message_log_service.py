from __future__ import annotations

from datetime import datetime, timezone

from src.contracts.core import EntityIdPrefix, generate_prefixed_id
from src.db.base import Base
from src.db.models import DraftArtifact, Ticket, TicketRun
from src.db.session import build_engine, create_session_factory, session_scope
from src.tickets.message_log import DraftMessagePayload, IngestEmailPayload, MessageLogService


def _ingest_payload(**overrides) -> IngestEmailPayload:
    payload = IngestEmailPayload(
        source_channel="gmail",
        source_thread_id="gmail-thread-9001",
        source_message_id="<msg-9001@gmail.com>",
        sender_email_raw='"Li Wei" <liwei@example.com>',
        subject="Refund question",
        body_text="I was charged twice.",
        message_timestamp=datetime.now(timezone.utc),
        references="<prev@gmail.com>",
        attachments=[{"filename": "invoice.pdf", "mime_type": "application/pdf"}],
    )
    return IngestEmailPayload(**{**payload.__dict__, **overrides})


def test_ingest_inbound_email_creates_ticket_and_message():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        service = MessageLogService(
            session,
            alias_map={"support+cn@example.com": "liwei@example.com"},
        )
        result = service.ingest_inbound_email(_ingest_payload())
        session.flush()

        assert result.created_ticket is True
        assert result.ticket.business_status == "new"
        assert result.ticket.processing_status == "queued"
        assert result.ticket.customer_id == "cust_email_liwei_example_com"
        assert result.message.message_type == "customer_email"
        assert result.message.message_metadata["attachments"][0]["filename"] == "invoice.pdf"


def test_ingest_inbound_email_is_idempotent_by_source_message_id():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        service = MessageLogService(session)
        first = service.ingest_inbound_email(_ingest_payload())
        session.flush()
        second = service.ingest_inbound_email(_ingest_payload())

        assert second.created_ticket is False
        assert first.ticket.ticket_id == second.ticket.ticket_id
        assert first.message.ticket_message_id == second.message.ticket_message_id


def test_ingest_inbound_email_reuses_active_ticket_for_same_thread():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        existing_ticket = Ticket(
            ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
            source_thread_id="gmail-thread-9001",
            source_message_id="<root@gmail.com>",
            gmail_thread_id="gmail-thread-9001",
            customer_email="liwei@example.com",
            customer_email_raw='"Li Wei" <liwei@example.com>',
            subject="Existing ticket",
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
        session.add(existing_ticket)
        session.flush()

        service = MessageLogService(session)
        result = service.ingest_inbound_email(
            _ingest_payload(source_message_id="<msg-9002@gmail.com>")
        )
        session.flush()

        assert result.created_ticket is False
        assert result.ticket.ticket_id == existing_ticket.ticket_id
        assert result.message.ticket_id == existing_ticket.ticket_id


def test_create_draft_message_log_writes_outbound_draft_record():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        ticket = Ticket(
            ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
            source_thread_id="gmail-thread-9100",
            source_message_id="<root@gmail.com>",
            gmail_thread_id="gmail-thread-9100",
            customer_email="liwei@example.com",
            customer_email_raw='"Li Wei" <liwei@example.com>',
            subject="Existing ticket",
            business_status="triaged",
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
        session.add(ticket)
        session.add(run)
        session.flush()
        draft = DraftArtifact(
            draft_id=generate_prefixed_id(EntityIdPrefix.DRAFT),
            ticket_id=ticket.ticket_id,
            run_id=run.run_id,
            version_index=1,
            draft_type="reply",
            content_text="We are reviewing this request.",
            qa_status="pending",
        )
        session.add(draft)
        session.flush()

        service = MessageLogService(session)
        message = service.create_draft_message_log(
            DraftMessagePayload(
                ticket_id=ticket.ticket_id,
                run_id=run.run_id,
                draft_id=draft.draft_id,
                source_thread_id=ticket.source_thread_id,
                source_message_id="draft-msg-001",
                gmail_thread_id=ticket.gmail_thread_id,
                message_type="reply_draft",
                sender_email="support@example.com",
                recipient_emails=["liwei@example.com"],
                subject="Draft reply",
                body_text="We are reviewing this request.",
                body_html=None,
                message_timestamp=datetime.now(timezone.utc),
                reply_to_source_message_id="<root@gmail.com>",
                attachments=[{"filename": "context.txt", "mime_type": "text/plain"}],
            )
        )
        session.flush()

        assert message.direction == "outbound_draft"
        assert message.message_type == "reply_draft"
        assert message.message_metadata["attachments"][0]["filename"] == "context.txt"


def test_ingest_inbound_email_reopens_closed_thread_with_new_ticket():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        closed_ticket = Ticket(
            ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
            source_thread_id="gmail-thread-reopen",
            source_message_id="<root@gmail.com>",
            gmail_thread_id="gmail-thread-reopen",
            customer_email="liwei@example.com",
            customer_email_raw='"Li Wei" <liwei@example.com>',
            subject="Closed thread",
            business_status="closed",
            processing_status="completed",
            priority="medium",
            secondary_routes=[],
            tags=[],
            multi_intent=False,
            needs_clarification=False,
            needs_escalation=False,
            risk_reasons=[],
            reopen_count=2,
            is_active=True,
            closed_at=datetime.now(timezone.utc),
        )
        session.add(closed_ticket)
        session.flush()

        service = MessageLogService(session)
        result = service.ingest_inbound_email(
            _ingest_payload(
                source_thread_id="gmail-thread-reopen",
                source_message_id="<msg-reopen@gmail.com>",
            )
        )
        session.flush()

        assert result.created_ticket is True
        assert result.reopened_from_ticket_id == closed_ticket.ticket_id
        assert result.ticket.ticket_id != closed_ticket.ticket_id
        assert result.ticket.reopen_count == 3
        assert closed_ticket.is_active is False


def test_get_thread_messages_for_drafting_returns_ordered_context():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        service = MessageLogService(session)
        inbound = service.ingest_inbound_email(
            _ingest_payload(
                source_thread_id="gmail-thread-context",
                source_message_id="<msg-context-1@gmail.com>",
                message_timestamp=datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc),
            )
        )
        session.flush()

        service.create_draft_message_log(
            DraftMessagePayload(
                ticket_id=inbound.ticket.ticket_id,
                source_thread_id=inbound.ticket.source_thread_id,
                source_message_id="draft-context-1",
                gmail_thread_id=inbound.ticket.gmail_thread_id,
                draft_id=None,
                message_type="clarification_request",
                sender_email="support@example.com",
                recipient_emails=["liwei@example.com"],
                subject="Need more information",
                body_text="Please share steps to reproduce.",
                body_html=None,
                message_timestamp=datetime(2026, 4, 1, 10, 5, tzinfo=timezone.utc),
            )
        )
        session.flush()

        service.ingest_inbound_email(
            _ingest_payload(
                source_thread_id="gmail-thread-context",
                source_message_id="<msg-context-2@gmail.com>",
                body_text="Here are the steps.",
                message_timestamp=datetime(2026, 4, 1, 10, 10, tzinfo=timezone.utc),
            )
        )
        session.flush()

        context = service.get_thread_messages_for_drafting("gmail-thread-context")

        assert [message.source_message_id for message in context.messages] == [
            "<msg-context-1@gmail.com>",
            "draft-context-1",
            "<msg-context-2@gmail.com>",
        ]
        assert context.latest_customer_message.source_message_id == "<msg-context-2@gmail.com>"
        assert context.latest_system_message.source_message_id == "draft-context-1"
