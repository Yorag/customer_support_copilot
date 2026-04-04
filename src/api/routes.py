from __future__ import annotations

from datetime import datetime
from functools import wraps
from typing import NoReturn, Optional

from fastapi import APIRouter, Depends, Query, status

from src.contracts.core import TicketRoute
from src.tickets.message_log import IngestEmailPayload

from .dependencies import RequestContext, get_container, get_request_context
from .errors import ApiError
from .schemas import (
    ApproveTicketRequest,
    CloseTicketRequest,
    CustomerMemoryResponse,
    EditAndApproveTicketRequest,
    EscalateTicketRequest,
    IngestEmailRequest,
    IngestEmailResponse,
    MetricsSummaryResponse,
    RewriteTicketRequest,
    RunTicketRequest,
    RunTicketResponse,
    TicketActionResponse,
    TicketDraftSummary,
    TicketRunSummary,
    TicketSnapshotResponse,
    TicketSummary,
    TicketTraceResponse,
    TraceEventResponse,
)
from .services import (
    CustomerNotFoundError,
    DuplicateRequestError,
    RunNotFoundError,
    TicketApiService,
    TicketNotFoundError,
)


router = APIRouter()


def get_ticket_api_service(container=Depends(get_container)) -> TicketApiService:
    return TicketApiService(container.ticket_store, container=container)


def _raise_service_api_error(exc: Exception) -> NoReturn:
    if isinstance(exc, TicketNotFoundError):
        raise ApiError(
            code="not_found",
            message=str(exc),
            status_code=404,
            details={"ticket_id": exc.ticket_id},
        ) from exc
    if isinstance(exc, CustomerNotFoundError):
        raise ApiError(
            code="not_found",
            message=str(exc),
            status_code=404,
            details={"customer_id": exc.customer_id},
        ) from exc
    if isinstance(exc, RunNotFoundError):
        raise ApiError(
            code="not_found",
            message=str(exc),
            status_code=404,
            details={"ticket_id": exc.ticket_id, "run_id": exc.run_id},
        ) from exc
    if isinstance(exc, DuplicateRequestError):
        raise ApiError(
            code="duplicate_request",
            message=str(exc),
            status_code=409,
            details={"idempotency_key": exc.key},
        ) from exc
    raise exc


def _map_service_errors(func):
    """Decorator that maps common service exceptions to ApiError responses."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (
            CustomerNotFoundError,
            DuplicateRequestError,
            RunNotFoundError,
            TicketNotFoundError,
        ) as exc:
            _raise_service_api_error(exc)

    return wrapper


def _require_actor_id(context: RequestContext) -> str:
    actor_id = (context.actor_id or "").strip()
    if actor_id:
        return actor_id
    raise ApiError(
        code="validation_error",
        message="X-Actor-Id header is required for manual ticket actions.",
        status_code=422,
        details={"header": "X-Actor-Id"},
    )


def _validate_metrics_summary_query(
    *,
    from_time: datetime,
    to_time: datetime,
    route: Optional[str],
) -> tuple[datetime, datetime, Optional[str]]:
    if from_time > to_time:
        raise ApiError(
            code="validation_error",
            message="`from` must be earlier than or equal to `to`.",
            status_code=422,
            details={"query": ["from", "to"]},
        )

    if route is None:
        return from_time, to_time, None

    normalized_route = route.strip()
    allowed_routes = sorted(item.value for item in TicketRoute)
    if normalized_route not in allowed_routes:
        raise ApiError(
            code="validation_error",
            message="`route` must be one of the supported V1 ticket routes.",
            status_code=422,
            details={
                "query": "route",
                "allowed_values": allowed_routes,
            },
        )
    return from_time, to_time, normalized_route


@router.post(
    "/tickets/ingest-email",
    response_model=IngestEmailResponse,
    status_code=status.HTTP_201_CREATED,
)
@_map_service_errors
def ingest_email(
    request: IngestEmailRequest,
    context: RequestContext = Depends(get_request_context),
    service: TicketApiService = Depends(get_ticket_api_service),
) -> IngestEmailResponse:
    ticket, created = service.ingest_email(
        payload=IngestEmailPayload(**request.model_dump()),
        idempotency_key=context.idempotency_key,
    )

    return IngestEmailResponse(
        ticket_id=ticket.ticket_id,
        created=created,
        business_status=ticket.business_status,
        processing_status=ticket.processing_status,
        version=ticket.version,
    )


@router.get("/tickets/{ticket_id}", response_model=TicketSnapshotResponse)
@_map_service_errors
def get_ticket(
    ticket_id: str,
    service: TicketApiService = Depends(get_ticket_api_service),
) -> TicketSnapshotResponse:
    (
        ticket,
        latest_run,
        claim_projection,
        evaluation_summary_ref,
        latest_draft,
    ) = service.get_ticket_snapshot(ticket_id)

    return TicketSnapshotResponse(
        ticket=TicketSummary(
            ticket_id=ticket.ticket_id,
            business_status=ticket.business_status,
            processing_status=ticket.processing_status,
            claimed_by=claim_projection.claimed_by,
            claimed_at=claim_projection.claimed_at,
            lease_until=claim_projection.lease_until,
            priority=ticket.priority,
            primary_route=ticket.primary_route,
            multi_intent=ticket.multi_intent,
            tags=ticket.tags or [],
            version=ticket.version,
        ),
        latest_run=(
            TicketRunSummary(
                run_id=latest_run.run_id,
                trace_id=latest_run.trace_id,
                status=latest_run.status,
                final_action=latest_run.final_action,
                evaluation_summary_ref=evaluation_summary_ref.__dict__,
            )
            if latest_run is not None
            else None
        ),
        latest_draft=(
            TicketDraftSummary(
                draft_id=latest_draft.draft_id,
                qa_status=latest_draft.qa_status,
            )
            if latest_draft is not None
            else None
        ),
    )


@router.post(
    "/tickets/{ticket_id}/run",
    response_model=RunTicketResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@_map_service_errors
def run_ticket(
    ticket_id: str,
    request: RunTicketRequest,
    context: RequestContext = Depends(get_request_context),
    service: TicketApiService = Depends(get_ticket_api_service),
) -> RunTicketResponse:
    result = service.run_ticket(
        ticket_id=ticket_id,
        ticket_version=request.ticket_version,
        trigger_type=request.trigger_type,
        force_retry=request.force_retry,
        actor_id=context.actor_id,
        request_id=context.request_id,
        idempotency_key=context.idempotency_key,
    )
    return RunTicketResponse(
        ticket_id=result.ticket.ticket_id,
        run_id=result.run.run_id,
        trace_id=result.run.trace_id,
        processing_status=result.ticket.processing_status,
    )


@router.post(
    "/tickets/{ticket_id}/approve",
    response_model=TicketActionResponse,
    response_model_exclude_none=True,
)
@_map_service_errors
def approve_ticket(
    ticket_id: str,
    request: ApproveTicketRequest,
    context: RequestContext = Depends(get_request_context),
    service: TicketApiService = Depends(get_ticket_api_service),
) -> TicketActionResponse:
    actor_id = _require_actor_id(context)
    ticket, review_id = service.approve_ticket(
        ticket_id=ticket_id,
        ticket_version=request.ticket_version,
        draft_id=request.draft_id,
        comment=request.comment,
        actor_id=actor_id,
        idempotency_key=context.idempotency_key,
    )
    return TicketActionResponse(
        ticket_id=ticket.ticket_id,
        review_id=review_id,
        business_status=ticket.business_status,
        processing_status=ticket.processing_status,
        version=ticket.version,
    )


@router.post(
    "/tickets/{ticket_id}/edit-and-approve",
    response_model=TicketActionResponse,
    response_model_exclude_none=True,
)
@_map_service_errors
def edit_and_approve_ticket(
    ticket_id: str,
    request: EditAndApproveTicketRequest,
    context: RequestContext = Depends(get_request_context),
    service: TicketApiService = Depends(get_ticket_api_service),
) -> TicketActionResponse:
    actor_id = _require_actor_id(context)
    ticket, review_id = service.edit_and_approve_ticket(
        ticket_id=ticket_id,
        ticket_version=request.ticket_version,
        draft_id=request.draft_id,
        comment=request.comment,
        edited_content_text=request.edited_content_text,
        actor_id=actor_id,
        idempotency_key=context.idempotency_key,
    )
    return TicketActionResponse(
        ticket_id=ticket.ticket_id,
        review_id=review_id,
        business_status=ticket.business_status,
        processing_status=ticket.processing_status,
        version=ticket.version,
    )


@router.post(
    "/tickets/{ticket_id}/rewrite",
    response_model=TicketActionResponse,
    response_model_exclude_none=True,
)
@_map_service_errors
def rewrite_ticket(
    ticket_id: str,
    request: RewriteTicketRequest,
    context: RequestContext = Depends(get_request_context),
    service: TicketApiService = Depends(get_ticket_api_service),
) -> TicketActionResponse:
    actor_id = _require_actor_id(context)
    ticket, review_id = service.rewrite_ticket(
        ticket_id=ticket_id,
        ticket_version=request.ticket_version,
        draft_id=request.draft_id,
        comment=request.comment,
        rewrite_reasons=request.rewrite_reasons,
        actor_id=actor_id,
        idempotency_key=context.idempotency_key,
    )
    return TicketActionResponse(
        ticket_id=ticket.ticket_id,
        review_id=review_id,
        business_status=ticket.business_status,
        processing_status=ticket.processing_status,
        version=ticket.version,
    )


@router.post(
    "/tickets/{ticket_id}/escalate",
    response_model=TicketActionResponse,
    response_model_exclude_none=True,
)
@_map_service_errors
def escalate_ticket(
    ticket_id: str,
    request: EscalateTicketRequest,
    context: RequestContext = Depends(get_request_context),
    service: TicketApiService = Depends(get_ticket_api_service),
) -> TicketActionResponse:
    actor_id = _require_actor_id(context)
    ticket, review_id = service.escalate_ticket(
        ticket_id=ticket_id,
        ticket_version=request.ticket_version,
        comment=request.comment,
        target_queue=request.target_queue,
        actor_id=actor_id,
        idempotency_key=context.idempotency_key,
    )
    return TicketActionResponse(
        ticket_id=ticket.ticket_id,
        review_id=review_id,
        business_status=ticket.business_status,
        processing_status=ticket.processing_status,
        version=ticket.version,
    )


@router.post(
    "/tickets/{ticket_id}/close",
    response_model=TicketActionResponse,
    response_model_exclude_none=True,
)
@_map_service_errors
def close_ticket(
    ticket_id: str,
    request: CloseTicketRequest,
    context: RequestContext = Depends(get_request_context),
    service: TicketApiService = Depends(get_ticket_api_service),
) -> TicketActionResponse:
    actor_id = _require_actor_id(context)
    ticket = service.close_ticket(
        ticket_id=ticket_id,
        ticket_version=request.ticket_version,
        reason=request.reason,
        actor_id=actor_id,
        idempotency_key=context.idempotency_key,
    )
    return TicketActionResponse(
        ticket_id=ticket.ticket_id,
        business_status=ticket.business_status,
        processing_status=ticket.processing_status,
        version=ticket.version,
    )


@router.get("/customers/{customer_id}/memory", response_model=CustomerMemoryResponse)
@_map_service_errors
def get_customer_memory(
    customer_id: str,
    service: TicketApiService = Depends(get_ticket_api_service),
) -> CustomerMemoryResponse:
    profile = service.get_customer_memory(customer_id)

    return CustomerMemoryResponse(
        customer_id=profile.customer_id,
        profile=profile.profile,
        risk_tags=profile.risk_tags,
        business_flags=profile.business_flags,
        historical_case_refs=profile.historical_case_refs,
        version=profile.version,
    )


@router.get("/tickets/{ticket_id}/trace", response_model=TicketTraceResponse)
@_map_service_errors
def get_ticket_trace(
    ticket_id: str,
    run_id: Optional[str] = Query(default=None),
    service: TicketApiService = Depends(get_ticket_api_service),
) -> TicketTraceResponse:
    ticket, run, events = service.get_ticket_trace(ticket_id, run_id=run_id)

    return TicketTraceResponse(
        ticket_id=ticket.ticket_id,
        run_id=run.run_id,
        trace_id=run.trace_id,
        latency_metrics=run.latency_metrics,
        resource_metrics=run.resource_metrics,
        response_quality=run.response_quality,
        trajectory_evaluation=run.trajectory_evaluation,
        events=[TraceEventResponse.from_record(event=event) for event in events],
    )


@router.get("/metrics/summary", response_model=MetricsSummaryResponse)
def get_metrics_summary(
    from_time: datetime = Query(alias="from"),
    to_time: datetime = Query(alias="to"),
    route: Optional[str] = Query(default=None),
    service: TicketApiService = Depends(get_ticket_api_service),
) -> MetricsSummaryResponse:
    from_time, to_time, route = _validate_metrics_summary_query(
        from_time=from_time,
        to_time=to_time,
        route=route,
    )
    summary = service.get_metrics_summary(
        from_time=from_time,
        to_time=to_time,
        route=route,
    )
    return MetricsSummaryResponse.model_validate(summary)
