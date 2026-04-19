from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.api.service_errors import GmailDisabledError
from src.db.models import AppMetadata
from src.tickets.message_log import IngestEmailPayload

from .base import TicketApiServiceBase


@dataclass(frozen=True)
class GmailScanPreviewItemPayload:
    source_thread_id: str
    source_message_id: str | None
    sender_email_raw: str
    subject: str
    skip_reason: str | None


@dataclass(frozen=True)
class GmailScanPreviewPayload:
    requested_max_results: int
    candidate_threads: int
    skipped_existing_draft_threads: int
    skipped_self_sent_threads: int
    items: list[GmailScanPreviewItemPayload]


@dataclass(frozen=True)
class GmailScanItemPayload:
    source_thread_id: str
    ticket_id: str | None
    created_ticket: bool
    queued_run_id: str | None


@dataclass(frozen=True)
class GmailScanPayload:
    scan_id: str
    requested_max_results: int
    fetched_threads: int
    ingested_tickets: int
    queued_runs: int
    skipped_existing_draft_threads: int
    skipped_self_sent_threads: int
    errors: int
    items: list[GmailScanItemPayload]


class GmailOpsServiceMixin(TicketApiServiceBase):
    def preview_gmail_scan(
        self,
        *,
        max_results: int | None,
    ) -> GmailScanPreviewPayload:
        if not self._container.gmail_enabled:
            raise GmailDisabledError()
        scan_result = self._container.gmail_client.scan_inbox(max_results=max_results)
        self._record_scan_metadata(
            status="preview_succeeded",
            recorded_at=datetime.now(timezone.utc),
        )
        return GmailScanPreviewPayload(
            requested_max_results=scan_result["requested_max_results"],
            candidate_threads=scan_result["candidate_threads"],
            skipped_existing_draft_threads=scan_result["skipped_existing_draft_threads"],
            skipped_self_sent_threads=scan_result["skipped_self_sent_threads"],
            items=[
                GmailScanPreviewItemPayload(
                    source_thread_id=item["threadId"],
                    source_message_id=item.get("messageId") or item.get("id"),
                    sender_email_raw=item["sender"],
                    subject=item["subject"],
                    skip_reason=item.get("skip_reason"),
                )
                for item in scan_result["items"]
            ],
        )

    def scan_gmail(
        self,
        *,
        max_results: int | None,
        enqueue: bool,
    ) -> GmailScanPayload:
        if not self._container.gmail_enabled:
            raise GmailDisabledError()
        recorded_at = datetime.now(timezone.utc)
        scan_result = self._container.gmail_client.scan_inbox(max_results=max_results)
        ingested_tickets = 0
        queued_runs = 0
        errors = 0
        items: list[GmailScanItemPayload] = []

        for item in scan_result["items"]:
            if item.get("skip_reason") is not None:
                continue

            try:
                ingest_payload = IngestEmailPayload(
                    source_channel="gmail",
                    source_thread_id=item["threadId"],
                    source_message_id=item.get("messageId") or item.get("id"),
                    sender_email_raw=item["sender"],
                    subject=item["subject"],
                    body_text=item["body"],
                    message_timestamp=datetime.now(timezone.utc),
                    references=item.get("references"),
                    attachments=[],
                )
                ticket, created = self.ingest_email(
                    payload=ingest_payload,
                    idempotency_key=None,
                )
                ingested_tickets += 1
                queued_run_id = None
                if enqueue:
                    run_result = self.run_ticket(
                        ticket_id=ticket.ticket_id,
                        ticket_version=ticket.version,
                        trigger_type="poller",
                        force_retry=False,
                        actor_id="system:poller",
                        request_id=f"poller:{ticket.ticket_id}",
                        idempotency_key=None,
                    )
                    queued_runs += 1
                    queued_run_id = run_result.run.run_id
                items.append(
                    GmailScanItemPayload(
                        source_thread_id=item["threadId"],
                        ticket_id=ticket.ticket_id,
                        created_ticket=created,
                        queued_run_id=queued_run_id,
                    )
                )
            except Exception:
                errors += 1
                items.append(
                    GmailScanItemPayload(
                        source_thread_id=item["threadId"],
                        ticket_id=None,
                        created_ticket=False,
                        queued_run_id=None,
                    )
                )

        self._record_scan_metadata(
            status="succeeded" if errors == 0 else "partial_failure",
            recorded_at=recorded_at,
        )
        return GmailScanPayload(
            scan_id=f"scan_{recorded_at.strftime('%Y%m%d%H%M%S')}",
            requested_max_results=scan_result["requested_max_results"],
            fetched_threads=scan_result["candidate_threads"],
            ingested_tickets=ingested_tickets,
            queued_runs=queued_runs,
            skipped_existing_draft_threads=scan_result["skipped_existing_draft_threads"],
            skipped_self_sent_threads=scan_result["skipped_self_sent_threads"],
            errors=errors,
            items=items,
        )

    def _record_scan_metadata(self, *, status: str, recorded_at: datetime) -> None:
        with self._store.session_scope() as session:
            last_scan_at = session.get(AppMetadata, "ops:gmail:last_scan_at")
            if last_scan_at is None:
                session.add(
                    AppMetadata(
                        key="ops:gmail:last_scan_at",
                        value=recorded_at.isoformat(),
                    )
                )
            else:
                last_scan_at.value = recorded_at.isoformat()

            last_scan_status = session.get(AppMetadata, "ops:gmail:last_scan_status")
            if last_scan_status is None:
                session.add(
                    AppMetadata(
                        key="ops:gmail:last_scan_status",
                        value=status,
                    )
                )
            else:
                last_scan_status.value = status
