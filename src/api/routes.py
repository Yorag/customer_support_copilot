from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from src.message_log import IngestEmailPayload

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


@router.post(
    "/tickets/ingest-email",
    response_model=IngestEmailResponse,
    status_code=status.HTTP_201_CREATED,
)
def ingest_email(
    request: IngestEmailRequest,
    context: RequestContext = Depends(get_request_context),
    service: TicketApiService = Depends(get_ticket_api_service),
) -> IngestEmailResponse:
    try:
        ticket, created = service.ingest_email(
            payload=IngestEmailPayload(**request.model_dump()),
            idempotency_key=context.idempotency_key,
        )
    except DuplicateRequestError as exc:
        raise ApiError(
            code="duplicate_request",
            message=str(exc),
            status_code=409,
            details={"idempotency_key": exc.key},
        ) from exc

    return IngestEmailResponse(
        ticket_id=ticket.ticket_id,
        created=created,
        business_status=ticket.business_status,
        processing_status=ticket.processing_status,
        version=ticket.version,
    )


@router.get("/tickets/{ticket_id}", response_model=TicketSnapshotResponse)
def get_ticket(
    ticket_id: str,
    service: TicketApiService = Depends(get_ticket_api_service),
) -> TicketSnapshotResponse:
    try:
        ticket, latest_run, latest_draft = service.get_ticket_snapshot(ticket_id)
    except TicketNotFoundError as exc:
        raise ApiError(
            code="not_found",
            message=str(exc),
            status_code=404,
            details={"ticket_id": exc.ticket_id},
        ) from exc

    return TicketSnapshotResponse(
        ticket=TicketSummary(
            ticket_id=ticket.ticket_id,
            business_status=ticket.business_status,
            processing_status=ticket.processing_status,
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
def run_ticket(
    ticket_id: str,
    request: RunTicketRequest,
    context: RequestContext = Depends(get_request_context),
    service: TicketApiService = Depends(get_ticket_api_service),
) -> RunTicketResponse:
    try:
        result = service.run_ticket(
            ticket_id=ticket_id,
            ticket_version=request.ticket_version,
            trigger_type=request.trigger_type,
            force_retry=request.force_retry,
            actor_id=context.actor_id,
            request_id=context.request_id,
            idempotency_key=context.idempotency_key,
        )
    except TicketNotFoundError as exc:
        raise ApiError(
            code="not_found",
            message=str(exc),
            status_code=404,
            details={"ticket_id": exc.ticket_id},
        ) from exc
    except DuplicateRequestError as exc:
        raise ApiError(
            code="duplicate_request",
            message=str(exc),
            status_code=409,
            details={"idempotency_key": exc.key},
        ) from exc

    return RunTicketResponse(
        ticket_id=result.ticket.ticket_id,
        run_id=result.run.run_id,
        trace_id=result.run.trace_id,
        processing_status=result.ticket.processing_status,
    )


@router.post("/tickets/{ticket_id}/approve", response_model=TicketActionResponse)
def approve_ticket(
    ticket_id: str,
    request: ApproveTicketRequest,
    context: RequestContext = Depends(get_request_context),
    service: TicketApiService = Depends(get_ticket_api_service),
) -> TicketActionResponse:
    actor_id = context.actor_id or "system:unknown"
    try:
        ticket, review_id = service.approve_ticket(
            ticket_id=ticket_id,
            ticket_version=request.ticket_version,
            draft_id=request.draft_id,
            comment=request.comment,
            actor_id=actor_id,
        )
    except TicketNotFoundError as exc:
        raise ApiError(
            code="not_found",
            message=str(exc),
            status_code=404,
            details={"ticket_id": exc.ticket_id},
        ) from exc

    return TicketActionResponse(
        ticket_id=ticket.ticket_id,
        review_id=review_id,
        business_status=ticket.business_status,
        processing_status=ticket.processing_status,
        version=ticket.version,
    )


@router.post("/tickets/{ticket_id}/edit-and-approve", response_model=TicketActionResponse)
def edit_and_approve_ticket(
    ticket_id: str,
    request: EditAndApproveTicketRequest,
    context: RequestContext = Depends(get_request_context),
    service: TicketApiService = Depends(get_ticket_api_service),
) -> TicketActionResponse:
    actor_id = context.actor_id or "system:unknown"
    try:
        ticket, review_id = service.edit_and_approve_ticket(
            ticket_id=ticket_id,
            ticket_version=request.ticket_version,
            draft_id=request.draft_id,
            comment=request.comment,
            edited_content_text=request.edited_content_text,
            actor_id=actor_id,
        )
    except TicketNotFoundError as exc:
        raise ApiError(
            code="not_found",
            message=str(exc),
            status_code=404,
            details={"ticket_id": exc.ticket_id},
        ) from exc

    return TicketActionResponse(
        ticket_id=ticket.ticket_id,
        review_id=review_id,
        business_status=ticket.business_status,
        processing_status=ticket.processing_status,
        version=ticket.version,
    )


@router.post("/tickets/{ticket_id}/rewrite", response_model=TicketActionResponse)
def rewrite_ticket(
    ticket_id: str,
    request: RewriteTicketRequest,
    context: RequestContext = Depends(get_request_context),
    service: TicketApiService = Depends(get_ticket_api_service),
) -> TicketActionResponse:
    actor_id = context.actor_id or "system:unknown"
    try:
        ticket, review_id = service.rewrite_ticket(
            ticket_id=ticket_id,
            ticket_version=request.ticket_version,
            draft_id=request.draft_id,
            comment=request.comment,
            rewrite_reasons=request.rewrite_reasons,
            actor_id=actor_id,
        )
    except TicketNotFoundError as exc:
        raise ApiError(
            code="not_found",
            message=str(exc),
            status_code=404,
            details={"ticket_id": exc.ticket_id},
        ) from exc

    return TicketActionResponse(
        ticket_id=ticket.ticket_id,
        review_id=review_id,
        business_status=ticket.business_status,
        processing_status=ticket.processing_status,
        version=ticket.version,
    )


@router.post("/tickets/{ticket_id}/escalate", response_model=TicketActionResponse)
def escalate_ticket(
    ticket_id: str,
    request: EscalateTicketRequest,
    context: RequestContext = Depends(get_request_context),
    service: TicketApiService = Depends(get_ticket_api_service),
) -> TicketActionResponse:
    actor_id = context.actor_id or "system:unknown"
    try:
        ticket, review_id = service.escalate_ticket(
            ticket_id=ticket_id,
            ticket_version=request.ticket_version,
            comment=request.comment,
            target_queue=request.target_queue,
            actor_id=actor_id,
        )
    except TicketNotFoundError as exc:
        raise ApiError(
            code="not_found",
            message=str(exc),
            status_code=404,
            details={"ticket_id": exc.ticket_id},
        ) from exc

    return TicketActionResponse(
        ticket_id=ticket.ticket_id,
        review_id=review_id,
        business_status=ticket.business_status,
        processing_status=ticket.processing_status,
        version=ticket.version,
    )


@router.post("/tickets/{ticket_id}/close", response_model=TicketActionResponse)
def close_ticket(
    ticket_id: str,
    request: CloseTicketRequest,
    service: TicketApiService = Depends(get_ticket_api_service),
) -> TicketActionResponse:
    try:
        ticket = service.close_ticket(
            ticket_id=ticket_id,
            ticket_version=request.ticket_version,
            reason=request.reason,
        )
    except TicketNotFoundError as exc:
        raise ApiError(
            code="not_found",
            message=str(exc),
            status_code=404,
            details={"ticket_id": exc.ticket_id},
        ) from exc

    return TicketActionResponse(
        ticket_id=ticket.ticket_id,
        business_status=ticket.business_status,
        processing_status=ticket.processing_status,
        version=ticket.version,
    )


@router.get("/customers/{customer_id}/memory", response_model=CustomerMemoryResponse)
def get_customer_memory(
    customer_id: str,
    service: TicketApiService = Depends(get_ticket_api_service),
) -> CustomerMemoryResponse:
    try:
        profile = service.get_customer_memory(customer_id)
    except CustomerNotFoundError as exc:
        raise ApiError(
            code="not_found",
            message=str(exc),
            status_code=404,
            details={"customer_id": exc.customer_id},
        ) from exc

    return CustomerMemoryResponse(
        customer_id=profile.customer_id,
        profile=profile.profile,
        risk_tags=profile.risk_tags,
        business_flags=profile.business_flags,
        historical_case_refs=profile.historical_case_refs,
        version=profile.version,
    )


@router.get("/tickets/{ticket_id}/trace", response_model=TicketTraceResponse)
def get_ticket_trace(
    ticket_id: str,
    run_id: Optional[str] = Query(default=None),
    service: TicketApiService = Depends(get_ticket_api_service),
) -> TicketTraceResponse:
    try:
        ticket, run, events = service.get_ticket_trace(ticket_id, run_id=run_id)
    except TicketNotFoundError as exc:
        raise ApiError(
            code="not_found",
            message=str(exc),
            status_code=404,
            details={"ticket_id": exc.ticket_id},
        ) from exc
    except RunNotFoundError as exc:
        raise ApiError(
            code="not_found",
            message=str(exc),
            status_code=404,
            details={"ticket_id": exc.ticket_id, "run_id": exc.run_id},
        ) from exc

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
    summary = service.get_metrics_summary(
        from_time=from_time,
        to_time=to_time,
        route=route,
    )
    return MetricsSummaryResponse.model_validate(summary)
