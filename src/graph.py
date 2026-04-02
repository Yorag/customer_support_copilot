from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import Nodes
from .state import GraphState


class Workflow:
    def __init__(
        self,
        *,
        nodes: Nodes | None = None,
        agents=None,
        service_container=None,
        session=None,
        repositories=None,
        state_service=None,
        message_log=None,
        run=None,
        worker_id: str | None = None,
    ):
        workflow = StateGraph(GraphState)
        nodes = nodes or Nodes(
            agents=agents,
            service_container=service_container,
            session=session,
            repositories=repositories,
            state_service=state_service,
            message_log=message_log,
            run=run,
            worker_id=worker_id,
        )

        workflow.add_node("load_ticket_context", nodes.load_ticket_context)
        workflow.add_node("load_memory", nodes.load_memory)
        workflow.add_node("triage", nodes.triage_ticket)
        workflow.add_node("knowledge_lookup", nodes.knowledge_lookup)
        workflow.add_node("policy_check", nodes.policy_check)
        workflow.add_node("customer_history_lookup", nodes.customer_history_lookup)
        workflow.add_node("draft_reply", nodes.draft_reply)
        workflow.add_node("qa_review", nodes.qa_review)
        workflow.add_node("clarify_request", nodes.clarify_request)
        workflow.add_node("create_gmail_draft", nodes.create_gmail_draft)
        workflow.add_node("escalate_to_human", nodes.escalate_to_human)
        workflow.add_node("close_ticket", nodes.close_ticket)

        workflow.set_entry_point("load_ticket_context")
        workflow.add_edge("load_ticket_context", "load_memory")
        workflow.add_edge("load_memory", "triage")
        workflow.add_conditional_edges(
            "triage",
            nodes.route_ticket,
            {
                "knowledge_lookup": "knowledge_lookup",
                "policy_check": "policy_check",
                "draft_reply": "draft_reply",
                "clarify_request": "clarify_request",
                "close_ticket": "close_ticket",
            },
        )
        workflow.add_conditional_edges(
            "knowledge_lookup",
            nodes.route_after_knowledge,
            {
                "draft_reply": "draft_reply",
                "customer_history_lookup": "customer_history_lookup",
                "escalate_to_human": "escalate_to_human",
            },
        )
        workflow.add_conditional_edges(
            "policy_check",
            nodes.route_after_knowledge,
            {
                "draft_reply": "draft_reply",
                "customer_history_lookup": "customer_history_lookup",
                "escalate_to_human": "escalate_to_human",
            },
        )
        workflow.add_conditional_edges(
            "customer_history_lookup",
            nodes.route_after_customer_history,
            {
                "draft_reply": "draft_reply",
                "escalate_to_human": "escalate_to_human",
            },
        )
        workflow.add_edge("draft_reply", "qa_review")
        workflow.add_conditional_edges(
            "qa_review",
            nodes.route_after_qa,
            {
                "create_gmail_draft": "create_gmail_draft",
                "draft_reply": "draft_reply",
                "escalate_to_human": "escalate_to_human",
            },
        )
        workflow.add_edge("clarify_request", END)
        workflow.add_edge("create_gmail_draft", END)
        workflow.add_edge("escalate_to_human", END)
        workflow.add_edge("close_ticket", END)

        self.app = workflow.compile()
