import type { TicketListQuery } from "@/lib/api/types";

export const queryKeys = {
  dashboard: () => ["dashboard"] as const,
  opsStatus: ["ops-status"] as const,
  metricsSummary: (params: { from?: string; to?: string; route?: string } = {}) =>
    ["metrics-summary", params] as const,
  tickets: (query: TicketListQuery = {}) => ["tickets", query] as const,
  ticketSnapshot: (ticketId: string) => ["ticket", ticketId, "snapshot"] as const,
  ticketRuns: (ticketId: string, page = 1, pageSize = 20) =>
    ["ticket", ticketId, "runs", page, pageSize] as const,
  ticketDrafts: (ticketId: string) => ["ticket", ticketId, "drafts"] as const,
  ticketTrace: (ticketId: string, runId?: string) =>
    ["ticket", ticketId, "trace", runId ?? "latest"] as const,
};
