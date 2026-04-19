import { useDeferredValue, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiClientError } from "@/lib/api/client";
import type {
  EvaluationSummaryRef,
  TicketMessage,
  TicketSnapshotResponse,
} from "@/lib/api/types";
import {
  formatScoreZh,
  formatTimestampZh,
  labelForCode,
} from "@/lib/presentation";
import {
  useApproveTicket,
  useCloseTicket,
  useEditAndApproveTicket,
  useEscalateTicket,
  useGenerateTicketDraft,
  useSaveTicketDraft,
  useTicketDrafts,
  useTicketRuns,
  useTicketSnapshot,
} from "@/lib/query/tickets";
import { useConsoleUiStore } from "@/state/console-ui-store";
import {
  EmptyState,
  Field,
  InlineNotice,
  Panel,
  StatusTag,
} from "@/ui-v2/primitives";

const RUN_HISTORY_PAGE_SIZE = 20;

type ActionNotice = {
  tone: "success" | "error";
  title: string;
  detail: string;
};

type FocusItem = {
  key: string;
  label: string;
  value: string;
  detail: string;
  tone?: "default" | "accent" | "success" | "danger" | "muted";
};

function shortenId(value: string) {
  if (value.length <= 18) {
    return value;
  }

  return `${value.slice(0, 12)}...${value.slice(-4)}`;
}

function formatTimestamp(value?: string | null) {
  return formatTimestampZh(value);
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

function getMessageTone(message: TicketMessage) {
  if (message.direction === "inbound") {
    return "accent" as const;
  }

  if (message.customer_visible) {
    return "success" as const;
  }

  return "muted" as const;
}

function getBusinessTone(status?: string | null) {
  if (status === "awaiting_human_review") {
    return "accent" as const;
  }

  if (status === "escalated") {
    return "danger" as const;
  }

  if (status === "approved" || status === "closed") {
    return "success" as const;
  }

  return "muted" as const;
}

function getRunTone(status?: string | null) {
  if (status === "failed" || status === "error") {
    return "danger" as const;
  }

  if (status === "succeeded" || status === "completed") {
    return "success" as const;
  }

  if (status === "running" || status === "queued") {
    return "accent" as const;
  }

  return "muted" as const;
}

function getMessageHeader(message: TicketMessage) {
  const metadata = (message.metadata ?? {}) as Record<string, unknown>;
  const senderEmailRaw =
    typeof metadata.sender_email_raw === "string" ? metadata.sender_email_raw : null;
  const sender =
    senderEmailRaw ?? message.sender_email ?? (message.direction === "inbound" ? "客户" : "系统");
  const recipients =
    message.recipient_emails.length > 0 ? message.recipient_emails.join(", ") : "未记录收件人";
  const relation = message.reply_to_source_message_id
    ? `回复 ${shortenId(message.reply_to_source_message_id)}`
    : "线程起点";

  return {
    sender,
    senderEmailRaw,
    recipients,
    relation,
    metadata,
    note: `${labelForCode(message.direction)} · ${labelForCode(message.message_type)} · ${formatTimestamp(message.message_timestamp)}`,
  };
}

function getMessagePreview(message: TicketMessage) {
  const body = message.body_text?.trim();
  if (body) {
    return body;
  }

  return "该消息没有可展示的正文。";
}

function formatMetadata(metadata?: Record<string, unknown> | null) {
  if (!metadata || Object.keys(metadata).length === 0) {
    return "无额外元数据。";
  }

  return JSON.stringify(metadata, null, 2);
}

function describeEvalStatus(summary: EvaluationSummaryRef) {
  if (summary.status === "complete") {
    return `质量 ${formatScore(summary.response_quality_overall_score)} · 轨迹 ${formatScore(summary.trajectory_score)}`;
  }

  if (summary.status === "partial") {
    if (summary.has_response_quality) {
      return `质量 ${formatScore(summary.response_quality_overall_score)} · 轨迹待补齐`;
    }

    if (summary.has_trajectory_evaluation) {
      return `轨迹 ${formatScore(summary.trajectory_score)} · ${summary.trajectory_violation_count ?? 0} 条违规`;
    }
  }

  return "评估结果暂不可用";
}

function hasResponseQuality(summary: EvaluationSummaryRef | undefined | null) {
  return Boolean(summary?.has_response_quality);
}

function hasTrajectoryEvaluation(summary: EvaluationSummaryRef | undefined | null) {
  return Boolean(summary?.has_trajectory_evaluation);
}

function buildHeroDescription(
  snapshot: TicketSnapshotResponse | undefined,
  latestInboundMessage: TicketMessage | undefined,
) {
  if (!snapshot) {
    return "正在载入工单快照。";
  }

  const subject = latestInboundMessage?.subject?.trim();
  if (subject) {
    return `${subject} · 版本 ${snapshot.ticket.version}`;
  }

  return `${labelForCode(snapshot.ticket.business_status)} · ${labelForCode(snapshot.ticket.processing_status)} · 版本 ${snapshot.ticket.version}`;
}

function buildFocusItems(
  snapshot: TicketSnapshotResponse | undefined,
  currentDraftId: string | null,
  currentDraftStatus: string | null,
  runsCount: number,
): FocusItem[] {
  if (!snapshot) {
    return [
      {
        key: "status",
        label: "当前状态",
        value: "正在加载",
        detail: "等待快照",
      },
      {
        key: "route",
        label: "当前路由",
        value: "正在加载",
        detail: "等待快照",
      },
      {
        key: "draft",
        label: "当前草稿",
        value: "正在加载",
        detail: "等待草稿",
      },
      {
        key: "run",
        label: "运行交接",
        value: "正在加载",
        detail: "等待运行历史",
      },
    ];
  }

  return [
    {
      key: "status",
      label: "当前状态",
      value: labelForCode(snapshot.ticket.business_status),
      detail: labelForCode(snapshot.ticket.processing_status),
      tone: getBusinessTone(snapshot.ticket.business_status),
    },
    {
      key: "route",
      label: "当前路由",
      value: snapshot.ticket.primary_route
        ? labelForCode(snapshot.ticket.primary_route)
        : "路由待定",
      detail: snapshot.ticket.multi_intent ? "多意图工单" : "单意图工单",
      tone: "muted",
    },
    {
      key: "draft",
      label: "当前草稿",
      value: currentDraftStatus ? labelForCode(currentDraftStatus) : "暂无草稿",
      detail: currentDraftId ? shortenId(currentDraftId) : "等待第一次起草",
      tone: currentDraftStatus === "passed" ? "success" : "muted",
    },
    {
      key: "run",
      label: "运行交接",
      value: snapshot.latest_run ? labelForCode(snapshot.latest_run.status) : "暂无运行",
      detail: snapshot.latest_run
        ? `${shortenId(snapshot.latest_run.run_id)} · 共 ${runsCount} 次`
        : "还没有可交接的执行记录",
      tone: getRunTone(snapshot.latest_run?.status),
    },
  ];
}

function parseRewriteReasons(value: string) {
  return value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function normalizeDraftBody(value?: string | null) {
  return (value ?? "").replace(/\r\n/g, "\n").trim();
}

function formatActionResult(
  title: string,
  result: {
    business_status: string;
    processing_status: string;
    version: number;
    review_id?: string | null;
  },
): ActionNotice {
  return {
    tone: "success",
    title,
    detail: `${labelForCode(result.business_status)} · ${labelForCode(result.processing_status)} · 工单版本 ${result.version}${result.review_id ? ` · 审核 ${result.review_id}` : ""}。`,
  };
}

export function TicketDetailPageV2() {
  const navigate = useNavigate();
  const params = useParams<{ ticketId: string }>();
  const selectedTicketId = useConsoleUiStore((state) => state.selectedTicketId);
  const setSelectedTicketId = useConsoleUiStore((state) => state.setSelectedTicketId);
  const setSelectedRunId = useConsoleUiStore((state) => state.setSelectedRunId);
  const ticketId = params.ticketId ?? selectedTicketId ?? "";
  const deferredTicketId = useDeferredValue(ticketId);
  const [actorId, setActorId] = useState("reviewer-console");
  const [operatorComment, setOperatorComment] = useState("");
  const [manualReplyText, setManualReplyText] = useState("");
  const [rewriteReasons, setRewriteReasons] = useState("");
  const [targetQueue, setTargetQueue] = useState("human_review");
  const [closeReason, setCloseReason] = useState("resolved_manually");
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const [seededDraftId, setSeededDraftId] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<ActionNotice | null>(null);

  useEffect(() => {
    if (params.ticketId && params.ticketId !== selectedTicketId) {
      setSelectedTicketId(params.ticketId);
    }
  }, [params.ticketId, selectedTicketId, setSelectedTicketId]);

  const snapshotQuery = useTicketSnapshot(deferredTicketId);
  const runsQuery = useTicketRuns(deferredTicketId, 1, RUN_HISTORY_PAGE_SIZE);
  const draftsQuery = useTicketDrafts(deferredTicketId);
  const approveMutation = useApproveTicket(deferredTicketId);
  const saveDraftMutation = useSaveTicketDraft(deferredTicketId);
  const editAndApproveMutation = useEditAndApproveTicket(deferredTicketId);
  const escalateMutation = useEscalateTicket(deferredTicketId);
  const closeMutation = useCloseTicket(deferredTicketId);
  const generateDraftMutation = useGenerateTicketDraft(deferredTicketId);

  const snapshot = snapshotQuery.data;
  const runs = runsQuery.data?.items ?? [];
  const drafts = draftsQuery.data?.items ?? [];
  const messages = snapshot?.messages ?? [];
  const latestRun = snapshot?.latest_run ?? null;
  const latestDraft = drafts.at(-1) ?? null;
  const currentDraftId = latestDraft?.draft_id ?? snapshot?.latest_draft?.draft_id ?? null;
  const currentDraftStatus = latestDraft?.qa_status ?? snapshot?.latest_draft?.qa_status ?? null;
  const currentDraftBody = latestDraft?.content_text ?? "";
  const latestInboundMessage = [...messages]
    .reverse()
    .find((message) => message.direction === "inbound");
  const selectedMessage =
    messages.find((message) => message.ticket_message_id === selectedMessageId) ??
    latestInboundMessage ??
    messages.at(-1);
  const ticketVersion = snapshot?.ticket.version;
  const focusItems = buildFocusItems(
    snapshot,
    currentDraftId,
    currentDraftStatus,
    runsQuery.data?.total ?? 0,
  );
  const draftDirty = normalizeDraftBody(manualReplyText) !== normalizeDraftBody(currentDraftBody);
  const actionsBusy =
    generateDraftMutation.isPending ||
    approveMutation.isPending ||
    saveDraftMutation.isPending ||
    editAndApproveMutation.isPending ||
    escalateMutation.isPending ||
    closeMutation.isPending;

  useEffect(() => {
    const preferredMessageId =
      latestInboundMessage?.ticket_message_id ?? messages.at(-1)?.ticket_message_id ?? null;

    if (!selectedMessageId || !messages.some((message) => message.ticket_message_id === selectedMessageId)) {
      setSelectedMessageId(preferredMessageId);
    }
  }, [latestInboundMessage, messages, selectedMessageId]);

  useEffect(() => {
    if (latestDraft?.draft_id && latestDraft.draft_id !== seededDraftId) {
      setManualReplyText(latestDraft.content_text);
      setSeededDraftId(latestDraft.draft_id);
      return;
    }

    if (!latestDraft?.draft_id && seededDraftId !== null) {
      setManualReplyText("");
      setSeededDraftId(null);
    }
  }, [latestDraft?.content_text, latestDraft?.draft_id, seededDraftId]);

  function openTrace() {
    if (!ticketId || !latestRun?.run_id) {
      return;
    }

    setSelectedTicketId(ticketId);
    setSelectedRunId(latestRun.run_id);
    navigate(`/trace?ticketId=${encodeURIComponent(ticketId)}&runId=${encodeURIComponent(latestRun.run_id)}`);
  }

  async function handleApprove() {
    if (!ticketVersion || !currentDraftId || !actorId.trim()) {
      return;
    }

    try {
      const result = await approveMutation.mutateAsync({
        actorId: actorId.trim(),
        payload: {
          ticket_version: ticketVersion,
          draft_id: currentDraftId,
          comment: operatorComment.trim() || null,
        },
      });
      setActionNotice(formatActionResult("已记录批准动作", result));
    } catch (error) {
      setActionNotice({
        tone: "error",
        title: "批准失败",
        detail: getErrorMessage(error, "批准请求失败。"),
      });
    }
  }

  async function handleGenerateDraft() {
    if (!ticketVersion || !actorId.trim()) {
      return;
    }

    const isRegenerate = Boolean(currentDraftId);
    try {
      const result = await generateDraftMutation.mutateAsync({
        actorId: actorId.trim(),
        payload: {
          ticket_version: ticketVersion,
          mode: isRegenerate ? "regenerate" : "create",
          source_draft_id: currentDraftId,
          comment: operatorComment.trim() || null,
        },
      });
      setActionNotice({
        tone: "success",
        title: isRegenerate ? "已提交重新生成草稿" : "已提交创建草稿",
        detail: `运行 ${shortenId(result.run_id)} 已入队，当前状态 ${labelForCode(result.processing_status)}。`,
      });
    } catch (error) {
      setActionNotice({
        tone: "error",
        title: isRegenerate ? "重新生成草稿失败" : "创建草稿失败",
        detail: getErrorMessage(error, "草稿生成请求失败。"),
      });
    }
  }

  function syncManualReplyFromLatestDraft() {
    if (!latestDraft) {
      return;
    }

    setManualReplyText(latestDraft.content_text);
  }

  async function handleSaveDraft() {
    if (!ticketVersion || !currentDraftId || !actorId.trim() || !manualReplyText.trim()) {
      return;
    }

    try {
      const result = await saveDraftMutation.mutateAsync({
        actorId: actorId.trim(),
        payload: {
          ticket_version: ticketVersion,
          draft_id: currentDraftId,
          comment: operatorComment.trim() || null,
          edited_content_text: manualReplyText.trim(),
        },
      });
      setActionNotice(formatActionResult("草稿已保存", result));
    } catch (error) {
      setActionNotice({
        tone: "error",
        title: "草稿保存失败",
        detail: getErrorMessage(error, "草稿保存请求失败。"),
      });
    }
  }

  async function handleSaveAndClose() {
    if (!ticketVersion || !currentDraftId || !actorId.trim() || !manualReplyText.trim()) {
      return;
    }

    let approvalResult:
      | {
          business_status: string;
          processing_status: string;
          review_id?: string | null;
          ticket_id: string;
          version: number;
        }
      | undefined;

    try {
      approvalResult = await editAndApproveMutation.mutateAsync({
        actorId: actorId.trim(),
        payload: {
          ticket_version: ticketVersion,
          draft_id: currentDraftId,
          comment: operatorComment.trim() || null,
          edited_content_text: manualReplyText.trim(),
        },
      });
    } catch (error) {
      setActionNotice({
        tone: "error",
        title: "保存并关闭失败",
        detail: getErrorMessage(error, "保存人工回复并批准失败。"),
      });
      return;
    }

    if (!closeReason.trim()) {
      setActionNotice({
        tone: "error",
        title: "缺少关闭原因",
        detail: "保存并关闭工单前，必须填写关闭原因。",
      });
      return;
    }

    try {
      const closeResult = await closeMutation.mutateAsync({
        actorId: actorId.trim(),
        payload: {
          ticket_version: approvalResult.version,
          reason: closeReason.trim(),
        },
      });
      setActionNotice(formatActionResult("人工回复已保存并关闭工单", closeResult));
    } catch (error) {
      setActionNotice({
        tone: "error",
        title: "人工回复已保存，但关闭失败",
        detail: getErrorMessage(error, "关闭请求失败。"),
      });
    }
  }

  async function handleRewrite() {
    if (!ticketVersion || !actorId.trim()) {
      return;
    }

    const reasons = parseRewriteReasons(rewriteReasons);
    if (reasons.length === 0) {
      setActionNotice({
        tone: "error",
        title: "必须填写重写原因",
        detail: "在重新提交工单前，至少填写一条重写原因。",
      });
      return;
    }

    try {
      const result = await generateDraftMutation.mutateAsync({
        actorId: actorId.trim(),
        payload: {
          ticket_version: ticketVersion,
          mode: currentDraftId ? "regenerate" : "create",
          source_draft_id: currentDraftId,
          comment: operatorComment.trim() || null,
          rewrite_guidance: reasons,
        },
      });
      setActionNotice({
        tone: "success",
        title: "已提交带指导的草稿重生成",
        detail: `运行 ${shortenId(result.run_id)} 已入队，当前状态 ${labelForCode(result.processing_status)}。`,
      });
    } catch (error) {
      setActionNotice({
        tone: "error",
        title: "按原因重写失败",
        detail: getErrorMessage(error, "带指导的草稿重生成请求失败。"),
      });
    }
  }

  async function handleEscalate() {
    if (!ticketVersion || !actorId.trim() || !targetQueue.trim()) {
      return;
    }

    try {
      const result = await escalateMutation.mutateAsync({
        actorId: actorId.trim(),
        payload: {
          ticket_version: ticketVersion,
          comment: operatorComment.trim() || null,
          target_queue: targetQueue.trim(),
        },
      });
      setActionNotice(formatActionResult("已记录外部升级动作", result));
    } catch (error) {
      setActionNotice({
        tone: "error",
        title: "外部升级失败",
        detail: getErrorMessage(error, "外部升级请求失败。"),
      });
    }
  }

  async function handleClose() {
    if (!ticketVersion || !actorId.trim() || !closeReason.trim()) {
      return;
    }

    try {
      const result = await closeMutation.mutateAsync({
        actorId: actorId.trim(),
        payload: {
          ticket_version: ticketVersion,
          reason: closeReason.trim(),
        },
      });
      setActionNotice(formatActionResult("工单已关闭", result));
    } catch (error) {
      setActionNotice({
        tone: "error",
        title: "关闭动作失败",
        detail: getErrorMessage(error, "关闭请求失败。"),
      });
    }
  }

  if (!ticketId) {
    return (
      <EmptyState
        label="没有激活工单"
        title="当前还没有选中任何案件"
        description="请先从工单列表进入详情页。"
      />
    );
  }

  return (
    <section className="v2-stack">
      <Panel
        label="案件"
        title={ticketId}
        description={buildHeroDescription(snapshot, latestInboundMessage)}
        actions={
          <div className="v2-action-row" aria-label="工单详情区域">
            <StatusTag tone={getBusinessTone(snapshot?.ticket.business_status)}>
              {snapshot ? labelForCode(snapshot.ticket.business_status) : "实时快照"}
            </StatusTag>
            <StatusTag tone="muted">
              {snapshot ? labelForCode(snapshot.ticket.processing_status) : "等待快照"}
            </StatusTag>
            <StatusTag tone="muted">
              {snapshot?.ticket.primary_route
                ? labelForCode(snapshot.ticket.primary_route)
                : "路由待定"}
            </StatusTag>
            <StatusTag tone="muted">
              {snapshot ? `v${snapshot.ticket.version}` : "版本待返回"}
            </StatusTag>
            <StatusTag tone="muted">
              {snapshot?.ticket.claimed_by
                ? `租约至 ${formatTimestamp(snapshot.ticket.lease_until)}`
                : "未占用"}
            </StatusTag>
          </div>
        }
      />

      {snapshotQuery.isError || runsQuery.isError || draftsQuery.isError ? (
        <InlineNotice
          tone="error"
          title="部分详情数据没有成功返回"
          detail={
            snapshotQuery.isError
              ? getErrorMessage(snapshotQuery.error, "快照请求失败。")
              : runsQuery.isError
                ? getErrorMessage(runsQuery.error, "运行历史请求失败。")
                : getErrorMessage(draftsQuery.error, "草稿历史请求失败。")
          }
        />
      ) : null}

      <Panel label="处理焦点" title="当前状态">
        <section className="v2-ticket-focus-grid" aria-label="工单处理焦点">
          {focusItems.map((item) => (
            <article
              key={item.key}
              className={`v2-ticket-focus-card${item.tone ? ` is-${item.tone}` : ""}`}
            >
              <p className="v2-panel-label">{item.label}</p>
              <strong>{item.value}</strong>
              <p>{item.detail}</p>
            </article>
          ))}
        </section>
      </Panel>

      <section className="v2-ticket-detail-layout">
        <div className="v2-ticket-detail-main">
          <Panel
            label="客户邮件"
            title={selectedMessage ? "原始邮件" : "等待客户来信"}
            actions={
              selectedMessage ? (
                <div className="v2-action-row" aria-label="邮件状态">
                  <StatusTag tone={getMessageTone(selectedMessage)}>
                    {labelForCode(selectedMessage.direction)}
                  </StatusTag>
                  <StatusTag tone="muted">
                    {labelForCode(selectedMessage.message_type)}
                  </StatusTag>
                </div>
              ) : null
            }
          >
            {selectedMessage ? (
              <section className="v2-ticket-stage-block v2-ticket-email-stage">
                <div className="v2-ticket-email-header">
                  <div className="v2-ticket-email-subject-row">
                    <div>
                      <p className="v2-panel-label">邮件主题</p>
                      <h3 className="v2-ticket-email-subject">
                        {selectedMessage.subject || "无主题邮件"}
                      </h3>
                    </div>
                  </div>
                  <dl className="v2-ticket-email-lines" aria-label="原始邮件头信息">
                    <div className="v2-ticket-email-line">
                      <dt>发件人</dt>
                      <dd>{getMessageHeader(selectedMessage).sender}</dd>
                    </div>
                    <div className="v2-ticket-email-line">
                      <dt>收件人</dt>
                      <dd>{getMessageHeader(selectedMessage).recipients}</dd>
                    </div>
                    <div className="v2-ticket-email-line">
                      <dt>时间</dt>
                      <dd>{formatTimestamp(selectedMessage.message_timestamp)}</dd>
                    </div>
                    <div className="v2-ticket-email-line">
                      <dt>Message-ID</dt>
                      <dd className="v2-code">{selectedMessage.source_message_id}</dd>
                    </div>
                    <div className="v2-ticket-email-line">
                      <dt>线程关系</dt>
                      <dd>{getMessageHeader(selectedMessage).relation}</dd>
                    </div>
                  </dl>
                </div>

                <section className="v2-ticket-email-body" aria-label="原始邮件正文">
                  <pre className="v2-ticket-email-pre">{getMessagePreview(selectedMessage)}</pre>
                </section>

                <details className="v2-ticket-inline-drawer">
                  <summary>{messages.length > 0 ? `邮件线程 ${messages.length} 条消息` : "邮件线程"}</summary>
                  <section className="v2-ticket-message-drawer">
                    {messages.length > 0 ? (
                      <section className="v2-divider-list" aria-label="工单消息线程">
                        {messages
                          .slice()
                          .reverse()
                          .map((message) => {
                            const header = getMessageHeader(message);

                            return (
                              <button
                                key={message.ticket_message_id}
                                type="button"
                                className={`v2-divider-row v2-ticket-thread-entry${
                                  selectedMessage?.ticket_message_id === message.ticket_message_id
                                    ? " is-active"
                                    : ""
                                }`}
                                aria-pressed={
                                  selectedMessage?.ticket_message_id === message.ticket_message_id
                                }
                                onClick={() => setSelectedMessageId(message.ticket_message_id)}
                              >
                                <div className="v2-action-row">
                                  <StatusTag tone={getMessageTone(message)}>
                                    {labelForCode(message.direction)}
                                  </StatusTag>
                                  <StatusTag tone="muted">
                                    {labelForCode(message.message_type)}
                                  </StatusTag>
                                  <StatusTag tone="muted">{header.relation}</StatusTag>
                                </div>
                                <strong>{message.subject || "无主题消息"}</strong>
                                <p>{header.note}</p>
                                <p>{header.sender}</p>
                                <p>{getMessagePreview(message).slice(0, 220)}</p>
                              </button>
                            );
                          })}
                      </section>
                    ) : (
                      <EmptyState
                        label="没有线程历史"
                        title="当前还没有更多上下文"
                      />
                    )}

                    <div className="v2-ticket-message-drawer-grid">
                      <article className="v2-ticket-message-drawer-card">
                        <span>发件人信封</span>
                        <strong>
                          {getMessageHeader(selectedMessage).senderEmailRaw ??
                            selectedMessage.sender_email ??
                            "未记录"}
                        </strong>
                      </article>
                      <article className="v2-ticket-message-drawer-card">
                        <span>run 关联</span>
                        <strong className="v2-code">{selectedMessage.run_id ?? "未关联"}</strong>
                      </article>
                      <article className="v2-ticket-message-drawer-card">
                        <span>draft 关联</span>
                        <strong className="v2-code">{selectedMessage.draft_id ?? "未关联"}</strong>
                      </article>
                    </div>
                    <div className="v2-ticket-draft-frame v2-ticket-message-raw">
                      <p className="v2-panel-label">Metadata</p>
                      <pre className="v2-ticket-draft-content">
                        {formatMetadata(getMessageHeader(selectedMessage).metadata)}
                      </pre>
                    </div>
                  </section>
                </details>
              </section>
            ) : (
              <EmptyState
                label="暂无原始消息"
                title="当前工单还没有可展示的客户邮件"
              />
            )}
          </Panel>

          <Panel
            label="运行交接"
            title="最新运行"
            className="v2-ticket-run-panel"
            description={latestRun ? undefined : "暂无可查看的运行。"}
            actions={
              latestRun ? (
                <button type="button" className="v2-button" onClick={openTrace}>
                  打开 Trace
                </button>
              ) : null
            }
          >
            <section className="v2-ticket-run-grid">
              <div className="v2-ticket-run-card">
                <p className="v2-panel-label">运行</p>
                <strong className="v2-code">
                  {latestRun ? latestRun.run_id : "当前没有关联运行"}
                </strong>
                {latestRun ? (
                  <p>
                    {labelForCode(latestRun.status)} ·{" "}
                    {latestRun.final_action ? labelForCode(latestRun.final_action) : "最终动作待定"}
                  </p>
                ) : (
                  <p>暂无运行记录。</p>
                )}
              </div>
              <div className="v2-ticket-run-card">
                <p className="v2-panel-label">Trace</p>
                <strong className="v2-code">{latestRun?.trace_id ?? "--"}</strong>
                {!latestRun ? <p>暂无 Trace 关联。</p> : null}
              </div>
              <div className="v2-ticket-run-card v2-ticket-run-card-wide">
                <p className="v2-panel-label">评估摘要</p>
                <strong>{latestRun ? describeEvalStatus(latestRun.evaluation_summary_ref) : "评估结果暂不可用"}</strong>
                {!latestRun ? <p>暂无评估摘要。</p> : null}
                {latestRun && !hasResponseQuality(latestRun.evaluation_summary_ref) ? (
                  <p>当前运行没有回复质量评分，只展示常规运行与轨迹信息。</p>
                ) : null}
              </div>
            </section>

            <details className="v2-ticket-inline-drawer">
              <summary>
                {runs.length > 0 ? `运行历史 ${runsQuery.data?.total ?? runs.length} 次` : "运行历史"}
              </summary>
              {runs.length > 0 ? (
                <section className="v2-divider-list" aria-label="运行历史卷带">
                  {runs.map((run) => (
                    <article key={run.run_id} className="v2-divider-row">
                      <strong>{run.run_id}</strong>
                      <p>
                        尝试 {run.attempt_index} · {labelForCode(run.status)} ·{" "}
                        {run.final_action ? labelForCode(run.final_action) : "暂无最终动作"}
                      </p>
                      <p>
                        {labelForCode(run.trigger_type)} · {run.triggered_by ?? "系统"} ·{" "}
                        {describeEvalStatus(run.evaluation_summary_ref)}
                      </p>
                    </article>
                  ))}
                </section>
              ) : (
                <EmptyState
                  label="暂无运行历史"
                  title="这个工单还没有任何已记录尝试"
                />
              )}
            </details>
          </Panel>
        </div>

        <div className="v2-ticket-detail-side">
          <Panel
            label="处理"
            title="草稿与动作"
            actions={
              <div className="v2-action-row" aria-label="人工动作状态">
                <StatusTag tone="muted">
                  {currentDraftId ? `草稿 ${shortenId(currentDraftId)}` : "暂无草稿"}
                </StatusTag>
                <StatusTag tone="muted">
                  {ticketVersion ? `工单 v${ticketVersion}` : "快照待返回"}
                </StatusTag>
                {actionsBusy ? <StatusTag tone="accent">提交中</StatusTag> : null}
              </div>
            }
          >
            {actionNotice ? (
              <InlineNotice
                tone={actionNotice.tone === "success" ? "success" : "error"}
                title={actionNotice.title}
                detail={actionNotice.detail}
              />
            ) : null}

            <section className="v2-ticket-stage-block">
              <div className="v2-ticket-section-head">
                <div>
                  <p className="v2-panel-label">当前草稿</p>
                  <h3 className="v2-ticket-section-title">
                    {latestDraft ? "草稿正文" : "当前没有草稿"}
                  </h3>
                </div>
                {latestDraft ? (
                  <div className="v2-action-row">
                    <StatusTag tone="muted">v{latestDraft.version_index}</StatusTag>
                    <StatusTag tone={latestDraft.qa_status === "passed" ? "success" : "muted"}>
                      {labelForCode(latestDraft.qa_status)}
                    </StatusTag>
                    <StatusTag tone="muted">{formatTimestamp(latestDraft.created_at)}</StatusTag>
                  </div>
                ) : null}
              </div>

              {latestDraft ? (
                <div className="v2-ticket-draft-frame">
                  <pre className="v2-ticket-draft-content">{latestDraft.content_text}</pre>
                </div>
              ) : (
                <EmptyState
                  label="暂无草稿"
                  title="该工单当前没有任何草稿版本"
                />
              )}

              <details className="v2-ticket-inline-drawer">
                <summary>{drafts.length > 0 ? `草稿历史 ${drafts.length} 个版本` : "草稿历史"}</summary>
                {drafts.length > 0 ? (
                  <section className="v2-divider-list" aria-label="草稿版本阶梯">
                    {drafts
                      .slice()
                      .reverse()
                      .map((draft) => (
                        <article key={draft.draft_id} className="v2-divider-row">
                          <strong>{draft.draft_id}</strong>
                          <p>
                            版本 {draft.version_index} · {labelForCode(draft.qa_status)} ·{" "}
                            {labelForCode(draft.draft_type)}
                          </p>
                          <p>{formatTimestamp(draft.created_at)}</p>
                        </article>
                      ))}
                  </section>
                ) : (
                  <EmptyState
                    label="没有草稿历史"
                    title="当前没有可展示的草稿版本"
                  />
                )}
              </details>
            </section>

            <section className="v2-ticket-stage-block">
              <div className="v2-ticket-section-head">
                <div>
                  <p className="v2-panel-label">人工动作</p>
                  <h3 className="v2-ticket-section-title">处理参数</h3>
                </div>
              </div>

              <div className="v2-ticket-action-fields">
                <Field label="审核人 ID">
                  <input
                    value={actorId}
                    onChange={(event) => setActorId(event.target.value)}
                    placeholder="reviewer-console"
                  />
                </Field>
                <Field label="操作备注" className="v2-ticket-field-wide">
                  <textarea
                    value={operatorComment}
                    onChange={(event) => setOperatorComment(event.target.value)}
                    placeholder="操作说明"
                    rows={3}
                  />
                </Field>
              </div>

              <section className="v2-ticket-stage-block v2-ticket-editor-stage">
                <div className="v2-ticket-section-head">
                  <div>
                    <p className="v2-panel-label">草稿编辑</p>
                    <h3 className="v2-ticket-section-title">人工编辑当前草稿</h3>
                  </div>
                  <div className="v2-action-row">
                    <StatusTag tone="muted">
                      {currentDraftId ? `基于 ${shortenId(currentDraftId)}` : "等待草稿"}
                    </StatusTag>
                    <button
                      type="button"
                      className="v2-button"
                      onClick={syncManualReplyFromLatestDraft}
                      disabled={!latestDraft || actionsBusy || !draftDirty}
                    >
                      恢复当前稿
                    </button>
                  </div>
                </div>

                {!currentDraftId ? (
                  <InlineNotice
                    tone="neutral"
                    title="当前还没有草稿"
                    detail="可以先创建草稿，再编辑并批准。"
                  />
                ) : null}

                {currentDraftId && draftDirty ? (
                  <InlineNotice
                    tone="neutral"
                    title="编辑区有未保存改动"
                    detail="保存草稿会生成新版本，并把这版内容作为新的当前草稿。"
                  />
                ) : null}

                <Field label="人工回复正文" className="v2-ticket-field-wide">
                  <textarea
                    value={manualReplyText}
                    onChange={(event) => setManualReplyText(event.target.value)}
                    placeholder="输入回复内容"
                    rows={12}
                  />
                </Field>

                <div className="v2-action-row v2-ticket-action-buttons">
                  <button
                    type="button"
                    className="v2-button is-primary"
                    onClick={() => void handleGenerateDraft()}
                    disabled={!ticketVersion || !actorId.trim() || actionsBusy}
                  >
                    {currentDraftId ? "重新生成草稿" : "创建草稿"}
                  </button>
                  <button
                    type="button"
                    className="v2-button"
                    onClick={() => void handleSaveDraft()}
                    disabled={
                      !ticketVersion ||
                      !currentDraftId ||
                      !actorId.trim() ||
                      !manualReplyText.trim() ||
                      !draftDirty ||
                      actionsBusy
                    }
                  >
                    保存草稿
                  </button>
                  <button
                    type="button"
                    className="v2-button"
                    onClick={() => void handleApprove()}
                    disabled={
                      !ticketVersion ||
                      !currentDraftId ||
                      !actorId.trim() ||
                      draftDirty ||
                      actionsBusy
                    }
                  >
                    批准当前草稿
                  </button>
                </div>
              </section>

              <div className="v2-ticket-drawer-stack">
                <details className="v2-ticket-inline-drawer">
                  <summary>更多操作</summary>
                  <Field label="重写原因">
                    <textarea
                      value={rewriteReasons}
                      onChange={(event) => setRewriteReasons(event.target.value)}
                      placeholder="每行一个原因"
                      rows={4}
                    />
                  </Field>
                  <Field label="外部队列">
                    <input
                      value={targetQueue}
                      onChange={(event) => setTargetQueue(event.target.value)}
                      placeholder="human_review"
                    />
                  </Field>
                  <div className="v2-action-row v2-ticket-action-buttons">
                    <button
                      type="button"
                      className="v2-button"
                      onClick={() => void handleEscalate()}
                      disabled={!ticketVersion || !actorId.trim() || !targetQueue.trim() || actionsBusy}
                    >
                      外部升级
                    </button>
                  </div>
                  <Field label="关闭原因">
                    <input
                      value={closeReason}
                      onChange={(event) => setCloseReason(event.target.value)}
                      placeholder="resolved_manually"
                    />
                  </Field>
                  <div className="v2-action-row v2-ticket-action-buttons">
                    <button
                      type="button"
                      className="v2-button"
                      onClick={() => void handleRewrite()}
                      disabled={!ticketVersion || !currentDraftId || !actorId.trim() || actionsBusy}
                    >
                      按原因重写
                    </button>
                    <button
                      type="button"
                      className="v2-button"
                      onClick={() => void handleSaveAndClose()}
                      disabled={
                        !ticketVersion ||
                        !currentDraftId ||
                        !actorId.trim() ||
                        !manualReplyText.trim() ||
                        !closeReason.trim() ||
                        actionsBusy
                      }
                    >
                      保存并批准后关闭
                    </button>
                    <button
                      type="button"
                      className="v2-button is-danger"
                      onClick={() => void handleClose()}
                      disabled={!ticketVersion || !actorId.trim() || !closeReason.trim() || actionsBusy}
                    >
                      直接关闭工单
                    </button>
                  </div>
                </details>
              </div>
            </section>
          </Panel>
        </div>
      </section>
    </section>
  );
}
