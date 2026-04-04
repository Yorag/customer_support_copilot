from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver

from src.orchestration.checkpointing import (
    CheckpointIdentity,
    CheckpointNamespaceAdapter,
    build_checkpoint_config,
    build_default_checkpointer,
    build_checkpoint_identity,
    build_test_checkpointer,
)
from src.orchestration.workflow import Workflow


def test_build_checkpoint_identity_uses_ticket_and_run_ids() -> None:
    identity = build_checkpoint_identity(ticket_id="t_123", run_id="run_456")

    assert identity == CheckpointIdentity(thread_id="t_123", checkpoint_ns="run_456")


def test_build_checkpoint_identity_rejects_blank_values() -> None:
    try:
        build_checkpoint_identity(ticket_id="", run_id="run_456")
    except ValueError as exc:
        assert str(exc) == "ticket_id must not be blank."
    else:  # pragma: no cover
        raise AssertionError("Expected blank ticket_id to be rejected.")

    try:
        build_checkpoint_identity(ticket_id="t_123", run_id=" ")
    except ValueError as exc:
        assert str(exc) == "run_id must not be blank."
    else:  # pragma: no cover
        raise AssertionError("Expected blank run_id to be rejected.")


def test_build_checkpoint_config_uses_langgraph_configurable_contract() -> None:
    config = build_checkpoint_config(ticket_id="t_123", run_id="run_456")

    assert config["configurable"] == {
        "thread_id": "t_123",
        "checkpoint_ns": "run_456",
    }
    assert isinstance(config["recursion_limit"], int)
    assert config["recursion_limit"] > 0


def test_build_test_checkpointer_returns_in_memory_saver() -> None:
    saver = build_test_checkpointer()

    assert isinstance(saver, CheckpointNamespaceAdapter)
    assert isinstance(saver._saver, InMemorySaver)


def test_build_default_checkpointer_runs_setup_on_first_get(monkeypatch) -> None:
    setup_calls: list[str] = []

    class FakeSaver:
        def setup(self) -> None:
            setup_calls.append("setup")

    class FakePostgresSaver:
        @staticmethod
        def from_conn_string(_dsn: str):
            class _Manager:
                def __enter__(self):
                    return FakeSaver()

                def __exit__(self, exc_type, exc, tb) -> None:
                    return None

            return _Manager()

    monkeypatch.setitem(
        __import__("sys").modules,
        "langgraph.checkpoint.postgres",
        type("_FakeModule", (), {"PostgresSaver": FakePostgresSaver})(),
    )

    managed = build_default_checkpointer()
    first = managed.get()
    second = managed.get()

    assert isinstance(first, CheckpointNamespaceAdapter)
    assert first is second
    assert setup_calls == ["setup"]


def test_workflow_compiles_with_provided_checkpointer() -> None:
    class StubNodes:
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

    saver = build_test_checkpointer()

    workflow = Workflow(nodes=StubNodes(), checkpointer=saver)

    assert workflow.checkpointer is saver


def test_checkpoint_namespace_adapter_preserves_checkpoint_ns_on_put_roundtrip() -> None:
    class MinimalNodes:
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

    saver = build_test_checkpointer()
    workflow = Workflow(nodes=MinimalNodes(), checkpointer=saver)
    config = {
        "configurable": {
            "thread_id": "t_123",
            "checkpoint_ns": "run_456",
        }
    }

    list(workflow.app.stream({}, config=config))
    state = workflow.app.get_state(
        {
            "configurable": {
                "thread_id": "t_123",
                "checkpoint_ns": "run_456",
                "__pregel_checkpointer": workflow.app.checkpointer,
            }
        }
    )

    assert state.config["configurable"]["checkpoint_ns"] == "run_456"
