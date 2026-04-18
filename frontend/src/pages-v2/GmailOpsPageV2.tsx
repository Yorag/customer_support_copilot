import { startTransition, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { ApiClientError } from "@/lib/api/client";
import type {
  GmailScanPreviewResponse,
  OpsStatusResponse,
} from "@/lib/api/types";
import {
  formatNumberZh,
  formatTimestampZh,
  labelForCode,
} from "@/lib/presentation";
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
  Panel,
  StatusTag,
} from "@/ui-v2/primitives";

type ActionNotice = {
  tone: "success" | "error";
  title: string;
  detail: string;
};

function formatTimestamp(value?: string | null) {
  if (!value) {
    return "暂无记录";
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

function buildPageSummary(status: OpsStatusResponse | undefined, enqueue: boolean) {
  if (!status) {
    return "先刷新状态，再预览候选，最后决定是否把这一批直接入队。";
  }

  return [
    status.gmail.enabled ? "邮箱可扫描" : "邮箱未启用",
    enqueue ? "本次摄入后自动入队" : "本次仅摄入不入队",
    status.gmail.last_scan_at ? `最近扫描 ${formatTimestamp(status.gmail.last_scan_at)}` : "尚无扫描记录",
  ].join(" · ");
}

function buildPreviewItems(previewResult: GmailScanPreviewResponse | null) {
  if (!previewResult) {
    return [];
  }

  return previewResult.items.map((item) => ({
    id: item.source_thread_id,
    subject: item.subject,
    sender: item.sender_email_raw,
    sourceMessageId: item.source_message_id ?? "暂无源消息 ID",
    state: item.skip_reason ? labelForCode(item.skip_reason) : "待摄入",
    note: item.skip_reason ? "本次批次会跳过" : "会进入本次摄入批次",
    tone: item.skip_reason ? ("danger" as const) : ("accent" as const),
  }));
}

function buildPreviewSummary(previewResult: GmailScanPreviewResponse | null) {
  if (!previewResult) {
    return "先点“预览候选”，这里才会显示本批待处理新邮件。";
  }

  return [
    `${formatNumber(previewResult.summary.candidate_threads)} 个待摄入候选`,
    `${formatNumber(previewResult.summary.skipped_existing_draft_threads)} 个已有草稿`,
    `${formatNumber(previewResult.summary.skipped_self_sent_threads)} 个自发邮件`,
  ].join(" · ");
}

export function GmailOpsPageV2() {
  const queryClient = useQueryClient();
  const statusQuery = useGmailOpsStatus();
  const previewMutation = usePreviewGmailScan();
  const scanMutation = useScanGmail();
  const [maxResultsInput, setMaxResultsInput] = useState("20");
  const [enqueue, setEnqueue] = useState(true);
  const [previewResult, setPreviewResult] = useState<GmailScanPreviewResponse | null>(null);
  const [notice, setNotice] = useState<ActionNotice | null>(null);

  const maxResults = parseMaxResults(maxResultsInput);
  const pageSummary = buildPageSummary(statusQuery.data, enqueue);
  const previewItems = buildPreviewItems(previewResult);
  const previewSummary = buildPreviewSummary(previewResult);

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
        setNotice({
          tone: "success",
          title: "批次已提交",
          detail: enqueue
            ? `已摄入 ${result.summary.ingested_tickets} 个工单，并入队 ${result.summary.queued_runs} 次运行。`
            : `已摄入 ${result.summary.ingested_tickets} 个工单，本次未自动入队。`,
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
    <section className="v2-stack v2-gmail-ops-page">
      <Panel
        label="Gmail 运维"
        title="摄入与入队"
        description={pageSummary}
      >
        <section className="v2-gmail-ops-toolbar-row" aria-label="Gmail 运维区域">
          <div className="v2-gmail-ops-toolbar-fields">
            <Field label="入队方式">
              <select
                aria-label="入队方式"
                value={enqueue ? "enqueue" : "hold"}
                onChange={(event) => setEnqueue(event.target.value === "enqueue")}
              >
                <option value="enqueue">摄入后自动入队运行</option>
                <option value="hold">只摄入，不创建运行</option>
              </select>
            </Field>

            <Field label="扫描上限">
              <input
                aria-label="扫描上限"
                value={maxResultsInput}
                onChange={(event) => setMaxResultsInput(event.target.value)}
                placeholder="20"
              />
            </Field>
          </div>

          <div className="v2-action-row v2-gmail-ops-toolbar-actions">
            <button
              type="button"
              className="v2-button"
              onClick={() => void handleRefreshStatus()}
              disabled={statusQuery.isFetching}
            >
              刷新状态
            </button>
            <button
              type="button"
              className="v2-button"
              onClick={() => void handlePreview()}
              disabled={previewMutation.isPending}
            >
              预览候选
            </button>
            <button
              type="button"
              className="v2-button is-primary"
              onClick={() => void handleScan()}
              disabled={scanMutation.isPending}
            >
              全部摄入当前批次
            </button>
          </div>
        </section>
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

      <Panel
        label="待入队新邮件"
        title={previewResult ? "候选邮件瀑布流" : "等待候选邮件"}
        description={previewSummary}
      >
        {previewItems.length > 0 ? (
          <div className="v2-gmail-ops-waterfall" aria-label="预览候选列表">
            {previewItems.map((item) => (
              <article
                key={item.id}
                className={`v2-gmail-ops-waterfall-card${item.tone ? ` is-${item.tone}` : ""}`}
              >
                <div className="v2-gmail-ops-waterfall-head">
                  <StatusTag tone={item.tone}>{item.state}</StatusTag>
                  <span className="v2-code">{item.id}</span>
                </div>
                <strong>{item.subject}</strong>
                <p>{item.sender}</p>
                <p className="v2-gmail-ops-waterfall-note">{item.note}</p>
                <p className="v2-gmail-ops-waterfall-meta">{item.sourceMessageId}</p>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            label="等待候选"
            title="当前还没有待处理新邮件"
            description="先点“预览候选”，这里会用瀑布列表显示本批候选邮件。"
          />
        )}
      </Panel>
    </section>
  );
}
