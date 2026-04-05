from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.bootstrap.container import ServiceContainer, get_service_container
from src.contracts.core import (
    RunStatus,
    RunTriggerType,
    TraceEventStatus,
    TraceEventType,
    to_api_timestamp,
    utc_now,
)
from src.contracts.protocols import TicketStoreProtocol
from src.db.models import Ticket, TicketRun
from src.orchestration.checkpointing import ManagedCheckpointer
from src.tickets.state_machine import TicketStateService
from src.workers.runner import TicketRunner, normalize_optional_datetime

DEFAULT_WORKER_POLL_INTERVAL_SECONDS = 5
DEFAULT_WORKER_RENEW_INTERVAL_SECONDS = 60


@dataclass(frozen=True)
class TicketWorkerResult:
    ticket: Ticket
    run: TicketRun
    worker_id: str
    restore_mode: str


class TicketWorker:
    DEFAULT_POLL_INTERVAL_SECONDS = DEFAULT_WORKER_POLL_INTERVAL_SECONDS
    DEFAULT_RENEW_INTERVAL_SECONDS = DEFAULT_WORKER_RENEW_INTERVAL_SECONDS

    def __init__(
        self,
        *,
        store: TicketStoreProtocol,
        container: ServiceContainer | None = None,
        worker_id: str,
        renew_interval_seconds: int = DEFAULT_RENEW_INTERVAL_SECONDS,
    ) -> None:
        self._store = store
        self._container = container or get_service_container()
        self._worker_id = worker_id
        self._renew_interval_seconds = renew_interval_seconds
        # Ensure checkpointer setup runs outside the per-run DB transaction.
        checkpointer = self._container.checkpointer
        if isinstance(checkpointer, ManagedCheckpointer):
            checkpointer.get()
            checkpointer.__exit__(None, None, None)

    def _build_runner(self, *, session, repositories) -> TicketRunner:
        return TicketRunner(
            session=session,
            repositories=repositories,
            container=self._container,
            checkpointer=self._container.checkpointer,
        )

    def claim_next(self) -> TicketWorkerResult | None:
        with self._store.session_scope() as session:
            repositories = self._store.repositories(session)
            state_service = TicketStateService(session, repositories=repositories)
            runner = self._build_runner(session=session, repositories=repositories)

            for candidate in repositories.tickets.list_worker_ready_candidates():
                run = (
                    repositories.ticket_runs.get(candidate.current_run_id)
                    if candidate.current_run_id
                    else None
                )
                if run is None:
                    continue
                previous_run_status = run.status
                had_started_at = run.started_at is not None

                now = utc_now()
                lease_expires_at = normalize_optional_datetime(candidate.lease_expires_at)
                if lease_expires_at is not None and lease_expires_at <= now:
                    recovered = state_service.reclaim_expired_lease(
                        candidate.ticket_id,
                        expected_version=candidate.version,
                        now=now,
                    )
                    self._record_worker_event(
                        runner=runner,
                        ticket=recovered,
                        run=run,
                        event_name="worker_reclaim_expired_lease",
                        now=now,
                    )
                    candidate = recovered
                    run = repositories.ticket_runs.get(candidate.current_run_id) if candidate.current_run_id else None
                    if run is None:
                        continue

                if run.status != RunStatus.QUEUED.value:
                    continue

                try:
                    claimed = state_service.claim_ticket(
                        candidate.ticket_id,
                        worker_id=self._worker_id,
                        run_id=run.run_id,
                        expected_version=candidate.version,
                        now=now,
                    )
                except Exception:
                    session.rollback()
                    continue
                self._record_worker_event(
                    runner=runner,
                    ticket=claimed,
                    run=run,
                    event_name="worker_claim_ticket",
                    now=now,
                )
                running = state_service.start_run(
                    claimed.ticket_id,
                    worker_id=self._worker_id,
                    run_id=run.run_id,
                    expected_version=claimed.version,
                    now=now,
                )
                run.status = RunStatus.RUNNING.value
                if run.started_at is None:
                    run.started_at = now
                runner.start_trace_for_worker_run(
                    ticket=running,
                    run=run,
                    trigger_type=run.trigger_type,
                    actor_id=run.triggered_by,
                    force_retry=run.trigger_type == RunTriggerType.SCHEDULED_RETRY.value,
                    worker_id=self._worker_id,
                )
                self._record_worker_event(
                    runner=runner,
                    ticket=running,
                    run=run,
                    event_name="worker_start_run",
                    now=now,
                )
                session.flush()
                restore_mode = (
                    "resume"
                    if previous_run_status in {RunStatus.RUNNING.value, RunStatus.FAILED.value}
                    and had_started_at
                    else "fresh"
                )
                if restore_mode == "resume":
                    self._record_worker_event(
                        runner=runner,
                        ticket=running,
                        run=run,
                        event_name="worker_resume_run",
                        now=now,
                    )
                return TicketWorkerResult(
                    ticket=running,
                    run=run,
                    worker_id=self._worker_id,
                    restore_mode=restore_mode,
                )
            return None

    def run_once(self) -> TicketWorkerResult | None:
        claimed = self.claim_next()
        if claimed is None:
            return None

        with self._store.session_scope() as session:
            repositories = self._store.repositories(session)
            state_service = TicketStateService(session, repositories=repositories)
            runner = self._build_runner(session=session, repositories=repositories)
            ticket = repositories.tickets.get(claimed.ticket.ticket_id)
            run = repositories.ticket_runs.get(claimed.run.run_id)
            if ticket is None or run is None:
                return None
            result = runner.execute_claimed_run(
                ticket=ticket,
                run=run,
                actor_id=run.triggered_by,
                worker_id=self._worker_id,
                state_service=state_service,
                restore_mode=claimed.restore_mode,
                renew_interval_seconds=self._renew_interval_seconds,
            )
            return TicketWorkerResult(
                ticket=result.ticket,
                run=result.run,
                worker_id=self._worker_id,
                restore_mode=claimed.restore_mode,
            )

    def _record_worker_event(
        self,
        *,
        runner: TicketRunner,
        ticket: Ticket,
        run: TicketRun,
        event_name: str,
        now: datetime,
    ) -> None:
        runner.trace_recorder.record_event(
            run=run,
            ticket=ticket,
            event_type=TraceEventType.WORKER.value,
            event_name=event_name,
            node_name="ticket_worker",
            start_time=now,
            end_time=now,
            status=TraceEventStatus.SUCCEEDED.value,
            metadata={
                "ticket_id": ticket.ticket_id,
                "run_id": run.run_id,
                "worker_id": self._worker_id,
                "lease_owner": ticket.lease_owner,
                "lease_expires_at": (
                    to_api_timestamp(ticket.lease_expires_at)
                    if ticket.lease_expires_at is not None
                    else None
                ),
            },
        )
