import { startTransition, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { ApiClientError } from "@/lib/api/client";
import {
  formatNumberZh,
  formatTimestampZh,
  labelForCode,
} from "@/lib/presentation";
import type {
  GmailScanPreviewResponse,
  GmailScanResponse,
  OpsStatusResponse,
} from "@/lib/api/types";
import {
  useGmailOpsStatus,
  usePreviewGmailScan,
  useScanGmail,
} from "@/lib/query/gmailOps";
import { queryKeys } from "@/lib/query/keys";

type ActionNotice = {
  tone: "success" | "error";
  title: string;
  detail: string;
};

function formatTimestamp(value?: string | null) {
  if (!value) {
    return "暂无信号";
  }

  return formatTimestampZh(value);
}

function formatNumber(value?: number | null) {
  return formatNumberZh(value);
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

function parseMaxResults(value: string) {
  const normalized = value.trim();
  if (!normalized) {
    return undefined;
  }

  const parsed = Number(normalized);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return undefined;
  }

  return Math.min(100, Math.round(parsed));
}

function buildRuntimeCards(status: OpsStatusResponse | undefined) {
  if (!status) {
    return [
      {
        label: "邮箱",
        value: "正在加载运行态",
        note: "等待 `GET /ops/status` 返回。",
      },
      {
        label: "队列",
        value: "正在加载运行态",
        note: "队列状态会随同这次状态请求一起返回。",
      },
      {
        label: "依赖",
        value: "正在加载运行态",
        note: "数据库、Gmail、LLM 和 checkpointing 会在这里展示。",
      },
    ];
  }

  return [
    {
      label: "邮箱",
      value: status.gmail.enabled ? "已连接" : "已禁用",
      note: status.gmail.account_email
        ? `${status.gmail.account_email} · 最近扫描 ${formatTimestamp(status.gmail.last_scan_at)}。`
        : `最近扫描 ${formatTimestamp(status.gmail.last_scan_at)}。`,
    },
    {
      label: "队列",
      value: `${formatNumber(status.queue.queued_runs)} 个排队 / ${formatNumber(status.queue.running_runs)} 个运行中`,
      note: `${formatNumber(status.queue.waiting_external_tickets)} 个等待外部处理 · ${formatNumber(status.queue.error_tickets)} 个错误工单。`,
    },
    {
      label: "依赖",
      value: `Gmail ${labelForCode(status.dependencies.gmail)} / 数据库 ${labelForCode(status.dependencies.database)}`,
      note: `LLM ${labelForCode(status.dependencies.llm)} · checkpointing ${labelForCode(status.dependencies.checkpointing)}。`,
    },
  ];
}

function PreviewDeck(props: {
  preview: GmailScanPreviewResponse | null;
}) {
  return (
    <section className="gmail-ops-panel">
      <div className="gmail-ops-panel-header">
        <div>
          <p className="dashboard-card-label">预览池</p>
          <h3>在创建任何工单之前先预览候选批次。</h3>
        </div>
        <span className="gmail-ops-chip">
          {props.preview
            ? `${props.preview.summary.candidate_threads} 个候选`
            : "尚无预览"}
        </span>
      </div>

      {props.preview ? (
        <>
          <section className="gmail-ops-summary-grid" aria-label="预览摘要">
            <article className="gmail-ops-summary-card">
              <span>候选数</span>
              <strong>{formatNumber(props.preview.summary.candidate_threads)}</strong>
              <p>当前有资格进入摄入流程的线程数。</p>
            </article>
            <article className="gmail-ops-summary-card">
              <span>已有草稿</span>
              <strong>
                {formatNumber(props.preview.summary.skipped_existing_draft_threads)}
              </strong>
              <p>因系统已持有草稿而被跳过。</p>
            </article>
            <article className="gmail-ops-summary-card">
              <span>自发邮件</span>
              <strong>
                {formatNumber(props.preview.summary.skipped_self_sent_threads)}
              </strong>
              <p>因发件人与邮箱所有者一致而被过滤。</p>
            </article>
          </section>

          <div className="gmail-ops-item-list" aria-label="预览候选列表">
            {props.preview.items.map((item) => (
              <article key={item.source_thread_id} className="gmail-ops-item-row">
                <div>
                  <strong>{item.subject}</strong>
                  <p>{item.sender_email_raw}</p>
                </div>
                <div>
                  <span>{item.source_thread_id}</span>
                  <p>{item.source_message_id ?? "暂无源消息 ID"}</p>
                </div>
                <div>
                  <strong>
                    {item.skip_reason ? labelForCode(item.skip_reason) : "候选"}
                  </strong>
                  <p>
                    {item.skip_reason
                      ? "在实际扫描中将被跳过。"
                      : "执行扫描时可进入摄入流程。"}
                  </p>
                </div>
              </article>
            ))}
          </div>
        </>
      ) : (
        <section className="gmail-ops-empty-state" role="status">
          <p className="dashboard-card-label">等待预览</p>
          <h3>当前还没有加载任何预览批次。</h3>
          <p>执行“预览扫描”即可在不修改系统状态的前提下查看候选项和跳过原因。</p>
        </section>
      )}
    </section>
  );
}

function ScanDeck(props: {
  result: GmailScanResponse | null;
}) {
  return (
    <section className="gmail-ops-panel gmail-ops-panel-accent">
      <div className="gmail-ops-panel-header">
        <div>
          <p className="dashboard-card-label">执行回执</p>
          <h3>实时扫描会返回摄入回执，而不是只有一个黑盒成功提示。</h3>
        </div>
        <span className="gmail-ops-chip">
          {props.result ? props.result.scan_id : "尚无实时扫描"}
        </span>
      </div>

      {props.result ? (
        <>
          <section className="gmail-ops-summary-grid" aria-label="扫描摘要">
            <article className="gmail-ops-summary-card">
              <span>扫描线程</span>
              <strong>{formatNumber(props.result.summary.fetched_threads)}</strong>
              <p>本次操作中实际扫描的线程数。</p>
            </article>
            <article className="gmail-ops-summary-card">
              <span>摄入工单</span>
              <strong>{formatNumber(props.result.summary.ingested_tickets)}</strong>
              <p>本次扫描中新创建的工单数。</p>
            </article>
            <article className="gmail-ops-summary-card">
              <span>已入队运行</span>
              <strong>{formatNumber(props.result.summary.queued_runs)}</strong>
              <p>
                {props.result.enqueue
                  ? "本批次已开启 run 创建。"
                  : "本批次明确未将 run 入队。"}
              </p>
            </article>
            <article className="gmail-ops-summary-card">
              <span>错误数</span>
              <strong>{formatNumber(props.result.summary.errors)}</strong>
              <p>回执中记录的批次级摄入错误数。</p>
            </article>
          </section>

          <div className="gmail-ops-item-list" aria-label="扫描回执列表">
            {props.result.items.map((item) => (
              <article key={item.source_thread_id} className="gmail-ops-item-row">
                <div>
                  <strong>{item.ticket_id ?? "未创建工单"}</strong>
                  <p>{item.source_thread_id}</p>
                </div>
                <div>
                  <span>{item.created_ticket ? "已创建工单" : "复用了已有工单"}</span>
                  <p>{item.queued_run_id ?? "未生成入队运行"}</p>
                </div>
                <div>
                  <strong>{item.queued_run_id ? "已入队" : "未入队"}</strong>
                  <p>
                    {item.queued_run_id
                      ? "Worker 可以继续拾取这次运行。"
                      : "工单摄入已完成，但没有创建新的入队运行。"}
                  </p>
                </div>
              </article>
            ))}
          </div>
        </>
      ) : (
        <section className="gmail-ops-empty-state" role="status">
          <p className="dashboard-card-label">等待执行</p>
          <h3>当前会话里还没有任何扫描回执。</h3>
          <p>在预览之后执行“立即扫描”，即可记录摄入数量、入队运行和工单映射。</p>
        </section>
      )}
    </section>
  );
}

export function GmailOpsPage() {
  const queryClient = useQueryClient();
  const statusQuery = useGmailOpsStatus();
  const previewMutation = usePreviewGmailScan();
  const scanMutation = useScanGmail();
  const [maxResultsInput, setMaxResultsInput] = useState("20");
  const [enqueue, setEnqueue] = useState(true);
  const [previewResult, setPreviewResult] = useState<GmailScanPreviewResponse | null>(null);
  const [scanResult, setScanResult] = useState<GmailScanResponse | null>(null);
  const [notice, setNotice] = useState<ActionNotice | null>(null);

  const runtimeCards = buildRuntimeCards(statusQuery.data);
  const maxResults = parseMaxResults(maxResultsInput);

  async function handleRefreshStatus() {
    await queryClient.invalidateQueries({ queryKey: queryKeys.opsStatus });
  }

  async function handlePreview() {
    try {
      const result = await previewMutation.mutateAsync({
        max_results: maxResults,
      });
      startTransition(() => {
        setPreviewResult(result);
        setNotice({
          tone: "success",
          title: "预览已加载",
          detail: `已检查 ${result.summary.candidate_threads} 个候选项，未发生工单摄入。`,
        });
      });
    } catch (error) {
      setNotice({
        tone: "error",
        title: "预览失败",
        detail: getErrorMessage(error, "预览请求失败。"),
      });
    }
  }

  async function handleScan() {
    try {
      const result = await scanMutation.mutateAsync({
        max_results: maxResults,
        enqueue,
      });
      startTransition(() => {
        setScanResult(result);
        setNotice({
          tone: "success",
          title: "扫描已接受",
          detail: `已摄入 ${result.summary.ingested_tickets} 个工单，并入队 ${result.summary.queued_runs} 次运行。`,
        });
      });
    } catch (error) {
      setNotice({
        tone: "error",
        title: "扫描失败",
        detail: getErrorMessage(error, "扫描请求失败。"),
      });
    }
  }

  return (
    <article className="gmail-ops-page">
      <section className="gmail-ops-hero">
        <div className="gmail-ops-hero-copy">
          <p className="placeholder-eyebrow">Gmail 运维</p>
          <h2>先预览候选，再执行摄入。</h2>
          <p>把邮箱扫描当成一次明确的批次操作，而不是后台动作。</p>
          <div className="gmail-ops-chip-row" aria-label="Gmail 运维区域">
            <span className="gmail-ops-chip">运行状态</span>
            <span className="gmail-ops-chip">预览池</span>
            <span className="gmail-ops-chip">执行回执</span>
            <span className="gmail-ops-chip">跳过原因</span>
          </div>
        </div>

        <div className="gmail-ops-runtime-card">
          <p className="dashboard-card-label">邮箱状态</p>
          <h3>
            {statusQuery.data?.gmail.enabled ? "当前邮箱已启用，允许操作员扫描。" : "当前邮箱摄入已禁用。"}
          </h3>
          <dl className="gmail-ops-runtime-meta">
            <div>
              <dt>账号</dt>
              <dd>{statusQuery.data?.gmail.account_email ?? "未配置"}</dd>
            </div>
            <div>
              <dt>最近扫描</dt>
              <dd>{formatTimestamp(statusQuery.data?.gmail.last_scan_at)}</dd>
            </div>
            <div>
              <dt>最近状态</dt>
              <dd>
                {statusQuery.data?.gmail.last_scan_status
                  ? labelForCode(statusQuery.data.gmail.last_scan_status)
                  : "暂无扫描记录"}
              </dd>
            </div>
          </dl>
        </div>
      </section>

      {statusQuery.isError ? (
        <section className="gmail-ops-alert gmail-ops-alert-error" role="alert">
          <p className="dashboard-card-label">状态不可用</p>
          <h3>无法加载运行状态。</h3>
          <p>{getErrorMessage(statusQuery.error, "Ops status 请求失败。")}</p>
        </section>
      ) : null}

      {notice ? (
        <section
          className={`gmail-ops-alert gmail-ops-alert-${notice.tone}`}
          role={notice.tone === "error" ? "alert" : "status"}
        >
          <p className="dashboard-card-label">操作通知</p>
          <h3>{notice.title}</h3>
          <p>{notice.detail}</p>
        </section>
      ) : null}

      <section className="gmail-ops-runtime-grid" aria-label="Gmail 运行态卡片">
        {runtimeCards.map((card) => (
          <article key={card.label} className="gmail-ops-runtime-cell">
            <span>{card.label}</span>
            <strong>{card.value}</strong>
            <p>{card.note}</p>
          </article>
        ))}
      </section>

      <section className="gmail-ops-control-grid">
        <section className="gmail-ops-panel">
          <div className="gmail-ops-panel-header">
            <div>
              <p className="dashboard-card-label">扫描控制</p>
              <h3>设置批次大小和是否自动入队。</h3>
            </div>
            <span className="gmail-ops-chip">
              {statusQuery.isFetching ? "正在刷新状态" : "控制面已就绪"}
            </span>
          </div>

          <div className="gmail-ops-form-grid">
            <label className="gmail-ops-field">
              <span>最大结果数</span>
              <input
                value={maxResultsInput}
                onChange={(event) => setMaxResultsInput(event.target.value)}
                placeholder="20"
              />
            </label>

            <label className="gmail-ops-toggle">
              <input
                type="checkbox"
                checked={enqueue}
                onChange={(event) => setEnqueue(event.target.checked)}
              />
              <span>摄入后自动入队运行</span>
            </label>
          </div>

          <div className="gmail-ops-button-row">
            <button
              type="button"
              className="gmail-ops-button"
              onClick={() => void handlePreview()}
              disabled={previewMutation.isPending}
            >
              预览扫描
            </button>
            <button
              type="button"
              className="gmail-ops-button gmail-ops-button-primary"
              onClick={() => void handleScan()}
              disabled={scanMutation.isPending}
            >
              立即扫描
            </button>
            <button
              type="button"
              className="gmail-ops-button"
              onClick={() => void handleRefreshStatus()}
              disabled={statusQuery.isFetching}
            >
              刷新状态
            </button>
          </div>
        </section>

        <section className="gmail-ops-panel">
          <div className="gmail-ops-panel-header">
            <div>
              <p className="dashboard-card-label">当前限制</p>
              <h3>这里只展示当前状态和本次批次回执。</h3>
            </div>
            <span className="gmail-ops-chip">暂无历史接口</span>
          </div>

          <ul className="gmail-ops-list">
            <li>`GET /ops/status` 只暴露最近扫描时间和状态，不提供时间序列表。</li>
            <li>`POST /ops/gmail/scan-preview` 是查看候选项的安全 dry-run 路径。</li>
            <li>`POST /ops/gmail/scan` 返回当前批次的摄入和入队回执。</li>
          </ul>

          {statusQuery.data?.recent_failure ? (
            <article className="gmail-ops-inline-card">
              <span>最近失败</span>
              <strong>{statusQuery.data.recent_failure.run_id}</strong>
              <p>
                {labelForCode(statusQuery.data.recent_failure.error_code, "unknown_error")} ·{" "}
                {statusQuery.data.recent_failure.ticket_id}
              </p>
            </article>
          ) : (
            <article className="gmail-ops-inline-card">
              <span>最近失败</span>
              <strong>当前没有失败交接项</strong>
              <p>目前 ops 快照没有报告失败运行。</p>
            </article>
          )}
        </section>
      </section>

      <section className="gmail-ops-deck-grid">
        <PreviewDeck preview={previewResult} />
        <ScanDeck result={scanResult} />
      </section>
    </article>
  );
}
