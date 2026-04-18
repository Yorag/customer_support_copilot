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
  formatPercentZh,
  formatScoreZh,
  formatTimestampZh,
  labelForCode,
} from "@/lib/presentation";
import { buildTraceMetricsWindow, useTicketTrace, useTraceMetrics } from "@/lib/query/trace";
import { useTicketRuns } from "@/lib/query/tickets";
import { useConsoleUiStore } from "@/state/console-ui-store";

const TRACE_RUN_PAGE_SIZE = 12;

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

function formatPercent(value?: number | null) {
  return formatPercentZh(value);
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

function buildTraceMetricCards(
  trace: TicketTraceResponse | undefined,
  metrics: MetricsSummaryResponse | undefined,
) {
  const latencyMetrics = (trace?.latency_metrics ?? {}) as Record<string, unknown>;
  const resourceMetrics = (trace?.resource_metrics ?? {}) as Record<string, unknown>;
  const responseQuality = (trace?.response_quality ?? {}) as Record<string, unknown>;
  const trajectory = (trace?.trajectory_evaluation ?? {}) as Record<string, unknown>;

  return [
    {
      label: "延迟镜头",
      value:
        latencyMetrics.end_to_end_ms !== undefined && latencyMetrics.end_to_end_ms !== null
          ? `${formatNumber(Number(latencyMetrics.end_to_end_ms))} ms`
          : "等待 Trace",
      note: trace
        ? `最慢节点 ${labelForCode(String(latencyMetrics.slowest_node ?? "not_available"))} · 窗口 P50 ${formatNumber(metrics?.latency.p50_ms)} ms · P95 ${formatNumber(metrics?.latency.p95_ms)} ms。`
        : "载入工单档案后，这里会把当前运行与近期延迟窗口进行对比。",
    },
    {
      label: "资源台账",
      value:
        resourceMetrics.total_tokens !== undefined && resourceMetrics.total_tokens !== null
          ? `${formatNumber(Number(resourceMetrics.total_tokens))} tokens`
          : "等待 Trace",
      note: trace
        ? `${formatNumber(Number(resourceMetrics.llm_call_count ?? 0))} 次模型调用 · ${formatNumber(Number(resourceMetrics.tool_call_count ?? 0))} 次工具调用 · 覆盖率 ${formatPercent(Number(resourceMetrics.token_coverage_ratio ?? 0))}。`
        : "只有在选中具体运行后，这里才会显示 tokens 和调用计数。",
    },
    {
      label: "质量轨",
      value:
        responseQuality.overall_score !== undefined && responseQuality.overall_score !== null
          ? formatScore(Number(responseQuality.overall_score))
          : "未评分",
      note: trace
        ? String(responseQuality.reason ?? "本次运行没有发布回复质量说明。")
        : "选择带评分的运行后，这里才会出现运行级回复质量。",
    },
    {
      label: "轨迹轨",
      value:
        trajectory.score !== undefined && trajectory.score !== null
          ? formatScore(Number(trajectory.score))
          : "未评分",
      note: trace
        ? `${labelForCode(String(trajectory.expected_route ?? "unknown"))} -> ${labelForCode(String(trajectory.actual_route ?? "unknown"))} · ${Array.isArray(trajectory.violations) ? trajectory.violations.length : 0} 条违规。`
        : "只有拿到 Trace 后，才会出现预期路径与实际路径的对比。",
    },
  ];
}

function getTraceStageTone(event: TraceEventResponse) {
  const normalizedStatus = event.status.toLowerCase();
  const normalizedType = event.event_type.toLowerCase();

  if (normalizedStatus === "failed" || normalizedStatus === "error") {
    return "trace-stage-card-alert";
  }

  if (normalizedType === "llm_call" || normalizedType === "tool_call") {
    return "trace-stage-card-accent";
  }

  return "";
}

function getEventRowTone(event: TraceEventResponse) {
  const normalizedStatus = event.status.toLowerCase();

  if (normalizedStatus === "failed" || normalizedStatus === "error") {
    return "trace-event-row-alert";
  }

  if (normalizedStatus === "succeeded") {
    return "trace-event-row-accent";
  }

  return "";
}

function buildRunSummary(
  trace: TicketTraceResponse | undefined,
  selectedRun: TicketRunHistoryItem | undefined,
  metrics: MetricsSummaryResponse | undefined,
) {
  if (!trace) {
    return {
      title: "运行浏览器正在等待工单档案。",
      detail: "输入工单 ID，或从工单详情进入此页后，才会绑定实时 Trace、评估和事件记录。",
      notes: [
        "页面会保留 FE-10 的档案墙布局。",
        "Trace 载入后，运行浏览器会固定当前 run 与 trace 引用。",
        "指标轨与原始记录抽屉只会对当前选中运行生效。",
      ],
    };
  }

  return {
    title: `${shortenId(trace.run_id)} 是当前 Trace 档案的锚点。`,
    detail: selectedRun
      ? `${labelForCode(selectedRun.status)} · ${selectedRun.final_action ? labelForCode(selectedRun.final_action) : "未记录最终动作"} · 第 ${selectedRun.attempt_index} 次尝试。`
      : `Trace ${shortenId(trace.trace_id)} 已载入，但当前没有匹配的运行摘要投影。`,
    notes: [
      `工单 ${trace.ticket_id} · Trace ${trace.trace_id}。`,
      selectedRun
        ? `触发者 ${selectedRun.triggered_by ?? "系统"} · 触发方式 ${labelForCode(selectedRun.trigger_type)} · 开始于 ${formatTimestamp(selectedRun.started_at)}。`
        : "当前 Trace 选择没有可用的运行历史摘要。",
      metrics
        ? `窗口质量 ${formatScore(metrics.response_quality.avg_overall_score)} · 轨迹 ${formatScore(metrics.trajectory_evaluation.avg_score)}。`
        : "对比窗口指标仍在加载中。",
    ],
  };
}

export function TraceEvalPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedTicketId = useConsoleUiStore((state) => state.selectedTicketId);
  const traceDrawerOpen = useConsoleUiStore((state) => state.traceDrawerOpen);
  const setSelectedTicketId = useConsoleUiStore((state) => state.setSelectedTicketId);
  const setSelectedRunId = useConsoleUiStore((state) => state.setSelectedRunId);
  const setTraceDrawerOpen = useConsoleUiStore((state) => state.setTraceDrawerOpen);

  const urlTicketId = searchParams.get("ticketId")?.trim() ?? "";
  const urlRunId = searchParams.get("runId")?.trim() ?? "";
  const activeTicketId = urlTicketId || selectedTicketId || "";
  const activeRunId = urlRunId;
  const [ticketInput, setTicketInput] = useState(activeTicketId);
  const [metricsWindow] = useState(() => buildTraceMetricsWindow());

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
  const runSummary = buildRunSummary(traceQuery.data, selectedRun, metricsQuery.data);
  const events = traceQuery.data?.events ?? [];
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
      setTraceDrawerOpen(false);
      updateSearch(normalizedTicketId, null);
    });
  }

  function handleClearSelection() {
    startTransition(() => {
      setTicketInput("");
      setSelectedTicketId(null);
      setSelectedRunId(null);
      setTraceDrawerOpen(false);
      setSearchParams(new URLSearchParams());
    });
  }

  function handleRunSelection(nextRunId: string) {
    startTransition(() => {
      setSelectedRunId(nextRunId || null);
      updateSearch(activeTicketId, nextRunId || null);
    });
  }

  return (
    <article className="trace-page">
      <section className="trace-hero">
        <div className="trace-hero-copy">
          <p className="placeholder-eyebrow">Trace</p>
          <h2>顺着一次运行看清楚发生了什么。</h2>
          <p>从运行选择开始，往下读事件、评分和原始记录。</p>
          <div className="trace-chip-row" aria-label="Trace 页面区域">
            <span className="trace-chip">运行浏览器</span>
            <span className="trace-chip">实时时间线墙</span>
            <span className="trace-chip">指标轨</span>
            <span className="trace-chip">事件台账</span>
            <span className="trace-chip">原始记录抽屉</span>
          </div>
        </div>

        <div className="trace-hero-card">
          <p className="dashboard-card-label">运行浏览器</p>
          <h3>{runSummary.title}</h3>
          <p className="trace-hero-card-copy">{runSummary.detail}</p>
          <ul className="trace-list trace-list-compact">
            {runSummary.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>

          <div className="trace-explorer-form">
            <label className="trace-explorer-field">
              <span>工单 ID</span>
              <input
                value={ticketInput}
                onChange={(event) => setTicketInput(event.target.value)}
                placeholder="ticket_..."
              />
            </label>

            <div className="trace-explorer-actions">
              <button
                type="button"
                className="trace-explorer-button trace-explorer-button-primary"
                onClick={handleTicketLoad}
                disabled={!ticketInput.trim()}
              >
                载入档案
              </button>
              <button
                type="button"
                className="trace-explorer-button"
                onClick={handleClearSelection}
                disabled={!activeTicketId}
              >
                清空
              </button>
            </div>
          </div>

          <label className="trace-explorer-field">
            <span>运行浏览器</span>
            <select
              aria-label="运行浏览器"
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
          </label>

          <dl className="trace-hero-meta">
            <div>
              <dt>工单焦点</dt>
              <dd>{activeTicketId || "尚未选择工单"}</dd>
            </div>
            <div>
              <dt>运行焦点</dt>
              <dd>{traceQuery.data ? traceQuery.data.run_id : selectedRun?.run_id ?? "最新运行"}</dd>
            </div>
            <div>
              <dt>Trace 引用</dt>
              <dd>{traceQuery.data?.trace_id ?? "等待 Trace 响应"}</dd>
            </div>
          </dl>
        </div>
      </section>

      {requestError ? (
        <section className="trace-request-alert" role="alert">
          <p className="dashboard-card-label">Trace 请求异常</p>
          <h3>当前无法完整载入 Trace 视图。</h3>
          <p>{requestError}</p>
        </section>
      ) : null}

      <section className="trace-summary-grid" aria-label="Trace 摘要">
        <article className="trace-summary-card trace-summary-card-accent">
          <p className="dashboard-card-label">运行档案</p>
          <h3>
            {traceQuery.data
              ? `${shortenId(traceQuery.data.run_id)} · ${shortenId(traceQuery.data.trace_id)}`
              : "选中运行后，这里会显示 Trace 身份。"}
          </h3>
          <p>{runSummary.detail}</p>
        </article>
        <article className="trace-summary-card">
          <p className="dashboard-card-label">事件压力</p>
          <h3>
            {traceQuery.data
              ? `当前已排布 ${events.length} 个事件。`
              : "事件台账正在等待选中的工单。"}
          </h3>
          <p>
            {traceQuery.data
              ? `最新事件发生于 ${formatTimestamp(events.at(-1)?.start_time)}。`
              : "选择工单 ID 后，下方台账会从预留态切换为实时事件面板。"}
          </p>
        </article>
        <article className="trace-summary-card">
          <p className="dashboard-card-label">对比窗口</p>
          <h3>
            {metricsQuery.data
              ? `质量 ${formatScore(metricsQuery.data.response_quality.avg_overall_score)} · 轨迹 ${formatScore(metricsQuery.data.trajectory_evaluation.avg_score)}`
              : "档案载入前，指标窗口保持空闲。"}
          </h3>
          <p>
            {metricsQuery.data
              ? `近期 P50 ${formatNumber(metricsQuery.data.latency.p50_ms)} ms · P95 ${formatNumber(metricsQuery.data.latency.p95_ms)} ms。`
              : "工单激活后，侧边指标轨会把当前运行与近期窗口进行对比。"}
          </p>
        </article>
      </section>

      <section className="trace-main-grid">
        <section className="trace-panel">
          <div className="trace-panel-header">
            <div>
              <p className="dashboard-card-label">时间线墙</p>
              <h3>按顺序阅读本次运行的事件。</h3>
            </div>
            <span className="trace-panel-chip">
              {traceQuery.isPending && hasTicketSelection
                ? "正在加载 Trace"
                : traceQuery.data
                  ? `${events.length} 个实时事件`
                  : "等待选择"}
            </span>
          </div>

          <div className="trace-stage-list" aria-label="Trace 时间线墙">
            {traceQuery.data ? (
              events.map((event, index) => (
                <article
                  key={event.event_id}
                  className={`trace-stage-card ${getTraceStageTone(event)}`.trim()}
                >
                  <div className="trace-stage-line" aria-hidden="true" />
                  <div className="trace-stage-content">
                    <div className="trace-stage-head">
                      <div>
                        <p className="trace-stage-label">
                          {`${String(index + 1).padStart(2, "0")} ${labelForCode(event.event_type)}`}
                        </p>
                        <h4>{labelForCode(event.event_name)}</h4>
                      </div>
                      <span className="trace-stage-duration">
                        {event.latency_ms !== null && event.latency_ms !== undefined
                          ? `${formatNumber(event.latency_ms)} ms`
                          : labelForCode(event.status)}
                      </span>
                    </div>
                    <p>
                      {event.node_name
                        ? `${labelForCode(event.node_name)} · ${formatTimestamp(event.start_time)}`
                        : `开始于 ${formatTimestamp(event.start_time)}`}
                    </p>
                    <ul className="trace-list">
                      <li>状态：{labelForCode(event.status)}</li>
                      <li>
                        {event.end_time
                          ? `结束于 ${formatTimestamp(event.end_time)}`
                          : "该事件还没有发布结束时间。"}
                      </li>
                      <li>{summarizeMetadata(event.metadata)}</li>
                    </ul>
                  </div>
                </article>
              ))
            ) : (
              <section className="trace-empty-state" role="status">
                <p className="dashboard-card-label">需要选择 Trace</p>
                <h3>当前还没有载入任何实时 Trace。</h3>
                <p>请输入工单 ID，或从工单案件室进入此页后再绑定运行档案。</p>
              </section>
            )}
          </div>
        </section>

        <section className="trace-side-rail">
          <section className="trace-panel">
            <div className="trace-panel-header">
              <div>
                <p className="dashboard-card-label">指标轨</p>
                <h3>对比当前运行和近期窗口。</h3>
              </div>
              <span className="trace-panel-chip">
                {metricsQuery.isPending && hasTicketSelection
                  ? "正在加载指标"
                  : metricsQuery.data
                    ? "实时对比"
                    : "空闲"}
              </span>
            </div>

            <div className="trace-metric-grid">
              {metricCards.map((card) => (
                <article key={card.label} className="trace-metric-card">
                  <span>{card.label}</span>
                  <strong>{card.value}</strong>
                  <p>{card.note}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="trace-panel trace-panel-accent">
            <div className="trace-panel-header">
              <div>
                <p className="dashboard-card-label">原始记录抽屉</p>
                <h3>需要时再展开结构化原始记录。</h3>
              </div>
              <button
                type="button"
                className="trace-drawer-button"
                onClick={() => setTraceDrawerOpen(!traceDrawerOpen)}
                disabled={!traceQuery.data}
              >
                {traceDrawerOpen ? "收起原始记录" : "打开原始记录"}
              </button>
            </div>
            <p className="trace-panel-copy">
              原始记录检查是第二步动作。优先视图仍然是可阅读的档案墙，JSON 只保留给核验和调试。
            </p>

            {traceDrawerOpen && traceQuery.data ? (
              <pre className="trace-raw-drawer" aria-label="Trace 原始记录抽屉">
                {JSON.stringify(
                  {
                    latency_metrics: traceQuery.data.latency_metrics,
                    resource_metrics: traceQuery.data.resource_metrics,
                    response_quality: traceQuery.data.response_quality,
                    trajectory_evaluation: traceQuery.data.trajectory_evaluation,
                  },
                  null,
                  2,
                )}
              </pre>
            ) : (
              <div className="trace-drawer-placeholder" aria-hidden="true">
                <span />
                <span />
                <span />
              </div>
            )}
          </section>
        </section>
      </section>

      <section className="trace-events-panel">
        <div className="trace-panel-header">
          <div>
            <p className="dashboard-card-label">事件台账</p>
            <h3>逐行查看每个事件的状态和细节。</h3>
          </div>
          <span className="trace-panel-chip">
            {traceQuery.data ? `${events.length} 行台账` : "暂无 Trace 行"}
          </span>
        </div>

        <div className="trace-events-head" aria-hidden="true">
          <span>事件</span>
          <span>节点</span>
          <span>状态</span>
          <span>时间</span>
          <span>细节</span>
        </div>

        <div className="trace-events-list" aria-label="Trace 事件台账">
          {traceQuery.data ? (
            events.map((event) => (
              <article
                key={`${event.event_id}-row`}
                className={`trace-event-row ${getEventRowTone(event)}`.trim()}
              >
                <div className="trace-event-cell">
                  <span>{labelForCode(event.event_type)}</span>
                  <strong>{labelForCode(event.event_name)}</strong>
                </div>
                <div className="trace-event-cell">
                  <strong>{event.node_name ? labelForCode(event.node_name) : "--"}</strong>
                  <p>{shortenId(event.event_id)}</p>
                </div>
                <div className="trace-event-cell">
                  <p>{labelForCode(event.status)}</p>
                </div>
                <div className="trace-event-cell">
                  <p>{formatTimestamp(event.start_time)}</p>
                  <p>
                    {event.latency_ms !== null && event.latency_ms !== undefined
                      ? `${formatNumber(event.latency_ms)} ms`
                      : "延迟不可用"}
                  </p>
                </div>
                <div className="trace-event-cell">
                  <p>{summarizeMetadata(event.metadata)}</p>
                </div>
              </article>
            ))
          ) : (
            <section className="trace-empty-state trace-empty-state-inline" role="status">
              <p className="dashboard-card-label">事件台账空闲</p>
              <h3>没有激活 Trace 时，不会出现任何事件行。</h3>
              <p>只要工单档案载入成功，台账就会立刻切换为实时记录。</p>
            </section>
          )}
        </div>
      </section>
    </article>
  );
}
