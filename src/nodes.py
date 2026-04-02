from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from colorama import Fore, Style

from .core_schema import (
    DraftQaStatus,
    DraftType,
    EntityIdPrefix,
    MessageType,
    RunFinalAction,
    TicketBusinessStatus,
    generate_prefixed_id,
    utc_now,
)
from .db.models import DraftArtifact, Ticket, TicketRun, TraceEvent
from .message_log import DraftMessagePayload, MessageLogService
from .state import (
    GraphState,
    Email,
    get_active_email,
    pop_pending_email,
    set_active_email,
)
from .ticket_state_machine import TicketStateService
from .tools.service_container import get_service_container
from .triage import TriageContext


class Nodes:
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
    ):
        if agents is None:
            from .agents import Agents

            agents = Agents()

        self.agents = agents
        self.services = service_container or get_service_container()
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

    # Transitional tutorial-flow nodes kept for compatibility with pre-X1 callers.
    def load_new_emails(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Loading new emails...\n" + Style.RESET_ALL)
        recent_emails = self.gmail_client.fetch_unanswered_emails()
        emails = [Email(**email) for email in recent_emails]
        active_email = emails[-1] if emails else None
        updates: GraphState = {
            "pending_emails": emails,
            "emails": list(emails),
        }
        updates.update(set_active_email(state, active_email))
        return updates

    def check_new_emails(self, state: GraphState) -> str:
        pending_emails = state.get("pending_emails") or state.get("emails", [])
        if len(pending_emails) == 0:
            print(Fore.RED + "No new emails" + Style.RESET_ALL)
            return "empty"
        print(Fore.GREEN + "New emails to process" + Style.RESET_ALL)
        return "process"

    def is_email_inbox_empty(self, state: GraphState) -> GraphState:
        return state

    def categorize_email(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Checking email category...\n" + Style.RESET_ALL)
        current_email = get_active_email(state)
        result = self.agents.categorize_email.invoke({"email": current_email.body})
        print(Fore.MAGENTA + f"Email category: {result.category.value}" + Style.RESET_ALL)
        return {
            "email_category": result.category.value,
            "normalized_email": current_email.body,
            **set_active_email(state, current_email),
        }

    def triage_email(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Running structured triage...\n" + Style.RESET_ALL)
        current_email = get_active_email(state)
        decision = self.agents.triage_email_with_rules(
            subject=current_email.subject,
            email=current_email.body,
            context=TriageContext(),
        )
        triage_output = decision.output.model_dump(mode="json")
        print(
            Fore.MAGENTA
            + f"Triage route: {triage_output['primary_route']}"
            + Style.RESET_ALL
        )
        return {
            **set_active_email(state, current_email),
            "normalized_email": current_email.body,
            "triage_result": triage_output,
            "primary_route": triage_output["primary_route"],
            "secondary_routes": triage_output["secondary_routes"],
            "tags": triage_output["tags"],
            "response_strategy": triage_output["response_strategy"],
            "multi_intent": triage_output["multi_intent"],
            "intent_confidence": triage_output["intent_confidence"],
            "priority": triage_output["priority"],
            "needs_clarification": triage_output["needs_clarification"],
            "needs_escalation": triage_output["needs_escalation"],
            "routing_reason": triage_output["routing_reason"],
            "email_category": self._map_route_to_legacy_category(
                triage_output["primary_route"]
            ),
        }

    def route_email_based_on_category(self, state: GraphState) -> str:
        print(Fore.YELLOW + "Routing email based on category...\n" + Style.RESET_ALL)
        category = state["email_category"]
        if category == "product_enquiry":
            return "product related"
        if category == "unrelated":
            return "unrelated"
        return "not product related"

    def route_email_based_on_triage(self, state: GraphState) -> str:
        print(Fore.YELLOW + "Routing email based on triage...\n" + Style.RESET_ALL)
        primary_route = state.get("primary_route") or state["triage_result"]["primary_route"]
        if primary_route == "knowledge_request":
            return "product related"
        if primary_route == "unrelated":
            return "unrelated"
        return "not product related"

    def construct_rag_queries(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Designing RAG query...\n" + Style.RESET_ALL)
        email_content = get_active_email(state).body
        query_result = self.agents.design_rag_queries.invoke({"email": email_content})
        return {"rag_queries": query_result.queries, "queries": query_result.queries}

    def retrieve_from_rag(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Retrieving information from internal knowledge...\n" + Style.RESET_ALL)
        answers = self.knowledge_provider.answer_questions(state["rag_queries"])
        final_answer = "\n\n".join(
            f"{item.question}\n{item.answer}" for item in answers
        )
        return {
            "retrieved_documents": final_answer,
            "knowledge_summary": final_answer,
            "retrieval_results": [
                {"question": item.question, "answer": item.answer} for item in answers
            ],
        }

    def write_draft_email(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Writing draft email...\n" + Style.RESET_ALL)
        inputs = (
            f'# **EMAIL CATEGORY:** {state["email_category"]}\n\n'
            f'# **EMAIL CONTENT:**\n{get_active_email(state).body}\n\n'
            f'# **POLICY GUIDANCE:**\n{self.policy_provider.get_policy(state["email_category"])}\n\n'
            f'# **INFORMATION:**\n{state["retrieved_documents"]}'
        )
        writer_messages = state.get("writer_messages", [])
        draft_result = self.agents.email_writer.invoke(
            {"email_information": inputs, "history": writer_messages}
        )
        email = draft_result.email
        trials = state.get("trials", 0) + 1
        writer_messages.append(f"**Draft {trials}:**\n{email}")
        draft_versions = list(state.get("draft_versions", []))
        draft_versions.append(
            {
                "version_index": trials,
                "content_text": email,
                "draft_type": "reply",
            }
        )
        return {
            "generated_email": email,
            "trials": trials,
            "rewrite_count": trials,
            "writer_messages": writer_messages,
            "draft_versions": draft_versions,
        }

    def verify_generated_email(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Verifying generated email...\n" + Style.RESET_ALL)
        review = self.agents.email_proofreader.invoke(
            {
                "initial_email": get_active_email(state).body,
                "generated_email": state["generated_email"],
            }
        )
        writer_messages = state.get("writer_messages", [])
        writer_messages.append(f"**Proofreader Feedback:**\n{review.feedback}")
        return {
            "sendable": review.send,
            "writer_messages": writer_messages,
            "qa_feedback": {"feedback": review.feedback, "sendable": review.send},
        }

    def must_rewrite(self, state: GraphState) -> str:
        if state["sendable"]:
            print(Fore.GREEN + "Email is good, ready to be sent!!!" + Style.RESET_ALL)
            pop_pending_email(state)
            state["emails"] = list(state.get("pending_emails", []))
            state.update(
                set_active_email(
                    state,
                    state.get("pending_emails", [None])[-1]
                    if state.get("pending_emails")
                    else None,
                )
            )
            state["writer_messages"] = []
            return "send"
        if state["trials"] >= 3:
            print(Fore.RED + "Email is not good, we reached max trials must stop!!!" + Style.RESET_ALL)
            pop_pending_email(state)
            state["emails"] = list(state.get("pending_emails", []))
            state.update(
                set_active_email(
                    state,
                    state.get("pending_emails", [None])[-1]
                    if state.get("pending_emails")
                    else None,
                )
            )
            state["writer_messages"] = []
            return "stop"
        print(Fore.RED + "Email is not good, must rewrite it..." + Style.RESET_ALL)
        return "rewrite"

    def create_draft_response(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Creating draft email...\n" + Style.RESET_ALL)
        self.gmail_client.create_draft_reply(get_active_email(state), state["generated_email"])
        return {
            "retrieved_documents": "",
            "knowledge_summary": "",
            "trials": 0,
            "rewrite_count": 0,
            "applied_response_strategy": state.get("response_strategy"),
        }

    def send_email_response(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Sending email...\n" + Style.RESET_ALL)
        self.gmail_client.send_reply(get_active_email(state), state["generated_email"])
        return {"retrieved_documents": "", "knowledge_summary": "", "trials": 0}

    def skip_unrelated_email(self, state):
        print("Skipping unrelated email...\n")
        pop_pending_email(state)
        state["emails"] = list(state.get("pending_emails", []))
        state.update(
            set_active_email(
                state,
                state.get("pending_emails", [None])[-1]
                if state.get("pending_emails")
                else None,
            )
        )
        return state

    # Ticket execution graph nodes.
    def load_ticket_context(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Loading ticket execution context...\n" + Style.RESET_ALL)
        ticket = self._require_ticket(state)
        inbound_context = self._require_message_log().get_thread_messages_for_drafting(
            ticket.gmail_thread_id
        )
        latest_customer_message = inbound_context.latest_customer_message
        attachments = []
        if latest_customer_message is not None:
            attachments = list(
                (latest_customer_message.message_metadata or {}).get("attachments", [])
            )
        active_email = self._build_email_from_ticket_message(ticket, latest_customer_message)
        return {
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

    def load_memory(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Loading ticket memory...\n" + Style.RESET_ALL)
        ticket = self._require_ticket(state)
        profile = None
        if ticket.customer_id:
            profile = self._repositories.customer_memory_profiles.get(ticket.customer_id)
        return {
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

    def triage_ticket(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Triage ticket...\n" + Style.RESET_ALL)
        ticket = self._require_ticket(state)
        active_email = get_active_email(state)
        profile = state.get("customer_profile") or {}
        business_flags = profile.get("business_flags", {}) if isinstance(profile, Mapping) else {}
        decision = self.agents.triage_email_with_rules(
            subject=active_email.subject,
            email=active_email.body,
            context=TriageContext(
                is_high_value_customer=bool(business_flags.get("high_value_customer", False)),
                recent_customer_replies_72h=0,
                requires_manual_approval=bool(
                    business_flags.get("requires_manual_approval", False)
                ),
                qa_failure_count=max(state.get("rewrite_count", 0) - 1, 0),
                knowledge_evidence_sufficient=ticket.primary_route != "knowledge_request",
            ),
        )
        triage_output = decision.output.model_dump(mode="json")
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
                "risk_reasons": list(decision.escalation_reasons),
            },
            clear_error=True,
        )
        self._record_event(
            ticket=routed,
            event_type="decision",
            event_name="triage_result",
            node_name="triage",
            status="succeeded",
            metadata={
                "primary_route": routed.primary_route,
                "secondary_routes": list(routed.secondary_routes or []),
                "response_strategy": routed.response_strategy,
                "needs_clarification": routed.needs_clarification,
                "needs_escalation": routed.needs_escalation,
                "final_action": self._planned_final_action_for_route(routed),
            },
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
            "triage_result": triage_output,
            "current_node": "triage",
        }

    def knowledge_lookup(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Knowledge lookup...\n" + Style.RESET_ALL)
        route = state.get("primary_route")
        active_email = get_active_email(state)
        queries = list(state.get("queries") or [])
        if route == "knowledge_request" and not queries:
            queries = [active_email.subject or active_email.body[:120]]
        if queries and hasattr(self.knowledge_provider, "answer_questions"):
            answers = self.knowledge_provider.answer_questions(queries)
        else:
            answers = []
        policy_text = (
            self.policy_provider.get_policy(route)
            if hasattr(self.policy_provider, "get_policy")
            else "No additional policy constraints."
        )
        result = self.agents.knowledge_policy_agent(
            primary_route=route or "knowledge_request",
            response_strategy=state.get("response_strategy") or "answer",
            normalized_email=state.get("normalized_email") or active_email.body,
            knowledge_answers=[
                {"question": item.question, "answer": item.answer} for item in answers
            ],
            policy_notes=policy_text,
            needs_escalation=bool(state.get("needs_escalation", False)),
        )
        payload = result.model_dump(mode="json")
        self._record_event(
            ticket=self._require_ticket(state),
            event_type="node",
            event_name="knowledge_lookup",
            node_name="knowledge_lookup",
            status="succeeded",
            metadata={"query_count": len(payload["queries"])},
        )
        return {
            "queries": payload["queries"],
            "rag_queries": payload["queries"],
            "knowledge_summary": payload["knowledge_summary"],
            "retrieved_documents": payload["knowledge_summary"],
            "retrieval_results": [
                {"question": item.question, "answer": item.answer} for item in answers
            ],
            "citations": payload["citations"],
            "knowledge_confidence": payload["knowledge_confidence"],
            "policy_notes": payload["policy_notes"],
            "allowed_actions": payload["allowed_actions"],
            "disallowed_actions": payload["disallowed_actions"],
            "knowledge_policy_result": payload,
            "current_node": "knowledge_lookup",
        }

    def policy_check(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Policy check...\n" + Style.RESET_ALL)
        route = state.get("primary_route") or "commercial_policy_request"
        active_email = get_active_email(state)
        policy_text = (
            self.policy_provider.get_policy(route)
            if hasattr(self.policy_provider, "get_policy")
            else "No additional policy constraints."
        )
        result = self.agents.knowledge_policy_agent(
            primary_route=route,
            response_strategy=state.get("response_strategy") or "policy_constrained",
            normalized_email=state.get("normalized_email") or active_email.body,
            knowledge_answers=[],
            policy_notes=policy_text,
            knowledge_confidence=0.85 if not state.get("needs_escalation") else 0.55,
            needs_escalation=bool(state.get("needs_escalation", False)),
        )
        payload = result.model_dump(mode="json")
        self._record_event(
            ticket=self._require_ticket(state),
            event_type="node",
            event_name="policy_check",
            node_name="policy_check",
            status="succeeded",
            metadata={"risk_level": payload["risk_level"]},
        )
        return {
            "knowledge_summary": payload["knowledge_summary"],
            "retrieved_documents": payload["knowledge_summary"],
            "citations": payload["citations"],
            "knowledge_confidence": payload["knowledge_confidence"],
            "policy_notes": payload["policy_notes"],
            "allowed_actions": payload["allowed_actions"],
            "disallowed_actions": payload["disallowed_actions"],
            "knowledge_policy_result": payload,
            "current_node": "policy_check",
        }

    def customer_history_lookup(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Customer history lookup...\n" + Style.RESET_ALL)
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
        self._record_event(
            ticket=self._require_ticket(state),
            event_type="node",
            event_name="customer_history_lookup",
            node_name="customer_history_lookup",
            status="succeeded",
            metadata={"history_count": len(historical_cases)},
        )
        return {"historical_cases": historical_cases, "current_node": "customer_history_lookup"}

    def draft_reply(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Draft reply...\n" + Style.RESET_ALL)
        ticket = self._require_ticket(state)
        active_email = get_active_email(state)
        rewrite_guidance = []
        if state.get("qa_result") and state["qa_result"].get("rewrite_guidance"):
            rewrite_guidance = list(state["qa_result"]["rewrite_guidance"])

        result = self.agents.drafting_agent(
            customer_email=ticket.customer_email,
            subject=active_email.subject,
            primary_route=state.get("primary_route") or "knowledge_request",
            response_strategy=state.get("response_strategy") or "answer",
            normalized_email=state.get("normalized_email") or active_email.body,
            knowledge_summary=state.get("knowledge_summary") or "",
            policy_notes=state.get("policy_notes") or "",
            rewrite_guidance=rewrite_guidance,
        )
        payload = result.model_dump(mode="json")
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
        self._record_event(
            ticket=ticket,
            event_type="node",
            event_name="draft_reply",
            node_name="draft_reply",
            status="succeeded",
            metadata={"version_index": version_index},
        )
        return {
            "generated_email": payload["draft_text"],
            "draft_versions": draft_versions,
            "rewrite_count": version_index,
            "trials": version_index,
            "applied_response_strategy": payload["applied_response_strategy"],
            "current_node": "draft_reply",
        }

    def qa_review(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "QA review...\n" + Style.RESET_ALL)
        result = self.agents.qa_handoff_agent(
            primary_route=state.get("primary_route") or "knowledge_request",
            draft_text=state.get("generated_email", ""),
            knowledge_confidence=float(state.get("knowledge_confidence") or 0.0),
            needs_escalation=bool(state.get("needs_escalation", False)),
            rewrite_count=int(state.get("rewrite_count", 0)),
            policy_notes=state.get("policy_notes", ""),
        )
        payload = result.model_dump(mode="json")
        self._record_event(
            ticket=self._require_ticket(state),
            event_type="node",
            event_name="qa_review",
            node_name="qa_review",
            status="succeeded",
            metadata={
                "approved": payload["approved"],
                "escalate": payload["escalate"],
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
        if route == "knowledge_request":
            return "knowledge_lookup"
        if route == "technical_issue":
            if state.get("needs_clarification"):
                return "clarify_request"
            return "knowledge_lookup"
        if route == "commercial_policy_request":
            return "policy_check"
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
        return self._finalize_with_draft(
            state,
            draft_type=DraftType.CLARIFICATION_REQUEST,
            message_type=MessageType.CLARIFICATION_REQUEST.value,
            content_text=content,
            qa_status=DraftQaStatus.PASSED,
            waiting_business_status=TicketBusinessStatus.AWAITING_CUSTOMER_INPUT,
            final_action=RunFinalAction.REQUEST_CLARIFICATION.value,
            node_name="clarify_request",
        )

    def create_gmail_draft(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Create Gmail draft...\n" + Style.RESET_ALL)
        return self._finalize_with_draft(
            state,
            draft_type=DraftType.REPLY,
            message_type=MessageType.REPLY_DRAFT.value,
            content_text=state["generated_email"],
            qa_status=DraftQaStatus.PASSED,
            completed_business_status=TicketBusinessStatus.DRAFT_CREATED,
            final_action=RunFinalAction.CREATE_DRAFT.value,
            node_name="create_gmail_draft",
        )

    def escalate_to_human(self, state: GraphState) -> GraphState:
        print(Fore.YELLOW + "Escalate to human...\n" + Style.RESET_ALL)
        ticket = self._require_ticket(state)
        current_ticket = self._require_state_service().mark_waiting_external(
            ticket.ticket_id,
            worker_id=self._require_worker_id(),
            business_status=TicketBusinessStatus.AWAITING_HUMAN_REVIEW,
            expected_version=ticket.version,
            metadata_updates={"risk_reasons": list(ticket.risk_reasons or [])},
        )
        self._record_event(
            ticket=current_ticket,
            event_type="decision",
            event_name="escalation_decision",
            node_name="escalate_to_human",
            status="succeeded",
            metadata={
                "primary_route": current_ticket.primary_route,
                "response_strategy": current_ticket.response_strategy,
                "needs_clarification": current_ticket.needs_clarification,
                "needs_escalation": True,
                "final_action": RunFinalAction.HANDOFF_TO_HUMAN.value,
            },
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
            state.get("generated_email")
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
        if hasattr(self.gmail_client, "create_draft_reply"):
            gmail_result = self.gmail_client.create_draft_reply(
                get_active_email(state),
                content_text,
            )
        else:
            gmail_result = {"id": f"gmail-draft-{draft.version_index}"}
        gmail_draft_id = self._extract_gmail_draft_id(gmail_result, draft.gmail_draft_id)
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
                subject=get_active_email(state).subject,
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
                business_status=waiting_business_status,
                expected_version=ticket.version,
                metadata_updates={"gmail_draft_id": gmail_draft_id},
            )
        else:
            updated_ticket = self._require_state_service().complete_run(
                ticket.ticket_id,
                worker_id=self._require_worker_id(),
                business_status=completed_business_status or TicketBusinessStatus.DRAFT_CREATED,
                expected_version=ticket.version,
                metadata_updates={"gmail_draft_id": gmail_draft_id},
            )
        self._record_event(
            ticket=updated_ticket,
            event_type="decision",
            event_name="final_action",
            node_name=node_name,
            status="succeeded",
            metadata={
                "primary_route": updated_ticket.primary_route,
                "response_strategy": updated_ticket.response_strategy,
                "needs_clarification": updated_ticket.needs_clarification,
                "needs_escalation": updated_ticket.needs_escalation,
                "final_action": final_action,
            },
        )
        return {
            "ticket_version": updated_ticket.version,
            "business_status": updated_ticket.business_status,
            "processing_status": updated_ticket.processing_status,
            "generated_email": content_text,
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
    ) -> None:
        if self._repositories is None or self._run is None:
            return
        now = utc_now()
        event = TraceEvent(
            event_id=generate_prefixed_id(EntityIdPrefix.TRACE),
            trace_id=self._run.trace_id,
            run_id=self._run.run_id,
            ticket_id=ticket.ticket_id,
            event_type=event_type,
            event_name=event_name,
            node_name=node_name,
            start_time=now,
            end_time=now,
            latency_ms=0,
            status=status,
            event_metadata=metadata,
        )
        self._repositories.trace_events.add(event)

    def _require_ticket(self, state: GraphState) -> Ticket:
        if self._repositories is None:
            raise RuntimeError("Ticket execution nodes require repositories.")
        ticket_id = state.get("ticket_id")
        if not ticket_id:
            raise RuntimeError("GraphState missing ticket_id.")
        ticket = self._repositories.tickets.get(ticket_id)
        if ticket is None:
            raise RuntimeError(f"Ticket `{ticket_id}` not found.")
        return ticket

    def _require_run(self) -> TicketRun:
        if self._run is None:
            raise RuntimeError("Ticket execution nodes require an active run.")
        return self._run

    def _require_state_service(self) -> TicketStateService:
        if self._state_service is None:
            raise RuntimeError("Ticket execution nodes require TicketStateService.")
        return self._state_service

    def _require_message_log(self) -> MessageLogService:
        if self._message_log is None:
            raise RuntimeError("Ticket execution nodes require MessageLogService.")
        return self._message_log

    def _require_worker_id(self) -> str:
        if not self._worker_id:
            raise RuntimeError("Ticket execution nodes require worker_id.")
        return self._worker_id

    def _next_draft_version_index(self, ticket_id: str) -> int:
        drafts = self._repositories.draft_artifacts.list_by_ticket(ticket_id)
        if not drafts:
            return 1
        return max(draft.version_index for draft in drafts) + 1

    def _extract_gmail_draft_id(self, result: Any, fallback: str | None = None) -> str | None:
        if isinstance(result, Mapping):
            if "id" in result:
                return str(result["id"])
            message = result.get("message")
            if isinstance(message, Mapping) and "id" in message:
                return str(message["id"])
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

    def _map_route_to_legacy_category(self, primary_route: str) -> str:
        if primary_route == "knowledge_request":
            return "product_enquiry"
        if primary_route == "technical_issue":
            return "customer_complaint"
        if primary_route == "commercial_policy_request":
            return "customer_complaint"
        if primary_route == "feedback_intake":
            return "customer_feedback"
        return "unrelated"
