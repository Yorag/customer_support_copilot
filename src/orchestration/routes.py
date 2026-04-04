from __future__ import annotations


TRIAGE_ROUTE_MAP: dict[str, str] = {
    "knowledge_lookup": "knowledge_lookup",
    "policy_check": "policy_check",
    "draft_reply": "draft_reply",
    "clarify_request": "clarify_request",
    "escalate_to_human": "escalate_to_human",
    "close_ticket": "close_ticket",
}

POST_KNOWLEDGE_ROUTE_MAP: dict[str, str] = {
    "draft_reply": "draft_reply",
    "customer_history_lookup": "customer_history_lookup",
    "escalate_to_human": "escalate_to_human",
}

POST_CUSTOMER_HISTORY_ROUTE_MAP: dict[str, str] = {
    "draft_reply": "draft_reply",
    "escalate_to_human": "escalate_to_human",
}

POST_QA_ROUTE_MAP: dict[str, str] = {
    "create_gmail_draft": "create_gmail_draft",
    "draft_reply": "draft_reply",
    "escalate_to_human": "escalate_to_human",
}

__all__ = [
    "POST_CUSTOMER_HISTORY_ROUTE_MAP",
    "POST_KNOWLEDGE_ROUTE_MAP",
    "POST_QA_ROUTE_MAP",
    "TRIAGE_ROUTE_MAP",
]
