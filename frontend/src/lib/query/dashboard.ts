import { useQuery } from "@tanstack/react-query";

import { controlPlaneApi } from "@/lib/api/controlPlane";
import type {
  MetricsSummaryResponse,
  OpsStatusResponse,
  TicketListItem,
  TicketListResponse,
} from "@/lib/api/types";
import { queryKeys } from "@/lib/query/keys";
import {
  formatNumberZh,
  formatPercentZh,
  formatRelativeTimeZh,
  formatScoreZh,
  formatTimestampZh,
  labelForCode,
} from "@/lib/presentation";

const DEFAULT_DASHBOARD_WINDOW_HOURS = 24;
const RECENT_TICKETS_PAGE_SIZE = 5;
const REVIEW_QUEUE_PAGE_SIZE = 5;

export type DashboardData = {
  opsStatus: OpsStatusResponse;
  metricsSummary: MetricsSummaryResponse;
  recentTickets: TicketListResponse;
  reviewQueue: TicketListResponse;
};

export type DashboardViewModel = {
  hero: {
    gmailLabel: string;
    workerLabel: string;
    queueLabel: string;
    scanLabel: string;
  };
  metrics: Array<{
    label: string;
    value: string;
    note: string;
  }>;
  trendCards: Array<{
    label: string;
    title: string;
    chip: string;
    bars: number[];
    summary: string;
    detail: string;
  }>;
  feeds: {
    recentTickets: Array<{
      id: string;
      title: string;
      meta: string;
      emphasis: string;
    }>;
    reviewQueue: Array<{
      id: string;
      title: string;
      meta: string;
      emphasis: string;
    }>;
  };
  incidents: Array<{
    title: string;
    eyebrow: string;
    chip: string;
    summary: string;
    detail: string;
    bars: number[];
  }>;
};

function buildDashboardWindow(hours = DEFAULT_DASHBOARD_WINDOW_HOURS) {
  const to = new Date();
  const from = new Date(to.getTime() - hours * 60 * 60 * 1000);
  return {
    from: from.toISOString(),
    to: to.toISOString(),
  };
}

async function fetchDashboardData(): Promise<DashboardData> {
  const window = buildDashboardWindow();

  const [opsStatus, metricsSummary, recentTickets, reviewQueue] = await Promise.all([
    controlPlaneApi.getOpsStatus(),
    controlPlaneApi.getMetricsSummary(window),
    controlPlaneApi.listTickets({ page: 1, page_size: RECENT_TICKETS_PAGE_SIZE }),
    controlPlaneApi.listTickets({
      page: 1,
      page_size: REVIEW_QUEUE_PAGE_SIZE,
      awaiting_review: true,
    }),
  ]);

  return {
    opsStatus,
    metricsSummary,
    recentTickets,
    reviewQueue,
  };
}

export function useDashboardData() {
  return useQuery({
    queryKey: queryKeys.dashboard(),
    queryFn: fetchDashboardData,
  });
}

function formatRelativeMinutes(dateString?: string | null): string {
  return formatRelativeTimeZh(dateString);
}

function formatTimestamp(dateString?: string | null): string {
  return formatTimestampZh(dateString);
}

function formatNumber(value?: number | null, digits = 0): string {
  return formatNumberZh(value, digits);
}

function formatScore(value?: number | null): string {
  return formatScoreZh(value);
}

function formatPercent(value?: number | null): string {
  return formatPercentZh(value);
}

function formatMetricBar(value?: number | null, divisor = 1, fallback = 28): number {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return fallback;
  }

  const normalized = Math.round(value / divisor);
  return Math.max(18, Math.min(92, normalized));
}

function describeWorkerHealth(opsStatus: OpsStatusResponse): string {
  if (opsStatus.worker.healthy === true) {
    const count = opsStatus.worker.worker_count ?? 0;
    return `${count} 个 Worker 健康`;
  }
  if (opsStatus.worker.healthy === false) {
    return "Worker 需要关注";
  }
  return "心跳信号未接入";
}

function describeScanStatus(opsStatus: OpsStatusResponse): string {
  if (!opsStatus.gmail.enabled) {
    return "Gmail 已禁用";
  }
  if (opsStatus.gmail.last_scan_at) {
    return `${labelForCode(opsStatus.gmail.last_scan_status, "最近扫描")} · ${formatRelativeMinutes(opsStatus.gmail.last_scan_at)}`;
  }
  return "尚无扫描记录";
}

function buildTicketFeedItems(
  items: TicketListItem[],
  variant: "recent" | "review",
): Array<{
  id: string;
  title: string;
  meta: string;
  emphasis: string;
}> {
  return items.map((ticket) => {
    const route = ticket.primary_route ?? "route_pending";
    const runStatus = ticket.latest_run?.status ?? "no_run";
    const draftStatus = ticket.latest_draft?.qa_status ?? "no_draft";

    return {
      id: ticket.ticket_id,
      title: ticket.subject,
      meta:
        variant === "review"
          ? `${ticket.ticket_id} · ${ticket.customer_email_raw} · ${formatTimestamp(ticket.updated_at)}`
          : `${ticket.ticket_id} · ${labelForCode(route, "待定路由")} · ${formatTimestamp(ticket.updated_at)}`,
      emphasis:
        variant === "review"
          ? `审核：${labelForCode(ticket.business_status)} · 草稿：${labelForCode(draftStatus, "暂无草稿")}`
          : `运行：${labelForCode(runStatus, "暂无运行")} · ${labelForCode(ticket.processing_status)}`,
    };
  });
}

export function buildDashboardViewModel(data: DashboardData): DashboardViewModel {
  const { opsStatus, metricsSummary, recentTickets, reviewQueue } = data;
  const responseQualityScore = metricsSummary.response_quality.avg_overall_score;
  const trajectoryScore = metricsSummary.trajectory_evaluation.avg_score;

  return {
    hero: {
      gmailLabel: opsStatus.gmail.enabled ? "已连接" : "已禁用",
      workerLabel: describeWorkerHealth(opsStatus),
      queueLabel: `${opsStatus.queue.queued_runs} 个排队 / ${opsStatus.queue.running_runs} 个运行中`,
      scanLabel: describeScanStatus(opsStatus),
    },
    metrics: [
      {
        label: "工单总量",
        value: formatNumber(recentTickets.total),
        note: `最近 ${recentTickets.items.length} 条已载入。`,
      },
      {
        label: "运行中任务",
        value: formatNumber(opsStatus.queue.running_runs),
        note: `排队 ${formatNumber(opsStatus.queue.queued_runs)} 个。`,
      },
      {
        label: "待审核",
        value: formatNumber(reviewQueue.total),
        note: `当前展示 ${reviewQueue.items.length} 条。`,
      },
      {
        label: "错误任务",
        value: formatNumber(opsStatus.queue.error_tickets),
        note: opsStatus.recent_failure
          ? `最近失败 ${formatRelativeMinutes(opsStatus.recent_failure.occurred_at)}。`
          : "当前没有失败任务。",
      },
    ],
    trendCards: [
      {
        label: "队列趋势",
        title: "队列流动与任务吞吐",
        chip: "实时队列摘要",
        bars: [
          formatMetricBar(opsStatus.queue.queued_runs, 1.2, 32),
          formatMetricBar(opsStatus.queue.running_runs, 0.4, 48),
          formatMetricBar(opsStatus.queue.waiting_external_tickets, 0.8, 30),
          formatMetricBar(opsStatus.queue.error_tickets, 0.25, 22),
          formatMetricBar(opsStatus.queue.queued_runs + opsStatus.queue.running_runs, 1.5, 54),
        ],
        summary: `${formatNumber(opsStatus.queue.queued_runs)} 个排队，${formatNumber(opsStatus.queue.running_runs)} 个运行中，${formatNumber(opsStatus.queue.waiting_external_tickets)} 个等待外部处理。`,
        detail:
          opsStatus.worker.last_heartbeat_at !== null &&
          opsStatus.worker.last_heartbeat_at !== undefined
            ? `最近一次 Worker 心跳在 ${formatRelativeMinutes(opsStatus.worker.last_heartbeat_at)}。`
            : "尚未发布 Worker 心跳。",
      },
      {
        label: "质量与轨迹",
        title: "回复质量与工作流正确性",
        chip: "24 小时指标窗口",
        bars: [
          formatMetricBar(responseQualityScore, 0.06, 40),
          formatMetricBar(trajectoryScore, 0.06, 42),
          formatMetricBar(metricsSummary.latency.p50_ms, 20, 38),
          formatMetricBar(metricsSummary.latency.p95_ms, 40, 56),
          formatMetricBar(metricsSummary.resources.avg_token_coverage_ratio, 0.012, 30),
        ],
        summary: `质量 ${formatScore(responseQualityScore)}，轨迹 ${formatScore(trajectoryScore)}，P50 延迟 ${formatNumber(metricsSummary.latency.p50_ms)} ms。`,
        detail: `当前指标窗口内 token 覆盖率为 ${formatPercent(metricsSummary.resources.avg_token_coverage_ratio)}。`,
      },
    ],
    feeds: {
      recentTickets: buildTicketFeedItems(recentTickets.items, "recent"),
      reviewQueue: buildTicketFeedItems(reviewQueue.items, "review"),
    },
    incidents: [
      {
        title: "最近失败",
        eyebrow: "GET /ops/status",
        chip: "失败交接",
        summary: opsStatus.recent_failure
          ? `${opsStatus.recent_failure.ticket_id} 上的 ${opsStatus.recent_failure.run_id}`
          : "当前没有失败任务。",
        detail: opsStatus.recent_failure
          ? `${labelForCode(opsStatus.recent_failure.error_code, "unknown_error")} · ${formatTimestamp(opsStatus.recent_failure.occurred_at)} · ${opsStatus.recent_failure.trace_id}`
          : "Trace 看板当前没有失败压力。",
        bars: [
          formatMetricBar(opsStatus.queue.error_tickets, 0.25, 22),
          formatMetricBar(opsStatus.queue.running_runs, 0.4, 34),
          formatMetricBar(opsStatus.queue.waiting_external_tickets, 0.8, 28),
        ],
      },
      {
        title: "最近扫描结果",
        eyebrow: "GET /ops/status",
        chip: "邮箱状态",
        summary: opsStatus.gmail.enabled
          ? `${labelForCode(opsStatus.gmail.last_scan_status, "未知")} · ${formatTimestamp(opsStatus.gmail.last_scan_at)}`
          : "当前运行时已禁用邮箱摄入。",
        detail: opsStatus.gmail.account_email
          ? `${opsStatus.gmail.account_email} · 依赖状态 ${labelForCode(opsStatus.dependencies.gmail)}`
          : `依赖状态 ${labelForCode(opsStatus.dependencies.gmail)}。`,
        bars: [
          opsStatus.gmail.enabled ? 72 : 24,
          formatMetricBar(opsStatus.queue.queued_runs, 1.6, 30),
          opsStatus.dependencies.gmail === "ok" ? 82 : 34,
        ],
      },
    ],
  };
}
