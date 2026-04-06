from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes_ticket import TicketNodes

from .checkpointing import ManagedCheckpointer, build_default_checkpointer
from .routes import (
    POST_CUSTOMER_HISTORY_ROUTE_MAP,
    POST_KNOWLEDGE_ROUTE_MAP,
    POST_QA_ROUTE_MAP,
    TRIAGE_ROUTE_MAP,
)
from .state import GraphState


NODE_HANDLERS: tuple[tuple[str, str], ...] = (
    ("load_ticket_context", "load_ticket_context"),
    ("load_memory", "load_memory"),
    ("triage", "triage_ticket"),
    ("knowledge_lookup", "knowledge_lookup"),
    ("policy_check", "policy_check"),
    ("customer_history_lookup", "customer_history_lookup"),
    ("collect_case_context", "collect_case_context"),
    ("extract_memory_updates", "extract_memory_updates"),
    ("validate_memory_updates", "validate_memory_updates"),
    ("draft_reply", "draft_reply"),
    ("qa_review", "qa_review"),
    ("clarify_request", "clarify_request"),
    ("create_gmail_draft", "create_gmail_draft"),
    ("escalate_to_human", "escalate_to_human"),
    ("close_ticket", "close_ticket"),
)

COLLECT_CASE_CONTEXT_SOURCES: tuple[str, ...] = (
    "clarify_request",
    "create_gmail_draft",
    "escalate_to_human",
    "close_ticket",
)

CONDITIONAL_EDGES: tuple[tuple[str, str, dict[str, str]], ...] = (
    ("triage", "route_ticket", TRIAGE_ROUTE_MAP),
    ("knowledge_lookup", "route_after_knowledge", POST_KNOWLEDGE_ROUTE_MAP),
    ("policy_check", "route_after_policy_check", POST_KNOWLEDGE_ROUTE_MAP),
    (
        "customer_history_lookup",
        "route_after_customer_history",
        POST_CUSTOMER_HISTORY_ROUTE_MAP,
    ),
    ("qa_review", "route_after_qa", POST_QA_ROUTE_MAP),
)

LINEAR_EDGES: tuple[tuple[str, str], ...] = (
    ("load_ticket_context", "load_memory"),
    ("load_memory", "triage"),
    ("draft_reply", "qa_review"),
    ("collect_case_context", "extract_memory_updates"),
    ("extract_memory_updates", "validate_memory_updates"),
    ("validate_memory_updates", END),
)


class Workflow:
    def __init__(
        self,
        *,
        nodes: TicketNodes | None = None,
        agents=None,
        service_container=None,
        session=None,
        repositories=None,
        state_service=None,
        message_log=None,
        run=None,
        worker_id: str | None = None,
        trace_recorder=None,
        checkpointer=None,
    ):
        workflow = StateGraph(GraphState)
        nodes = nodes or TicketNodes(
            agents=agents,
            service_container=service_container,
            session=session,
            repositories=repositories,
            state_service=state_service,
            message_log=message_log,
            run=run,
            worker_id=worker_id,
            trace_recorder=trace_recorder,
        )

        self._register_nodes(workflow, nodes)

        self._register_edges(workflow, nodes)

        self.checkpointer = checkpointer or build_default_checkpointer()
        self.app = workflow.compile(
            checkpointer=self._resolve_checkpointer(self.checkpointer)
        )

    def _register_nodes(self, workflow: StateGraph, nodes: TicketNodes) -> None:
        for node_name, handler_name in NODE_HANDLERS:
            workflow.add_node(node_name, getattr(nodes, handler_name))

    def _register_edges(self, workflow: StateGraph, nodes: TicketNodes) -> None:
        workflow.set_entry_point("load_ticket_context")

        for source, target in LINEAR_EDGES:
            workflow.add_edge(source, target)

        for source in COLLECT_CASE_CONTEXT_SOURCES:
            workflow.add_edge(source, "collect_case_context")

        for source, route_handler_name, route_map in CONDITIONAL_EDGES:
            workflow.add_conditional_edges(
                source,
                getattr(nodes, route_handler_name),
                route_map,
            )

    def _resolve_checkpointer(self, checkpointer):
        if isinstance(checkpointer, ManagedCheckpointer):
            return checkpointer.get()
        return checkpointer


__all__ = ["Workflow"]
