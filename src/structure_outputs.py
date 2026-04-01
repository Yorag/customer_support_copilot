from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .core_schema import (
    ResponseStrategy,
    TicketPriority,
    TicketRoute,
    TicketTag,
    normalize_ticket_routing,
)


class EmailCategory(str, Enum):
    product_enquiry = "product_enquiry"
    customer_complaint = "customer_complaint"
    customer_feedback = "customer_feedback"
    unrelated = "unrelated"


class CategorizeEmailOutput(BaseModel):
    category: EmailCategory = Field(
        ...,
        description="The category assigned to the email, indicating its type based on predefined rules.",
    )


class TriageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_route: TicketRoute = Field(
        ...,
        description="The dominant support route selected from the fixed V1 route set.",
    )
    secondary_routes: list[TicketRoute] = Field(
        default_factory=list,
        max_length=2,
        description="Up to two secondary routes that materially affect execution when the email is multi-intent.",
    )
    tags: list[TicketTag] = Field(
        default_factory=list,
        max_length=5,
        description="Up to five normalized tags describing route nuances and execution risks.",
    )
    response_strategy: ResponseStrategy = Field(
        ...,
        description="The drafting strategy implied by the selected primary route.",
    )
    multi_intent: bool = Field(
        ...,
        description="Whether the email contains multiple distinct support intents.",
    )
    intent_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score for the selected routing decision, in the inclusive range [0.0, 1.0].",
    )
    priority: TicketPriority = Field(
        ...,
        description="Normalized ticket priority after applying base and escalation rules.",
    )
    needs_clarification: bool = Field(
        ...,
        description="Whether the customer must provide more diagnostic context before the workflow can proceed.",
    )
    needs_escalation: bool = Field(
        ...,
        description="Whether the case must be routed to human review or escalation handling.",
    )
    routing_reason: str = Field(
        ...,
        min_length=1,
        description="Human-readable explanation of why the route and strategy were selected.",
    )

    _EXPECTED_RESPONSE_STRATEGIES = {
        TicketRoute.KNOWLEDGE_REQUEST: ResponseStrategy.ANSWER,
        TicketRoute.TECHNICAL_ISSUE: ResponseStrategy.TROUBLESHOOTING,
        TicketRoute.COMMERCIAL_POLICY_REQUEST: ResponseStrategy.POLICY_CONSTRAINED,
        TicketRoute.FEEDBACK_INTAKE: ResponseStrategy.ACKNOWLEDGEMENT,
        TicketRoute.UNRELATED: ResponseStrategy.ACKNOWLEDGEMENT,
    }

    @field_validator("secondary_routes", "tags", mode="after")
    @classmethod
    def _dedupe_preserving_order(
        cls,
        values: list[TicketRoute] | list[TicketTag],
    ) -> list[TicketRoute] | list[TicketTag]:
        deduped: list[TicketRoute] | list[TicketTag] = []
        for value in values:
            if value not in deduped:
                deduped.append(value)
        return deduped

    @field_validator("routing_reason", mode="after")
    @classmethod
    def _strip_routing_reason(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("routing_reason must not be blank.")
        return stripped

    @model_validator(mode="after")
    def _normalize_and_validate(self) -> TriageOutput:
        if self.primary_route in self.secondary_routes:
            raise ValueError("secondary_routes cannot repeat primary_route.")

        expected_strategy = self._EXPECTED_RESPONSE_STRATEGIES[self.primary_route]
        if self.response_strategy is not expected_strategy:
            raise ValueError(
                "response_strategy does not match the fixed mapping for primary_route."
            )

        if self.needs_clarification and self.primary_route is not TicketRoute.TECHNICAL_ISSUE:
            raise ValueError(
                "needs_clarification can only be true when primary_route=technical_issue."
            )

        if self.intent_confidence < 0.60 and not self.needs_escalation:
            raise ValueError(
                "intent_confidence below 0.60 requires needs_escalation=true."
            )

        routing_selection = normalize_ticket_routing(
            primary_route=self.primary_route,
            secondary_routes=self.secondary_routes,
            tags=self.tags,
            multi_intent=self.multi_intent,
        )

        normalized_tags = list(routing_selection.tags)
        normalized_tags = _sync_boolean_tag(
            normalized_tags,
            TicketTag.NEEDS_CLARIFICATION,
            self.needs_clarification,
        )
        normalized_tags = _sync_boolean_tag(
            normalized_tags,
            TicketTag.NEEDS_ESCALATION,
            self.needs_escalation,
        )

        if len(normalized_tags) > 5:
            raise ValueError("tags cannot contain more than 5 items.")

        self.secondary_routes = list(routing_selection.secondary_routes)
        self.tags = normalized_tags
        return self


class RAGQueriesOutput(BaseModel):
    queries: list[str] = Field(
        ...,
        description="A list of up to three questions representing the customer's intent, based on their email.",
    )


class WriterOutput(BaseModel):
    email: str = Field(
        ...,
        description="The draft email written in response to the customer's inquiry, adhering to company tone and standards.",
    )


class ProofReaderOutput(BaseModel):
    feedback: str = Field(
        ...,
        description="Detailed feedback explaining why the email is or is not sendable.",
    )
    send: bool = Field(
        ...,
        description="Indicates whether the email is ready to be sent (true) or requires rewriting (false).",
    )


def _sync_boolean_tag(
    tags: list[TicketTag],
    tag: TicketTag,
    enabled: bool,
) -> list[TicketTag]:
    if enabled:
        if tag not in tags:
            tags.append(tag)
        return tags

    return [current_tag for current_tag in tags if current_tag is not tag]
