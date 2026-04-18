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
import {
  EmptyState,
  Field,
  InlineNotice,
  MetricCard,
  Panel,
  StatusTag,
  Toolbar,
} from "@/ui-v2/primitives";

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
      { label: "邮箱", value: "正在加载运行态", note: "等待 GET /ops/status 返回。" },
      { label: "队列", value: "正在加载运行态", note: "等待队列快照。" },
      { label: "依赖", value: "正在加载运行态", note: "等待依赖状态。" },
    ];
  }

  return [
    {
      label: "邮箱",
      value: status.gmail.enabled ? "已连接" : "已禁用",
      note: status.gmail.account_email
        ? `${status.gmail.account_email} · 最近扫描 ${formatTimestamp(status.gmail.last_scan_at)}`
        : `最近扫描 ${formatTimestamp(status.gmail.last_scan_at)}`,
    },
    {
      label: "队列",
      value: `${formatNumber(status.queue.queued_runs)} 个排队 / ${formatNumber(status.queue.running_runs)} 个运行中`,
      note: `${formatNumber(status.queue.waiting_external_tickets)} 个等待外部处理 · ${formatNumber(status.queue.error_tickets)} 个错误工单`,
    },
    {
      label: "依赖",
      value: `Gmail ${labelForCode(status.dependencies.gmail)} / 数据库 ${labelForCode(status.dependencies.database)}`,
      note: `LLM ${labelForCode(status.dependencies.llm)} · checkpointing ${labelForCode(status.dependencies.checkpointing)}`,
    },
  ];
}

export function GmailOpsPageV2() {
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
    <section className="v2-stack">
      <Panel
        label="Gmail 运维"
        title="手动控制邮箱摄入批次"
        description="先看状态，再决定预览或执行。"
      >
        <div className="v2-metric-grid" aria-label="Gmail 运维区域">
          {runtimeCards.map((card) => (
            <MetricCard key={card.label} label={card.label} value={card.value} note={card.note} />
          ))}
          <MetricCard
            label="运行模式"
            value={enqueue ? "扫描并入队" : "仅扫描"}
            note="是否在摄入后自动创建运行"
            tone="accent"
          />
        </div>
      </Panel>

      {statusQuery.isError ? (
        <InlineNotice
          tone="error"
          title="状态不可用"
          detail={getErrorMessage(statusQuery.error, "Ops status 请求失败。")}
        />
      ) : null}

      {notice ? (
        <InlineNotice
          tone={notice.tone === "success" ? "success" : "error"}
          title={notice.title}
          detail={notice.detail}
        />
      ) : null}

      <Toolbar
        actions={
          <div className="v2-action-row">
            <button
              type="button"
              className="v2-button"
              onClick={() => void handlePreview()}
              disabled={previewMutation.isPending}
            >
              预览扫描
            </button>
            <button
              type="button"
              className="v2-button is-primary"
              onClick={() => void handleScan()}
              disabled={scanMutation.isPending}
            >
              立即扫描
            </button>
            <button
              type="button"
              className="v2-button"
              onClick={() => void handleRefreshStatus()}
              disabled={statusQuery.isFetching}
            >
              刷新状态
            </button>
          </div>
        }
      >
        <Field label="最大结果数">
          <input
            value={maxResultsInput}
            onChange={(event) => setMaxResultsInput(event.target.value)}
            placeholder="20"
          />
        </Field>
        <Field label="摄入策略">
          <select
            aria-label="摄入策略"
            value={enqueue ? "enqueue" : "hold"}
            onChange={(event) => setEnqueue(event.target.value === "enqueue")}
          >
            <option value="enqueue">摄入后自动入队运行</option>
            <option value="hold">只摄入，不创建运行</option>
          </select>
        </Field>
      </Toolbar>

      <div className="v2-tiles-grid">
        <Panel
          label="预览池"
          title={previewResult ? `${previewResult.summary.candidate_threads} 个候选` : "等待预览"}
          actions={<StatusTag tone="muted">POST /ops/gmail/scan-preview</StatusTag>}
        >
          {previewResult ? (
            <div className="v2-stack">
              <div className="v2-summary-grid" aria-label="预览摘要">
                <MetricCard label="候选数" value={formatNumber(previewResult.summary.candidate_threads)} note="可进入摄入流程" />
                <MetricCard label="已有草稿" value={formatNumber(previewResult.summary.skipped_existing_draft_threads)} note="因草稿存在被跳过" />
                <MetricCard label="自发邮件" value={formatNumber(previewResult.summary.skipped_self_sent_threads)} note="因发件人与邮箱所有者一致被过滤" />
              </div>
              <section className="v2-divider-list" aria-label="预览候选列表">
                {previewResult.items.map((item) => (
                  <article key={item.source_thread_id} className="v2-divider-row">
                    <strong>{item.subject}</strong>
                    <p>{item.sender_email_raw}</p>
                    <div className="v2-action-row">
                      <StatusTag tone="muted">{item.source_thread_id}</StatusTag>
                      <StatusTag tone={item.skip_reason ? "danger" : "success"}>
                        {item.skip_reason ? labelForCode(item.skip_reason) : "候选"}
                      </StatusTag>
                    </div>
                  </article>
                ))}
              </section>
            </div>
          ) : (
            <EmptyState
              label="等待预览"
              title="当前还没有加载任何预览批次"
              description="执行“预览扫描”即可在不修改系统状态的前提下查看候选项和跳过原因。"
            />
          )}
        </Panel>

        <Panel
          label="执行回执"
          title={scanResult ? scanResult.scan_id : "等待执行"}
          actions={<StatusTag tone="muted">POST /ops/gmail/scan</StatusTag>}
        >
          {scanResult ? (
            <div className="v2-stack">
              <div className="v2-summary-grid" aria-label="扫描摘要">
                <MetricCard label="扫描线程" value={formatNumber(scanResult.summary.fetched_threads)} note="本次扫描的线程数" />
                <MetricCard label="摄入工单" value={formatNumber(scanResult.summary.ingested_tickets)} note="新创建工单数" />
                <MetricCard label="已入队运行" value={formatNumber(scanResult.summary.queued_runs)} note={scanResult.enqueue ? "本批次已创建运行" : "本批次未创建运行"} />
              </div>
              <section className="v2-divider-list" aria-label="扫描回执列表">
                {scanResult.items.map((item) => (
                  <article key={item.source_thread_id} className="v2-divider-row">
                    <strong>{item.ticket_id ?? "未创建工单"}</strong>
                    <p>{item.source_thread_id}</p>
                    <div className="v2-action-row">
                      <StatusTag tone={item.created_ticket ? "success" : "muted"}>
                        {item.created_ticket ? "已创建工单" : "复用已有工单"}
                      </StatusTag>
                      <StatusTag tone={item.queued_run_id ? "accent" : "muted"}>
                        {item.queued_run_id ?? "未生成入队运行"}
                      </StatusTag>
                    </div>
                  </article>
                ))}
              </section>
            </div>
          ) : (
            <EmptyState
              label="等待执行"
              title="当前会话里还没有任何扫描回执"
              description="在预览之后执行“立即扫描”，即可记录摄入数量、入队运行和工单映射。"
            />
          )}
        </Panel>
      </div>
    </section>
  );
}
