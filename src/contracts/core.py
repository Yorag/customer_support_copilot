from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Sequence, TypeVar


_CROCKFORD_BASE32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ULID_BODY_LENGTH = 26
INITIAL_VERSION = 1


class StringEnum(str, Enum):
    """Backport-style string enum base for Python 3.10+."""


class CoreSchemaError(ValueError):
    """Raised when persisted business data violates the shared schema rules."""


class VersionConflictError(CoreSchemaError):
    """Raised when optimistic locking detects a stale version."""

    def __init__(self, *, entity: str, expected: int, actual: int) -> None:
        super().__init__(
            f"{entity} version conflict: expected version {expected}, got {actual}."
        )
        self.entity = entity
        self.expected = expected
        self.actual = actual


class InvalidStateTransitionError(CoreSchemaError):
    """Raised when a persisted state transition violates the workflow spec."""

    def __init__(
        self,
        *,
        entity: str,
        current_status: str,
        target_status: str,
        reason: str | None = None,
        allowed_transitions: Sequence[str] | None = None,
    ) -> None:
        message = (
            f"{entity} cannot transition from `{current_status}` to "
            f"`{target_status}`."
        )
        if allowed_transitions:
            allowed_text = ", ".join(allowed_transitions)
            message = f"{message} Allowed transitions: {allowed_text}."
        if reason:
            message = f"{message} {reason}"
        super().__init__(message)
        self.entity = entity
        self.current_status = current_status
        self.target_status = target_status
        self.reason = reason
        self.allowed_transitions = tuple(allowed_transitions or ())


class LeaseConflictError(CoreSchemaError):
    """Raised when a worker attempts to act on a ticket without a valid lease."""

    def __init__(
        self,
        *,
        ticket_id: str,
        message: str,
        lease_owner: str | None = None,
    ) -> None:
        super().__init__(message)
        self.ticket_id = ticket_id
        self.lease_owner = lease_owner


class EntityIdPrefix(StringEnum):
    TICKET = "t"
    RUN = "run"
    TRACE = "trace"
    DRAFT = "draft"
    REVIEW = "review"
    MEMORY_EVENT = "me"
    TICKET_MESSAGE = "tm"


class SourceChannel(StringEnum):
    GMAIL = "gmail"


class TicketBusinessStatus(StringEnum):
    NEW = "new"
    TRIAGED = "triaged"
    DRAFT_CREATED = "draft_created"
    AWAITING_CUSTOMER_INPUT = "awaiting_customer_input"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    FAILED = "failed"
    CLOSED = "closed"


class TicketProcessingStatus(StringEnum):
    IDLE = "idle"
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    WAITING_EXTERNAL = "waiting_external"
    COMPLETED = "completed"
    ERROR = "error"


class TicketPriority(StringEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TicketRoute(StringEnum):
    KNOWLEDGE_REQUEST = "knowledge_request"
    TECHNICAL_ISSUE = "technical_issue"
    COMMERCIAL_POLICY_REQUEST = "commercial_policy_request"
    FEEDBACK_INTAKE = "feedback_intake"
    UNRELATED = "unrelated"


class TicketTag(StringEnum):
    FEATURE_REQUEST = "feature_request"
    COMPLAINT = "complaint"
    GENERAL_FEEDBACK = "general_feedback"
    BILLING_QUESTION = "billing_question"
    REFUND_REQUEST = "refund_request"
    MULTI_INTENT = "multi_intent"
    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_ESCALATION = "needs_escalation"


class ResponseStrategy(StringEnum):
    ANSWER = "answer"
    TROUBLESHOOTING = "troubleshooting"
    POLICY_CONSTRAINED = "policy_constrained"
    ACKNOWLEDGEMENT = "acknowledgement"


class RunTriggerType(StringEnum):
    POLLER = "poller"
    MANUAL_API = "manual_api"
    SCHEDULED_RETRY = "scheduled_retry"
    HUMAN_ACTION = "human_action"


class RunStatus(StringEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class RunFinalAction(StringEnum):
    CREATE_DRAFT = "create_draft"
    REQUEST_CLARIFICATION = "request_clarification"
    HANDOFF_TO_HUMAN = "handoff_to_human"
    SKIP_UNRELATED = "skip_unrelated"
    CLOSE_TICKET = "close_ticket"
    NO_OP = "no_op"


class DraftType(StringEnum):
    REPLY = "reply"
    CLARIFICATION_REQUEST = "clarification_request"
    HANDOFF_SUMMARY = "handoff_summary"
    LIGHTWEIGHT_TEMPLATE = "lightweight_template"


class DraftQaStatus(StringEnum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    ESCALATED = "escalated"


class HumanReviewAction(StringEnum):
    SAVE_DRAFT = "save_draft"
    APPROVE = "approve"
    EDIT_AND_APPROVE = "edit_and_approve"
    REJECT_FOR_REWRITE = "reject_for_rewrite"
    ESCALATE = "escalate"


class TraceEventType(StringEnum):
    NODE = "node"
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    DECISION = "decision"
    CHECKPOINT = "checkpoint"
    WORKER = "worker"


class TraceEventStatus(StringEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class MemorySourceStage(StringEnum):
    LOAD_MEMORY = "load_memory"
    CUSTOMER_HISTORY_LOOKUP = "customer_history_lookup"
    AWAITING_CUSTOMER_INPUT = "awaiting_customer_input"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    CLOSE_TICKET = "close_ticket"


class MemoryEventType(StringEnum):
    PROFILE_UPDATE = "profile_update"
    RISK_TAG_ADD = "risk_tag_add"
    RISK_TAG_REMOVE = "risk_tag_remove"
    HISTORICAL_CASE_APPEND = "historical_case_append"
    BUSINESS_FLAG_UPDATE = "business_flag_update"


class MessageDirection(StringEnum):
    INBOUND = "inbound"
    OUTBOUND_DRAFT = "outbound_draft"
    SYSTEM = "system"


class MessageType(StringEnum):
    CUSTOMER_EMAIL = "customer_email"
    REPLY_DRAFT = "reply_draft"
    CLARIFICATION_REQUEST = "clarification_request"
    HANDOFF_SUMMARY = "handoff_summary"
    INTERNAL_NOTE = "internal_note"


@dataclass(frozen=True)
class TicketRoutingSelection:
    source_channel: SourceChannel
    primary_route: TicketRoute | None
    secondary_routes: tuple[TicketRoute, ...]
    tags: tuple[TicketTag, ...]
    multi_intent: bool


@dataclass(frozen=True)
class CustomerIdentity:
    normalized_email: str
    customer_id: str


EnumT = TypeVar("EnumT", bound=StringEnum)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_timezone_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CoreSchemaError("Datetime values must include timezone information.")
    return value


def to_api_timestamp(value: datetime) -> str:
    return ensure_timezone_aware(value).isoformat()


def validate_version(value: int) -> int:
    if value < INITIAL_VERSION:
        raise CoreSchemaError(
            f"Version must be >= {INITIAL_VERSION}, got {value}."
        )
    return value


def next_version(current_version: int) -> int:
    return validate_version(current_version) + 1


def assert_expected_version(
    *,
    expected: int,
    actual: int,
    entity: str = "entity",
) -> None:
    validate_version(expected)
    validate_version(actual)
    if expected != actual:
        raise VersionConflictError(entity=entity, expected=expected, actual=actual)


def validate_source_channel(value: SourceChannel | str) -> SourceChannel:
    try:
        channel = SourceChannel(value)
    except ValueError as exc:
        raise CoreSchemaError(f"Unsupported source_channel `{value}`.") from exc

    if channel is not SourceChannel.GMAIL:
        raise CoreSchemaError("V1 source_channel must be `gmail`.")

    return channel


def normalize_ticket_routing(
    *,
    source_channel: SourceChannel | str = SourceChannel.GMAIL,
    primary_route: TicketRoute | str | None = None,
    secondary_routes: Sequence[TicketRoute | str] | None = None,
    tags: Sequence[TicketTag | str] | None = None,
    multi_intent: bool,
) -> TicketRoutingSelection:
    normalized_source_channel = validate_source_channel(source_channel)
    normalized_primary_route = (
        _coerce_enum(TicketRoute, primary_route) if primary_route is not None else None
    )
    normalized_secondary_routes = _coerce_unique_enum_sequence(
        TicketRoute,
        secondary_routes,
    )
    normalized_tags = list(_coerce_unique_enum_sequence(TicketTag, tags))

    if normalized_secondary_routes and not multi_intent:
        raise CoreSchemaError(
            "secondary_routes require multi_intent=true in persisted ticket data."
        )

    if multi_intent:
        if TicketTag.MULTI_INTENT not in normalized_tags:
            normalized_tags.append(TicketTag.MULTI_INTENT)
    else:
        normalized_tags = [
            tag for tag in normalized_tags if tag is not TicketTag.MULTI_INTENT
        ]

    return TicketRoutingSelection(
        source_channel=normalized_source_channel,
        primary_route=normalized_primary_route,
        secondary_routes=normalized_secondary_routes,
        tags=tuple(normalized_tags),
        multi_intent=multi_intent,
    )


def generate_prefixed_id(prefix: EntityIdPrefix) -> str:
    return f"{prefix.value}_{generate_ulid()}"


def validate_prefixed_id(value: str, prefix: EntityIdPrefix) -> str:
    pattern = re.compile(rf"^{re.escape(prefix.value)}_[{_CROCKFORD_BASE32}]{{26}}$")
    if not pattern.fullmatch(value):
        raise CoreSchemaError(
            f"Invalid ID `{value}` for prefix `{prefix.value}`. Expected "
            f"`{prefix.value}_<26-char-ulid>`."
        )
    return value


def normalize_email_address(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = value.strip().lower()
    if not cleaned:
        return None

    match = re.search(r"<([^<>]+)>", cleaned)
    email = match.group(1).strip() if match else cleaned
    if email.count("@") != 1:
        return None

    local_part, domain = email.split("@", 1)
    if not local_part or not domain:
        return None

    if "." not in domain or domain.startswith(".") or domain.endswith("."):
        return None

    return email


def build_customer_identity(
    raw_email: str | None,
    *,
    alias_map: dict[str, str] | None = None,
) -> CustomerIdentity | None:
    normalized_email = normalize_email_address(raw_email)
    if normalized_email is None:
        return None

    canonical_email = normalized_email
    if alias_map:
        normalized_alias_map = {
            alias.strip().lower(): target.strip().lower()
            for alias, target in alias_map.items()
            if alias.strip() and target.strip()
        }
        canonical_email = normalized_alias_map.get(normalized_email, normalized_email)

    normalized_customer_token = re.sub(r"[^a-z0-9]+", "_", canonical_email).strip("_")
    if not normalized_customer_token:
        return None

    return CustomerIdentity(
        normalized_email=canonical_email,
        customer_id=f"cust_email_{normalized_customer_token}",
    )


def generate_ulid(timestamp: datetime | None = None) -> str:
    current_time = ensure_timezone_aware(timestamp or utc_now()).astimezone(
        timezone.utc
    )
    timestamp_ms = int(current_time.timestamp() * 1000)
    if timestamp_ms < 0 or timestamp_ms >= 2**48:
        raise CoreSchemaError("ULID timestamp is out of range.")

    return _encode_base32(timestamp_ms, 10) + _encode_base32(secrets.randbits(80), 16)


def _encode_base32(value: int, length: int) -> str:
    if value < 0:
        raise CoreSchemaError("Base32 encoding only supports non-negative integers.")

    chars = ["0"] * length
    for index in range(length - 1, -1, -1):
        chars[index] = _CROCKFORD_BASE32[value & 0x1F]
        value >>= 5

    if value:
        raise CoreSchemaError("Value does not fit in the requested Base32 length.")

    return "".join(chars)


def _coerce_enum(enum_cls: type[EnumT], value: EnumT | str) -> EnumT:
    if isinstance(value, enum_cls):
        return value

    try:
        return enum_cls(value)
    except ValueError as exc:
        raise CoreSchemaError(
            f"Unsupported {enum_cls.__name__} value `{value}`."
        ) from exc


def _coerce_unique_enum_sequence(
    enum_cls: type[EnumT],
    values: Sequence[EnumT | str] | None,
) -> tuple[EnumT, ...]:
    if not values:
        return ()

    normalized: list[EnumT] = []
    seen: set[EnumT] = set()
    for value in values:
        enum_value = _coerce_enum(enum_cls, value)
        if enum_value in seen:
            continue
        seen.add(enum_value)
        normalized.append(enum_value)

    return tuple(normalized)
