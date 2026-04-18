import { useQuery } from "@tanstack/react-query";

import { controlPlaneApi } from "@/lib/api/controlPlane";
import { queryKeys } from "@/lib/query/keys";

const DEFAULT_TRACE_WINDOW_HOURS = 24;

export function buildTraceMetricsWindow(hours = DEFAULT_TRACE_WINDOW_HOURS) {
  const to = new Date();
  const from = new Date(to.getTime() - hours * 60 * 60 * 1000);

  return {
    from: from.toISOString(),
    to: to.toISOString(),
  };
}

export function useTicketTrace(ticketId: string, runId?: string) {
  return useQuery({
    queryKey: queryKeys.ticketTrace(ticketId, runId),
    queryFn: () => controlPlaneApi.getTicketTrace(ticketId, runId),
    enabled: ticketId.length > 0,
  });
}

export function useTraceMetrics(window: { from: string; to: string }, enabled = true) {
  return useQuery({
    queryKey: queryKeys.metricsSummary(window),
    queryFn: () => controlPlaneApi.getMetricsSummary(window),
    enabled,
  });
}
