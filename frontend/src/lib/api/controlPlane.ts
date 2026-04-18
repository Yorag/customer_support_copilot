import { getApiBaseUrl } from "@/env";
import { ApiClient } from "@/lib/api/client";
import type {
  ApproveTicketRequest,
  CloseTicketRequest,
  EditAndApproveTicketRequest,
  EscalateTicketRequest,
  GmailScanPreviewRequest,
  GmailScanPreviewResponse,
  GmailScanRequest,
  GmailScanResponse,
  MetricsSummaryResponse,
  OpsStatusResponse,
  RetryTicketRequest,
  RewriteTicketRequest,
  RunTicketResponse,
  TicketActionResponse,
  TestEmailRequest,
  TestEmailResponse,
  TicketDraftsResponse,
  TicketListQuery,
  TicketListResponse,
  TicketRunsResponse,
  TicketSnapshotResponse,
  TicketTraceResponse,
} from "@/lib/api/types";

export function createControlPlaneApi(
  client = new ApiClient({ baseUrl: getApiBaseUrl() }),
) {
  function createActorHeaders(actorId: string) {
    return {
      "X-Actor-Id": actorId,
    };
  }

  return {
    listTickets(query: TicketListQuery = {}) {
      return client.get<TicketListResponse>("/tickets", query);
    },
    getTicketSnapshot(ticketId: string) {
      return client.get<TicketSnapshotResponse>(`/tickets/${ticketId}`);
    },
    getTicketRuns(ticketId: string, page = 1, pageSize = 20) {
      return client.get<TicketRunsResponse>(`/tickets/${ticketId}/runs`, {
        page,
        page_size: pageSize,
      });
    },
    getTicketDrafts(ticketId: string) {
      return client.get<TicketDraftsResponse>(`/tickets/${ticketId}/drafts`);
    },
    getTicketTrace(ticketId: string, runId?: string) {
      return client.get<TicketTraceResponse>(`/tickets/${ticketId}/trace`, {
        run_id: runId,
      });
    },
    getOpsStatus() {
      return client.get<OpsStatusResponse>("/ops/status");
    },
    getMetricsSummary(params: { from?: string; to?: string; route?: string } = {}) {
      return client.get<MetricsSummaryResponse>("/metrics/summary", params);
    },
    previewGmailScan(payload: GmailScanPreviewRequest) {
      return client.post<GmailScanPreviewResponse>("/ops/gmail/scan-preview", payload);
    },
    scanGmail(payload: GmailScanRequest) {
      return client.post<GmailScanResponse>("/ops/gmail/scan", payload);
    },
    createTestEmail(payload: TestEmailRequest) {
      return client.post<TestEmailResponse>("/dev/test-email", payload);
    },
    retryTicket(ticketId: string, payload: RetryTicketRequest) {
      return client.post<RunTicketResponse>(`/tickets/${ticketId}/retry`, payload);
    },
    approveTicket(ticketId: string, actorId: string, payload: ApproveTicketRequest) {
      return client.post<TicketActionResponse>(
        `/tickets/${ticketId}/approve`,
        payload,
        createActorHeaders(actorId),
      );
    },
    editAndApproveTicket(
      ticketId: string,
      actorId: string,
      payload: EditAndApproveTicketRequest,
    ) {
      return client.post<TicketActionResponse>(
        `/tickets/${ticketId}/edit-and-approve`,
        payload,
        createActorHeaders(actorId),
      );
    },
    rewriteTicket(ticketId: string, actorId: string, payload: RewriteTicketRequest) {
      return client.post<TicketActionResponse>(
        `/tickets/${ticketId}/rewrite`,
        payload,
        createActorHeaders(actorId),
      );
    },
    escalateTicket(ticketId: string, actorId: string, payload: EscalateTicketRequest) {
      return client.post<TicketActionResponse>(
        `/tickets/${ticketId}/escalate`,
        payload,
        createActorHeaders(actorId),
      );
    },
    closeTicket(ticketId: string, actorId: string, payload: CloseTicketRequest) {
      return client.post<TicketActionResponse>(
        `/tickets/${ticketId}/close`,
        payload,
        createActorHeaders(actorId),
      );
    },
  };
}

export const controlPlaneApi = createControlPlaneApi();
