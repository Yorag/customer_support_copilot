from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy.orm import Session

from src.core_schema import (
    CoreSchemaError,
    EntityIdPrefix,
    MemoryEventType,
    MemorySourceStage,
    TicketBusinessStatus,
    TicketPriority,
    TicketRoute,
    TicketTag,
    build_customer_identity,
    generate_prefixed_id,
)
from src.db.models import CustomerMemoryEvent, CustomerMemoryProfile, Ticket, TicketRun
from src.db.repositories import RepositoryBundle, build_repository_bundle


def _default_profile() -> dict[str, Any]:
    return {
        "name": "",
        "account_tier": "unknown",
        "preferred_language": "unknown",
        "preferred_tone": "unknown",
    }


def _default_business_flags() -> dict[str, Any]:
    return {
        "high_value_customer": False,
        "refund_dispute_history": False,
        "requires_manual_approval": False,
    }


@dataclass(frozen=True)
class MemoryEventDraft:
    source_stage: MemorySourceStage
    event_type: MemoryEventType
    payload: dict[str, Any]
    idempotency_suffix: str


@dataclass(frozen=True)
class MemoryExtractionResult:
    customer_id: str | None
    profile_patch: dict[str, Any]
    risk_tags_to_add: tuple[str, ...]
    risk_tags_to_remove: tuple[str, ...]
    business_flags_patch: dict[str, Any]
    historical_case_ref: dict[str, Any] | None
    events: tuple[MemoryEventDraft, ...]


class CustomerMemoryService:
    def __init__(
        self,
        session: Session,
        *,
        repositories: RepositoryBundle | None = None,
    ) -> None:
        self._session = session
        self._repositories = repositories or build_repository_bundle(session)

    def collect_case_context(
        self,
        *,
        ticket: Ticket,
        run: TicketRun | None = None,
        stage: MemorySourceStage,
        state: Mapping[str, Any] | None = None,
        draft_text: str | None = None,
        review_comment: str | None = None,
        target_queue: str | None = None,
    ) -> dict[str, Any]:
        profile = (
            self._repositories.customer_memory_profiles.get(ticket.customer_id)
            if ticket.customer_id
            else None
        )
        business_flags = (
            dict(profile.business_flags) if profile is not None else _default_business_flags()
        )
        return {
            "ticket_id": ticket.ticket_id,
            "run_id": run.run_id if run is not None else None,
            "stage": stage.value,
            "business_status": ticket.business_status,
            "processing_status": ticket.processing_status,
            "customer_email": ticket.customer_email,
            "customer_email_raw": ticket.customer_email_raw,
            "customer_id": ticket.customer_id,
            "subject": ticket.subject,
            "primary_route": ticket.primary_route,
            "priority": ticket.priority,
            "tags": list(ticket.tags or []),
            "risk_reasons": list(ticket.risk_reasons or []),
            "routing_reason": ticket.routing_reason,
            "needs_clarification": bool(ticket.needs_clarification),
            "needs_escalation": bool(ticket.needs_escalation),
            "customer_profile": (
                {
                    "profile": dict(profile.profile),
                    "risk_tags": list(profile.risk_tags),
                    "business_flags": dict(profile.business_flags),
                    "historical_case_refs": list(profile.historical_case_refs),
                    "version": profile.version,
                }
                if profile is not None
                else None
            ),
            "state_memory_updates": dict((state or {}).get("memory_updates") or {}),
            "human_handoff_summary": (state or {}).get("human_handoff_summary"),
            "thread_summary": (state or {}).get("thread_summary"),
            "draft_text": draft_text,
            "review_comment": review_comment,
            "target_queue": target_queue,
            "requires_manual_approval": bool(
                business_flags.get("requires_manual_approval", False)
            ),
        }

    def extract_memory_updates(
        self,
        *,
        ticket: Ticket,
        run: TicketRun | None = None,
        case_context: Mapping[str, Any],
    ) -> MemoryExtractionResult:
        customer_id = ticket.customer_id
        if customer_id is None:
            identity = build_customer_identity(ticket.customer_email_raw)
            customer_id = identity.customer_id if identity is not None else None

        stage = MemorySourceStage(case_context["stage"])
        profile_patch = self._extract_profile_patch(ticket, case_context)
        business_flags_patch = self._extract_business_flags_patch(ticket, case_context, stage)
        risk_tags_to_add = self._extract_risk_tags(ticket)
        historical_case_ref = self._extract_historical_case_ref(ticket, case_context, stage)

        events: list[MemoryEventDraft] = []
        if profile_patch:
            events.append(
                MemoryEventDraft(
                    source_stage=stage,
                    event_type=MemoryEventType.PROFILE_UPDATE,
                    payload=profile_patch,
                    idempotency_suffix="profile",
                )
            )
        if business_flags_patch:
            events.append(
                MemoryEventDraft(
                    source_stage=stage,
                    event_type=MemoryEventType.BUSINESS_FLAG_UPDATE,
                    payload=business_flags_patch,
                    idempotency_suffix="business_flags",
                )
            )
        for tag in risk_tags_to_add:
            events.append(
                MemoryEventDraft(
                    source_stage=stage,
                    event_type=MemoryEventType.RISK_TAG_ADD,
                    payload={"tag": tag},
                    idempotency_suffix=f"risk_tag_add:{tag}",
                )
            )
        if historical_case_ref is not None:
            events.append(
                MemoryEventDraft(
                    source_stage=stage,
                    event_type=MemoryEventType.HISTORICAL_CASE_APPEND,
                    payload=historical_case_ref,
                    idempotency_suffix="historical_case",
                )
            )

        return MemoryExtractionResult(
            customer_id=customer_id,
            profile_patch=profile_patch,
            risk_tags_to_add=tuple(risk_tags_to_add),
            risk_tags_to_remove=(),
            business_flags_patch=business_flags_patch,
            historical_case_ref=historical_case_ref,
            events=tuple(events),
        )

    def validate_memory_updates(
        self,
        updates: MemoryExtractionResult | Mapping[str, Any],
    ) -> dict[str, Any] | None:
        if isinstance(updates, Mapping):
            updates = MemoryExtractionResult(
                customer_id=updates.get("customer_id"),
                profile_patch=dict(updates.get("profile_patch") or {}),
                risk_tags_to_add=tuple(updates.get("risk_tags_to_add") or ()),
                risk_tags_to_remove=tuple(updates.get("risk_tags_to_remove") or ()),
                business_flags_patch=dict(updates.get("business_flags_patch") or {}),
                historical_case_ref=(
                    dict(updates["historical_case_ref"])
                    if updates.get("historical_case_ref") is not None
                    else None
                ),
                events=tuple(
                    MemoryEventDraft(
                        source_stage=MemorySourceStage(item["source_stage"]),
                        event_type=MemoryEventType(item["event_type"]),
                        payload=dict(item["payload"]),
                        idempotency_suffix=str(item["idempotency_suffix"]),
                    )
                    for item in updates.get("events") or ()
                ),
            )
        if updates.customer_id is None:
            return None

        validated_profile = {
            **_default_profile(),
            **updates.profile_patch,
        }
        validated_business_flags = {
            **_default_business_flags(),
            **updates.business_flags_patch,
        }
        risk_tags = sorted(
            {tag for tag in updates.risk_tags_to_add if tag}
        )
        payload = {
            "customer_id": updates.customer_id,
            "profile": validated_profile,
            "risk_tags_to_add": risk_tags,
            "risk_tags_to_remove": list(updates.risk_tags_to_remove),
            "business_flags": validated_business_flags,
            "historical_case_ref": updates.historical_case_ref,
            "events": [
                {
                    "source_stage": event.source_stage.value,
                    "event_type": event.event_type.value,
                    "payload": event.payload,
                    "idempotency_suffix": event.idempotency_suffix,
                }
                for event in updates.events
            ],
        }
        return payload

    def serialize_extraction_result(
        self,
        updates: MemoryExtractionResult,
    ) -> dict[str, Any]:
        return {
            "customer_id": updates.customer_id,
            "profile_patch": dict(updates.profile_patch),
            "risk_tags_to_add": list(updates.risk_tags_to_add),
            "risk_tags_to_remove": list(updates.risk_tags_to_remove),
            "business_flags_patch": dict(updates.business_flags_patch),
            "historical_case_ref": (
                dict(updates.historical_case_ref)
                if updates.historical_case_ref is not None
                else None
            ),
            "events": [
                {
                    "source_stage": event.source_stage.value,
                    "event_type": event.event_type.value,
                    "payload": dict(event.payload),
                    "idempotency_suffix": event.idempotency_suffix,
                }
                for event in updates.events
            ],
        }

    def apply_memory_updates(
        self,
        *,
        ticket: Ticket,
        run: TicketRun,
        validated_updates: Mapping[str, Any] | None,
    ) -> CustomerMemoryProfile | None:
        if not validated_updates:
            return None

        customer_id = str(validated_updates["customer_id"])
        profile = self._repositories.customer_memory_profiles.get(customer_id)
        created_profile = profile is None
        if profile is None:
            profile = CustomerMemoryProfile(
                customer_id=customer_id,
                primary_email=ticket.customer_email,
                alias_emails=[ticket.customer_email],
                profile=_default_profile(),
                risk_tags=[],
                business_flags=_default_business_flags(),
                historical_case_refs=[],
            )
            self._repositories.customer_memory_profiles.add(profile)
            self._session.flush()

        merged_profile = {
            **dict(profile.profile),
            **dict(validated_updates.get("profile") or {}),
        }
        merged_business_flags = {
            **dict(profile.business_flags),
            **dict(validated_updates.get("business_flags") or {}),
        }
        merged_risk_tags = set(profile.risk_tags or [])
        merged_risk_tags.update(validated_updates.get("risk_tags_to_add") or [])
        merged_risk_tags.difference_update(validated_updates.get("risk_tags_to_remove") or [])
        historical_case_ref = validated_updates.get("historical_case_ref")
        merged_history = list(profile.historical_case_refs or [])
        if historical_case_ref and not any(
            item.get("ticket_id") == historical_case_ref.get("ticket_id")
            and item.get("stage") == historical_case_ref.get("stage")
            for item in merged_history
        ):
            merged_history.append(dict(historical_case_ref))

        profile.primary_email = ticket.customer_email
        alias_emails = {email for email in profile.alias_emails if email}
        alias_emails.add(ticket.customer_email)
        profile.alias_emails = sorted(alias_emails)
        profile.profile = {
            key: merged_profile.get(key, default)
            for key, default in _default_profile().items()
        }
        profile.risk_tags = sorted(merged_risk_tags)
        profile.business_flags = {
            key: bool(merged_business_flags.get(key, default))
            for key, default in _default_business_flags().items()
        }
        profile.historical_case_refs = merged_history
        if not created_profile:
            profile.version += 1

        for event in validated_updates.get("events") or []:
            self._upsert_memory_event(
                customer_id=customer_id,
                ticket=ticket,
                run=run,
                event=event,
            )
        self._session.flush()
        return profile

    def apply_stage_updates(
        self,
        *,
        ticket: Ticket,
        run: TicketRun,
        stage: MemorySourceStage,
        state: Mapping[str, Any] | None = None,
        draft_text: str | None = None,
        review_comment: str | None = None,
        target_queue: str | None = None,
    ) -> dict[str, Any] | None:
        case_context = self.collect_case_context(
            ticket=ticket,
            run=run,
            stage=stage,
            state=state,
            draft_text=draft_text,
            review_comment=review_comment,
            target_queue=target_queue,
        )
        extracted = self.extract_memory_updates(
            ticket=ticket,
            run=run,
            case_context=case_context,
        )
        validated = self.validate_memory_updates(extracted)
        self.apply_memory_updates(ticket=ticket, run=run, validated_updates=validated)
        return validated

    def _extract_profile_patch(
        self,
        ticket: Ticket,
        case_context: Mapping[str, Any],
    ) -> dict[str, Any]:
        existing_profile = (
            case_context.get("customer_profile", {}) if case_context.get("customer_profile") else {}
        )
        existing_profile_fields = dict(existing_profile.get("profile") or {})
        subject = (ticket.subject or "").lower()
        preferred_language = existing_profile_fields.get("preferred_language", "unknown")
        if preferred_language == "unknown":
            if any(token in subject for token in ("退款", "发票", "账户", "故障")):
                preferred_language = "zh-CN"
            else:
                preferred_language = "en"

        account_tier = existing_profile_fields.get("account_tier", "unknown")
        if ticket.priority in {
            TicketPriority.HIGH.value,
            TicketPriority.CRITICAL.value,
        }:
            account_tier = "priority"

        return {
            "name": existing_profile_fields.get("name", ""),
            "account_tier": account_tier,
            "preferred_language": preferred_language,
            "preferred_tone": existing_profile_fields.get("preferred_tone", "direct"),
        }

    def _extract_business_flags_patch(
        self,
        ticket: Ticket,
        case_context: Mapping[str, Any],
        stage: MemorySourceStage,
    ) -> dict[str, Any]:
        flags = _default_business_flags()
        existing_profile = case_context.get("customer_profile") or {}
        flags.update(dict(existing_profile.get("business_flags") or {}))

        if ticket.priority in {
            TicketPriority.HIGH.value,
            TicketPriority.CRITICAL.value,
        }:
            flags["high_value_customer"] = True
        if TicketTag.REFUND_REQUEST.value in (ticket.tags or []):
            flags["refund_dispute_history"] = True
        if ticket.needs_escalation or ticket.business_status in {
            TicketBusinessStatus.AWAITING_HUMAN_REVIEW.value,
            TicketBusinessStatus.ESCALATED.value,
        }:
            flags["requires_manual_approval"] = True
        if stage is MemorySourceStage.CLOSE_TICKET and ticket.business_status == TicketBusinessStatus.CLOSED.value:
            flags["requires_manual_approval"] = bool(flags["requires_manual_approval"])

        return flags

    def _extract_risk_tags(self, ticket: Ticket) -> list[str]:
        risk_tags: set[str] = set()
        if ticket.needs_escalation:
            risk_tags.add(TicketTag.NEEDS_ESCALATION.value)
        if TicketTag.REFUND_REQUEST.value in (ticket.tags or []):
            risk_tags.add("refund_dispute_history")
        if ticket.primary_route == TicketRoute.COMMERCIAL_POLICY_REQUEST.value:
            risk_tags.add("policy_sensitive_case")
        return sorted(risk_tags)

    def _extract_historical_case_ref(
        self,
        ticket: Ticket,
        case_context: Mapping[str, Any],
        stage: MemorySourceStage,
    ) -> dict[str, Any] | None:
        if stage not in {
            MemorySourceStage.AWAITING_CUSTOMER_INPUT,
            MemorySourceStage.ESCALATE_TO_HUMAN,
            MemorySourceStage.CLOSE_TICKET,
        }:
            return None

        summary_parts = [
            ticket.routing_reason or f"route={ticket.primary_route or 'unknown'}",
        ]
        if case_context.get("review_comment"):
            summary_parts.append(str(case_context["review_comment"]))
        if case_context.get("human_handoff_summary"):
            summary_parts.append(str(case_context["human_handoff_summary"]))
        if case_context.get("draft_text"):
            summary_parts.append(str(case_context["draft_text"])[:120])

        if stage is MemorySourceStage.AWAITING_CUSTOMER_INPUT:
            outcome = "awaiting_customer_input"
        elif stage is MemorySourceStage.ESCALATE_TO_HUMAN:
            outcome = "manual_review_required"
        else:
            outcome = ticket.business_status

        return {
            "ticket_id": ticket.ticket_id,
            "route": ticket.primary_route,
            "stage": stage.value,
            "summary": " | ".join(part for part in summary_parts if part),
            "outcome": outcome,
        }

    def _upsert_memory_event(
        self,
        *,
        customer_id: str,
        ticket: Ticket,
        run: TicketRun,
        event: Mapping[str, Any],
    ) -> None:
        idempotency_key = (
            f"memory:{ticket.ticket_id}:{run.run_id}:{event['source_stage']}:{event['idempotency_suffix']}"
        )
        existing = next(
            (
                item
                for item in self._repositories.customer_memory_events.list_by_customer(customer_id)
                if item.idempotency_key == idempotency_key
            ),
            None,
        )
        if existing is not None:
            return

        self._repositories.customer_memory_events.add(
            CustomerMemoryEvent(
                memory_event_id=generate_prefixed_id(EntityIdPrefix.MEMORY_EVENT),
                customer_id=customer_id,
                ticket_id=ticket.ticket_id,
                run_id=run.run_id,
                source_stage=str(event["source_stage"]),
                event_type=str(event["event_type"]),
                payload=dict(event["payload"]),
                idempotency_key=idempotency_key,
            )
        )


def memory_updates_or_raise(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        raise CoreSchemaError(
            "memory updates are unavailable because the ticket has no reliable customer_id."
        )
    return payload
