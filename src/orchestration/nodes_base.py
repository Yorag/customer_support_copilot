from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..config import get_settings
from ..contracts.core import (
    DraftQaStatus,
    DraftType,
    EntityIdPrefix,
    MemorySourceStage,
    MessageType,
    RunFinalAction,
    TicketBusinessStatus,
    generate_prefixed_id,
    utc_now,
)
from ..db.models import DraftArtifact, Ticket, TicketRun, TraceEvent
from ..memory import CustomerMemoryService
from ..tickets.message_log import DraftMessagePayload, MessageLogService
from src.llm.runtime import LlmInvocationResult, normalize_usage_payload
from ..telemetry import TraceRecorder
from .state import Email, GraphState, get_active_email
from ..tickets.state_machine import TicketStateService
from ..bootstrap.container import get_service_container


class BaseNodes:
    def __init__(
        self,
        agents=None,
        service_container=None,
        *,
        session=None,
        repositories=None,
        state_service: TicketStateService | None = None,
        message_log: MessageLogService | None = None,
        run: TicketRun | None = None,
        worker_id: str | None = None,
        trace_recorder: TraceRecorder | None = None,
    ):
        self.services = service_container or get_service_container()
        self.agents = agents or self.services.agents
        self.gmail_client = self.services.gmail_client
        self.knowledge_provider = self.services.knowledge_provider
        self.policy_provider = self.services.policy_provider
        self.ticket_store = self.services.ticket_store
        self._session = session
        self._repositories = repositories
        self._state_service = state_service
        self._message_log = message_log
        self._run = run
        self._worker_id = worker_id
        self._trace_recorder = trace_recorder
        self._memory_service = (
            CustomerMemoryService(
                session,
                repositories=repositories,
                extractor=getattr(self.services, "memory_extractor", None),
            )
            if session is not None and repositories is not None
            else None
        )
        self._chat_model_name = get_settings().llm.chat_model
        self._chat_provider = "openai-compatible"

    def _build_decision_event_metadata(
        self,
        *,
        ticket: Ticket,
        final_action: str,
        include_secondary_routes: bool = False,
        needs_escalation: bool | None = None,
    ) -> dict[str, Any]:
        metadata = {
            "primary_route": ticket.primary_route,
            "response_strategy": ticket.response_strategy,
            "needs_clarification": ticket.needs_clarification,
            "needs_escalation": (
                ticket.needs_escalation
                if needs_escalation is None
                else needs_escalation
            ),
            "final_action": final_action,
        }
        if include_secondary_routes:
            metadata["secondary_routes"] = list(ticket.secondary_routes or [])
        return metadata

    def _finalize_with_draft(
        self,
        state: GraphState,
        *,
        draft_type: DraftType,
        message_type: str,
        content_text: str,
        qa_status: DraftQaStatus,
        final_action: str,
        node_name: str,
        completed_business_status: TicketBusinessStatus | None = None,
        waiting_business_status: TicketBusinessStatus | None = None,
    ) -> GraphState:
        started_at = utc_now()
        ticket = self._require_ticket(state)
        run = self._require_run()
        next_version_index = self._next_draft_version_index(ticket.ticket_id)
        existing = self._require_state_service().ensure_draft_idempotency(
            ticket_id=ticket.ticket_id,
            draft_type=draft_type,
            version_index=next_version_index,
        )
        draft = existing or self._create_draft_artifact(
            ticket=ticket,
            run=run,
            draft_type=draft_type,
            content_text=content_text,
            qa_status=qa_status,
            version_index=next_version_index,
        )
        active_email = get_active_email(state)
        gmail_draft_id = draft.gmail_draft_id
        if existing is not None and gmail_draft_id:
            gmail_result = {"id": gmail_draft_id}
        elif hasattr(self.gmail_client, "create_draft_reply"):
            tool_started_at = utc_now()
            gmail_result = self.gmail_client.create_draft_reply(
                active_email,
                content_text,
            )
            self._record_tool_call(
                ticket=ticket,
                node_name=node_name,
                tool_name="gmail_client.create_draft_reply",
                started_at=tool_started_at,
                input_ref=active_email.messageId,
                output_ref=str(gmail_result),
            )
        else:
            gmail_result = {"id": f"gmail-draft-{draft.version_index}"}
        gmail_draft_id = self._extract_gmail_draft_id(gmail_result, gmail_draft_id)
        if gmail_draft_id and draft.gmail_draft_id != gmail_draft_id:
            draft.gmail_draft_id = gmail_draft_id
        self._require_message_log().create_draft_message_log(
            DraftMessagePayload(
                ticket_id=ticket.ticket_id,
                run_id=run.run_id,
                draft_id=draft.draft_id,
                source_thread_id=ticket.source_thread_id,
                source_message_id=f"{run.run_id}:{draft.version_index}:{message_type}",
                gmail_thread_id=ticket.gmail_thread_id,
                message_type=message_type,
                sender_email="support@example.com",
                recipient_emails=[ticket.customer_email],
                subject=active_email.subject,
                body_text=content_text,
                body_html=None,
                message_timestamp=utc_now(),
                reply_to_source_message_id=ticket.source_message_id,
            )
        )
        if waiting_business_status is not None:
            updated_ticket = self._require_state_service().mark_waiting_external(
                ticket.ticket_id,
                worker_id=self._require_worker_id(),
                run_id=run.run_id,
                business_status=waiting_business_status,
                expected_version=ticket.version,
                metadata_updates={"gmail_draft_id": gmail_draft_id},
            )
        else:
            updated_ticket = self._require_state_service().complete_run(
                ticket.ticket_id,
                worker_id=self._require_worker_id(),
                run_id=run.run_id,
                business_status=completed_business_status or TicketBusinessStatus.DRAFT_CREATED,
                expected_version=ticket.version,
                metadata_updates={"gmail_draft_id": gmail_draft_id},
            )
        self._record_node_event(
            ticket=updated_ticket,
            node_name=node_name,
            started_at=started_at,
            metadata={
                "draft_type": draft_type.value,
                "version_index": draft.version_index,
                "gmail_draft_id": gmail_draft_id,
            },
        )
        self._record_event(
            ticket=updated_ticket,
            event_type="decision",
            event_name="final_action",
            node_name=node_name,
            status="succeeded",
            metadata=self._build_decision_event_metadata(
                ticket=updated_ticket,
                final_action=final_action,
            ),
        )
        return {
            "ticket_version": updated_ticket.version,
            "business_status": updated_ticket.business_status,
            "processing_status": updated_ticket.processing_status,
            "side_effect_records": {
                **state.get("side_effect_records", {}),
                "gmail_draft_id": gmail_draft_id,
                "draft_id": draft.draft_id,
            },
            "final_action": final_action,
            "approval_status": (
                "awaiting_customer_input"
                if waiting_business_status is TicketBusinessStatus.AWAITING_CUSTOMER_INPUT
                else "draft_created"
            ),
            "current_node": node_name,
        }

    def _create_draft_artifact(
        self,
        *,
        ticket: Ticket,
        run: TicketRun,
        draft_type: DraftType,
        content_text: str,
        qa_status: DraftQaStatus,
        version_index: int,
    ) -> DraftArtifact:
        draft = DraftArtifact(
            draft_id=generate_prefixed_id(EntityIdPrefix.DRAFT),
            ticket_id=ticket.ticket_id,
            run_id=run.run_id,
            version_index=version_index,
            draft_type=draft_type.value,
            content_text=content_text,
            qa_status=qa_status.value,
            gmail_draft_id=None,
            idempotency_key=self._require_state_service().build_draft_idempotency_key(
                ticket_id=ticket.ticket_id,
                draft_type=draft_type,
                version_index=version_index,
            ),
            source_evidence_summary=(
                f"route={ticket.primary_route}; strategy={ticket.response_strategy}"
            ),
        )
        self._repositories.draft_artifacts.add(draft)
        self._session.flush()
        return draft

    def _record_event(
        self,
        *,
        ticket: Ticket,
        event_type: str,
        event_name: str,
        node_name: str | None,
        status: str,
        metadata: dict[str, Any] | None = None,
        start_time=None,
        end_time=None,
    ) -> None:
        if self._repositories is None or self._run is None:
            return
        current_start = start_time or utc_now()
        current_end = end_time or current_start
        if self._trace_recorder is not None:
            self._trace_recorder.record_event(
                run=self._run,
                ticket=ticket,
                event_type=event_type,
                event_name=event_name,
                node_name=node_name,
                start_time=current_start,
                end_time=current_end,
                status=status,
                metadata=metadata,
            )
            return
        event = TraceEvent(
            event_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trace_id=self._run.trace_id,
            run_id=self._run.run_id,
            ticket_id=ticket.ticket_id,
            event_type=event_type,
            event_name=event_name,
            node_name=node_name,
            start_time=current_start,
            end_time=current_end,
            latency_ms=0,
            status=status,
            event_metadata=metadata,
        )
        self._repositories.trace_events.add(event)

    def _record_node_event(
        self,
        *,
        ticket: Ticket,
        node_name: str,
        started_at,
        metadata: dict[str, Any] | None = None,
        status: str = "succeeded",
    ) -> None:
        self._record_event(
            ticket=ticket,
            event_type="node",
            event_name=node_name,
            node_name=node_name,
            status=status,
            metadata=metadata,
            start_time=started_at,
            end_time=utc_now(),
        )

    def _record_tool_call(
        self,
        *,
        ticket: Ticket,
        node_name: str,
        tool_name: str,
        started_at,
        input_ref: str,
        output_ref: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "tool_name": tool_name,
            "input_ref": input_ref,
            "output_ref": output_ref,
            **(metadata or {}),
        }
        self._record_event(
            ticket=ticket,
            event_type="tool_call",
            event_name=f"tool.{tool_name}",
            node_name=node_name,
            status="succeeded",
            metadata=payload,
            start_time=started_at,
            end_time=utc_now(),
        )

    def _record_llm_invocation(
        self,
        *,
        ticket: Ticket,
        node_name: str,
        call_name: str,
        started_at,
        invocation: LlmInvocationResult,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._record_event(
            ticket=ticket,
            event_type="llm_call",
            event_name=f"llm.{call_name}",
            node_name=node_name,
            status="succeeded",
            metadata={
                "model": invocation.model,
                "provider": invocation.provider,
                **normalize_usage_payload(invocation.usage),
                "request_id": invocation.request_id,
                "finish_reason": invocation.finish_reason,
                **(metadata or {}),
            },
            start_time=started_at,
            end_time=utc_now(),
        )

    def _require_component(self, value: Any, error_message: str):
        if value is None:
            raise RuntimeError(error_message)
        return value

    def _require_ticket(self, state: GraphState) -> Ticket:
        repositories = self._require_component(
            self._repositories,
            "Ticket execution nodes require repositories.",
        )
        ticket_id = state.get("ticket_id")
        if not ticket_id:
            raise RuntimeError("GraphState missing ticket_id.")
        ticket = repositories.tickets.get(ticket_id)
        if ticket is None:
            raise RuntimeError(f"Ticket `{ticket_id}` not found.")
        return ticket

    def _require_run(self) -> TicketRun:
        return self._require_component(
            self._run,
            "Ticket execution nodes require an active run.",
        )

    def _require_state_service(self) -> TicketStateService:
        return self._require_component(
            self._state_service,
            "Ticket execution nodes require TicketStateService.",
        )

    def _require_message_log(self) -> MessageLogService:
        return self._require_component(
            self._message_log,
            "Ticket execution nodes require MessageLogService.",
        )

    def _require_worker_id(self) -> str:
        if not self._worker_id:
            raise RuntimeError("Ticket execution nodes require worker_id.")
        return self._worker_id

    def _require_memory_service(self) -> CustomerMemoryService:
        return self._require_component(
            self._memory_service,
            "Ticket execution nodes require CustomerMemoryService.",
        )

    def _next_draft_version_index(self, ticket_id: str) -> int:
        drafts = self._repositories.draft_artifacts.list_by_ticket(ticket_id)
        if not drafts:
            return 1
        return max(draft.version_index for draft in drafts) + 1

    def _extract_gmail_draft_id(self, result: Any, fallback: str | None = None) -> str | None:
        if isinstance(result, Mapping):
            draft_id = result.get("id")
            if draft_id is not None:
                return str(draft_id)
            message = result.get("message")
            if isinstance(message, Mapping):
                draft_id = message.get("id")
                if draft_id is not None:
                    return str(draft_id)
        return fallback

    def _build_email_from_ticket_message(self, ticket: Ticket, latest_customer_message) -> Email:
        if latest_customer_message is None:
            return Email(
                id=ticket.source_message_id,
                threadId=ticket.gmail_thread_id,
                messageId=ticket.source_message_id,
                references="",
                sender=ticket.customer_email_raw,
                subject=ticket.subject,
                body=ticket.latest_message_excerpt or "",
            )
        metadata = latest_customer_message.message_metadata or {}
        return Email(
            id=latest_customer_message.source_message_id or latest_customer_message.ticket_message_id,
            threadId=latest_customer_message.gmail_thread_id,
            messageId=latest_customer_message.source_message_id or "",
            references=str(metadata.get("references", latest_customer_message.reply_to_source_message_id or "")),
            sender=metadata.get("sender_email_raw")
            or latest_customer_message.sender_email
            or ticket.customer_email_raw,
            subject=latest_customer_message.subject or ticket.subject,
            body=latest_customer_message.body_text or ticket.latest_message_excerpt or "",
        )

    def _summarize_thread(self, messages) -> str | None:
        if not messages:
            return None
        lines = []
        for message in messages[-4:]:
            text = (message.body_text or "").strip()
            if not text:
                continue
            prefix = "customer" if message.direction == "inbound" else "system"
            lines.append(f"{prefix}: {text[:120]}")
        return "\n".join(lines) or None

    def _planned_draft_type(self, state: GraphState) -> str:
        if state.get("needs_clarification"):
            return DraftType.CLARIFICATION_REQUEST.value
        if state.get("primary_route") == "unrelated":
            return DraftType.LIGHTWEIGHT_TEMPLATE.value
        return DraftType.REPLY.value

    def _planned_final_action_for_route(self, ticket: Ticket) -> str:
        if ticket.needs_clarification:
            return RunFinalAction.REQUEST_CLARIFICATION.value
        if ticket.needs_escalation:
            return RunFinalAction.HANDOFF_TO_HUMAN.value
        if ticket.primary_route == "unrelated":
            return RunFinalAction.SKIP_UNRELATED.value
        return RunFinalAction.CREATE_DRAFT.value

    def _memory_stage_for_state(self, state: GraphState) -> MemorySourceStage:
        final_action = state.get("final_action")
        business_status = state.get("business_status")
        if self._matches_memory_stage(
            final_action=final_action,
            business_status=business_status,
            target_action=RunFinalAction.REQUEST_CLARIFICATION.value,
            target_status=TicketBusinessStatus.AWAITING_CUSTOMER_INPUT.value,
        ):
            return MemorySourceStage.AWAITING_CUSTOMER_INPUT
        if self._matches_memory_stage(
            final_action=final_action,
            business_status=business_status,
            target_action=RunFinalAction.HANDOFF_TO_HUMAN.value,
            target_status=TicketBusinessStatus.AWAITING_HUMAN_REVIEW.value,
        ):
            return MemorySourceStage.ESCALATE_TO_HUMAN
        return MemorySourceStage.CLOSE_TICKET

    def _matches_memory_stage(
        self,
        *,
        final_action: Any,
        business_status: Any,
        target_action: str,
        target_status: str,
    ) -> bool:
        return final_action == target_action or business_status == target_status


