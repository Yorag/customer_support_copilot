from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
from typing import NoReturn, Optional, Sequence

from fastapi import APIRouter, Depends, Query, status

from src.contracts.core import (
    RunTriggerType,
    TicketBusinessStatus,
    TicketProcessingStatus,
    TicketRoute,
    to_api_timestamp,
)
from src.config import get_settings
from src.tickets.message_log import IngestEmailPayload

from .dependencies import RequestContext, get_container, get_request_context
from .errors import ApiError
from .schemas import (
    ApproveTicketRequest,
    CloseTicketRequest,
    CustomerMemoryResponse,
    EditAndApproveTicketRequest,
    EscalateTicketRequest,
    GmailScanPreviewRequest,
    GmailScanPreviewResponse,
    GmailScanPreviewItem,
    GmailScanPreviewSummary,
    GmailScanRequest,
    GmailScanResponse,
    GmailScanItem,
    GmailScanSummary,
    IngestEmailRequest,
    IngestEmailResponse,
    MetricsSummaryResponse,
    OpsStatusDependencies,
    OpsStatusGmail,
    OpsStatusQueue,
    OpsStatusRecentFailure,
    OpsStatusResponse,
    OpsStatusWorker,
    RetryTicketRequest,
    RewriteTicketRequest,
    RunTicketRequest,
    RunTicketResponse,
    TestEmailMetadata,
    TestEmailRequest,
    TestEmailResponse,
    TestEmailRunResult,
    TestEmailTicketResult,
    TicketActionResponse,
    TicketDraftDetail,
    TicketDraftsResponse,
    TicketListItem,
    TicketListResponse,
    TicketDraftSummary,
    TicketMessage,
    TicketRunHistoryItem,
    TicketRunSummary,
    TicketRunsResponse,
    TicketSnapshotResponse,
    TicketSummary,
    TicketTraceResponse,
    TraceEventResponse,
)
from .services import (
    CustomerNotFoundError,
    DuplicateRequestError,
    GmailDisabledError,
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
    if isinstance(exc, GmailDisabledError):
        raise ApiError(
            code="invalid_state_transition",
            message=str(exc),
            status_code=409,
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
            GmailDisabledError,
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


def _validate_optional_enum_query(
    *,
    value: Optional[str],
    field_name: str,
    allowed_values: Sequence[str],
) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized not in allowed_values:
        raise ApiError(
            code="validation_error",
            message=f"`{field_name}` must be one of the supported values.",
            status_code=422,
            details={
                "query": field_name,
                "allowed_values": list(allowed_values),
            },
        )
    return normalized


def _serialize_datetime(value: datetime) -> str:
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return to_api_timestamp(normalized)


def _serialize_optional_datetime(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return _serialize_datetime(value)


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


@router.post(
    "/ops/gmail/scan-preview",
    response_model=GmailScanPreviewResponse,
)
@_map_service_errors
def preview_gmail_scan(
    request: GmailScanPreviewRequest,
    service: TicketApiService = Depends(get_ticket_api_service),
    container=Depends(get_container),
) -> GmailScanPreviewResponse:
    result = service.preview_gmail_scan(max_results=request.max_results)
    return GmailScanPreviewResponse(
        gmail_enabled=container.gmail_enabled,
        requested_max_results=result.requested_max_results,
        summary=GmailScanPreviewSummary(
            candidate_threads=result.candidate_threads,
            skipped_existing_draft_threads=result.skipped_existing_draft_threads,
            skipped_self_sent_threads=result.skipped_self_sent_threads,
        ),
        items=[
            GmailScanPreviewItem(
                source_thread_id=item.source_thread_id,
                source_message_id=item.source_message_id,
                sender_email_raw=item.sender_email_raw,
                subject=item.subject,
                skip_reason=item.skip_reason,
            )
            for item in result.items
        ],
    )


@router.post(
    "/ops/gmail/scan",
    response_model=GmailScanResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@_map_service_errors
def scan_gmail(
    request: GmailScanRequest,
    service: TicketApiService = Depends(get_ticket_api_service),
    container=Depends(get_container),
) -> GmailScanResponse:
    result = service.scan_gmail(
        max_results=request.max_results,
        enqueue=request.enqueue,
    )
    return GmailScanResponse(
        scan_id=result.scan_id,
        status="accepted",
        gmail_enabled=container.gmail_enabled,
        requested_max_results=result.requested_max_results,
        enqueue=request.enqueue,
        summary=GmailScanSummary(
            fetched_threads=result.fetched_threads,
            ingested_tickets=result.ingested_tickets,
            queued_runs=result.queued_runs,
            skipped_existing_draft_threads=result.skipped_existing_draft_threads,
            skipped_self_sent_threads=result.skipped_self_sent_threads,
            errors=result.errors,
        ),
        items=[
            GmailScanItem(
                source_thread_id=item.source_thread_id,
                ticket_id=item.ticket_id,
                created_ticket=item.created_ticket,
                queued_run_id=item.queued_run_id,
            )
            for item in result.items
        ],
    )


@router.get("/ops/status", response_model=OpsStatusResponse)
@_map_service_errors
def get_ops_status(
    service: TicketApiService = Depends(get_ticket_api_service),
) -> OpsStatusResponse:
    result = service.get_ops_status()
    return OpsStatusResponse(
        gmail=OpsStatusGmail(
            enabled=result.gmail_enabled,
            account_email=result.gmail_account_email,
            last_scan_at=_serialize_optional_datetime(result.gmail_last_scan_at),
            last_scan_status=result.gmail_last_scan_status,
        ),
        worker=OpsStatusWorker(
            healthy=result.worker_healthy,
            worker_count=result.worker_count,
            last_heartbeat_at=_serialize_optional_datetime(result.worker_last_heartbeat_at),
        ),
        queue=OpsStatusQueue(
            queued_runs=result.queued_runs,
            running_runs=result.running_runs,
            waiting_external_tickets=result.waiting_external_tickets,
            error_tickets=result.error_tickets,
        ),
        dependencies=OpsStatusDependencies(
            database=result.database_status,
            gmail=result.gmail_dependency_status,
            llm=result.llm_dependency_status,
            checkpointing=result.checkpointing_status,
        ),
        recent_failure=(
            OpsStatusRecentFailure(
                ticket_id=result.recent_failure.ticket_id,
                run_id=result.recent_failure.run_id,
                trace_id=result.recent_failure.trace_id,
                error_code=result.recent_failure.error_code,
                occurred_at=_serialize_optional_datetime(result.recent_failure.occurred_at),
            )
            if result.recent_failure is not None
            else None
        ),
    )


@router.post("/dev/test-email", response_model=TestEmailResponse)
@_map_service_errors
def create_test_email(
    request: TestEmailRequest,
    service: TicketApiService = Depends(get_ticket_api_service),
) -> TestEmailResponse:
    result = service.create_test_email(
        sender_email_raw=request.sender_email_raw,
        subject=request.subject,
        body_text=request.body_text,
        references=request.references,
        auto_enqueue=request.auto_enqueue,
        scenario_label=request.scenario_label,
    )
    return TestEmailResponse(
        ticket=TestEmailTicketResult(
            ticket_id=result.ticket_id,
            created=result.created,
            business_status=result.business_status,
            processing_status=result.processing_status,
            version=result.version,
        ),
        run=(
            TestEmailRunResult(
                run_id=result.run_id,
                trace_id=result.trace_id,
                processing_status=result.processing_status,
            )
            if result.run_id is not None and result.trace_id is not None
            else None
        ),
        test_metadata=TestEmailMetadata(
            scenario_label=result.scenario_label,
            auto_enqueue=result.auto_enqueue,
            source_channel=result.source_channel,
        ),
    )


@router.get("/tickets", response_model=TicketListResponse)
@_map_service_errors
def list_tickets(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    business_status: Optional[str] = Query(default=None),
    processing_status: Optional[str] = Query(default=None),
    primary_route: Optional[str] = Query(default=None),
    has_draft: Optional[bool] = Query(default=None),
    awaiting_review: Optional[bool] = Query(default=None),
    query: Optional[str] = Query(default=None),
    service: TicketApiService = Depends(get_ticket_api_service),
) -> TicketListResponse:
    business_status = _validate_optional_enum_query(
        value=business_status,
        field_name="business_status",
        allowed_values=[item.value for item in TicketBusinessStatus],
    )
    processing_status = _validate_optional_enum_query(
        value=processing_status,
        field_name="processing_status",
        allowed_values=[item.value for item in TicketProcessingStatus],
    )
    primary_route = _validate_optional_enum_query(
        value=primary_route,
        field_name="primary_route",
        allowed_values=[item.value for item in TicketRoute],
    )
    query = query.strip() if query is not None else None
    if query == "":
        query = None

    result = service.list_tickets(
        page=page,
        page_size=page_size,
        business_status=business_status,
        processing_status=processing_status,
        primary_route=primary_route,
        has_draft=has_draft,
        awaiting_review=awaiting_review,
        query=query,
    )

    return TicketListResponse(
        items=[
            TicketListItem(
                ticket_id=item.ticket.ticket_id,
                customer_id=item.ticket.customer_id,
                customer_email_raw=item.ticket.customer_email_raw,
                subject=item.ticket.subject,
                business_status=item.ticket.business_status,
                processing_status=item.ticket.processing_status,
                priority=item.ticket.priority,
                primary_route=item.ticket.primary_route,
                multi_intent=item.ticket.multi_intent,
                version=item.ticket.version,
                updated_at=_serialize_datetime(item.ticket.updated_at),
                latest_run=(
                    TicketRunSummary(
                        run_id=item.latest_run.run_id,
                        trace_id=item.latest_run.trace_id,
                        status=item.latest_run.status,
                        final_action=item.latest_run.final_action,
                        evaluation_summary_ref=item.evaluation_summary_ref.__dict__,
                    )
                    if item.latest_run is not None and item.evaluation_summary_ref is not None
                    else None
                ),
                latest_draft=(
                    TicketDraftSummary(
                        draft_id=item.latest_draft.draft_id,
                        qa_status=item.latest_draft.qa_status,
                    )
                    if item.latest_draft is not None
                    else None
                ),
            )
            for item in result.items
        ],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get("/tickets/{ticket_id}/runs", response_model=TicketRunsResponse)
@_map_service_errors
def get_ticket_runs(
    ticket_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    service: TicketApiService = Depends(get_ticket_api_service),
) -> TicketRunsResponse:
    result = service.get_ticket_runs(ticket_id, page=page, page_size=page_size)
    return TicketRunsResponse(
        ticket_id=result.ticket_id,
        items=[
            TicketRunHistoryItem(
                run_id=item.run.run_id,
                trace_id=item.run.trace_id,
                trigger_type=item.run.trigger_type,
                triggered_by=item.run.triggered_by,
                status=item.run.status,
                final_action=item.run.final_action,
                started_at=_serialize_optional_datetime(item.run.started_at),
                ended_at=_serialize_optional_datetime(item.run.ended_at),
                attempt_index=item.run.attempt_index,
                is_human_action=item.run.trigger_type == RunTriggerType.HUMAN_ACTION.value,
                evaluation_summary_ref=item.evaluation_summary_ref.__dict__,
            )
            for item in result.items
        ],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get("/tickets/{ticket_id}/drafts", response_model=TicketDraftsResponse)
@_map_service_errors
def get_ticket_drafts(
    ticket_id: str,
    service: TicketApiService = Depends(get_ticket_api_service),
) -> TicketDraftsResponse:
    result = service.get_ticket_drafts(ticket_id)
    return TicketDraftsResponse(
        ticket_id=result.ticket_id,
        items=[
            TicketDraftDetail(
                draft_id=item.draft_id,
                run_id=item.run_id,
                version_index=item.version_index,
                draft_type=item.draft_type,
                qa_status=item.qa_status,
                content_text=item.content_text,
                source_evidence_summary=item.source_evidence_summary,
                gmail_draft_id=item.gmail_draft_id,
                created_at=_serialize_datetime(item.created_at),
            )
            for item in result.items
        ],
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
        messages,
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
        messages=[
            TicketMessage(
                ticket_message_id=item.ticket_message_id,
                run_id=item.run_id,
                draft_id=item.draft_id,
                source_message_id=item.source_message_id,
                direction=item.direction,
                message_type=item.message_type,
                sender_email=item.sender_email,
                recipient_emails=item.recipient_emails,
                subject=item.subject,
                body_text=item.body_text,
                reply_to_source_message_id=item.reply_to_source_message_id,
                customer_visible=item.customer_visible,
                message_timestamp=_serialize_datetime(item.message_timestamp),
                metadata=item.message_metadata,
            )
            for item in messages
        ],
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
    "/tickets/{ticket_id}/retry",
    response_model=RunTicketResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@_map_service_errors
def retry_ticket(
    ticket_id: str,
    request: RetryTicketRequest,
    context: RequestContext = Depends(get_request_context),
    service: TicketApiService = Depends(get_ticket_api_service),
) -> RunTicketResponse:
    result = service.retry_ticket(
        ticket_id=ticket_id,
        ticket_version=request.ticket_version,
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
