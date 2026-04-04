from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from src.db.models import (
    CustomerMemoryEvent,
    CustomerMemoryProfile,
    DraftArtifact,
    HumanReview,
    Ticket,
    TicketMessage,
    TicketRun,
    TraceEvent,
)


class TicketRepositoryProtocol(Protocol):
    def add(self, ticket: Ticket) -> Ticket:
        ...

    def get(self, ticket_id: str) -> Ticket | None:
        ...

    def get_active_by_gmail_thread_id(self, gmail_thread_id: str) -> Ticket | None:
        ...

    def get_latest_closed_by_gmail_thread_id(self, gmail_thread_id: str) -> Ticket | None:
        ...

    def list_all(self) -> list[Ticket]:
        ...

    def list_worker_ready_candidates(self) -> list[Ticket]:
        ...


class TicketRunRepositoryProtocol(Protocol):
    def add(self, run: TicketRun) -> TicketRun:
        ...

    def get(self, run_id: str) -> TicketRun | None:
        ...

    def list_by_ticket(self, ticket_id: str) -> list[TicketRun]:
        ...


class DraftArtifactRepositoryProtocol(Protocol):
    def add(self, draft: DraftArtifact) -> DraftArtifact:
        ...

    def get(self, draft_id: str) -> DraftArtifact | None:
        ...

    def list_by_ticket(self, ticket_id: str) -> list[DraftArtifact]:
        ...


class HumanReviewRepositoryProtocol(Protocol):
    def add(self, review: HumanReview) -> HumanReview:
        ...

    def get(self, review_id: str) -> HumanReview | None:
        ...

    def list_by_ticket(self, ticket_id: str) -> list[HumanReview]:
        ...


class TraceEventRepositoryProtocol(Protocol):
    def add(self, event: TraceEvent) -> TraceEvent:
        ...

    def get(self, event_id: str) -> TraceEvent | None:
        ...

    def list_by_run(self, run_id: str) -> list[TraceEvent]:
        ...


class CustomerMemoryProfileRepositoryProtocol(Protocol):
    def add(self, profile: CustomerMemoryProfile) -> CustomerMemoryProfile:
        ...

    def get(self, customer_id: str) -> CustomerMemoryProfile | None:
        ...

    def list_all(self) -> list[CustomerMemoryProfile]:
        ...


class CustomerMemoryEventRepositoryProtocol(Protocol):
    def add(self, event: CustomerMemoryEvent) -> CustomerMemoryEvent:
        ...

    def get(self, memory_event_id: str) -> CustomerMemoryEvent | None:
        ...

    def list_by_customer(self, customer_id: str) -> list[CustomerMemoryEvent]:
        ...


class TicketMessageRepositoryProtocol(Protocol):
    def add(self, message: TicketMessage) -> TicketMessage:
        ...

    def get(self, ticket_message_id: str) -> TicketMessage | None:
        ...

    def get_by_source_message_id(self, source_message_id: str) -> TicketMessage | None:
        ...

    def list_by_ticket(self, ticket_id: str) -> list[TicketMessage]:
        ...

    def list_by_thread(self, gmail_thread_id: str) -> list[TicketMessage]:
        ...


class SqlAlchemyTicketRepository(TicketRepositoryProtocol):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, ticket: Ticket) -> Ticket:
        self._session.add(ticket)
        return ticket

    def get(self, ticket_id: str) -> Ticket | None:
        return self._session.get(Ticket, ticket_id)

    def get_active_by_gmail_thread_id(self, gmail_thread_id: str) -> Ticket | None:
        statement = select(Ticket).where(
            Ticket.gmail_thread_id == gmail_thread_id,
            Ticket.is_active.is_(True),
            Ticket.business_status != "closed",
        )
        return self._session.scalar(statement)

    def get_latest_closed_by_gmail_thread_id(self, gmail_thread_id: str) -> Ticket | None:
        statement = (
            select(Ticket)
            .where(
                Ticket.gmail_thread_id == gmail_thread_id,
                Ticket.business_status == "closed",
            )
            .order_by(Ticket.closed_at.desc(), Ticket.updated_at.desc())
        )
        return self._session.scalar(statement)

    def list_all(self) -> list[Ticket]:
        return list(self._session.scalars(select(Ticket)))

    def list_worker_ready_candidates(self) -> list[Ticket]:
        priority_rank = case(
            (Ticket.priority == "critical", 0),
            (Ticket.priority == "high", 1),
            (Ticket.priority == "medium", 2),
            else_=3,
        )
        statement = (
            select(Ticket)
            .join(TicketRun, TicketRun.run_id == Ticket.current_run_id)
            .where(
                Ticket.business_status.not_in(("approved", "closed")),
                TicketRun.ended_at.is_(None),
                or_(
                    Ticket.processing_status.in_(("queued", "error")),
                    Ticket.lease_expires_at.is_not(None),
                ),
            )
            .order_by(priority_rank.asc(), Ticket.created_at.asc(), Ticket.ticket_id.asc())
        )
        return list(self._session.scalars(statement))


class SqlAlchemyTicketRunRepository(TicketRunRepositoryProtocol):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, run: TicketRun) -> TicketRun:
        self._session.add(run)
        return run

    def get(self, run_id: str) -> TicketRun | None:
        return self._session.get(TicketRun, run_id)

    def list_by_ticket(self, ticket_id: str) -> list[TicketRun]:
        statement = select(TicketRun).where(TicketRun.ticket_id == ticket_id)
        return list(self._session.scalars(statement))


class SqlAlchemyDraftArtifactRepository(DraftArtifactRepositoryProtocol):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, draft: DraftArtifact) -> DraftArtifact:
        self._session.add(draft)
        return draft

    def get(self, draft_id: str) -> DraftArtifact | None:
        return self._session.get(DraftArtifact, draft_id)

    def list_by_ticket(self, ticket_id: str) -> list[DraftArtifact]:
        statement = select(DraftArtifact).where(DraftArtifact.ticket_id == ticket_id)
        return list(self._session.scalars(statement))


class SqlAlchemyHumanReviewRepository(HumanReviewRepositoryProtocol):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, review: HumanReview) -> HumanReview:
        self._session.add(review)
        return review

    def get(self, review_id: str) -> HumanReview | None:
        return self._session.get(HumanReview, review_id)

    def list_by_ticket(self, ticket_id: str) -> list[HumanReview]:
        statement = select(HumanReview).where(HumanReview.ticket_id == ticket_id)
        return list(self._session.scalars(statement))


class SqlAlchemyTraceEventRepository(TraceEventRepositoryProtocol):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, event: TraceEvent) -> TraceEvent:
        self._session.add(event)
        return event

    def get(self, event_id: str) -> TraceEvent | None:
        return self._session.get(TraceEvent, event_id)

    def list_by_run(self, run_id: str) -> list[TraceEvent]:
        statement = select(TraceEvent).where(TraceEvent.run_id == run_id)
        return list(self._session.scalars(statement))


class SqlAlchemyCustomerMemoryProfileRepository(
    CustomerMemoryProfileRepositoryProtocol
):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, profile: CustomerMemoryProfile) -> CustomerMemoryProfile:
        self._session.add(profile)
        return profile

    def get(self, customer_id: str) -> CustomerMemoryProfile | None:
        return self._session.get(CustomerMemoryProfile, customer_id)

    def list_all(self) -> list[CustomerMemoryProfile]:
        return list(self._session.scalars(select(CustomerMemoryProfile)))


class SqlAlchemyCustomerMemoryEventRepository(CustomerMemoryEventRepositoryProtocol):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, event: CustomerMemoryEvent) -> CustomerMemoryEvent:
        self._session.add(event)
        return event

    def get(self, memory_event_id: str) -> CustomerMemoryEvent | None:
        return self._session.get(CustomerMemoryEvent, memory_event_id)

    def list_by_customer(self, customer_id: str) -> list[CustomerMemoryEvent]:
        statement = select(CustomerMemoryEvent).where(
            CustomerMemoryEvent.customer_id == customer_id
        )
        return list(self._session.scalars(statement))


class SqlAlchemyTicketMessageRepository(TicketMessageRepositoryProtocol):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, message: TicketMessage) -> TicketMessage:
        self._session.add(message)
        return message

    def get(self, ticket_message_id: str) -> TicketMessage | None:
        return self._session.get(TicketMessage, ticket_message_id)

    def get_by_source_message_id(self, source_message_id: str) -> TicketMessage | None:
        statement = select(TicketMessage).where(
            TicketMessage.source_message_id == source_message_id
        )
        return self._session.scalar(statement)

    def list_by_ticket(self, ticket_id: str) -> list[TicketMessage]:
        statement = select(TicketMessage).where(TicketMessage.ticket_id == ticket_id)
        return list(self._session.scalars(statement))

    def list_by_thread(self, gmail_thread_id: str) -> list[TicketMessage]:
        statement = (
            select(TicketMessage)
            .where(TicketMessage.gmail_thread_id == gmail_thread_id)
            .order_by(TicketMessage.message_timestamp.asc(), TicketMessage.created_at.asc())
        )
        return list(self._session.scalars(statement))


@dataclass(frozen=True)
class RepositoryBundle:
    tickets: TicketRepositoryProtocol
    ticket_runs: TicketRunRepositoryProtocol
    draft_artifacts: DraftArtifactRepositoryProtocol
    human_reviews: HumanReviewRepositoryProtocol
    trace_events: TraceEventRepositoryProtocol
    customer_memory_profiles: CustomerMemoryProfileRepositoryProtocol
    customer_memory_events: CustomerMemoryEventRepositoryProtocol
    ticket_messages: TicketMessageRepositoryProtocol


def build_repository_bundle(session: Session) -> RepositoryBundle:
    return RepositoryBundle(
        tickets=SqlAlchemyTicketRepository(session),
        ticket_runs=SqlAlchemyTicketRunRepository(session),
        draft_artifacts=SqlAlchemyDraftArtifactRepository(session),
        human_reviews=SqlAlchemyHumanReviewRepository(session),
        trace_events=SqlAlchemyTraceEventRepository(session),
        customer_memory_profiles=SqlAlchemyCustomerMemoryProfileRepository(session),
        customer_memory_events=SqlAlchemyCustomerMemoryEventRepository(session),
        ticket_messages=SqlAlchemyTicketMessageRepository(session),
    )
