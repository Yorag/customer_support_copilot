from __future__ import annotations

from .core_schema import ResponseStrategy, TicketPriority, TicketRoute


ROUTE_PRIORITY = {
    TicketRoute.COMMERCIAL_POLICY_REQUEST: 0,
    TicketRoute.TECHNICAL_ISSUE: 1,
    TicketRoute.KNOWLEDGE_REQUEST: 2,
    TicketRoute.FEEDBACK_INTAKE: 3,
    TicketRoute.UNRELATED: 4,
}

ROUTE_RESPONSE_STRATEGY = {
    TicketRoute.KNOWLEDGE_REQUEST: ResponseStrategy.ANSWER,
    TicketRoute.TECHNICAL_ISSUE: ResponseStrategy.TROUBLESHOOTING,
    TicketRoute.COMMERCIAL_POLICY_REQUEST: ResponseStrategy.POLICY_CONSTRAINED,
    TicketRoute.FEEDBACK_INTAKE: ResponseStrategy.ACKNOWLEDGEMENT,
    TicketRoute.UNRELATED: ResponseStrategy.ACKNOWLEDGEMENT,
}

PRIORITY_SEQUENCE = (
    TicketPriority.LOW,
    TicketPriority.MEDIUM,
    TicketPriority.HIGH,
    TicketPriority.CRITICAL,
)

PRIORITY_RANK = {
    priority: index for index, priority in enumerate(PRIORITY_SEQUENCE)
}


def max_priority(*priorities: TicketPriority) -> TicketPriority:
    return max(priorities, key=lambda priority: PRIORITY_RANK[priority])


def bump_priority(priority: TicketPriority) -> TicketPriority:
    index = PRIORITY_RANK[priority]
    if index == len(PRIORITY_SEQUENCE) - 1:
        return priority
    return PRIORITY_SEQUENCE[index + 1]
