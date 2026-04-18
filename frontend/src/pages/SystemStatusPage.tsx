import { ApiClientError } from "@/lib/api/client";
import {
  formatTimestampZh,
  labelForCode,
} from "@/lib/presentation";
import { useSystemStatus } from "@/lib/query/systemStatus";

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
    return "system-status-dependency-card-ok";
  }

  if (normalized === "unknown") {
    return "system-status-dependency-card-warn";
  }

  return "system-status-dependency-card-alert";
}

function buildRuntimeCards(data: ReturnType<typeof useSystemStatus>["data"]) {
  if (!data) {
    return [
      {
        label: "Worker",
        value: "正在加载状态",
        note: "等待 Worker 健康和心跳信号。",
      },
      {
        label: "队列",
        value: "正在加载状态",
        note: "排队、运行和阻塞数量会显示在这里。",
      },
      {
        label: "邮箱",
        value: "正在加载状态",
        note: "Gmail 可用性和最近扫描状态会随同这次状态读取一起返回。",
      },
    ];
  }

  return [
    {
      label: "Worker",
      value:
        data.worker.healthy === true
          ? "健康"
          : data.worker.healthy === false
            ? "降级"
            : "未知",
      note: `${data.worker.worker_count ?? 0} 个 Worker · 心跳 ${formatTimestamp(data.worker.last_heartbeat_at)}。`,
    },
    {
      label: "队列",
      value: `${data.queue.queued_runs} 个排队 / ${data.queue.running_runs} 个运行中`,
      note: `${data.queue.waiting_external_tickets} 个等待外部处理 · ${data.queue.error_tickets} 个错误工单。`,
    },
    {
      label: "邮箱",
      value: data.gmail.enabled ? "已启用" : "已禁用",
      note: `${data.gmail.account_email ?? "未配置邮箱"} · 最近扫描 ${formatTimestamp(data.gmail.last_scan_at)}。`,
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
    items.push(
      `Checkpointing 依赖状态为 ${labelForCode(data.dependencies.checkpointing)}。`,
    );
  }

  if (items.length === 0) {
    items.push("当前 GET /ops/status 没有报告任何降级信号。");
  }

  return items;
}

export function SystemStatusPage() {
  const statusQuery = useSystemStatus();

  if (statusQuery.isPending) {
    return (
      <article className="system-status-page">
        <section className="system-status-hero">
          <div className="system-status-hero-copy">
            <p className="placeholder-eyebrow">系统状态</p>
            <h2>正在收集健康度信号。</h2>
            <p>稍后会显示 Worker、依赖和最近失败记录。</p>
          </div>
          <div className="system-status-hero-card">
            <p className="dashboard-card-label">状态加载</p>
            <h3>正在等待第一份 `GET /ops/status` 快照。</h3>
            <p className="system-status-copy">
              一旦状态 payload 返回，这张看板就会从预留态切换到实时状态。
            </p>
          </div>
        </section>
      </article>
    );
  }

  if (statusQuery.isError || !statusQuery.data) {
    return (
      <article className="system-status-page">
        <section className="system-status-alert system-status-alert-error" role="alert">
          <p className="dashboard-card-label">系统状态不可用</p>
          <h3>无法加载可靠性信号。</h3>
          <p>{getErrorMessage(statusQuery.error, "系统状态请求失败。")}</p>
        </section>
      </article>
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
    <article className="system-status-page">
      <section className="system-status-hero">
        <div className="system-status-hero-copy">
          <p className="placeholder-eyebrow">系统状态</p>
          <h2>把 Worker、依赖和故障信号放在一处。</h2>
          <p>这里不做业务操作，专门用于判断系统是否稳定。</p>
          <div className="system-status-chip-row" aria-label="系统状态区域">
            <span className="system-status-chip">运行态</span>
            <span className="system-status-chip">依赖面板</span>
            <span className="system-status-chip">关注列表</span>
            <span className="system-status-chip">失败交接</span>
          </div>
        </div>

        <div className="system-status-hero-card">
          <p className="dashboard-card-label">值班摘要</p>
          <h3>
            {status.worker.healthy === true
              ? "当前 Worker 心跳健康。"
              : "Worker 健康状态需要关注。"}
          </h3>
          <p className="system-status-copy">
            Gmail 当前{status.gmail.enabled ? "已启用" : "已禁用"}，最近上报状态为 {labelForCode(status.gmail.last_scan_status ?? "no_signal")}。
          </p>

          <dl className="system-status-hero-meta">
            <div>
              <dt>心跳</dt>
              <dd>{formatTimestamp(status.worker.last_heartbeat_at)}</dd>
            </div>
            <div>
              <dt>排队运行</dt>
              <dd>{status.queue.queued_runs}</dd>
            </div>
            <div>
              <dt>错误工单</dt>
              <dd>{status.queue.error_tickets}</dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="system-status-runtime-grid" aria-label="系统运行态卡片">
        {runtimeCards.map((card) => (
          <article key={card.label} className="system-status-runtime-card">
            <span>{card.label}</span>
            <strong>{card.value}</strong>
            <p>{card.note}</p>
          </article>
        ))}
      </section>

      <section className="system-status-main-grid">
        <section className="system-status-panel">
          <div className="system-status-panel-header">
            <div>
              <p className="dashboard-card-label">依赖面板</p>
              <h3>单独查看每个依赖的当前状态。</h3>
            </div>
            <span className="system-status-chip">实时合约</span>
          </div>

          <div className="system-status-dependency-grid" aria-label="依赖面板">
            {dependencies.map(([label, value]) => (
              <article
                key={label}
                className={`system-status-dependency-card ${getDependencyTone(value)}`}
              >
                <span>{label}</span>
                <strong>{labelForCode(value)}</strong>
                <p>{label} 当前仅通过 `GET /ops/status` 报告。</p>
              </article>
            ))}
          </div>
        </section>

        <section className="system-status-panel system-status-panel-accent">
          <div className="system-status-panel-header">
            <div>
              <p className="dashboard-card-label">关注列表</p>
              <h3>把需要跟进的问题集中列出来。</h3>
            </div>
            <span className="system-status-chip">{watchList.length} 条信号</span>
          </div>

          <ul className="system-status-watch-list">
            {watchList.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      </section>

      <section className="system-status-bottom-grid">
        <section className="system-status-panel">
          <div className="system-status-panel-header">
            <div>
              <p className="dashboard-card-label">失败交接</p>
              <h3>最近失败运行会显示在这里。</h3>
            </div>
            <span className="system-status-chip">
              {status.recent_failure ? "已记录失败" : "没有失败"}
            </span>
          </div>

          {status.recent_failure ? (
            <article className="system-status-failure-card">
              <span>运行</span>
              <strong>{status.recent_failure.run_id}</strong>
              <p>
                工单 {status.recent_failure.ticket_id} · trace {status.recent_failure.trace_id}
              </p>
              <p>
                {labelForCode(status.recent_failure.error_code, "unknown_error")} · 发生于{" "}
                {formatTimestamp(status.recent_failure.occurred_at)}
              </p>
            </article>
          ) : (
            <section className="system-status-empty-state" role="status">
              <p className="dashboard-card-label">失败预留区</p>
              <h3>当前没有发布最近失败运行。</h3>
              <p>一旦状态 payload 含有失败记录，这张可靠性看板就会展示最近失败。</p>
            </section>
          )}
        </section>

        <section className="system-status-panel">
          <div className="system-status-panel-header">
            <div>
              <p className="dashboard-card-label">队列记账</p>
              <h3>当前积压和执行压力。</h3>
            </div>
            <span className="system-status-chip">仅快照</span>
          </div>

          <div className="system-status-queue-grid" aria-label="队列记账">
            <article className="system-status-queue-card">
              <span>排队中</span>
              <strong>{status.queue.queued_runs}</strong>
              <p>等待 Worker 循环拾取的运行数。</p>
            </article>
            <article className="system-status-queue-card">
              <span>运行中</span>
              <strong>{status.queue.running_runs}</strong>
              <p>当前正在 Worker 池中执行的运行数。</p>
            </article>
            <article className="system-status-queue-card">
              <span>等待外部处理</span>
              <strong>{status.queue.waiting_external_tickets}</strong>
              <p>因人工或系统外跟进而暂停的工单数。</p>
            </article>
            <article className="system-status-queue-card">
              <span>错误状态</span>
              <strong>{status.queue.error_tickets}</strong>
              <p>需要操作员恢复或重试审核的工单数。</p>
            </article>
          </div>
        </section>
      </section>
    </article>
  );
}
