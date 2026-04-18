import { ApiClientError } from "@/lib/api/client";
import { formatTimestampZh, labelForCode } from "@/lib/presentation";
import { useSystemStatus } from "@/lib/query/systemStatus";
import { EmptyState, MetricCard, Panel, StatusTag } from "@/ui-v2/primitives";

function formatTimestamp(value?: string | null) {
  if (!value) {
    return "暂无信号";
  }

  return formatTimestampZh(value);
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

function getDependencyTone(value: string) {
  const normalized = value.toLowerCase();

  if (normalized === "ok") {
    return "success";
  }

  if (normalized === "unknown") {
    return "muted";
  }

  return "danger";
}

function buildRuntimeCards(data: ReturnType<typeof useSystemStatus>["data"]) {
  if (!data) {
    return [
      { label: "Worker", value: "正在加载状态", note: "等待健康和心跳信号" },
      { label: "队列", value: "正在加载状态", note: "等待排队和运行读数" },
      { label: "邮箱", value: "正在加载状态", note: "等待 Gmail 可用性快照" },
    ];
  }

  return [
    {
      label: "Worker",
      value:
        data.worker.healthy === true ? "健康" : data.worker.healthy === false ? "降级" : "未知",
      note: `${data.worker.worker_count ?? 0} 个 Worker · 心跳 ${formatTimestamp(data.worker.last_heartbeat_at)}`,
    },
    {
      label: "队列",
      value: `${data.queue.queued_runs} 个排队 / ${data.queue.running_runs} 个运行中`,
      note: `${data.queue.waiting_external_tickets} 个等待外部处理 · ${data.queue.error_tickets} 个错误工单`,
    },
    {
      label: "邮箱",
      value: data.gmail.enabled ? "已启用" : "已禁用",
      note: `${data.gmail.account_email ?? "未配置邮箱"} · 最近扫描 ${formatTimestamp(data.gmail.last_scan_at)}`,
    },
  ];
}

function buildWatchList(data: NonNullable<ReturnType<typeof useSystemStatus>["data"]>) {
  const items: string[] = [];

  if (data.worker.healthy !== true) {
    items.push("当前 Worker 健康状态未被报告为健康。");
  }
  if (data.queue.error_tickets > 0) {
    items.push(`当前有 ${data.queue.error_tickets} 个工单处于错误状态。`);
  }
  if (data.queue.waiting_external_tickets > 0) {
    items.push(`当前有 ${data.queue.waiting_external_tickets} 个工单正在等待外部跟进。`);
  }
  if (data.dependencies.gmail !== "ok") {
    items.push(`Gmail 依赖状态为 ${labelForCode(data.dependencies.gmail)}。`);
  }
  if (data.dependencies.llm !== "ok") {
    items.push(`LLM 依赖状态为 ${labelForCode(data.dependencies.llm)}。`);
  }
  if (data.dependencies.database !== "ok") {
    items.push(`数据库依赖状态为 ${labelForCode(data.dependencies.database)}。`);
  }
  if (data.dependencies.checkpointing !== "ok") {
    items.push(`Checkpointing 依赖状态为 ${labelForCode(data.dependencies.checkpointing)}。`);
  }
  if (items.length === 0) {
    items.push("当前 GET /ops/status 没有报告任何降级信号。");
  }

  return items;
}

export function SystemStatusPageV2() {
  const statusQuery = useSystemStatus();

  if (statusQuery.isPending) {
    return (
      <Panel label="系统状态" title="正在收集健康度信号" description="稍后会显示 Worker、依赖和最近失败记录。">
        <div className="v2-metric-grid" aria-label="系统状态区域">
          <MetricCard label="Worker" value="载入中" note="等待状态" />
          <MetricCard label="队列" value="载入中" note="等待状态" />
          <MetricCard label="邮箱" value="载入中" note="等待状态" />
          <MetricCard label="可靠性" value="载入中" note="等待状态" />
        </div>
      </Panel>
    );
  }

  if (statusQuery.isError || !statusQuery.data) {
    return (
      <EmptyState
        label="系统状态不可用"
        title="无法加载可靠性信号"
        description={getErrorMessage(statusQuery.error, "系统状态请求失败。")}
      />
    );
  }

  const status = statusQuery.data;
  const runtimeCards = buildRuntimeCards(status);
  const watchList = buildWatchList(status);
  const dependencies = [
    ["Database", status.dependencies.database],
    ["Gmail", status.dependencies.gmail],
    ["LLM", status.dependencies.llm],
    ["Checkpointing", status.dependencies.checkpointing],
  ] as const;

  return (
    <section className="v2-stack">
      <Panel
        label="系统状态"
        title="当前系统健康度"
        description="只看可靠性信号。"
      >
        <div className="v2-metric-grid" aria-label="系统状态区域">
          {runtimeCards.map((card) => (
            <MetricCard key={card.label} label={card.label} value={card.value} note={card.note} />
          ))}
          <MetricCard
            label="最近扫描状态"
            value={labelForCode(status.gmail.last_scan_status ?? "no_signal")}
            note={`最近扫描 ${formatTimestamp(status.gmail.last_scan_at)}`}
            tone="accent"
          />
        </div>
      </Panel>

      <div className="v2-tiles-grid">
        <Panel
          label="依赖"
          title="各依赖当前状态"
          actions={<StatusTag tone="muted">GET /ops/status</StatusTag>}
        >
          <div className="v2-summary-grid" aria-label="依赖面板">
            {dependencies.map(([label, value]) => (
              <MetricCard
                key={label}
                label={label}
                value={labelForCode(value)}
                note={`${label} 当前仅通过 GET /ops/status 报告`}
                tone={getDependencyTone(value) as "success" | "muted" | "danger"}
              />
            ))}
          </div>
        </Panel>

        <Panel
          label="关注列表"
          title={`${watchList.length} 条需要跟进的信号`}
          actions={<StatusTag tone="muted">可靠性信号</StatusTag>}
        >
          <section className="v2-divider-list">
            {watchList.map((item) => (
              <article key={item} className="v2-divider-row">
                <strong>{item}</strong>
              </article>
            ))}
          </section>
        </Panel>
      </div>

      <div className="v2-tiles-grid">
        <Panel
          label="失败交接"
          title={status.recent_failure ? "最近失败运行" : "当前没有失败交接项"}
        >
          {status.recent_failure ? (
            <section className="v2-divider-list">
              <article className="v2-divider-row">
                <strong>{status.recent_failure.run_id}</strong>
                <p>工单 {status.recent_failure.ticket_id} · trace {status.recent_failure.trace_id}</p>
                <p>
                  {labelForCode(status.recent_failure.error_code, "unknown_error")} · 发生于{" "}
                  {formatTimestamp(status.recent_failure.occurred_at)}
                </p>
              </article>
            </section>
          ) : (
            <EmptyState
              label="失败预留区"
              title="当前没有发布最近失败运行"
              description="一旦状态 payload 含有失败记录，这里就会展示最近失败。"
            />
          )}
        </Panel>

        <Panel label="队列记账" title="当前积压和执行压力">
          <div className="v2-summary-grid" aria-label="队列记账">
            <MetricCard label="排队中" value={status.queue.queued_runs} note="等待 Worker 循环拾取" />
            <MetricCard label="运行中" value={status.queue.running_runs} note="当前正在执行" />
            <MetricCard label="等待外部处理" value={status.queue.waiting_external_tickets} note="因人工或系统外跟进而暂停" />
            <MetricCard label="错误状态" value={status.queue.error_tickets} note="需要恢复或重试审核" tone="danger" />
          </div>
        </Panel>
      </div>
    </section>
  );
}
