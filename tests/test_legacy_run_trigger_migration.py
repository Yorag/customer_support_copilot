from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations

from src.contracts.core import EntityIdPrefix, generate_prefixed_id
from src.db.base import Base
from src.db.models import Ticket, TicketRun
from src.db.session import build_engine, create_session_factory, session_scope


def _load_migration_module():
    module_path = (
        Path(__file__).resolve().parent.parent
        / "alembic"
        / "versions"
        / "20260415_0007_normalize_legacy_run_trigger_types.py"
    )
    spec = importlib.util.spec_from_file_location("migration_20260415_0007", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load migration module from {module_path}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_ticket() -> Ticket:
    return Ticket(
        ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
        source_thread_id="thread-migration-run-trigger",
        source_message_id=generate_prefixed_id(EntityIdPrefix.TICKET),
        gmail_thread_id="gmail-thread-migration-run-trigger",
        customer_email="migration@example.com",
        customer_email_raw='"Migration User" <migration@example.com>',
        subject="Run trigger migration",
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


def test_legacy_run_trigger_type_migration_normalizes_offline_eval() -> None:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        ticket = _build_ticket()
        session.add(ticket)
        session.flush()
        session.execute(
            TicketRun.__table__.insert().values(
                run_id="run-migration-legacy",
                ticket_id=ticket.ticket_id,
                trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
                trigger_type="offline_eval",
                status="queued",
                attempt_index=1,
            )
        )
        session.execute(
            TicketRun.__table__.insert().values(
                run_id="run-migration-current",
                ticket_id=ticket.ticket_id,
                trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
                trigger_type="manual_api",
                status="queued",
                attempt_index=1,
            )
        )

    migration = _load_migration_module()
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        migration.op = Operations(context)
        migration.upgrade()

    with session_scope(session_factory) as session:
        legacy_run = session.get(TicketRun, "run-migration-legacy")
        current_run = session.get(TicketRun, "run-migration-current")
        assert legacy_run is not None
        assert current_run is not None
        assert legacy_run.trigger_type == "manual_api"
        assert current_run.trigger_type == "manual_api"
