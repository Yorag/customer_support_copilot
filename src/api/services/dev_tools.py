from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.tickets.message_log import IngestEmailPayload

from .base import TicketApiServiceBase


@dataclass(frozen=True)
class TestEmailResultPayload:
    ticket_id: str
    created: bool
    business_status: str
    processing_status: str
    version: int
    run_id: str | None
    trace_id: str | None
    scenario_label: str | None
    auto_enqueue: bool
    source_channel: str


class DevToolsServiceMixin(TicketApiServiceBase):
    def create_test_email(
        self,
        *,
        sender_email_raw: str,
        subject: str,
        body_text: str,
        references: str | None,
        auto_enqueue: bool,
        scenario_label: str | None,
    ) -> TestEmailResultPayload:
        synthetic_message_id = (
            f"<test-{int(datetime.now(timezone.utc).timestamp() * 1000)}@local.test>"
        )
        synthetic_thread_id = (
            f"test-thread-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        )
        ticket, created = self.ingest_email(
            payload=IngestEmailPayload(
                source_channel="gmail",
                source_thread_id=synthetic_thread_id,
                source_message_id=synthetic_message_id,
                sender_email_raw=sender_email_raw,
                subject=subject,
                body_text=body_text,
                message_timestamp=datetime.now(timezone.utc),
                references=references,
                attachments=[],
            ),
            idempotency_key=None,
        )
        run_id = None
        trace_id = None
        processing_status = ticket.processing_status
        if auto_enqueue:
            run_result = self.run_ticket(
                ticket_id=ticket.ticket_id,
                ticket_version=ticket.version,
                trigger_type="manual_api",
                force_retry=False,
                actor_id="system:test-email",
                request_id=f"dev-test-email:{ticket.ticket_id}",
                idempotency_key=None,
            )
            run_id = run_result.run.run_id
            trace_id = run_result.run.trace_id
            processing_status = run_result.ticket.processing_status
            ticket = run_result.ticket

        return TestEmailResultPayload(
            ticket_id=ticket.ticket_id,
            created=created,
            business_status=ticket.business_status,
            processing_status=processing_status,
            version=ticket.version,
            run_id=run_id,
            trace_id=trace_id,
            scenario_label=scenario_label,
            auto_enqueue=auto_enqueue,
            source_channel="gmail_test",
        )
