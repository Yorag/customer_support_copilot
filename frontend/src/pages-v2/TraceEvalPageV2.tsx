import { startTransition, useDeferredValue, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ApiClientError } from "@/lib/api/client";
import type {
  MetricsSummaryResponse,
  TicketRunHistoryItem,
  TicketTraceResponse,
  TraceEventResponse,
} from "@/lib/api/types";
import {
  formatNumberZh,
  formatScoreZh,
  formatTimestampZh,
  labelForCode,
} from "@/lib/presentation";
import { buildTraceMetricsWindow, useTicketTrace, useTraceMetrics } from "@/lib/query/trace";
import { useTicketRuns } from "@/lib/query/tickets";
import { useConsoleUiStore } from "@/state/console-ui-store";
import {
  EmptyState,
  Field,
  InfoTip,
  InlineNotice,
  Panel,
  StatusTag,
} from "@/ui-v2/primitives";

const TRACE_RUN_PAGE_SIZE = 12;
type TraceEventGroupKey = "decision" | "tool" | "model" | "worker";

type TraceNodeRecord = {
  id: string;
  key: string;
  occurrence: number;
  status: string;
  latencyMs: number | null;
  summary: string;
  issueCount: number;
  eventCount: number;
  nodeEvent: TraceEventResponse | null;
  activityEvents: TraceEventResponse[];
  events: TraceEventResponse[];
  groupKey: TraceEventGroupKey;
};

type TraceMetricCard = {
  label: string;
  value: string;
  note: string;
  tooltipTitle?: string;
  tooltipLines?: string[];
};

type TraceRunMetaCard = {
  label: string;
  value: string;
  code?: boolean;
  span?: "compact" | "wide";
};

const TRACE_EVENT_GROUPS: Array<{
  key: TraceEventGroupKey;
  label: string;
  note: string;
}> = [
  {
    key: "decision",
    label: "决策",
    note: "路由判断和节点推进放在一起看，先确认有没有跑偏。",
  },
  {
    key: "tool",
    label: "工具",
    note: "检索、读写、上下文装配这类外部调用。",
  },
  {
    key: "model",
    label: "模型",
    note: "提示词、判定、评分和模型返回状态。",
  },
  {
    key: "worker",
    label: "Worker",
    note: "执行器、租约和检查点恢复轨迹。",
  },
];

function shortenId(value?: string | null) {
  if (!value) {
    return "--";
  }
  if (value.length <= 18) {
    return value;
  }
  return `${value.slice(0, 12)}...${value.slice(-4)}`;
}

function formatTimestamp(value?: string | null) {
  return formatTimestampZh(value, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatNumber(value?: number | null, digits = 0) {
  return formatNumberZh(value, digits);
}

function formatScore(value?: number | null) {
  return formatScoreZh(value);
}

function getErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiClientError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return fallback;
}

function summarizeMetadata(metadata?: Record<string, unknown> | null) {
  if (!metadata || Object.keys(metadata).length === 0) {
    return "该事件没有发布额外元数据。";
  }

  const entries = Object.entries(metadata)
    .slice(0, 3)
    .map(([key, value]) => {
      if (Array.isArray(value)) {
        return `${key}: ${value.length} 项`;
      }
      if (value && typeof value === "object") {
        return `${key}: 对象`;
      }
      return `${key}: ${String(value)}`;
    });

  return entries.join(" · ");
}

function formatMetadataValue(key: string, value: unknown) {
  if (value === null || value === undefined) {
    return "--";
  }

  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }

  if (typeof value === "number") {
    return formatNumber(value);
  }

  if (Array.isArray(value)) {
    return value.map((item) => String(item)).join(" · ");
  }

  if (typeof value === "string") {
    if (key.endsWith("_at") || key.includes("expires_at")) {
      return formatTimestamp(value);
    }
    if (
      key.includes("route") ||
      key.includes("action") ||
      key === "token_source" ||
      key === "judge_status" ||
      key === "response_strategy"
    ) {
      return labelForCode(value, value);
    }
    return value;
  }

  return JSON.stringify(value);
}

function buildEventSignals(event: TraceEventResponse) {
  const metadata = (event.metadata ?? {}) as Record<string, unknown>;

  if (event.event_type === "llm_call") {
    return [
      typeof metadata.model === "string" ? metadata.model : null,
      typeof metadata.prompt_version === "string" ? metadata.prompt_version : null,
      typeof metadata.judge_status === "string"
        ? `Judge ${labelForCode(metadata.judge_status, metadata.judge_status)}`
        : null,
    ].filter(Boolean) as string[];
  }

  if (event.event_type === "tool_call") {
    return [
      typeof metadata.tool_name === "string" ? metadata.tool_name : null,
      typeof metadata.input_ref === "string" ? `输入 ${shortenId(metadata.input_ref)}` : null,
      typeof metadata.output_ref === "string" ? `输出 ${shortenId(metadata.output_ref)}` : null,
    ].filter(Boolean) as string[];
  }

  if (event.event_type === "decision") {
    return [
      typeof metadata.primary_route === "string"
        ? labelForCode(metadata.primary_route, metadata.primary_route)
        : null,
      typeof metadata.final_action === "string"
        ? labelForCode(metadata.final_action, metadata.final_action)
        : null,
      typeof metadata.needs_escalation === "boolean"
        ? metadata.needs_escalation
          ? "需要升级"
          : "无需升级"
        : null,
    ].filter(Boolean) as string[];
  }

  if (event.event_type === "checkpoint") {
    return [
      typeof metadata.restore_mode === "string" ? metadata.restore_mode : null,
      typeof metadata.restored === "boolean" ? (metadata.restored ? "已恢复" : "未恢复") : null,
    ].filter(Boolean) as string[];
  }

  if (event.event_type === "worker") {
    return [
      typeof metadata.worker_id === "string" ? metadata.worker_id : null,
      typeof metadata.lease_owner === "string" ? `租约 ${metadata.lease_owner}` : null,
    ].filter(Boolean) as string[];
  }

  if (event.event_type === "node") {
    return [
      event.node_name ? `节点 ${labelForCode(event.node_name)}` : null,
      typeof metadata.error_message === "string" ? metadata.error_message : null,
    ].filter(Boolean) as string[];
  }

  if (event.status.toLowerCase() === "failed" || event.status.toLowerCase() === "error") {
    return [typeof metadata.error_message === "string" ? metadata.error_message : "失败节点"];
  }

  return [];
}

function buildEventInspectorFields(event: TraceEventResponse) {
  const metadata = (event.metadata ?? {}) as Record<string, unknown>;
  const orderedKeysByType: Record<string, string[]> = {
    llm_call: [
      "model",
      "provider",
      "prompt_version",
      "judge_status",
      "request_id",
      "finish_reason",
      "token_source",
      "prompt_tokens",
      "completion_tokens",
      "total_tokens",
      "error_message",
    ],
    tool_call: ["tool_name", "input_ref", "output_ref"],
    decision: [
      "primary_route",
      "response_strategy",
      "final_action",
      "needs_clarification",
      "needs_escalation",
      "error_message",
    ],
    checkpoint: ["thread_id", "checkpoint_ns", "restore_mode", "restored"],
    worker: ["worker_id", "lease_owner", "lease_expires_at", "ticket_id", "run_id"],
    node: ["error_message"],
  };

  const orderedKeys = orderedKeysByType[event.event_type] ?? [];
  const seen = new Set<string>();
  const fields: Array<{ label: string; value: string }> = [];

  for (const key of orderedKeys) {
    if (key in metadata) {
      seen.add(key);
      fields.push({
        label: key,
        value: formatMetadataValue(key, metadata[key]),
      });
    }
  }

  for (const [key, value] of Object.entries(metadata)) {
    if (seen.has(key)) {
      continue;
    }
    fields.push({
      label: key,
      value: formatMetadataValue(key, value),
    });
  }

  return fields;
}

function getEventTone(event: TraceEventResponse) {
  const normalizedStatus = event.status.toLowerCase();

  if (normalizedStatus === "failed" || normalizedStatus === "error") {
    return "danger" as const;
  }

  if (event.event_type.toLowerCase() === "llm_call" || event.event_type.toLowerCase() === "tool_call") {
    return "accent" as const;
  }

  return "muted" as const;
}

function getStatusTone(status?: string | null) {
  const normalizedStatus = (status ?? "").toLowerCase();

  if (normalizedStatus === "failed" || normalizedStatus === "error" || normalizedStatus === "timed_out") {
    return "danger" as const;
  }

  if (normalizedStatus === "succeeded" || normalizedStatus === "completed") {
    return "success" as const;
  }

  return "muted" as const;
}

function getRunTone(status?: string | null) {
  return getStatusTone(status);
}

function isFailedStatus(status?: string | null) {
  const normalizedStatus = (status ?? "").toLowerCase();
  return normalizedStatus === "failed" || normalizedStatus === "error";
}

function parseTimestampMs(value?: string | null) {
  if (!value) {
    return null;
  }

  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function getNodeGroupKey(nodeKey: string, events: TraceEventResponse[]): TraceEventGroupKey {
  if (
    nodeKey === "ticket_worker" ||
    nodeKey === "run_ticket" ||
    events.some((event) => event.event_type === "worker" || event.event_type === "checkpoint")
  ) {
    return "worker";
  }

  if (events.some((event) => event.event_type === "llm_call")) {
    return "model";
  }

  if (events.some((event) => event.event_type === "tool_call")) {
    return "tool";
  }

  return "decision";
}

function buildNodeLatencyMs(nodeEvent: TraceEventResponse | null, events: TraceEventResponse[]) {
  if (nodeEvent?.latency_ms !== null && nodeEvent?.latency_ms !== undefined) {
    return nodeEvent.latency_ms;
  }

  const starts = events
    .map((event) => parseTimestampMs(event.start_time))
    .filter((value): value is number => value !== null);
  const ends = events
    .map((event) => parseTimestampMs(event.end_time ?? event.start_time))
    .filter((value): value is number => value !== null);

  if (starts.length === 0 || ends.length === 0) {
    return null;
  }

  return Math.max(0, Math.round(Math.max(...ends) - Math.min(...starts)));
}

function buildNodeStatus(nodeEvent: TraceEventResponse | null, events: TraceEventResponse[]) {
  const latestFailure = [...events].reverse().find((event) => isFailedStatus(event.status));
  if (latestFailure) {
    return latestFailure.status;
  }

  if (nodeEvent?.status) {
    return nodeEvent.status;
  }

  return events[events.length - 1]?.status ?? "unknown";
}

function buildNodeSummary(
  nodeKey: string,
  nodeEvent: TraceEventResponse | null,
  activityEvents: TraceEventResponse[],
) {
  const nodeMetadata = (nodeEvent?.metadata ?? {}) as Record<string, unknown>;
  if (Object.keys(nodeMetadata).length > 0) {
    return summarizeMetadata(nodeMetadata);
  }

  const preferredEvent =
    activityEvents.find((event) => event.event_type === "decision") ??
    activityEvents.find((event) => event.event_type === "llm_call") ??
    activityEvents.find((event) => event.event_type === "tool_call") ??
    activityEvents[0];

  if (preferredEvent) {
    return buildEventCardSummary(preferredEvent);
  }

  return `节点 ${nodeKey}`;
}

function buildNodeEventMix(events: TraceEventResponse[]) {
  const counts = new Map<string, number>();

  for (const event of events) {
    const count = counts.get(event.event_type) ?? 0;
    counts.set(event.event_type, count + 1);
  }

  return [...counts.entries()]
    .map(([eventType, count]) => `${labelForCode(eventType, eventType)} ${count}`)
    .join(" · ");
}

function buildNodeRecords(events: TraceEventResponse[]): TraceNodeRecord[] {
  const records: Array<{ key: string; events: TraceEventResponse[] }> = [];

  for (const event of events) {
    const key = event.node_name ?? event.event_name;
    if (!key) {
      continue;
    }

    const current = records[records.length - 1];
    const shouldStartNewRecord =
      !current ||
      current.key !== key ||
      (event.event_type === "node" &&
        current.events.some((currentEvent) => currentEvent.event_type === "node"));

    if (shouldStartNewRecord) {
      records.push({ key, events: [event] });
      continue;
    }

    current.events.push(event);
  }

  const occurrenceByKey = new Map<string, number>();

  return records.map((record) => {
    const occurrence = (occurrenceByKey.get(record.key) ?? 0) + 1;
    occurrenceByKey.set(record.key, occurrence);

    const nodeEvent =
      [...record.events].reverse().find((event) => event.event_type === "node") ?? null;
    const activityEvents = record.events.filter((event) => event.event_type !== "node");
    const status = buildNodeStatus(nodeEvent, record.events);
    const latencyMs = buildNodeLatencyMs(nodeEvent, record.events);

    return {
      id: `${record.key}:${occurrence}`,
      key: record.key,
      occurrence,
      status,
      latencyMs,
      summary: buildNodeSummary(record.key, nodeEvent, activityEvents),
      issueCount: record.events.filter((event) => isFailedStatus(event.status)).length,
      eventCount: record.events.length,
      nodeEvent,
      activityEvents,
      events: record.events,
      groupKey: getNodeGroupKey(record.key, record.events),
    };
  });
}

function buildEventCardSummary(event: TraceEventResponse) {
  const signals = buildEventSignals(event);
  if (signals.length > 0) {
    return signals.join(" · ");
  }

  const metadata = (event.metadata ?? {}) as Record<string, unknown>;
  if (Object.keys(metadata).length > 0) {
    return summarizeMetadata(metadata);
  }

  if (event.node_name) {
    return `节点 ${event.node_name}`;
  }

  return `状态 ${labelForCode(event.status)}`;
}

function extractTrajectoryRoute(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => String(item))
    .filter((item) => item.length > 0 && item !== "run_ticket");
}

function buildTrajectoryHighlights(
  trace: TicketTraceResponse | undefined,
  events: TraceEventResponse[],
) {
  const trajectory = (trace?.trajectory_evaluation ?? {}) as Record<string, unknown>;
  const actualRoute = extractTrajectoryRoute(trajectory.actual_route);
  const expectedRoute = extractTrajectoryRoute(trajectory.expected_route);
  const violations = Array.isArray(trajectory.violations)
    ? trajectory.violations.map((item) => String(item))
    : [];
  const fallbackRoute = events
    .filter((event) => event.status.toLowerCase() === "succeeded")
    .map((event) => event.node_name ?? event.event_name)
    .filter((name): name is string => Boolean(name) && name !== "run_ticket");
  const currentRoute =
    actualRoute.length > 0 ? actualRoute : expectedRoute.length > 0 ? expectedRoute : fallbackRoute;

  return {
    currentRoute:
      currentRoute.length > 0
        ? currentRoute.join(" -> ")
        : "暂无轨迹",
    violations,
  };
}

function buildEventTitle(event: TraceEventResponse | undefined) {
  if (!event) {
    return "选中一个阶段后再查看详情";
  }

  if (event.event_type === "tool_call") {
    const metadata = (event.metadata ?? {}) as Record<string, unknown>;
    if (typeof metadata.tool_name === "string") {
      return metadata.tool_name;
    }
  }

  return event.event_name;
}

function buildNodeRawRecord(
  node: TraceNodeRecord | null,
  trace: TicketTraceResponse | undefined,
) {
  if (!node) {
    return "";
  }

  return JSON.stringify(
    {
      node: {
        key: node.key,
        occurrence: node.occurrence,
        status: node.status,
        latency_ms: node.latencyMs,
        event_count: node.eventCount,
        node_event: node.nodeEvent,
      },
      events: node.events,
      run_context: trace
        ? {
            trace_id: trace.trace_id,
            run_id: trace.run_id,
            trajectory_evaluation: trace.trajectory_evaluation,
            ...(trace.response_quality
              ? { response_quality: trace.response_quality }
              : {}),
          }
        : null,
    },
    null,
    2,
  );
}

function buildResponseQualityTooltip(trace: TicketTraceResponse | undefined) {
  const responseQuality = (trace?.response_quality ?? {}) as Record<string, unknown>;
  const subscores =
    responseQuality.subscores && typeof responseQuality.subscores === "object"
      ? (responseQuality.subscores as Record<string, unknown>)
      : null;
  const lines = [
    "1-5 分，四个维度等权平均。",
    "overall_score = round((relevance + correctness + intent_alignment + clarity) / 4, 2)",
  ];

  if (subscores) {
    lines.push(
      `本次子分：相关性 ${String(subscores.relevance ?? "--")} · 正确性 ${String(subscores.correctness ?? "--")} · 意图对齐 ${String(subscores.intent_alignment ?? "--")} · 清晰度 ${String(subscores.clarity ?? "--")}`,
    );
  }

  return {
    title: "回复质量评分说明",
    lines,
  };
}

function buildTrajectoryTooltip(trace: TicketTraceResponse | undefined) {
  const trajectory = (trace?.trajectory_evaluation ?? {}) as Record<string, unknown>;
  const violations = Array.isArray(trajectory.violations)
    ? trajectory.violations
        .map((item) =>
          item && typeof item === "object" && "type" in item
            ? String((item as Record<string, unknown>).type)
            : String(item),
        )
        .slice(0, 3)
    : [];

  const lines = [
    "初始分 5.0，按违规类型扣分，最低 0。",
    "missing_required_node -1.5 · wrong_order -1.0 · missed_escalation -2.0 · missed_clarification -2.0 · unexpected_auto_draft -1.5",
  ];

  if (violations.length > 0) {
    lines.push(`本次违规：${violations.join(" · ")}`);
  }

  return {
    title: "轨迹符合度评分说明",
    lines,
  };
}

function buildTraceMetricCards(
  trace: TicketTraceResponse | undefined,
  metrics: MetricsSummaryResponse | undefined,
): TraceMetricCard[] {
  const latencyMetrics = (trace?.latency_metrics ?? {}) as Record<string, unknown>;
  const resourceMetrics = (trace?.resource_metrics ?? {}) as Record<string, unknown>;
  const responseQuality = (trace?.response_quality ?? {}) as Record<string, unknown>;
  const trajectory = (trace?.trajectory_evaluation ?? {}) as Record<string, unknown>;
  const cards: TraceMetricCard[] = [
    {
      label: "端到端延迟",
      value:
        latencyMetrics.end_to_end_ms !== undefined && latencyMetrics.end_to_end_ms !== null
          ? `${formatNumber(Number(latencyMetrics.end_to_end_ms))} ms`
          : "等待 Trace",
      note: trace
        ? `最慢节点 ${labelForCode(String(latencyMetrics.slowest_node ?? "not_available"))}`
        : "等待运行",
    },
    {
      label: "资源消耗",
      value:
        resourceMetrics.total_tokens !== undefined && resourceMetrics.total_tokens !== null
          ? `${formatNumber(Number(resourceMetrics.total_tokens))} tokens`
          : "等待 Trace",
      note: trace
        ? `${formatNumber(Number(resourceMetrics.llm_call_count ?? 0))} 次模型调用 · ${formatNumber(Number(resourceMetrics.tool_call_count ?? 0))} 次工具调用`
        : "等待运行",
    },
    {
      label: "轨迹符合度评分",
      value:
        trajectory.score !== undefined && trajectory.score !== null
          ? formatScore(Number(trajectory.score))
          : "未评分",
      note: trace
        ? `${Array.isArray(trajectory.violations) ? trajectory.violations.length : 0} 条违规`
        : "等待评分",
      tooltipTitle: buildTrajectoryTooltip(trace).title,
      tooltipLines: buildTrajectoryTooltip(trace).lines,
    },
  ];

  if (responseQuality.overall_score !== undefined && responseQuality.overall_score !== null) {
    cards.splice(2, 0, {
      label: "回复质量评分",
      value: formatScore(Number(responseQuality.overall_score)),
      note: trace ? String(responseQuality.reason ?? "无说明") : "等待评分",
      tooltipTitle: buildResponseQualityTooltip(trace).title,
      tooltipLines: buildResponseQualityTooltip(trace).lines,
    });
  }

  return cards;
}

function buildRunMetaCards(
  trace: TicketTraceResponse | undefined,
  selectedRun: TicketRunHistoryItem | undefined,
): TraceRunMetaCard[] {
  return [
    {
      label: "状态",
      value: selectedRun ? labelForCode(selectedRun.status) : "等待选择",
      span: "compact",
    },
    {
      label: "最终动作",
      value: selectedRun?.final_action ? labelForCode(selectedRun.final_action) : "--",
      span: "compact",
    },
    {
      label: "尝试次数",
      value: selectedRun ? `第 ${selectedRun.attempt_index} 次` : "--",
      span: "compact",
    },
    {
      label: "Trace 引用",
      value: trace?.trace_id ?? "等待 Trace 响应",
      code: true,
      span: "wide",
    },
  ];
}

function buildRunSummary(
  trace: TicketTraceResponse | undefined,
  selectedRun: TicketRunHistoryItem | undefined,
) {
  if (!trace) {
    return {
      title: "等待载入运行",
      detail: "输入工单 ID 后选择运行。",
    };
  }

  return {
    title: shortenId(trace.run_id),
    detail: selectedRun
      ? `${labelForCode(selectedRun.status)} · ${selectedRun.final_action ? labelForCode(selectedRun.final_action) : "未记录最终动作"} · 第 ${selectedRun.attempt_index} 次尝试`
      : `Trace ${shortenId(trace.trace_id)} 已载入，但当前没有匹配的运行摘要投影`,
  };
}

export function TraceEvalPageV2() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedTicketId = useConsoleUiStore((state) => state.selectedTicketId);
  const setSelectedTicketId = useConsoleUiStore((state) => state.setSelectedTicketId);
  const setSelectedRunId = useConsoleUiStore((state) => state.setSelectedRunId);

  const urlTicketId = searchParams.get("ticketId")?.trim() ?? "";
  const urlRunId = searchParams.get("runId")?.trim() ?? "";
  const activeTicketId = urlTicketId || selectedTicketId || "";
  const activeRunId = urlRunId;
  const [ticketInput, setTicketInput] = useState(activeTicketId);
  const [metricsWindow] = useState(() => buildTraceMetricsWindow());
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  useEffect(() => {
    setTicketInput(activeTicketId);
  }, [activeTicketId]);

  useEffect(() => {
    if (urlTicketId && urlTicketId !== selectedTicketId) {
      setSelectedTicketId(urlTicketId);
    }
  }, [selectedTicketId, setSelectedTicketId, urlTicketId]);

  useEffect(() => {
    if (urlRunId) {
      setSelectedRunId(urlRunId);
    }
  }, [setSelectedRunId, urlRunId]);

  const deferredTicketId = useDeferredValue(activeTicketId);
  const deferredRunId = useDeferredValue(activeRunId);
  const runsQuery = useTicketRuns(deferredTicketId, 1, TRACE_RUN_PAGE_SIZE);
  const traceQuery = useTicketTrace(deferredTicketId, deferredRunId || undefined);
  const metricsQuery = useTraceMetrics(metricsWindow, deferredTicketId.length > 0);

  const selectedRun =
    runsQuery.data?.items.find((item) => item.run_id === (traceQuery.data?.run_id ?? deferredRunId)) ??
    runsQuery.data?.items[0];
  const metricCards = buildTraceMetricCards(traceQuery.data, metricsQuery.data);
  const runMetaCards = buildRunMetaCards(traceQuery.data, selectedRun);
  const events = traceQuery.data?.events ?? [];
  const nodeRecords = buildNodeRecords(events);
  const runSummary = buildRunSummary(traceQuery.data, selectedRun);
  const trajectoryHighlights = buildTrajectoryHighlights(traceQuery.data, events);
  const selectedNode =
    nodeRecords.find((node) => node.id === selectedNodeId) ?? nodeRecords[0] ?? null;
  const selectedNodeFields =
    selectedNode?.nodeEvent ? buildEventInspectorFields(selectedNode.nodeEvent) : [];
  const selectedNodeRawRecord = buildNodeRawRecord(selectedNode, traceQuery.data);
  const hasTicketSelection = deferredTicketId.length > 0;
  const requestError = traceQuery.isError
    ? getErrorMessage(traceQuery.error, "Trace 请求失败。")
    : runsQuery.isError
      ? getErrorMessage(runsQuery.error, "运行历史请求失败。")
      : metricsQuery.isError
        ? getErrorMessage(metricsQuery.error, "指标请求失败。")
        : null;

  function updateSearch(nextTicketId: string | null, nextRunId: string | null) {
    const nextParams = new URLSearchParams();
    if (nextTicketId) {
      nextParams.set("ticketId", nextTicketId);
    }
    if (nextTicketId && nextRunId) {
      nextParams.set("runId", nextRunId);
    }
    setSearchParams(nextParams);
  }

  function handleTicketLoad() {
    const normalizedTicketId = ticketInput.trim();
    if (!normalizedTicketId) {
      return;
    }

    startTransition(() => {
      setSelectedTicketId(normalizedTicketId);
      setSelectedRunId(null);
      setSelectedNodeId(null);
      updateSearch(normalizedTicketId, null);
    });
  }

  function handleClearSelection() {
    startTransition(() => {
      setTicketInput("");
      setSelectedTicketId(null);
      setSelectedRunId(null);
      setSelectedNodeId(null);
      setSearchParams(new URLSearchParams());
    });
  }

  function handleRunSelection(nextRunId: string) {
    startTransition(() => {
      setSelectedRunId(nextRunId || null);
      setSelectedNodeId(null);
      updateSearch(activeTicketId, nextRunId || null);
    });
  }

  useEffect(() => {
    if (nodeRecords.length === 0) {
      setSelectedNodeId(null);
      return;
    }

    if (!selectedNodeId || !nodeRecords.some((node) => node.id === selectedNodeId)) {
      setSelectedNodeId(nodeRecords[0].id);
    }
  }, [nodeRecords, selectedNodeId]);

  return (
    <section className="v2-stack">
      {requestError ? (
        <InlineNotice
          tone="error"
          title="当前无法完整载入 Trace 视图"
          detail={requestError}
        />
      ) : null}

      <section className="v2-trace-layout v2-trace-layout-expanded">
        <div className="v2-trace-main">
          <Panel
            label="执行轨迹"
            title={traceQuery.data ? "当前运行轨迹" : "等待选择 Trace"}
            description={
              traceQuery.data
                ? undefined
                : "先在右侧载入工单和运行，再展开执行轨迹。"
            }
            actions={
              traceQuery.data ? (
                <div className="v2-action-row">
                  <StatusTag tone={trajectoryHighlights.violations.length > 0 ? "danger" : "success"}>
                    {trajectoryHighlights.currentRoute}
                  </StatusTag>
                </div>
              ) : undefined
            }
          >
            {traceQuery.data ? (
              <section className="v2-trace-stage-list" aria-label="Trace 执行轨迹">
                {nodeRecords.map((node, index) => (
                  <div key={node.id} className="v2-trace-stage-shell">
                    <button
                      type="button"
                      className={`v2-trace-stage-card${selectedNode?.id === node.id ? " is-active" : ""}`}
                      onClick={() => setSelectedNodeId(node.id)}
                      aria-label={`轨迹节点 ${node.key}`}
                    >
                      <div className="v2-trace-stage-index" aria-hidden="true">
                        {String(index + 1).padStart(2, "0")}
                      </div>
                      <div className="v2-trace-stage-body">
                        <div className="v2-ticket-section-head">
                          <div>
                            <p className="v2-panel-label">节点</p>
                            <h3 className="v2-ticket-section-title">{node.key}</h3>
                          </div>
                          <div className="v2-action-row">
                            <StatusTag tone={getStatusTone(node.status)}>{labelForCode(node.status)}</StatusTag>
                            {node.latencyMs !== null ? (
                              <StatusTag tone="muted">{`${formatNumber(node.latencyMs)} ms`}</StatusTag>
                            ) : null}
                          </div>
                        </div>

                        <p className="v2-trace-stage-note">{node.summary}</p>

                        {node.activityEvents.length > 0 || node.issueCount > 0 ? (
                          <div className="v2-action-row">
                            {node.activityEvents.length > 0 ? (
                              <StatusTag tone="muted">{`${node.activityEvents.length} 条关联记录`}</StatusTag>
                            ) : null}
                            {node.issueCount > 0 ? (
                              <StatusTag tone="danger">{`${node.issueCount} 个异常`}</StatusTag>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    </button>

                    {selectedNode?.id === node.id ? (
                      <section className="v2-trace-observer" aria-label="Trace 节点观察">
                        <div className="v2-trace-observer-head">
                          <div>
                            <p className="v2-panel-label">节点观察台</p>
                            <h4 className="v2-ticket-section-title">{node.key}</h4>
                          </div>
                          <div className="v2-action-row">
                            <StatusTag tone={getStatusTone(node.status)}>{labelForCode(node.status)}</StatusTag>
                            {node.activityEvents.length > 0 ? (
                              <StatusTag tone="muted">{`${node.activityEvents.length} 条关联记录`}</StatusTag>
                            ) : null}
                          </div>
                        </div>

                        <div className="v2-trace-inspector-grid">
                          <div className="v2-trace-focus-card">
                            <p className="v2-panel-label">节点</p>
                            <strong>{node.key}</strong>
                          </div>
                          <div className="v2-trace-focus-card">
                            <p className="v2-panel-label">发生序号</p>
                            <strong>{`第 ${node.occurrence} 次`}</strong>
                          </div>
                          <div className="v2-trace-focus-card">
                            <p className="v2-panel-label">节点状态</p>
                            <strong>{labelForCode(node.status)}</strong>
                          </div>
                          <div className="v2-trace-focus-card">
                            <p className="v2-panel-label">节点耗时</p>
                            <strong>{node.latencyMs !== null ? `${formatNumber(node.latencyMs)} ms` : "--"}</strong>
                          </div>
                          {node.activityEvents.length > 0 ? (
                            <div className="v2-trace-focus-card">
                              <p className="v2-panel-label">关联记录</p>
                              <strong>{`${node.activityEvents.length} 条`}</strong>
                            </div>
                          ) : null}
                          {node.activityEvents.length > 0 ? (
                            <div className="v2-trace-focus-card">
                              <p className="v2-panel-label">关联类型</p>
                              <strong>{buildNodeEventMix(node.activityEvents) || "--"}</strong>
                            </div>
                          ) : null}
                        </div>

                        {selectedNodeFields.length > 0 ? (
                          <dl className="v2-kv-grid">
                            {selectedNodeFields.map((field) => (
                              <div key={field.label} className="v2-kv-card">
                                <dt>{field.label}</dt>
                                <dd>{field.value}</dd>
                              </div>
                            ))}
                          </dl>
                        ) : null}

                        {node.activityEvents.length > 0 ? (
                          <div className="v2-trace-activity-list" aria-label="节点关联事件">
                            {node.activityEvents.map((event) => {
                              const eventFields = buildEventInspectorFields(event);

                              return (
                                <article key={event.event_id} className="v2-trace-activity-card">
                                  <div className="v2-trace-activity-head">
                                    <div>
                                      <p className="v2-panel-label">{labelForCode(event.event_type)}</p>
                                      <strong>{buildEventTitle(event)}</strong>
                                    </div>
                                    <div className="v2-action-row">
                                      <StatusTag tone={getEventTone(event)}>
                                        {labelForCode(event.status)}
                                      </StatusTag>
                                      {event.latency_ms !== null && event.latency_ms !== undefined ? (
                                        <StatusTag tone="muted">{`${formatNumber(event.latency_ms)} ms`}</StatusTag>
                                      ) : null}
                                    </div>
                                  </div>
                                  <p className="v2-trace-activity-note">{buildEventCardSummary(event)}</p>

                                  {eventFields.length > 0 ? (
                                    <dl className="v2-trace-activity-fields">
                                      {eventFields.map((field) => (
                                        <div key={`${event.event_id}:${field.label}`} className="v2-trace-activity-field">
                                          <dt>{field.label}</dt>
                                          <dd>{field.value}</dd>
                                        </div>
                                      ))}
                                    </dl>
                                  ) : null}
                                </article>
                              );
                            })}
                          </div>
                        ) : selectedNodeFields.length === 0 ? (
                          <EmptyState
                            label="节点摘要"
                            title="这个节点没有单独 metadata"
                            description="当前只记录了节点状态和它挂接的子事件。"
                          />
                        ) : null}

                        <details className="v2-trace-inline-drawer">
                          <summary>展开该节点原始记录</summary>
                          <pre className="v2-code v2-trace-json">{selectedNodeRawRecord}</pre>
                        </details>
                      </section>
                    ) : null}
                  </div>
                ))}
              </section>
            ) : (
              <EmptyState
                label="需要选择 Trace"
                title="当前还没有载入任何实时 Trace"
                description="请输入工单 ID，或从工单案件室进入此页后再绑定运行档案。"
              />
            )}
          </Panel>

        </div>

        <div className="v2-trace-side">
          <Panel
            label="运行浏览器"
            title={runSummary.title}
            actions={
              selectedRun ? <StatusTag tone={getRunTone(selectedRun.status)}>当前运行</StatusTag> : undefined
            }
            className="v2-trace-control-panel"
          >
            <div className="v2-stack">
              <Field label="工单 ID">
                <input
                  value={ticketInput}
                  onChange={(event) => setTicketInput(event.target.value)}
                  placeholder="ticket_..."
                />
              </Field>

              <div className="v2-action-row">
                <button
                  type="button"
                  className="v2-button is-primary"
                  onClick={handleTicketLoad}
                  disabled={!ticketInput.trim()}
                >
                  载入档案
                </button>
                <button
                  type="button"
                  className="v2-button"
                  onClick={handleClearSelection}
                  disabled={!activeTicketId}
                >
                  清空
                </button>
              </div>

              <Field label="运行">
                <select
                  aria-label="运行选择"
                  value={selectedRun?.run_id ?? ""}
                  onChange={(event) => handleRunSelection(event.target.value)}
                  disabled={!runsQuery.data || runsQuery.data.items.length === 0}
                >
                  {runsQuery.data?.items.length ? (
                    runsQuery.data.items.map((run) => (
                      <option key={run.run_id} value={run.run_id}>
                        {`${run.run_id} · ${labelForCode(run.status)} · 第 ${run.attempt_index} 次尝试`}
                      </option>
                    ))
                  ) : (
                    <option value="">暂无已载入运行</option>
                  )}
                </select>
              </Field>

              <div className="v2-trace-control-grid v2-trace-control-grid-relaxed v2-trace-control-grid-run">
                {runMetaCards.map((card) => (
                  <div
                    key={card.label}
                    className={`v2-trace-focus-card${card.span === "wide" ? " is-wide" : " is-compact"}`}
                  >
                    <p className="v2-panel-label">{card.label}</p>
                    <strong className={card.code ? "v2-code" : undefined}>{card.value}</strong>
                  </div>
                ))}
              </div>

              {hasTicketSelection ? <p className="v2-trace-compact-note">{runSummary.detail}</p> : null}
            </div>
          </Panel>

          <Panel label="运行评估" title="当前运行结果" className="v2-trace-eval-panel">
            <div className="v2-trace-metric-grid">
              {metricCards.map((card) => (
                <div key={card.label} className="v2-trace-metric-card">
                  <div className="v2-trace-metric-head">
                    <p className="v2-metric-label">{card.label}</p>
                    {card.tooltipTitle && card.tooltipLines ? (
                      <InfoTip label={card.label} title={card.tooltipTitle}>
                        {card.tooltipLines.map((line) => (
                          <p key={line}>{line}</p>
                        ))}
                      </InfoTip>
                    ) : null}
                  </div>
                  <strong className="v2-metric-value">{card.value}</strong>
                  <p className="v2-metric-note v2-trace-metric-note-clamp">{card.note}</p>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </section>
    </section>
  );
}
