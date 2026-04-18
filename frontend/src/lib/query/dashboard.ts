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
    note?: string;
  }>;
  qualityCards: Array<{
    label: string;
    value: string;
    note?: string;
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
  reliability: {
    summaryCards: Array<{
      label: string;
      value: string;
      note?: string;
      tone?: "default" | "accent" | "danger" | "success" | "muted";
    }>;
    dependencies: Array<{
      label: string;
      value: string;
      tone: "success" | "muted" | "danger";
    }>;
    watchItems: string[];
    failure: {
      title: string;
      detail: string;
      tone?: "default" | "accent" | "danger" | "success" | "muted";
    };
    scan: {
      title: string;
      detail: string;
      tone?: "default" | "accent" | "danger" | "success" | "muted";
    };
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

function getDependencyTone(value: string): "success" | "muted" | "danger" {
  const normalized = value.toLowerCase();

  if (normalized === "ok") {
    return "success";
  }

  if (normalized === "unknown") {
    return "muted";
  }

  return "danger";
}

function buildWatchList(opsStatus: OpsStatusResponse) {
  const items: string[] = [];

  if (opsStatus.worker.healthy !== true) {
    items.push("当前 Worker 健康状态未被报告为健康。");
  }
  if (opsStatus.queue.error_tickets > 0) {
    items.push(`当前有 ${opsStatus.queue.error_tickets} 个工单处于错误状态。`);
  }
  if (opsStatus.queue.waiting_external_tickets > 0) {
    items.push(`当前有 ${opsStatus.queue.waiting_external_tickets} 个工单正在等待外部跟进。`);
  }
  if (opsStatus.recent_failure) {
    items.push(`最近失败运行 ${opsStatus.recent_failure.run_id} 需要继续复盘。`);
  }
  if (opsStatus.dependencies.gmail !== "ok") {
    items.push(`Gmail 依赖状态为 ${labelForCode(opsStatus.dependencies.gmail)}。`);
  }
  if (opsStatus.dependencies.llm !== "ok") {
    items.push(`LLM 依赖状态为 ${labelForCode(opsStatus.dependencies.llm)}。`);
  }
  if (opsStatus.dependencies.database !== "ok") {
    items.push(`数据库依赖状态为 ${labelForCode(opsStatus.dependencies.database)}。`);
  }
  if (opsStatus.dependencies.checkpointing !== "ok") {
    items.push(`Checkpointing 依赖状态为 ${labelForCode(opsStatus.dependencies.checkpointing)}。`);
  }
  if (items.length === 0) {
    items.push("当前控制面没有报告任何降级信号。");
  }

  return items;
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
    const processingLabel = labelForCode(ticket.processing_status);
    const runLabel = labelForCode(runStatus, processingLabel);
    const businessLabel = labelForCode(ticket.business_status);
    const draftLabel = labelForCode(draftStatus, "暂无草稿");

    return {
      id: ticket.ticket_id,
      title: ticket.subject,
      meta:
        variant === "review"
          ? `${ticket.ticket_id} · ${formatTimestamp(ticket.updated_at)}`
          : `${ticket.ticket_id} · ${labelForCode(route, "待定路由")} · ${formatTimestamp(ticket.updated_at)}`,
      emphasis:
        variant === "review"
          ? `${businessLabel} · ${draftLabel}`
          : runLabel === processingLabel
            ? processingLabel
            : `${runLabel} · ${processingLabel}`,
    };
  });
}

export function buildDashboardViewModel(data: DashboardData): DashboardViewModel {
  const { opsStatus, metricsSummary, recentTickets, reviewQueue } = data;
  const responseQualityScore = metricsSummary.response_quality.avg_overall_score;
  const trajectoryScore = metricsSummary.trajectory_evaluation.avg_score;
  const hasResponseQuality = responseQualityScore !== null && responseQualityScore !== undefined;
  const dependencies = [
    ["Database", opsStatus.dependencies.database],
    ["Gmail", opsStatus.dependencies.gmail],
    ["LLM", opsStatus.dependencies.llm],
    ["Checkpointing", opsStatus.dependencies.checkpointing],
  ] as const;
  const degradedDependencies = dependencies.filter(([, value]) => value !== "ok");
  const watchItems = buildWatchList(opsStatus);

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
    qualityCards: [
      ...(hasResponseQuality
        ? [
            {
              label: "回复质量",
              value: formatScore(responseQualityScore),
              note: "24 小时平均得分",
            },
          ]
        : []),
      {
        label: "轨迹评分",
        value: formatScore(trajectoryScore),
        note: "工作流正确性",
      },
      {
        label: "P50 延迟",
        value: `${formatNumber(metricsSummary.latency.p50_ms)} ms`,
        note: "当前指标窗口",
      },
      {
        label: "Token 覆盖",
        value: formatPercent(metricsSummary.resources.avg_token_coverage_ratio),
        note: "资源信号完整度",
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
        summary: hasResponseQuality
          ? `质量 ${formatScore(responseQualityScore)}，轨迹 ${formatScore(trajectoryScore)}，P50 延迟 ${formatNumber(metricsSummary.latency.p50_ms)} ms。`
          : `轨迹 ${formatScore(trajectoryScore)}，P50 延迟 ${formatNumber(metricsSummary.latency.p50_ms)} ms，质量评分当前未启用。`,
        detail: `当前指标窗口内 token 覆盖率为 ${formatPercent(metricsSummary.resources.avg_token_coverage_ratio)}。`,
      },
    ],
    feeds: {
      recentTickets: buildTicketFeedItems(recentTickets.items, "recent"),
      reviewQueue: buildTicketFeedItems(reviewQueue.items, "review"),
    },
    reliability: {
      summaryCards: [
        {
          label: "Worker",
          value: describeWorkerHealth(opsStatus),
          tone:
            opsStatus.worker.healthy === true
              ? "success"
              : opsStatus.worker.healthy === false
                ? "danger"
                : "muted",
        },
        {
          label: "依赖",
          value:
            degradedDependencies.length === 0
              ? `${dependencies.length} 项正常`
              : `${degradedDependencies.length} 项需关注`,
          tone: degradedDependencies.length === 0 ? "success" : "danger",
        },
        {
          label: "最近失败",
          value: opsStatus.recent_failure ? labelForCode(opsStatus.recent_failure.error_code, "unknown_error") : "无失败交接",
          tone: opsStatus.recent_failure ? "danger" : "muted",
        },
        {
          label: "最近扫描",
          value: labelForCode(opsStatus.gmail.last_scan_status ?? "no_signal"),
          tone: opsStatus.gmail.enabled ? "accent" : "muted",
        },
      ],
      dependencies: dependencies.map(([label, value]) => ({
        label,
        value: labelForCode(value),
        tone: getDependencyTone(value),
      })),
      watchItems,
      failure: {
        title: opsStatus.recent_failure
          ? `${opsStatus.recent_failure.run_id} · ${labelForCode(opsStatus.recent_failure.error_code, "unknown_error")}`
          : "当前没有失败交接项",
        detail: opsStatus.recent_failure
          ? `工单 ${opsStatus.recent_failure.ticket_id} · trace ${opsStatus.recent_failure.trace_id} · ${formatTimestamp(opsStatus.recent_failure.occurred_at)}`
          : "一旦状态 payload 含有失败记录，这里会显示最近失败运行。",
        tone: opsStatus.recent_failure ? "danger" : "muted",
      },
      scan: {
        title: opsStatus.gmail.enabled
          ? `${labelForCode(opsStatus.gmail.last_scan_status, "未知")} · ${formatTimestamp(opsStatus.gmail.last_scan_at)}`
          : "当前运行时已禁用邮箱摄入",
        detail: opsStatus.gmail.account_email
          ? `${opsStatus.gmail.account_email} · 依赖状态 ${labelForCode(opsStatus.dependencies.gmail)}`
          : `依赖状态 ${labelForCode(opsStatus.dependencies.gmail)}`,
        tone: opsStatus.gmail.enabled ? "accent" : "muted",
      },
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
