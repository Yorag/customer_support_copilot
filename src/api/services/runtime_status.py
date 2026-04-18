from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import desc, func, select

from src.config import get_settings
from src.db.models import AppMetadata, Ticket, TicketRun

from .base import TicketApiServiceBase


@dataclass(frozen=True)
class OpsStatusRecentFailurePayload:
    ticket_id: str
    run_id: str
    trace_id: str
    error_code: str | None
    occurred_at: datetime | None


@dataclass(frozen=True)
class OpsStatusPayload:
    gmail_enabled: bool
    gmail_account_email: str | None
    gmail_last_scan_at: datetime | None
    gmail_last_scan_status: str | None
    worker_healthy: bool | None
    worker_count: int | None
    worker_last_heartbeat_at: datetime | None
    queued_runs: int
    running_runs: int
    waiting_external_tickets: int
    error_tickets: int
    database_status: str
    gmail_dependency_status: str
    llm_dependency_status: str
    checkpointing_status: str
    recent_failure: OpsStatusRecentFailurePayload | None


class RuntimeStatusServiceMixin(TicketApiServiceBase):
    def get_ops_status(self) -> OpsStatusPayload:
        current_settings = get_settings()
        gmail_enabled = current_settings.gmail.enabled
        gmail_account_email = current_settings.gmail.my_email

        with self._store.session_scope() as session:
            gmail_last_scan_at = self._read_metadata_datetime(
                session,
                "ops:gmail:last_scan_at",
            )
            gmail_last_scan_status = self._read_metadata_value(
                session,
                "ops:gmail:last_scan_status",
            )
            queued_runs = session.scalar(
                select(func.count()).select_from(TicketRun).where(TicketRun.status == "queued")
            ) or 0
            running_runs = session.scalar(
                select(func.count()).select_from(TicketRun).where(TicketRun.status == "running")
            ) or 0
            waiting_external_tickets = session.scalar(
                select(func.count())
                .select_from(Ticket)
                .where(Ticket.is_active.is_(True), Ticket.processing_status == "waiting_external")
            ) or 0
            error_tickets = session.scalar(
                select(func.count())
                .select_from(Ticket)
                .where(Ticket.is_active.is_(True), Ticket.processing_status == "error")
            ) or 0

            latest_failed_row = session.execute(
                select(TicketRun, Ticket)
                .join(Ticket, Ticket.ticket_id == TicketRun.ticket_id)
                .where(TicketRun.status == "failed")
                .order_by(desc(TicketRun.ended_at), desc(TicketRun.created_at), desc(TicketRun.run_id))
                .limit(1)
            ).first()

        database_status = "ok" if self._store.ping() else "error"
        gmail_dependency_status = "ok" if gmail_enabled else "disabled"
        llm_dependency_status = "unknown"
        checkpointing_status = "ok"
        try:
            _ = self._container.checkpointer
        except Exception:
            checkpointing_status = "error"

        recent_failure = None
        if latest_failed_row is not None:
            failed_run, failed_ticket = latest_failed_row
            recent_failure = OpsStatusRecentFailurePayload(
                ticket_id=failed_ticket.ticket_id,
                run_id=failed_run.run_id,
                trace_id=failed_run.trace_id,
                error_code=failed_run.error_code or failed_ticket.last_error_code,
                occurred_at=failed_run.ended_at or failed_run.created_at,
            )

        return OpsStatusPayload(
            gmail_enabled=gmail_enabled,
            gmail_account_email=gmail_account_email,
            gmail_last_scan_at=gmail_last_scan_at,
            gmail_last_scan_status=gmail_last_scan_status,
            worker_healthy=None,
            worker_count=None,
            worker_last_heartbeat_at=None,
            queued_runs=queued_runs,
            running_runs=running_runs,
            waiting_external_tickets=waiting_external_tickets,
            error_tickets=error_tickets,
            database_status=database_status,
            gmail_dependency_status=gmail_dependency_status,
            llm_dependency_status=llm_dependency_status,
            checkpointing_status=checkpointing_status,
            recent_failure=recent_failure,
        )

    def _read_metadata_value(self, session, key: str) -> str | None:
        record = session.get(AppMetadata, key)
        if record is None or record.value is None:
            return None
        return record.value

    def _read_metadata_datetime(self, session, key: str) -> datetime | None:
        raw_value = self._read_metadata_value(session, key)
        if raw_value is None:
            return None
        return datetime.fromisoformat(raw_value)
