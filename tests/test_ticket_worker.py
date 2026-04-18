from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest
import run_worker

from src.bootstrap.container import ServiceContainer
from src.contracts.core import EntityIdPrefix, generate_prefixed_id
from src.contracts.core import TicketProcessingStatus
from src.db.base import Base
from src.db.models import DraftArtifact, Ticket, TicketRun, TraceEvent
from src.db.session import build_engine, create_session_factory, session_scope
from src.orchestration.checkpointing import ManagedCheckpointer, build_test_checkpointer
from src.tickets.state_machine import TicketStateService
from src.tools.ticket_store import SqlAlchemyTicketStore
from src.workers.runner import TicketRunner
from src.workers.ticket_worker import TicketWorker


def _build_store() -> SqlAlchemyTicketStore:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SqlAlchemyTicketStore(engine=engine, session_factory=create_session_factory(engine))


def _create_ticket(
    *,
    priority: str,
    processing_status: str = "queued",
    business_status: str = "triaged",
    version: int = 1,
) -> Ticket:
    return Ticket(
        ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
        source_thread_id=generate_prefixed_id(EntityIdPrefix.TICKET),
        source_message_id=f"<{generate_prefixed_id(EntityIdPrefix.TICKET)}@gmail.com>",
        gmail_thread_id=generate_prefixed_id(EntityIdPrefix.TICKET),
        customer_email="worker@example.com",
        customer_email_raw='"Worker" <worker@example.com>',
        subject="worker test",
        latest_message_excerpt="please help",
        business_status=business_status,
        processing_status=processing_status,
        priority=priority,
        secondary_routes=[],
        tags=[],
        multi_intent=False,
        needs_clarification=False,
        needs_escalation=False,
        risk_reasons=[],
        version=version,
    )


def _queued_run(ticket: Ticket, *, run_id: str | None = None) -> TicketRun:
    return TicketRun(
        run_id=run_id or generate_prefixed_id(EntityIdPrefix.RUN),
        ticket_id=ticket.ticket_id,
        trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
        trigger_type="manual_api",
        status="queued",
        attempt_index=1,
    )


def test_worker_claim_next_prefers_priority_then_created_at():
    store = _build_store()
    container = ServiceContainer(
        ticket_store_factory=lambda: store,
        checkpointer_factory=build_test_checkpointer,
    )
    worker = TicketWorker(store=store, container=container, worker_id="worker-1")

    with store.session_scope() as session:
        low = _create_ticket(priority="low")
        high = _create_ticket(priority="high")
        session.add(low)
        session.add(high)
        session.flush()
        low.created_at = datetime(2026, 4, 3, 1, 0, tzinfo=timezone.utc)
        high.created_at = datetime(2026, 4, 3, 2, 0, tzinfo=timezone.utc)
        low_run = _queued_run(low)
        high_run = _queued_run(high)
        low.current_run_id = low_run.run_id
        high.current_run_id = high_run.run_id
        session.add(low_run)
        session.add(high_run)

    claimed = worker.claim_next()

    assert claimed is not None
    assert claimed.ticket.ticket_id == high.ticket_id
    assert claimed.run.run_id == high_run.run_id


def test_worker_reclaims_expired_lease_and_reuses_same_run():
    store = _build_store()
    container = ServiceContainer(
        ticket_store_factory=lambda: store,
        checkpointer_factory=build_test_checkpointer,
    )
    worker = TicketWorker(store=store, container=container, worker_id="worker-2")
    expired_at = datetime.now(timezone.utc) - timedelta(minutes=1)

    with store.session_scope() as session:
        ticket = _create_ticket(priority="medium", processing_status="running")
        run = _queued_run(ticket, run_id="run-resume-worker")
        run.status = "running"
        run.started_at = expired_at - timedelta(minutes=2)
        ticket.current_run_id = run.run_id
        ticket.lease_owner = "worker-old"
        ticket.lease_expires_at = expired_at
        session.add(ticket)
        session.add(run)

    claimed = worker.claim_next()

    assert claimed is not None
    assert claimed.run.run_id == "run-resume-worker"
    assert claimed.restore_mode == "resume"
    with store.session_scope() as session:
        persisted_run = session.get(TicketRun, "run-resume-worker")
        persisted_ticket = session.get(Ticket, claimed.ticket.ticket_id)
        assert persisted_run is not None
        assert persisted_ticket is not None
        assert persisted_run.status == "running"
        assert persisted_ticket.processing_status == "running"
        assert persisted_ticket.lease_owner == "worker-2"


def test_worker_claim_next_skips_ticket_without_queued_or_resumable_run():
    store = _build_store()
    container = ServiceContainer(
        ticket_store_factory=lambda: store,
        checkpointer_factory=build_test_checkpointer,
    )
    worker = TicketWorker(store=store, container=container, worker_id="worker-3")

    with store.session_scope() as session:
        ticket = _create_ticket(priority="critical")
        run = _queued_run(ticket)
        run.status = "failed"
        run.ended_at = datetime.now(timezone.utc)
        ticket.current_run_id = run.run_id
        session.add(ticket)
        session.add(run)

    assert worker.claim_next() is None


def test_worker_cli_parser_defaults_to_loop_mode():
    parser = run_worker.build_worker_arg_parser()

    args = parser.parse_args([])

    assert args.once is False
    assert args.poll_interval_seconds == TicketWorker.DEFAULT_POLL_INTERVAL_SECONDS
    assert args.worker_id.startswith("worker-")


def test_worker_main_runs_once_when_once_flag_is_set(monkeypatch):
    observed: list[tuple[str, int | str]] = []

    class FakeWorker:
        def __init__(self, *, store, container, worker_id):
            observed.append(("init", worker_id))

        def run_once(self):
            observed.append(("run_once", 1))
            return None

    class FakeContainer:
        ticket_store = object()

    monkeypatch.setattr(run_worker, "validate_required_settings", lambda _: None)
    monkeypatch.setattr(run_worker, "get_service_container", lambda: FakeContainer())
    monkeypatch.setattr(run_worker, "TicketWorker", FakeWorker)

    result = run_worker.main(["--once", "--worker-id", "worker-test"])

    assert result == 0
    assert observed == [("init", "worker-test"), ("run_once", 1)]


def test_worker_main_loops_by_default(monkeypatch):
    observed: list[tuple[str, int | str | float]] = []

    class FakeWorker:
        def __init__(self, *, store, container, worker_id):
            observed.append(("init", worker_id))

        def run_once(self):
            observed.append(("run_once", len(observed)))
            return None

    class FakeContainer:
        ticket_store = object()

    def fake_sleep(seconds: float) -> None:
        observed.append(("sleep", seconds))
        raise KeyboardInterrupt

    monkeypatch.setattr(run_worker, "validate_required_settings", lambda _: None)
    monkeypatch.setattr(run_worker, "get_service_container", lambda: FakeContainer())
    monkeypatch.setattr(run_worker, "TicketWorker", FakeWorker)
    monkeypatch.setattr(run_worker.time, "sleep", fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        run_worker.main(["--worker-id", "worker-loop", "--poll-interval-seconds", "7"])

    assert observed == [
        ("init", "worker-loop"),
        ("run_once", 1),
        ("sleep", 7),
    ]


def test_two_workers_cannot_claim_same_ticket_sequentially():
    store = _build_store()
    container = ServiceContainer(
        ticket_store_factory=lambda: store,
        checkpointer_factory=build_test_checkpointer,
    )
    worker_a = TicketWorker(store=store, container=container, worker_id="worker-a")
    worker_b = TicketWorker(store=store, container=container, worker_id="worker-b")

    with store.session_scope() as session:
        ticket = _create_ticket(priority="high", processing_status="queued")
        run = _queued_run(ticket, run_id="run-claim-race")
        ticket.current_run_id = run.run_id
        session.add(ticket)
        session.add(run)

    first = worker_a.claim_next()
    second = worker_b.claim_next()

    assert first is not None
    assert first.run.run_id == "run-claim-race"
    assert second is None
    with store.session_scope() as session:
        persisted_ticket = session.get(Ticket, first.ticket.ticket_id)
        persisted_run = session.get(TicketRun, "run-claim-race")
        assert persisted_ticket is not None
        assert persisted_run is not None
        assert persisted_ticket.lease_owner == "worker-a"
        assert persisted_ticket.processing_status == "running"
        assert persisted_run.status == "running"


def test_worker_claim_next_records_worker_events():
    store = _build_store()
    container = ServiceContainer(
        ticket_store_factory=lambda: store,
        checkpointer_factory=build_test_checkpointer,
    )
    worker = TicketWorker(store=store, container=container, worker_id="worker-events")

    with store.session_scope() as session:
        ticket = _create_ticket(priority="medium", processing_status="queued")
        run = _queued_run(ticket, run_id="run-worker-events")
        ticket.current_run_id = run.run_id
        session.add(ticket)
        session.add(run)

    claimed = worker.claim_next()

    assert claimed is not None
    with store.session_scope() as session:
        events = (
            session.query(TraceEvent)
            .filter(TraceEvent.run_id == "run-worker-events")
            .order_by(TraceEvent.start_time.asc(), TraceEvent.created_at.asc())
            .all()
        )
        event_names = [event.event_name for event in events]
        assert "worker_claim_ticket" in event_names
        assert "worker_start_run" in event_names


def test_worker_initialization_prewarms_managed_checkpointer() -> None:
    store = _build_store()
    events: list[str] = []

    class FakeManagedCheckpointer(ManagedCheckpointer):
        def __init__(self) -> None:
            super().__init__(lambda: self)

        def __enter__(self):
            events.append("get")
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            events.append("exit")
            self._manager = None
            self._checkpointer = None

    container = ServiceContainer(
        ticket_store_factory=lambda: store,
        checkpointer_factory=lambda: FakeManagedCheckpointer(),
    )

    TicketWorker(store=store, container=container, worker_id="worker-prewarm")

    assert events == ["get", "exit"]


def test_execute_claimed_run_rejects_state_updates_after_lease_loss(monkeypatch):
    store = _build_store()
    checkpointer = build_test_checkpointer()
    container = ServiceContainer(
        ticket_store_factory=lambda: store,
        checkpointer_factory=lambda: checkpointer,
    )
    now = datetime.now(timezone.utc)

    class FakeWorkflowApp:
        def __init__(self) -> None:
            self.checkpointer = checkpointer

        def stream(self, stream_input, config=None):
            yield {"load_ticket_context": {"current_node": "load_ticket_context"}}

    class FakeWorkflow:
        def __init__(self, **kwargs) -> None:
            self.app = FakeWorkflowApp()
            self.checkpointer = checkpointer

    with store.session_scope() as session:
        ticket = _create_ticket(
            priority="medium",
            business_status="triaged",
            processing_status="running",
            version=4,
        )
        run = TicketRun(
            run_id="run-lease-loss",
            ticket_id=ticket.ticket_id,
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type="manual_api",
            triggered_by="api-user",
            status="running",
            started_at=now - timedelta(seconds=5),
            attempt_index=1,
        )
        ticket.current_run_id = run.run_id
        ticket.lease_owner = "worker-a"
        ticket.lease_expires_at = now + timedelta(minutes=5)
        session.add(ticket)
        session.add(run)
        session.flush()
        repositories = store.repositories(session)
        state_service = TicketStateService(session, repositories=repositories)
        runner = TicketRunner(
            session=session,
            repositories=repositories,
            container=container,
            checkpointer=checkpointer,
        )

        monkeypatch.setattr("src.workers.runner.Workflow", FakeWorkflow)
        monkeypatch.setattr(
            runner,
            "_prepare_checkpoint_context",
            lambda **kwargs: {"restore_mode": "fresh", "stream_config": {"configurable": {}}},
        )

        original_get = repositories.tickets.get
        call_count = {"value": 0}

        def get_ticket_with_lease_loss(ticket_id: str):
            record = original_get(ticket_id)
            if record is not None and call_count["value"] == 0:
                record.lease_owner = "worker-b"
                record.lease_expires_at = now + timedelta(minutes=5)
                call_count["value"] += 1
            return record

        repositories.tickets.get = get_ticket_with_lease_loss  # type: ignore[method-assign]

        result = runner.execute_claimed_run(
            ticket=ticket,
            run=run,
            actor_id="api-user",
            worker_id="worker-a",
            state_service=state_service,
            restore_mode="fresh",
            renew_interval_seconds=60,
        )
        session.flush()

        assert result.run.status == "failed"
        assert result.run.error_code == "lease_lost"
        lose_lease_events = [
            event
            for event in repositories.trace_events.list_by_run(run.run_id)
            if event.event_name == "worker_lose_lease"
        ]
        assert len(lose_lease_events) == 1
        assert lose_lease_events[0].event_metadata["worker_id"] == "worker-a"


def test_execute_claimed_run_allows_terminal_processing_state_without_active_lease(monkeypatch):
    store = _build_store()
    checkpointer = build_test_checkpointer()
    container = ServiceContainer(
        ticket_store_factory=lambda: store,
        checkpointer_factory=lambda: checkpointer,
    )
    now = datetime.now(timezone.utc)

    class FakeWorkflowApp:
        def __init__(self) -> None:
            self.checkpointer = checkpointer

        def stream(self, stream_input, config=None):
            persisted_ticket = session.get(Ticket, ticket.ticket_id)
            assert persisted_ticket is not None
            persisted_ticket.processing_status = TicketProcessingStatus.WAITING_EXTERNAL.value
            persisted_ticket.lease_owner = None
            persisted_ticket.lease_expires_at = None
            yield {"escalate_to_human": {"current_node": "escalate_to_human"}}

    class FakeWorkflow:
        def __init__(self, **kwargs) -> None:
            self.app = FakeWorkflowApp()
            self.checkpointer = checkpointer

    with store.session_scope() as session:
        ticket = _create_ticket(
            priority="medium",
            business_status="awaiting_human_review",
            processing_status="running",
            version=4,
        )
        run = TicketRun(
            run_id="run-terminal-no-lease",
            ticket_id=ticket.ticket_id,
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type="manual_api",
            triggered_by="api-user",
            status="running",
            started_at=now - timedelta(seconds=5),
            attempt_index=1,
        )
        ticket.current_run_id = run.run_id
        ticket.lease_owner = "worker-a"
        ticket.lease_expires_at = now + timedelta(minutes=5)
        session.add(ticket)
        session.add(run)
        session.flush()
        repositories = store.repositories(session)
        state_service = TicketStateService(session, repositories=repositories)
        runner = TicketRunner(
            session=session,
            repositories=repositories,
            container=container,
            checkpointer=checkpointer,
        )

        monkeypatch.setattr("src.workers.runner.Workflow", FakeWorkflow)
        monkeypatch.setattr(
            runner,
            "_prepare_checkpoint_context",
            lambda **kwargs: {"restore_mode": "fresh", "stream_config": {"configurable": {}}},
        )
        monkeypatch.setattr(runner, "_build_response_quality", lambda **kwargs: None)
        monkeypatch.setattr(
            runner,
            "_build_trajectory_evaluation",
            lambda *args, **kwargs: {
                "score": 5.0,
                "expected_route": ["triage", "escalate_to_human"],
                "actual_route": ["triage", "escalate_to_human"],
                "violations": [],
            },
        )
        monkeypatch.setattr(runner.trace_recorder, "list_run_events", lambda run_id: [])
        monkeypatch.setattr(runner.trace_recorder, "build_latency_metrics", lambda **kwargs: {})
        monkeypatch.setattr(runner.trace_recorder, "build_resource_metrics", lambda **kwargs: {})
        monkeypatch.setattr(runner.trace_recorder, "finalize_run", lambda **kwargs: None)

        result = runner.execute_claimed_run(
            ticket=ticket,
            run=run,
            actor_id="api-user",
            worker_id="worker-a",
            state_service=state_service,
            restore_mode="fresh",
            renew_interval_seconds=60,
        )
        session.flush()

        assert result.run.status == "succeeded"
        assert result.ticket.processing_status == "waiting_external"


def test_build_response_quality_skips_when_judge_disabled():
    store = _build_store()
    container = ServiceContainer(
        ticket_store_factory=lambda: store,
        response_quality_judge_factory=lambda: None,
        checkpointer_factory=build_test_checkpointer,
    )

    with store.session_scope() as session:
        ticket = _create_ticket(priority="medium")
        run = TicketRun(
            run_id="run-no-judge",
            ticket_id=ticket.ticket_id,
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type="manual_api",
            status="succeeded",
            started_at=datetime.now(timezone.utc),
            attempt_index=1,
        )
        session.add(ticket)
        session.add(run)
        session.flush()
        repositories = store.repositories(session)
        runner = TicketRunner(
            session=session,
            repositories=repositories,
            container=container,
            checkpointer=build_test_checkpointer(),
        )

        result = runner._build_response_quality(run=run, ticket=ticket)

        assert result is None
        assert run.app_metadata["response_quality_status"] == "disabled"


def test_build_response_quality_skips_when_current_run_has_no_draft():
    store = _build_store()

    class FakeJudge:
        def evaluate(self, **kwargs):
            raise AssertionError("judge should not be called without a current-run draft")

    container = ServiceContainer(
        ticket_store_factory=lambda: store,
        response_quality_judge_factory=lambda: FakeJudge(),
        checkpointer_factory=build_test_checkpointer,
    )

    with store.session_scope() as session:
        ticket = _create_ticket(priority="medium")
        prior_run = TicketRun(
            run_id="run-old-draft",
            ticket_id=ticket.ticket_id,
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type="manual_api",
            status="succeeded",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            attempt_index=1,
        )
        current_run = TicketRun(
            run_id="run-no-draft",
            ticket_id=ticket.ticket_id,
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type="manual_api",
            status="succeeded",
            started_at=datetime.now(timezone.utc),
            attempt_index=2,
        )
        session.add(ticket)
        session.add(prior_run)
        session.add(current_run)
        session.flush()
        session.add(
            DraftArtifact(
                draft_id=generate_prefixed_id(EntityIdPrefix.DRAFT),
                ticket_id=ticket.ticket_id,
                run_id=prior_run.run_id,
                version_index=1,
                draft_type="reply",
                content_text="old draft",
                qa_status="passed",
                gmail_draft_id=None,
                idempotency_key="draft:old",
                source_evidence_summary="old evidence",
            )
        )
        session.flush()
        repositories = store.repositories(session)
        runner = TicketRunner(
            session=session,
            repositories=repositories,
            container=container,
            checkpointer=build_test_checkpointer(),
        )

        result = runner._build_response_quality(run=current_run, ticket=ticket)

        assert result is None
        assert current_run.app_metadata["response_quality_status"] == "skipped_no_draft"
