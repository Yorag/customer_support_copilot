from __future__ import annotations

from src.api.service_errors import (
    CustomerNotFoundError,
    DuplicateRequestError,
    GmailDisabledError,
    RunExecutionFailedError,
    RunNotFoundError,
    TicketNotFoundError,
)

from .base import TicketApiServiceBase
from .commands import TicketCommandServiceMixin
from .draft_actions import TicketDraftActionServiceMixin
from .dev_tools import DevToolsServiceMixin
from .gmail_ops import GmailOpsServiceMixin
from .common import (
    EvaluationSummaryRefPayload,
    IdempotencyService,
    TicketClaimProjectionPayload,
    build_evaluation_summary_ref,
    build_ticket_claim_projection,
)
from .manual_actions import TicketManualActionServiceMixin
from .queries import TicketQueryServiceMixin
from .runtime_status import RuntimeStatusServiceMixin


class TicketApiService(
    DevToolsServiceMixin,
    RuntimeStatusServiceMixin,
    GmailOpsServiceMixin,
    TicketDraftActionServiceMixin,
    TicketManualActionServiceMixin,
    TicketQueryServiceMixin,
    TicketCommandServiceMixin,
    TicketApiServiceBase,
):
    pass


__all__ = [
    "CustomerNotFoundError",
    "DuplicateRequestError",
    "EvaluationSummaryRefPayload",
    "GmailDisabledError",
    "IdempotencyService",
    "RunExecutionFailedError",
    "RunNotFoundError",
    "TicketApiService",
    "TicketClaimProjectionPayload",
    "TicketNotFoundError",
    "build_evaluation_summary_ref",
    "build_ticket_claim_projection",
]
