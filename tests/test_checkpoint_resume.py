from __future__ import annotations

from datetime import datetime, timedelta, timezone
from os import close
from tempfile import mkstemp

from src.bootstrap.container import ServiceContainer
from src.contracts.core import EntityIdPrefix, generate_prefixed_id
from src.db.base import Base
from src.db.models import DraftArtifact, Ticket, TicketRun
from src.db.session import build_engine, create_session_factory
from src.orchestration.checkpointing import build_checkpoint_config, build_test_checkpointer
from src.orchestration.nodes_ticket import TicketNodes
from src.orchestration.state import build_ticket_run_state
from src.orchestration.workflow import Workflow
from src.tickets.state_machine import TicketStateService
from src.tools.ticket_store import SqlAlchemyTicketStore
from src.workers.runner import TicketRunner


class _MinimalNodeSet:
    def load_ticket_context(self, state):
        return state

    def load_memory(self, state):
        return state

    def triage_ticket(self, state):
        return state

    def knowledge_lookup(self, state):
        return state

    def policy_check(self, state):
        return state

    def customer_history_lookup(self, state):
        return state

    def collect_case_context(self, state):
        return state

    def extract_memory_updates(self, state):
        return state

    def validate_memory_updates(self, state):
        return state

    def draft_reply(self, state):
        return state

    def qa_review(self, state):
        return state

    def clarify_request(self, state):
        return state

    def create_gmail_draft(self, state):
        return state

    def escalate_to_human(self, state):
        return state

    def close_ticket(self, state):
        return state

    def route_ticket(self, state):
        return "close_ticket"

    def route_after_knowledge(self, state):
        return "draft_reply"

    def route_after_customer_history(self, state):
        return "draft_reply"

    def route_after_qa(self, state):
        return "create_gmail_draft"


def _build_store() -> SqlAlchemyTicketStore:
    fd, path = mkstemp(suffix=".db")
    close(fd)
    engine = build_engine(f"sqlite+pysqlite:///{path}")
    Base.metadata.create_all(engine)
    return SqlAlchemyTicketStore(
        engine=engine,
        session_factory=create_session_factory(engine),
    )


def _create_ticket() -> Ticket:
    thread_seed = generate_prefixed_id(EntityIdPrefix.TICKET)
    return Ticket(
        ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
        source_thread_id=f"gmail-thread-{thread_seed}",
        source_message_id=f"<root-{thread_seed}@gmail.com>",
        gmail_thread_id=f"gmail-thread-{thread_seed}",
        customer_id="cust_email_liwei_example_com",
        customer_email="liwei@example.com",
        customer_email_raw='"Li Wei" <liwei@example.com>',
        subject="Need help",
        latest_message_excerpt="Please help with a broken workflow.",
        business_status="triaged",
        processing_status="completed",
        priority="medium",
        primary_route="knowledge_request",
        secondary_routes=[],
        tags=[],
        multi_intent=False,
        needs_clarification=False,
        needs_escalation=False,
        risk_reasons=[],
        version=3,
    )


def test_prepare_checkpoint_context_records_checkpoint_metadata() -> None:
    store = _build_store()
    checkpointer = build_test_checkpointer()
    container = ServiceContainer(
        ticket_store_factory=lambda: store,
        checkpointer_factory=lambda: checkpointer,
    )
    now = datetime.now(timezone.utc)

    with store.session_scope() as session:
        ticket = _create_ticket()
        run = TicketRun(
            run_id=generate_prefixed_id(EntityIdPrefix.RUN),
            ticket_id=ticket.ticket_id,
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type="manual_api",
            triggered_by="api-user",
            status="running",
            started_at=now - timedelta(seconds=20),
            attempt_index=1,
        )
        ticket.current_run_id = run.run_id
        ticket.lease_owner = "req-resume"
        ticket.lease_expires_at = now + timedelta(minutes=5)
        session.add(ticket)
        session.add(run)
        repositories = store.repositories(session)
        runner = TicketRunner(
            session=session,
            repositories=repositories,
            container=container,
            checkpointer=checkpointer,
        )
        workflow = Workflow(nodes=_MinimalNodeSet(), checkpointer=checkpointer)
        workflow_config = build_checkpoint_config(ticket_id=ticket.ticket_id, run_id=run.run_id)
        list(workflow.app.stream({}, config=workflow_config))

        context = runner._prepare_checkpoint_context(
            workflow=workflow,
            workflow_config=workflow_config,
            ticket=ticket,
            run=run,
            worker_id="req-resume",
            default_restore_mode="resume",
        )

        assert context["restore_mode"] == "resume"
        assert run.app_metadata == {
            "checkpoint": {
                "thread_id": ticket.ticket_id,
                "checkpoint_ns": run.run_id,
                "restore_mode": "resume",
                "last_checkpoint_node": None,
            }
        }
        session.flush()
        events = repositories.trace_events.list_by_run(run.run_id)
        event_names = {event.event_name for event in events}
        assert event_names == {"checkpoint_resume_decision", "checkpoint_restore"}


def test_prepare_checkpoint_context_updates_resume_state_metadata() -> None:
    store = _build_store()
    checkpointer = build_test_checkpointer()
    container = ServiceContainer(
        ticket_store_factory=lambda: store,
        checkpointer_factory=lambda: checkpointer,
    )
    now = datetime.now(timezone.utc)

    with store.session_scope() as session:
        ticket = _create_ticket()
        run = TicketRun(
            run_id=generate_prefixed_id(EntityIdPrefix.RUN),
            ticket_id=ticket.ticket_id,
            trace_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trigger_type="manual_api",
            triggered_by="api-user",
            status="running",
            started_at=now - timedelta(seconds=20),
            attempt_index=1,
        )
        ticket.current_run_id = run.run_id
        ticket.lease_owner = "req-resume"
        ticket.lease_expires_at = now + timedelta(minutes=5)
        session.add(ticket)
        session.add(run)
        repositories = store.repositories(session)
        runner = TicketRunner(
            session=session,
            repositories=repositories,
            container=container,
            checkpointer=checkpointer,
        )
        workflow = Workflow(nodes=_MinimalNodeSet(), checkpointer=checkpointer)
        workflow_config = build_checkpoint_config(ticket_id=ticket.ticket_id, run_id=run.run_id)
        initial_state = build_ticket_run_state(
            ticket_id=ticket.ticket_id,
            business_status=ticket.business_status,
            processing_status=ticket.processing_status,
            ticket_version=ticket.version,
            trace_id=run.trace_id,
            run_id=run.run_id,
        )
        list(workflow.app.stream(initial_state, config=workflow_config))

        context = runner._prepare_checkpoint_context(
            workflow=workflow,
            workflow_config=workflow_config,
            ticket=ticket,
            run=run,
            worker_id="req-resume",
            default_restore_mode="resume",
        )

        state = workflow.app.get_state(context["stream_config"])
        assert context["restore_mode"] == "resume"
        assert state.values["resume_count"] == 1
        assert state.values["checkpoint_metadata"] == {
            "thread_id": ticket.ticket_id,
            "checkpoint_ns": run.run_id,
            "last_checkpoint_node": None,
            "last_checkpoint_at": state.values["checkpoint_metadata"]["last_checkpoint_at"],
        }
        assert state.values["checkpoint_metadata"]["last_checkpoint_at"] is not None


def test_resume_after_interrupted_node_continues_from_next_node() -> None:
    class CrashAfterTriageNodes(_MinimalNodeSet):
        def __init__(self) -> None:
            self.calls: list[str] = []

        def load_ticket_context(self, state):
            self.calls.append("load_ticket_context")
            return {"current_node": "load_ticket_context"}

        def load_memory(self, state):
            self.calls.append("load_memory")
            return {"current_node": "load_memory"}

        def triage_ticket(self, state):
            self.calls.append("triage")
            return {
                "current_node": "triage",
                "primary_route": "feedback_intake",
                "draft_versions": [
                    {
                        "version_index": 1,
                        "draft_type": "reply",
                        "content_text": "reply after resume",
                    }
                ],
            }

        def close_ticket(self, state):
            self.calls.append("close_ticket")
            if state.get("resume_count", 0) == 0:
                raise RuntimeError("crash after triage checkpoint")
            return {
                "current_node": "close_ticket",
                "final_action": "skip_unrelated",
            }

        def collect_case_context(self, state):
            self.calls.append("collect_case_context")
            return {"current_node": "collect_case_context"}

        def extract_memory_updates(self, state):
            self.calls.append("extract_memory_updates")
            return {"current_node": "extract_memory_updates"}

        def validate_memory_updates(self, state):
            self.calls.append("validate_memory_updates")
            return {"current_node": "validate_memory_updates"}

    nodes = CrashAfterTriageNodes()
    checkpointer = build_test_checkpointer()
    workflow = Workflow(nodes=nodes, checkpointer=checkpointer)
    config = build_checkpoint_config(ticket_id="t_resume", run_id="run_resume")
    initial_state = build_ticket_run_state(
        ticket_id="t_resume",
        run_id="run_resume",
        trace_id="trace_resume",
    )

    try:
        list(workflow.app.stream(initial_state, config=config))
    except RuntimeError as exc:
        assert str(exc) == "crash after triage checkpoint"
    else:  # pragma: no cover
        raise AssertionError("Expected interrupted workflow to raise.")

    crashed_state = workflow.app.get_state(
        {
            "configurable": {
                "thread_id": "t_resume",
                "checkpoint_ns": "run_resume",
                "__pregel_checkpointer": workflow.app.checkpointer,
            }
        }
    )
    assert crashed_state.next == ("close_ticket",)
    assert nodes.calls == ["load_ticket_context", "load_memory", "triage", "close_ticket"]

    workflow.app.update_state(
        {
            **crashed_state.config,
            "configurable": {
                **crashed_state.config["configurable"],
                "__pregel_checkpointer": workflow.app.checkpointer,
            },
        },
        {
            "resume_count": 1,
            "checkpoint_metadata": {
                "thread_id": "t_resume",
                "checkpoint_ns": "run_resume",
                "last_checkpoint_node": "triage",
                "last_checkpoint_at": crashed_state.created_at.isoformat()
                if hasattr(crashed_state.created_at, "isoformat")
                else str(crashed_state.created_at),
            },
        },
    )
    resumed_state = workflow.app.get_state(
        {
            **crashed_state.config,
            "configurable": {
                **crashed_state.config["configurable"],
                "__pregel_checkpointer": workflow.app.checkpointer,
            },
        }
    )

    resumed_output = list(workflow.app.stream(None, config={
        **resumed_state.config,
        "configurable": {
            **resumed_state.config["configurable"],
            "__pregel_checkpointer": workflow.app.checkpointer,
        },
    }))
    assert resumed_output[-1]["validate_memory_updates"]["current_node"] == "validate_memory_updates"
    assert nodes.calls == [
        "load_ticket_context",
        "load_memory",
        "triage",
        "close_ticket",
        "close_ticket",
        "collect_case_context",
        "extract_memory_updates",
        "validate_memory_updates",
    ]


def test_new_run_uses_isolated_checkpoint_namespace() -> None:
    class NamespaceAwareNodes(_MinimalNodeSet):
        def load_ticket_context(self, state):
            return {
                "current_node": "load_ticket_context",
                "draft_versions": [
                    {
                        "version_index": 1,
                        "draft_type": "reply",
                        "content_text": "fresh-state",
                    }
                ],
            }

        def close_ticket(self, state):
            return {
                "current_node": "close_ticket",
                "final_action": "skip_unrelated",
                "draft_versions": list(state.get("draft_versions") or []),
            }

        def collect_case_context(self, state):
            return {"current_node": "collect_case_context"}

        def extract_memory_updates(self, state):
            return {"current_node": "extract_memory_updates"}

        def validate_memory_updates(self, state):
            return {"current_node": "validate_memory_updates"}

    checkpointer = build_test_checkpointer()
    workflow = Workflow(nodes=NamespaceAwareNodes(), checkpointer=checkpointer)
    config_run_1 = build_checkpoint_config(ticket_id="t_isolated", run_id="run_1")
    config_run_2 = build_checkpoint_config(ticket_id="t_isolated", run_id="run_2")

    state_run_1 = build_ticket_run_state(
        ticket_id="t_isolated",
        run_id="run_1",
        trace_id="trace_1",
    )
    state_run_1["draft_versions"] = [
        {"version_index": 1, "draft_type": "reply", "content_text": "from-run-1"}
    ]
    list(workflow.app.stream(state_run_1, config=config_run_1))

    isolated_state = workflow.app.get_state(
        {
            "configurable": {
                "thread_id": "t_isolated",
                "checkpoint_ns": "run_2",
                "__pregel_checkpointer": workflow.app.checkpointer,
            }
        }
    )
    assert isolated_state.values == {}
    assert isolated_state.next == ()

    state_run_2 = build_ticket_run_state(
        ticket_id="t_isolated",
        run_id="run_2",
        trace_id="trace_2",
    )
    list(workflow.app.stream(state_run_2, config=config_run_2))
    final_state_run_2 = workflow.app.get_state(
        {
            "configurable": {
                "thread_id": "t_isolated",
                "checkpoint_ns": "run_2",
                "__pregel_checkpointer": workflow.app.checkpointer,
            }
        }
    )
    assert final_state_run_2.values["draft_versions"][-1]["content_text"] == "fresh-state"


def test_resume_after_qa_review_does_not_repeat_draft_side_effect(sample_email_payload) -> None:
    from tests.test_nodes import FakeAgents, FakeServices, FakeGmailClient
    from src.db.repositories import build_repository_bundle
    from src.contracts.outputs import TriageOutput
    from src.tickets.message_log import MessageLogService
    from src.db.session import session_scope

    class CrashBeforeMemoryNodes:
        def __init__(self, base_nodes) -> None:
            self._base = base_nodes
            self._crashed = False

        def __getattr__(self, item):
            return getattr(self._base, item)

        def collect_case_context(self, state):
            if not self._crashed:
                self._crashed = True
                raise RuntimeError("crash after qa_review")
            return self._base.collect_case_context(state)

    class TicketExecutionAgents(FakeAgents):
        def triage_email_with_rules(self, *, subject, email, context=None):
            return type(
                "Decision",
                (),
                {
                    "output": TriageOutput(
                        primary_route="knowledge_request",
                        secondary_routes=[],
                        tags=[],
                        response_strategy="answer",
                        multi_intent=False,
                        intent_confidence=0.91,
                        priority="medium",
                        needs_clarification=False,
                        needs_escalation=False,
                        routing_reason="Knowledge request.",
                    ),
                    "escalation_reasons": [],
                },
            )()

    store = _build_store()
    checkpointer = build_test_checkpointer()
    with store.session_scope() as session:
        ticket = Ticket(
            ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
            source_thread_id="thread-checkpoint-draft",
            source_message_id=sample_email_payload["messageId"],
            gmail_thread_id="thread-checkpoint-draft",
            customer_id="cust_email_customer_example_com",
            customer_email="customer@example.com",
            customer_email_raw='"Customer" <customer@example.com>',
            subject=sample_email_payload["subject"],
            latest_message_excerpt=sample_email_payload["body"],
            business_status="new",
            processing_status="running",
            priority="medium",
            secondary_routes=[],
            tags=[],
            multi_intent=False,
            needs_clarification=False,
            needs_escalation=False,
            risk_reasons=[],
            lease_owner="worker-1",
            lease_expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
            current_run_id="run-draft-recovery",
        )
        run = TicketRun(
            run_id="run-draft-recovery",
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
        message_log = MessageLogService(session)
        message_log.ingest_inbound_email(
            type(
                "InboundPayload",
                (),
                {
                    "source_channel": "gmail",
                    "source_thread_id": "thread-checkpoint-draft",
                    "source_message_id": sample_email_payload["messageId"],
                    "sender_email_raw": sample_email_payload["sender"],
                    "subject": sample_email_payload["subject"],
                    "body_text": sample_email_payload["body"],
                    "message_timestamp": datetime.now(timezone.utc),
                    "references": sample_email_payload["references"],
                    "attachments": [],
                },
            )()
        )
        session.flush()
        repositories = build_repository_bundle(session)
        state_service = TicketStateService(session, repositories=repositories)
        gmail_client = FakeGmailClient()
        base_nodes = TicketNodes(
            agents=TicketExecutionAgents(),
            service_container=FakeServices(gmail_client),
            session=session,
            repositories=repositories,
            state_service=state_service,
            message_log=message_log,
            run=run,
            worker_id="worker-1",
        )
        nodes = CrashBeforeMemoryNodes(base_nodes)
        workflow = Workflow(nodes=nodes, checkpointer=checkpointer)
        initial_state = build_ticket_run_state(
            ticket_id=ticket.ticket_id,
            business_status=ticket.business_status,
            processing_status=ticket.processing_status,
            ticket_version=ticket.version,
            trace_id=run.trace_id,
            run_id=run.run_id,
        )
        config = build_checkpoint_config(ticket_id=ticket.ticket_id, run_id=run.run_id)

        try:
            list(workflow.app.stream(initial_state, config=config))
        except RuntimeError as exc:
            assert str(exc) == "crash after qa_review"
        else:  # pragma: no cover
            raise AssertionError("Expected workflow to crash after qa_review.")

        assert len(gmail_client.created_drafts) == 1
        assert len(repositories.draft_artifacts.list_by_ticket(ticket.ticket_id)) == 1

        crashed_state = workflow.app.get_state(
            {
                "configurable": {
                    "thread_id": ticket.ticket_id,
                    "checkpoint_ns": run.run_id,
                    "__pregel_checkpointer": workflow.app.checkpointer,
                }
            }
        )
        workflow.app.update_state(
            {
                **crashed_state.config,
                "configurable": {
                    **crashed_state.config["configurable"],
                    "__pregel_checkpointer": workflow.app.checkpointer,
                },
            },
            {
                "resume_count": 1,
                "checkpoint_metadata": {
                    "thread_id": ticket.ticket_id,
                    "checkpoint_ns": run.run_id,
                    "last_checkpoint_node": "create_gmail_draft",
                    "last_checkpoint_at": crashed_state.created_at.isoformat()
                    if hasattr(crashed_state.created_at, "isoformat")
                    else str(crashed_state.created_at),
                },
            },
        )
        resumed_state = workflow.app.get_state(
            {
                **crashed_state.config,
                "configurable": {
                    **crashed_state.config["configurable"],
                    "__pregel_checkpointer": workflow.app.checkpointer,
                },
            }
        )
        list(
            workflow.app.stream(
                None,
                config={
                    **resumed_state.config,
                    "configurable": {
                        **resumed_state.config["configurable"],
                        "__pregel_checkpointer": workflow.app.checkpointer,
                    },
                },
            )
        )
        session.flush()

        drafts = repositories.draft_artifacts.list_by_ticket(ticket.ticket_id)
        messages = repositories.ticket_messages.list_by_ticket(ticket.ticket_id)
        assert len(gmail_client.created_drafts) == 1
        assert len(drafts) == 1
        assert len([message for message in messages if message.direction == "outbound_draft"]) == 1
        assert drafts[0].gmail_draft_id == "draft_001"
