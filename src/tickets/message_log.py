from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy.orm import Session

from src.contracts.core import (
    EntityIdPrefix,
    MessageDirection,
    MessageType,
    SourceChannel,
    TicketBusinessStatus,
    TicketProcessingStatus,
    build_customer_identity,
    generate_prefixed_id,
    normalize_email_address,
)
from src.db.models import DraftArtifact, Ticket, TicketMessage
from src.db.repositories import RepositoryBundle, build_repository_bundle


@dataclass(frozen=True)
class IngestEmailPayload:
    source_channel: str
    source_thread_id: str
    source_message_id: str
    sender_email_raw: str
    subject: str | None
    body_text: str | None
    message_timestamp: datetime
    references: str | None = None
    attachments: Sequence[dict[str, Any]] | None = None


@dataclass(frozen=True)
class IngestEmailResult:
    ticket: Ticket
    message: TicketMessage
    created_ticket: bool
    reopened_from_ticket_id: str | None


@dataclass(frozen=True)
class DraftMessagePayload:
    ticket_id: str
    source_thread_id: str
    source_message_id: str
    gmail_thread_id: str
    draft_id: str | None
    message_type: str
    sender_email: str | None
    recipient_emails: Sequence[str]
    subject: str | None
    body_text: str | None
    body_html: str | None
    message_timestamp: datetime
    reply_to_source_message_id: str | None = None
    customer_visible: bool = True
    attachments: Sequence[dict[str, Any]] | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class TicketMessageReadResult:
    messages: list[TicketMessage]
    latest_customer_message: TicketMessage | None
    latest_system_message: TicketMessage | None


class MessageLogService:
    def __init__(
        self,
        session: Session,
        *,
        repositories: RepositoryBundle | None = None,
        alias_map: dict[str, str] | None = None,
    ) -> None:
        self._session = session
        self._repositories = repositories or build_repository_bundle(session)
        self._alias_map = alias_map or {}

    def ingest_inbound_email(self, payload: IngestEmailPayload) -> IngestEmailResult:
        existing_message = self._repositories.ticket_messages.get_by_source_message_id(
            payload.source_message_id
        )
        if existing_message is not None:
            ticket = self._repositories.tickets.get(existing_message.ticket_id)
            return IngestEmailResult(
                ticket=ticket,
                message=existing_message,
                created_ticket=False,
                reopened_from_ticket_id=None,
            )

        ticket = self._repositories.tickets.get_active_by_gmail_thread_id(
            payload.source_thread_id
        )
        created_ticket = False
        reopened_from_ticket_id = None
        if ticket is None:
            previous_closed_ticket = (
                self._repositories.tickets.get_latest_closed_by_gmail_thread_id(
                    payload.source_thread_id
                )
            )
            ticket = self._build_new_ticket(
                payload,
                reopen_count=(
                    (previous_closed_ticket.reopen_count + 1)
                    if previous_closed_ticket is not None
                    else 0
                ),
            )
            if previous_closed_ticket is not None:
                previous_closed_ticket.is_active = False
                reopened_from_ticket_id = previous_closed_ticket.ticket_id
            self._repositories.tickets.add(ticket)
            self._session.flush()
            created_ticket = True

        message = TicketMessage(
            ticket_message_id=generate_prefixed_id(EntityIdPrefix.TICKET_MESSAGE),
            ticket_id=ticket.ticket_id,
            source_thread_id=payload.source_thread_id,
            source_message_id=payload.source_message_id,
            gmail_thread_id=ticket.gmail_thread_id,
            direction=MessageDirection.INBOUND.value,
            message_type=MessageType.CUSTOMER_EMAIL.value,
            sender_email=normalize_email_address(payload.sender_email_raw),
            recipient_emails=[],
            subject=payload.subject,
            body_text=payload.body_text,
            reply_to_source_message_id=payload.references,
            customer_visible=True,
            message_timestamp=payload.message_timestamp,
            message_metadata={
                "attachments": list(payload.attachments or []),
                "sender_email_raw": payload.sender_email_raw,
                "references": payload.references,
            },
        )
        self._repositories.ticket_messages.add(message)
        return IngestEmailResult(
            ticket=ticket,
            message=message,
            created_ticket=created_ticket,
            reopened_from_ticket_id=reopened_from_ticket_id,
        )

    def create_draft_message_log(self, payload: DraftMessagePayload) -> TicketMessage:
        existing_message = self._repositories.ticket_messages.get_by_source_message_id(
            payload.source_message_id
        )
        if existing_message is not None:
            return existing_message

        message = TicketMessage(
            ticket_message_id=generate_prefixed_id(EntityIdPrefix.TICKET_MESSAGE),
            ticket_id=payload.ticket_id,
            run_id=payload.run_id,
            draft_id=payload.draft_id,
            source_thread_id=payload.source_thread_id,
            source_message_id=payload.source_message_id,
            gmail_thread_id=payload.gmail_thread_id,
            direction=MessageDirection.OUTBOUND_DRAFT.value,
            message_type=payload.message_type,
            sender_email=payload.sender_email,
            recipient_emails=list(payload.recipient_emails),
            subject=payload.subject,
            body_text=payload.body_text,
            body_html=payload.body_html,
            reply_to_source_message_id=payload.reply_to_source_message_id,
            customer_visible=payload.customer_visible,
            message_timestamp=payload.message_timestamp,
            message_metadata={"attachments": list(payload.attachments or [])},
        )
        self._repositories.ticket_messages.add(message)
        return message

    def get_thread_messages_for_drafting(self, gmail_thread_id: str) -> TicketMessageReadResult:
        messages = self._repositories.ticket_messages.list_by_thread(gmail_thread_id)
        latest_customer_message = next(
            (
                message
                for message in reversed(messages)
                if message.direction == MessageDirection.INBOUND.value
                and message.message_type == MessageType.CUSTOMER_EMAIL.value
            ),
            None,
        )
        latest_system_message = next(
            (
                message
                for message in reversed(messages)
                if message.message_type
                in {
                    MessageType.REPLY_DRAFT.value,
                    MessageType.CLARIFICATION_REQUEST.value,
                    MessageType.HANDOFF_SUMMARY.value,
                }
            ),
            None,
        )
        return TicketMessageReadResult(
            messages=messages,
            latest_customer_message=latest_customer_message,
            latest_system_message=latest_system_message,
        )

    def _build_new_ticket(
        self,
        payload: IngestEmailPayload,
        *,
        reopen_count: int,
    ) -> Ticket:
        customer_identity = build_customer_identity(
            payload.sender_email_raw,
            alias_map=self._alias_map,
        )
        normalized_email = normalize_email_address(payload.sender_email_raw)

        return Ticket(
            ticket_id=generate_prefixed_id(EntityIdPrefix.TICKET),
            source_channel=SourceChannel.GMAIL.value,
            source_thread_id=payload.source_thread_id,
            source_message_id=payload.source_message_id,
            gmail_thread_id=payload.source_thread_id,
            customer_id=customer_identity.customer_id if customer_identity else None,
            customer_email=(
                customer_identity.normalized_email
                if customer_identity
                else (normalized_email or payload.sender_email_raw.strip().lower())
            ),
            customer_email_raw=payload.sender_email_raw,
            subject=payload.subject or "",
            latest_message_excerpt=(payload.body_text or "")[:280] or None,
            business_status=TicketBusinessStatus.NEW.value,
            processing_status=TicketProcessingStatus.QUEUED.value,
            priority="medium",
            secondary_routes=[],
            tags=[],
            multi_intent=False,
            needs_clarification=False,
            needs_escalation=False,
            risk_reasons=[],
            reopen_count=reopen_count,
        )

