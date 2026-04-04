from __future__ import annotations

from collections.abc import Mapping

from colorama import Fore, Style

from src.triage import TriageContext

from .state import GraphState, get_active_email, set_active_email
from ..contracts.core import (
    DraftQaStatus,
    DraftType,
    MessageType,
    RunFinalAction,
    TicketBusinessStatus,
    utc_now,
)


class TicketExecutionNodesMixin:
    # Ticket execution graph nodes.
    def load_ticket_context(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Loading ticket execution context...\n" + Style.RESET_ALL)
        started_at = utc_now()
        ticket = self._require_ticket(state)
        tool_started_at = utc_now()
        inbound_context = self._require_message_log().get_thread_messages_for_drafting(
            ticket.gmail_thread_id
        )
        self._record_tool_call(
            ticket=ticket,
            node_name="load_ticket_context",
            tool_name="message_log.get_thread_messages_for_drafting",
            started_at=tool_started_at,
            input_ref=ticket.gmail_thread_id,
            output_ref=f"messages:{len(inbound_context.messages)}",
            metadata={"message_count": len(inbound_context.messages)},
        )
        latest_customer_message = inbound_context.latest_customer_message
        attachments = []
        if latest_customer_message is not None:
            attachments = list(
                (latest_customer_message.message_metadata or {}).get("attachments", [])
            )
        active_email = self._build_email_from_ticket_message(ticket, latest_customer_message)
        result = {
            **set_active_email(state, active_email),
            "ticket_id": ticket.ticket_id,
            "channel": ticket.source_channel,
            "customer_id": ticket.customer_id,
            "thread_id": ticket.gmail_thread_id,
            "business_status": ticket.business_status,
            "processing_status": ticket.processing_status,
            "ticket_version": ticket.version,
            "ticket_created_at": ticket.created_at.isoformat() if ticket.created_at else None,
            "ticket_updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
            "normalized_email": active_email.body,
            "attachments": attachments,
            "thread_summary": self._summarize_thread(inbound_context.messages),
            "current_node": "load_ticket_context",
        }
        self._record_node_event(
            ticket=ticket,
            node_name="load_ticket_context",
            started_at=started_at,
            metadata={"attachment_count": len(attachments)},
        )
        return result

    def load_memory(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Loading ticket memory...\n" + Style.RESET_ALL)
        started_at = utc_now()
        ticket = self._require_ticket(state)
        profile = None
        if ticket.customer_id:
            tool_started_at = utc_now()
            profile = self._repositories.customer_memory_profiles.get(ticket.customer_id)
            self._record_tool_call(
                ticket=ticket,
                node_name="load_memory",
                tool_name="customer_memory_profiles.get",
                started_at=tool_started_at,
                input_ref=ticket.customer_id,
                output_ref="profile:hit" if profile is not None else "profile:miss",
            )
        result = {
            "customer_profile": (
                {
                    "customer_id": profile.customer_id,
                    "profile": profile.profile,
                    "risk_tags": list(profile.risk_tags),
                    "business_flags": dict(profile.business_flags),
                }
                if profile is not None
                else None
            ),
            "historical_cases": list(profile.historical_case_refs) if profile is not None else [],
            "current_node": "load_memory",
        }
        self._record_node_event(
            ticket=ticket,
            node_name="load_memory",
            started_at=started_at,
            metadata={"has_customer_profile": profile is not None},
        )
        return result

    def triage_ticket(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Triage ticket...\n" + Style.RESET_ALL)
        started_at = utc_now()
        ticket = self._require_ticket(state)
        active_email = get_active_email(state)
        profile = state.get("customer_profile") or {}
        business_flags = profile.get("business_flags", {}) if isinstance(profile, Mapping) else {}
        llm_started_at = utc_now()
        triage_context = TriageContext(
            is_high_value_customer=bool(business_flags.get("high_value_customer", False)),
            recent_customer_replies_72h=0,
            requires_manual_approval=bool(
                business_flags.get("requires_manual_approval", False)
            ),
            qa_failure_count=max(state.get("rewrite_count", 0) - 1, 0),
            knowledge_evidence_sufficient=ticket.primary_route != "knowledge_request",
        )
        triage_method = getattr(
            self.agents,
            "triage_email_with_rules_detailed",
            getattr(self.agents, "triage_email_with_rules"),
        )
        decision = triage_method(
            subject=active_email.subject,
            email=active_email.body,
            context=triage_context,
        )
        triage_output = decision.output.model_dump(mode="json")
        selected_rule = getattr(decision, "selected_rule", "deterministic_v1")
        matched_rules = list(getattr(decision, "matched_rules", ()) or [selected_rule])
        escalation_reasons = list(getattr(decision, "escalation_reasons", ()) or [])
        llm_invocation = getattr(decision, "llm_invocation", None)
        if llm_invocation is not None:
            self._record_llm_invocation(
                ticket=ticket,
                node_name="triage",
                call_name="triage",
                started_at=llm_started_at,
                invocation=llm_invocation,
                metadata={
                    "selected_rule": selected_rule,
                    "matched_rules": matched_rules,
                },
            )
        routed = self._require_state_service().transition_business_status(
            ticket.ticket_id,
            target_status=TicketBusinessStatus.TRIAGED,
            expected_version=ticket.version,
            metadata_updates={
                "primary_route": triage_output["primary_route"],
                "secondary_routes": triage_output["secondary_routes"],
                "tags": triage_output["tags"],
                "priority": triage_output["priority"],
                "intent_confidence": triage_output["intent_confidence"],
                "response_strategy": triage_output["response_strategy"],
                "multi_intent": triage_output["multi_intent"],
                "needs_clarification": triage_output["needs_clarification"],
                "needs_escalation": triage_output["needs_escalation"],
                "routing_reason": triage_output["routing_reason"],
                "risk_reasons": escalation_reasons,
            },
            clear_error=True,
        )
        self._record_node_event(
            ticket=routed,
            node_name="triage",
            started_at=started_at,
            metadata={"selected_rule": selected_rule},
        )
        final_action = self._planned_final_action_for_route(routed)
        self._record_event(
            ticket=routed,
            event_type="decision",
            event_name="triage_result",
            node_name="triage",
            status="succeeded",
            metadata=self._build_decision_event_metadata(
                ticket=routed,
                final_action=final_action,
                include_secondary_routes=True,
            ),
        )
        decision_metadata = self._build_decision_event_metadata(
            ticket=routed,
            final_action=final_action,
        )
        for event_name in ("clarification_decision", "escalation_decision"):
            self._record_event(
                ticket=routed,
                event_type="decision",
                event_name=event_name,
                node_name="triage",
                status="succeeded",
                metadata=decision_metadata,
            )
        return {
            "ticket_version": routed.version,
            "business_status": routed.business_status,
            "processing_status": routed.processing_status,
            "primary_route": routed.primary_route,
            "secondary_routes": list(routed.secondary_routes or []),
            "tags": list(routed.tags or []),
            "response_strategy": routed.response_strategy,
            "multi_intent": routed.multi_intent,
            "intent_confidence": float(routed.intent_confidence) if routed.intent_confidence is not None else None,
            "priority": routed.priority,
            "needs_clarification": routed.needs_clarification,
            "needs_escalation": routed.needs_escalation,
            "routing_reason": routed.routing_reason,
            "escalation_reason": "; ".join(routed.risk_reasons or []) or None,
            "current_node": "triage",
        }

    def knowledge_lookup(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Knowledge lookup...\n" + Style.RESET_ALL)
        started_at = utc_now()
        ticket = self._require_ticket(state)
        route = state.get("primary_route")
        active_email = get_active_email(state)
        queries = list(state.get("queries") or [])
        if route == "knowledge_request" and not queries:
            queries = [active_email.subject or active_email.body[:120]]
        if queries and hasattr(self.knowledge_provider, "answer_questions"):
            knowledge_tool_started_at = utc_now()
            answers = self.knowledge_provider.answer_questions(queries)
            self._record_tool_call(
                ticket=ticket,
                node_name="knowledge_lookup",
                tool_name="knowledge_provider.answer_questions",
                started_at=knowledge_tool_started_at,
                input_ref=f"queries:{len(queries)}",
                output_ref=f"answers:{len(answers)}",
            )
        else:
            answers = []
        policy_tool_started_at = utc_now()
        policy_text = (
            self.policy_provider.get_policy(route)
            if hasattr(self.policy_provider, "get_policy")
            else "No additional policy constraints."
        )
        self._record_tool_call(
            ticket=ticket,
            node_name="knowledge_lookup",
            tool_name="policy_provider.get_policy",
            started_at=policy_tool_started_at,
            input_ref=str(route or "knowledge_request"),
            output_ref=f"chars:{len(policy_text)}",
        )
        llm_started_at = utc_now()
        agent_result = self.agents.knowledge_policy_agent_detailed(
            primary_route=route or "knowledge_request",
            response_strategy=state.get("response_strategy") or "answer",
            normalized_email=state.get("normalized_email") or active_email.body,
            knowledge_answers=[
                {"question": item.question, "answer": item.answer} for item in answers
            ],
            policy_notes=policy_text,
            needs_escalation=bool(state.get("needs_escalation", False)),
        )
        if agent_result.llm_invocation is not None:
            self._record_llm_invocation(
                ticket=ticket,
                node_name="knowledge_lookup",
                call_name="knowledge_policy_agent",
                started_at=llm_started_at,
                invocation=agent_result.llm_invocation,
                metadata={
                    "fallback_used": agent_result.fallback_used,
                    "guardrails_adjusted": agent_result.guardrails_adjusted,
                },
            )
        payload = agent_result.output.model_dump(mode="json")
        self._record_node_event(
            ticket=ticket,
            node_name="knowledge_lookup",
            started_at=started_at,
            metadata={
                "query_count": len(payload["queries"]),
                "logic_type": (
                    "llm_role_with_fallback"
                    if agent_result.llm_invocation is not None
                    else "deterministic_fallback"
                ),
            },
        )
        return {
            "queries": payload["queries"],
            "knowledge_summary": payload["knowledge_summary"],
            "retrieval_results": [
                {"question": item.question, "answer": item.answer} for item in answers
            ],
            "citations": payload["citations"],
            "knowledge_confidence": payload["knowledge_confidence"],
            "policy_notes": payload["policy_notes"],
            "allowed_actions": payload["allowed_actions"],
            "disallowed_actions": payload["disallowed_actions"],
            "current_node": "knowledge_lookup",
        }

    def policy_check(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Policy check...\n" + Style.RESET_ALL)
        started_at = utc_now()
        ticket = self._require_ticket(state)
        route = state.get("primary_route") or "commercial_policy_request"
        active_email = get_active_email(state)
        tool_started_at = utc_now()
        policy_text = (
            self.policy_provider.get_policy(route)
            if hasattr(self.policy_provider, "get_policy")
            else "No additional policy constraints."
        )
        self._record_tool_call(
            ticket=ticket,
            node_name="policy_check",
            tool_name="policy_provider.get_policy",
            started_at=tool_started_at,
            input_ref=str(route),
            output_ref=f"chars:{len(policy_text)}",
        )
        llm_started_at = utc_now()
        agent_result = self.agents.knowledge_policy_agent_detailed(
            primary_route=route,
            response_strategy=state.get("response_strategy") or "policy_constrained",
            normalized_email=state.get("normalized_email") or active_email.body,
            knowledge_answers=[],
            policy_notes=policy_text,
            knowledge_confidence=0.85 if not state.get("needs_escalation") else 0.55,
            needs_escalation=bool(state.get("needs_escalation", False)),
        )
        if agent_result.llm_invocation is not None:
            self._record_llm_invocation(
                ticket=ticket,
                node_name="policy_check",
                call_name="knowledge_policy_agent",
                started_at=llm_started_at,
                invocation=agent_result.llm_invocation,
                metadata={
                    "fallback_used": agent_result.fallback_used,
                    "guardrails_adjusted": agent_result.guardrails_adjusted,
                },
            )
        payload = agent_result.output.model_dump(mode="json")
        self._record_node_event(
            ticket=ticket,
            node_name="policy_check",
            started_at=started_at,
            metadata={
                "risk_level": payload["risk_level"],
                "logic_type": (
                    "llm_role_with_fallback"
                    if agent_result.llm_invocation is not None
                    else "deterministic_fallback"
                ),
            },
        )
        return {
            "knowledge_summary": payload["knowledge_summary"],
            "citations": payload["citations"],
            "knowledge_confidence": payload["knowledge_confidence"],
            "policy_notes": payload["policy_notes"],
            "allowed_actions": payload["allowed_actions"],
            "disallowed_actions": payload["disallowed_actions"],
            "current_node": "policy_check",
        }

    def customer_history_lookup(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Customer history lookup...\n" + Style.RESET_ALL)
        started_at = utc_now()
        historical_cases = list(state.get("historical_cases") or [])
        profile = state.get("customer_profile") or {}
        business_flags = profile.get("business_flags", {}) if isinstance(profile, Mapping) else {}
        if business_flags.get("refund_dispute_history"):
            historical_cases.append(
                {
                    "ticket_id": "hist_refund_dispute",
                    "summary": "Customer has refund dispute history and requires careful policy handling.",
                }
            )
        self._record_node_event(
            ticket=self._require_ticket(state),
            node_name="customer_history_lookup",
            started_at=started_at,
            metadata={"history_count": len(historical_cases)},
        )
        return {"historical_cases": historical_cases, "current_node": "customer_history_lookup"}

    def collect_case_context(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Collect case context...\n" + Style.RESET_ALL)
        started_at = utc_now()
        ticket = self._require_ticket(state)
        run = self._require_run()
        stage = self._memory_stage_for_state(state)
        case_context = self._require_memory_service().collect_case_context(
            ticket=ticket,
            run=run,
            stage=stage,
            state=state,
            draft_text=self._get_latest_draft_text(state),
        )
        self._record_node_event(
            ticket=ticket,
            node_name="collect_case_context",
            started_at=started_at,
            metadata={"stage": stage.value},
        )
        return {
            "case_context": case_context,
            "current_node": "collect_case_context",
        }

    def extract_memory_updates(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Extract memory updates...\n" + Style.RESET_ALL)
        started_at = utc_now()
        ticket = self._require_ticket(state)
        run = self._require_run()
        extracted = self._require_memory_service().extract_memory_updates(
            ticket=ticket,
            run=run,
            case_context=state.get("case_context") or {},
        )
        payload = self._require_memory_service().serialize_extraction_result(extracted)
        self._record_node_event(
            ticket=ticket,
            node_name="extract_memory_updates",
            started_at=started_at,
            metadata={
                "has_customer_id": bool(extracted.customer_id),
                "event_count": len(extracted.events),
            },
        )
        return {
            "memory_update_candidates": payload,
            "current_node": "extract_memory_updates",
        }

    def validate_memory_updates(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Validate memory updates...\n" + Style.RESET_ALL)
        started_at = utc_now()
        ticket = self._require_ticket(state)
        run = self._require_run()
        validated = self._require_memory_service().validate_memory_updates(
            state.get("memory_update_candidates") or {}
        )
        self._require_memory_service().apply_memory_updates(
            ticket=ticket,
            run=run,
            validated_updates=validated,
        )
        self._record_node_event(
            ticket=ticket,
            node_name="validate_memory_updates",
            started_at=started_at,
            metadata={
                "persisted": validated is not None,
                "event_count": len((validated or {}).get("events", [])),
            },
        )
        return {
            "memory_updates": validated,
            "current_node": "validate_memory_updates",
        }

    def draft_reply(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Draft reply...\n" + Style.RESET_ALL)
        started_at = utc_now()
        ticket = self._require_ticket(state)
        active_email = get_active_email(state)
        llm_started_at = utc_now()
        rewrite_guidance = []
        if state.get("qa_result") and state["qa_result"].get("rewrite_guidance"):
            rewrite_guidance = list(state["qa_result"]["rewrite_guidance"])

        agent_result = self.agents.drafting_agent_detailed(
            customer_email=ticket.customer_email,
            subject=active_email.subject,
            primary_route=state.get("primary_route") or "knowledge_request",
            response_strategy=state.get("response_strategy") or "answer",
            normalized_email=state.get("normalized_email") or active_email.body,
            knowledge_summary=state.get("knowledge_summary") or "",
            policy_notes=state.get("policy_notes") or "",
            rewrite_guidance=rewrite_guidance,
            allowed_actions=list(state.get("allowed_actions") or []),
            disallowed_actions=list(state.get("disallowed_actions") or []),
        )
        if agent_result.llm_invocation is not None:
            self._record_llm_invocation(
                ticket=ticket,
                node_name="draft_reply",
                call_name="drafting_agent",
                started_at=llm_started_at,
                invocation=agent_result.llm_invocation,
                metadata={
                    "fallback_used": agent_result.fallback_used,
                    "guardrails_adjusted": agent_result.guardrails_adjusted,
                },
            )
        payload = agent_result.output.model_dump(mode="json")
        draft_versions = list(state.get("draft_versions", []))
        version_index = len(draft_versions) + 1
        draft_versions.append(
            {
                "version_index": version_index,
                "draft_type": self._planned_draft_type(state),
                "content_text": payload["draft_text"],
                "rationale": payload["draft_rationale"],
            }
        )
        self._record_node_event(
            ticket=ticket,
            node_name="draft_reply",
            started_at=started_at,
            metadata={
                "version_index": version_index,
                "logic_type": (
                    "llm_role_with_fallback"
                    if agent_result.llm_invocation is not None
                    else "deterministic_fallback"
                ),
            },
        )
        return {
            "draft_versions": draft_versions,
            "rewrite_count": version_index,
            "applied_response_strategy": payload["applied_response_strategy"],
            "current_node": "draft_reply",
        }

    def qa_review(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "QA review...\n" + Style.RESET_ALL)
        started_at = utc_now()
        ticket = self._require_ticket(state)
        llm_started_at = utc_now()
        agent_result = self.agents.qa_handoff_agent_detailed(
            primary_route=state.get("primary_route") or "knowledge_request",
            draft_text=self._get_latest_draft_text(state),
            knowledge_confidence=float(state.get("knowledge_confidence") or 0.0),
            needs_escalation=bool(state.get("needs_escalation", False)),
            rewrite_count=int(state.get("rewrite_count", 0)),
            policy_notes=state.get("policy_notes", ""),
        )
        if agent_result.llm_invocation is not None:
            self._record_llm_invocation(
                ticket=ticket,
                node_name="qa_review",
                call_name="qa_handoff_agent",
                started_at=llm_started_at,
                invocation=agent_result.llm_invocation,
                metadata={
                    "fallback_used": agent_result.fallback_used,
                    "guardrails_adjusted": agent_result.guardrails_adjusted,
                },
            )
        payload = agent_result.output.model_dump(mode="json")
        self._record_node_event(
            ticket=ticket,
            node_name="qa_review",
            started_at=started_at,
            metadata={
                "approved": payload["approved"],
                "escalate": payload["escalate"],
                "logic_type": (
                    "llm_role_with_fallback"
                    if agent_result.llm_invocation is not None
                    else "deterministic_fallback"
                ),
            },
        )
        return {
            "qa_feedback": {
                "issues": payload["issues"],
                "rewrite_guidance": payload["rewrite_guidance"],
                "quality_scores": payload["quality_scores"],
                "reason": payload["reason"],
            },
            "qa_result": payload,
            "human_handoff_summary": payload["human_handoff_summary"],
            "current_node": "qa_review",
        }

    def route_ticket(self, state: GraphState) -> str:
        route = state.get("primary_route")
        secondary_routes = set(state.get("secondary_routes") or [])

        if route == "technical_issue" and state.get("needs_clarification"):
            return "clarify_request"
        if state.get("needs_escalation") and (
            route == "unrelated" or "commercial_policy_request" in secondary_routes
        ):
            return "escalate_to_human"
        if route == "commercial_policy_request" or "commercial_policy_request" in secondary_routes:
            return "policy_check"
        if route == "knowledge_request":
            return "knowledge_lookup"
        if route == "technical_issue":
            return "knowledge_lookup"
        if route == "feedback_intake":
            return "draft_reply"
        return "close_ticket"

    def route_after_knowledge(self, state: GraphState) -> str:
        if state.get("needs_escalation"):
            return "escalate_to_human"
        if state.get("primary_route") == "commercial_policy_request":
            return "customer_history_lookup"
        return "draft_reply"

    def route_after_customer_history(self, state: GraphState) -> str:
        profile = state.get("customer_profile") or {}
        business_flags = profile.get("business_flags", {}) if isinstance(profile, Mapping) else {}
        if state.get("needs_escalation") or business_flags.get("requires_manual_approval"):
            return "escalate_to_human"
        return "draft_reply"

    def route_after_qa(self, state: GraphState) -> str:
        qa_result = state.get("qa_result") or {}
        if qa_result.get("approved"):
            return "create_gmail_draft"
        if qa_result.get("escalate"):
            return "escalate_to_human"
        if int(state.get("rewrite_count", 0)) >= 3:
            return "escalate_to_human"
        return "draft_reply"

    def clarify_request(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Clarification request...\n" + Style.RESET_ALL)
        content = (
            "Please share the reproduction steps, the exact error, expected versus actual behavior, and your environment details so we can continue troubleshooting."
        )
        asked_at = utc_now().isoformat()
        result = self._finalize_with_draft(
            state,
            draft_type=DraftType.CLARIFICATION_REQUEST,
            message_type=MessageType.CLARIFICATION_REQUEST.value,
            content_text=content,
            qa_status=DraftQaStatus.PASSED,
            waiting_business_status=TicketBusinessStatus.AWAITING_CUSTOMER_INPUT,
            final_action=RunFinalAction.REQUEST_CLARIFICATION.value,
            node_name="clarify_request",
        )
        result["clarification_history"] = [
            *state.get("clarification_history", []),
            {
                "question": content,
                "asked_at": asked_at,
                "source": "clarify_request",
            },
        ]
        return result

    def create_gmail_draft(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Create Gmail draft...\n" + Style.RESET_ALL)
        return self._finalize_with_draft(
            state,
            draft_type=DraftType.REPLY,
            message_type=MessageType.REPLY_DRAFT.value,
            content_text=self._get_latest_draft_text(state),
            qa_status=DraftQaStatus.PASSED,
            completed_business_status=TicketBusinessStatus.DRAFT_CREATED,
            final_action=RunFinalAction.CREATE_DRAFT.value,
            node_name="create_gmail_draft",
        )

    def escalate_to_human(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Escalate to human...\n" + Style.RESET_ALL)
        started_at = utc_now()
        ticket = self._require_ticket(state)
        current_ticket = self._require_state_service().mark_waiting_external(
            ticket.ticket_id,
            worker_id=self._require_worker_id(),
            run_id=self._require_run().run_id,
            business_status=TicketBusinessStatus.AWAITING_HUMAN_REVIEW,
            expected_version=ticket.version,
            metadata_updates={"risk_reasons": list(ticket.risk_reasons or [])},
        )
        self._record_node_event(
            ticket=current_ticket,
            node_name="escalate_to_human",
            started_at=started_at,
            metadata={"risk_reason_count": len(current_ticket.risk_reasons or [])},
        )
        self._record_event(
            ticket=current_ticket,
            event_type="decision",
            event_name="escalation_decision",
            node_name="escalate_to_human",
            status="succeeded",
            metadata=self._build_decision_event_metadata(
                ticket=current_ticket,
                final_action=RunFinalAction.HANDOFF_TO_HUMAN.value,
                needs_escalation=True,
            ),
        )
        return {
            "ticket_version": current_ticket.version,
            "business_status": current_ticket.business_status,
            "processing_status": current_ticket.processing_status,
            "final_action": RunFinalAction.HANDOFF_TO_HUMAN.value,
            "approval_status": "awaiting_human_review",
            "current_node": "escalate_to_human",
        }

    def close_ticket(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Close ticket...\n" + Style.RESET_ALL)
        content = (
            self._get_latest_draft_text(state)
            or "We received your message, but it does not appear to match the supported customer support scope for this workflow."
        )
        return self._finalize_with_draft(
            state,
            draft_type=DraftType.LIGHTWEIGHT_TEMPLATE,
            message_type=MessageType.REPLY_DRAFT.value,
            content_text=content,
            qa_status=DraftQaStatus.PASSED,
            completed_business_status=TicketBusinessStatus.DRAFT_CREATED,
            final_action=RunFinalAction.SKIP_UNRELATED.value,
            node_name="close_ticket",
        )

    def _get_latest_draft_text(self, state: GraphState) -> str:
        draft_versions = list(state.get("draft_versions") or [])
        if not draft_versions:
            return ""
        latest = draft_versions[-1]
        return str(latest.get("content_text") or "")


from .nodes_base import BaseNodes


class TicketNodes(TicketExecutionNodesMixin, BaseNodes):
    pass



