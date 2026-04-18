import { useEffect, useState } from "react";
import { useDeferredValue } from "react";
import { useParams } from "react-router-dom";

import { ApiClientError } from "@/lib/api/client";
import {
  formatScoreZh,
  formatTimestampZh,
  labelForCode,
} from "@/lib/presentation";
import type {
  EvaluationSummaryRef,
  TicketDraftDetail,
  TicketRunHistoryItem,
  TicketSnapshotResponse,
} from "@/lib/api/types";
import {
  useApproveTicket,
  useCloseTicket,
  useEditAndApproveTicket,
  useEscalateTicket,
  useRewriteTicket,
  useTicketDrafts,
  useTicketRuns,
  useTicketSnapshot,
} from "@/lib/query/tickets";
import { useConsoleUiStore } from "@/state/console-ui-store";

const RUN_HISTORY_PAGE_SIZE = 20;

type DetailBoard = {
  label: string;
  title: string;
  copy: string;
  points: string[];
};

type SummarySlot = {
  label: string;
  value: string;
  note: string;
  tone?: "default" | "accent";
};

type ActionNotice = {
  tone: "success" | "error";
  title: string;
  detail: string;
};

function shortenId(value: string) {
  if (value.length <= 18) {
    return value;
  }

  return `${value.slice(0, 12)}...${value.slice(-4)}`;
}

function formatTimestamp(dateString?: string | null) {
  return formatTimestampZh(dateString);
}

function formatScore(value?: number | null) {
  return formatScoreZh(value);
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

function buildSummarySlots(
  snapshot: TicketSnapshotResponse | undefined,
  runsCount: number,
  draftsCount: number,
): SummarySlot[] {
  if (!snapshot) {
    return [
      {
        label: "业务状态",
        value: "正在加载快照",
        note: "等待工单快照响应返回。",
      },
      {
        label: "处理状态",
        value: "正在加载快照",
        note: "处理状态与快照合约一起返回。",
      },
      {
        label: "主路由",
        value: "正在加载快照",
        note: "路由和多意图摘要由快照一并提供。",
      },
      {
        label: "租约占用",
        value: "正在加载快照",
        note: "租约归属与时间信息由快照解析。",
      },
      {
        label: "最新运行",
        value: "正在加载历史",
        note: "当前运行状态和 Trace 引用由快照补全。",
      },
      {
        label: "草稿阶梯",
        value: "正在加载草稿",
        note: "草稿数量和最新 QA 状态来自草稿历史。",
      },
    ];
  }

  const claimValue = snapshot.ticket.claimed_by
    ? `${snapshot.ticket.claimed_by}，租约至 ${formatTimestamp(snapshot.ticket.lease_until)}`
    : "未占用";
  const latestRunValue = snapshot.latest_run
    ? `${snapshot.latest_run.run_id} · ${labelForCode(snapshot.latest_run.status)}`
    : "暂无运行";
  const latestDraftValue = snapshot.latest_draft
    ? `${snapshot.latest_draft.draft_id} · ${labelForCode(snapshot.latest_draft.qa_status)}`
    : "暂无草稿";

  return [
    {
      label: "业务状态",
      value: labelForCode(snapshot.ticket.business_status),
      note: `当前案件状态对应工单版本 ${snapshot.ticket.version}。`,
      tone: "accent",
    },
    {
      label: "处理状态",
      value: labelForCode(snapshot.ticket.processing_status),
      note: "处理态始终显示在案件标题旁。",
    },
    {
      label: "主路由",
      value: snapshot.ticket.primary_route
        ? labelForCode(snapshot.ticket.primary_route)
        : "路由待定",
      note: snapshot.ticket.multi_intent
        ? "当前是跨越多个路由的多意图工单。"
        : "当前按单意图解释处理。",
    },
    {
      label: "租约占用",
      value: claimValue,
      note: snapshot.ticket.claimed_at
        ? `租约开始于 ${formatTimestamp(snapshot.ticket.claimed_at)}。`
        : "当前没有执行器持有租约。",
    },
    {
      label: "最新运行",
      value: latestRunValue,
      note: snapshot.latest_run
        ? `${describeEvalStatus(snapshot.latest_run.evaluation_summary_ref)} · 共 ${runsCount} 次运行。`
        : "该工单当前没有运行历史。",
    },
    {
      label: "草稿阶梯",
      value: latestDraftValue,
      note:
        draftsCount > 0
          ? `中央工作台已载入 ${draftsCount} 个草稿版本。`
          : "该工单当前还没有草稿历史。",
    },
  ];
}

function buildMessageBoards(ticketId: string, snapshot: TicketSnapshotResponse | undefined): DetailBoard[] {
  return [
    {
      label: "入站消息",
      title: "适配快照合约的线程叙述区",
      copy: snapshot
        ? `当前合约暴露了工单外层信息，但还没有消息线程本体。该面板以 ${ticketId} 为锚点，已经能反映实时主题、客户和路由状态。`
        : "左侧面板正在等待第一份快照响应，随后才会显示实时工单外层信息。",
      points: snapshot
        ? [
            `当前案件主路由：${snapshot.ticket.primary_route ? labelForCode(snapshot.ticket.primary_route) : "路由待定"}，业务状态为 ${labelForCode(snapshot.ticket.business_status)}。`,
            `租约状态：${snapshot.ticket.claimed_by ? `由 ${snapshot.ticket.claimed_by} 持有` : "未被占用"}，处理态为 ${labelForCode(snapshot.ticket.processing_status)}。`,
            "当前控制面合约还没有暴露消息线程正文。",
          ]
        : [
            "工单外层信息依赖 GET /tickets/{ticket_id}。",
            "在线程接口出现之前，消息时序区域仍保持预留。",
            "未来可以在不改页面结构的前提下接入源消息元数据。",
          ],
    },
    {
      label: "前置信息",
      title: "会话时序预留区",
      copy:
        "当前前端合约没有独立的消息日志接口，因此 FE-07 选择明确保留这个区域，而不是伪造会话数据。",
      points: [
        "未来接入消息日志时可直接落在这里，无需改布局。",
        "操作员评论和重写备注也可以复用同一条时序泳道。",
        "当前页面已经用真实数据展示工单、草稿和运行状态。",
      ],
    },
    {
      label: "证据来源",
      title: "当前已知合约边界",
      copy:
        "当前案件室只绑定 `snapshot`、`runs` 和 `drafts`。线程 ID、源消息 ID、引用链和附件仍需后续扩展合约。",
      points: [
        "避免假装消息数据源已经存在。",
        "为未来扩展保留证据栏位。",
        "保持操作员对完整案件室的认知模型。",
      ],
    },
  ];
}

function buildDraftBoardCopy(drafts: TicketDraftDetail[]) {
  if (drafts.length === 0) {
    return {
      title: "该工单当前还没有任何草稿版本。",
      detail:
        "工作台保持可见，这样第一份生成草稿落地时无需再改页面结构。",
    };
  }

  const latest = drafts.at(-1)!;
  return {
    title: `最新草稿 ${latest.draft_id} 是版本 ${latest.version_index}。`,
    detail: `${labelForCode(latest.qa_status)} · ${labelForCode(latest.draft_type)} · ${formatTimestamp(latest.created_at)}`,
  };
}

function getRunTone(run: TicketRunHistoryItem) {
  if (run.status === "failed" || run.status === "error") {
    return "ticket-detail-history-row-alert";
  }

  if (run.is_human_action) {
    return "ticket-detail-history-row-accent";
  }

  return "";
}

function parseRewriteReasons(value: string) {
  return value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
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

function getErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiClientError) {
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return fallback;
}

export function TicketDetailPage() {
  const params = useParams<{ ticketId: string }>();
  const selectedTicketId = useConsoleUiStore((state) => state.selectedTicketId);
  const setSelectedTicketId = useConsoleUiStore((state) => state.setSelectedTicketId);
  const ticketId = params.ticketId ?? selectedTicketId ?? "";
  const deferredTicketId = useDeferredValue(ticketId);
  const [actorId, setActorId] = useState("reviewer-console");
  const [operatorComment, setOperatorComment] = useState("");
  const [editedContentText, setEditedContentText] = useState("");
  const [rewriteReasons, setRewriteReasons] = useState("");
  const [targetQueue, setTargetQueue] = useState("human_review");
  const [closeReason, setCloseReason] = useState("resolved_manually");
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
  const editAndApproveMutation = useEditAndApproveTicket(deferredTicketId);
  const rewriteMutation = useRewriteTicket(deferredTicketId);
  const escalateMutation = useEscalateTicket(deferredTicketId);
  const closeMutation = useCloseTicket(deferredTicketId);

  const snapshot = snapshotQuery.data;
  const runs = runsQuery.data?.items ?? [];
  const drafts = draftsQuery.data?.items ?? [];
  const draftLead = buildDraftBoardCopy(drafts);
  const summarySlots = buildSummarySlots(snapshot, runsQuery.data?.total ?? 0, drafts.length);
  const messageBoards = buildMessageBoards(ticketId || "ticket_pending", snapshot);
  const latestRun = snapshot?.latest_run;
  const latestDraft = drafts.at(-1);
  const snapshotError =
    snapshotQuery.error instanceof Error ? snapshotQuery.error.message : "快照请求失败。";
  const runsError =
    runsQuery.error instanceof Error ? runsQuery.error.message : "运行历史请求失败。";
  const draftsError =
    draftsQuery.error instanceof Error ? draftsQuery.error.message : "草稿历史请求失败。";
  const selectedDraft = latestDraft ?? snapshot?.latest_draft ?? null;
  const ticketVersion = snapshot?.ticket.version;
  const actionsBusy =
    approveMutation.isPending ||
    editAndApproveMutation.isPending ||
    rewriteMutation.isPending ||
    escalateMutation.isPending ||
    closeMutation.isPending;

  async function handleApprove() {
    if (!ticketVersion || !selectedDraft || !actorId.trim()) {
      return;
    }

    try {
      const result = await approveMutation.mutateAsync({
        actorId: actorId.trim(),
        payload: {
          ticket_version: ticketVersion,
          draft_id: selectedDraft.draft_id,
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

  async function handleEditAndApprove() {
    if (!ticketVersion || !selectedDraft || !actorId.trim() || !editedContentText.trim()) {
      return;
    }

    try {
      const result = await editAndApproveMutation.mutateAsync({
        actorId: actorId.trim(),
        payload: {
          ticket_version: ticketVersion,
          draft_id: selectedDraft.draft_id,
          comment: operatorComment.trim() || null,
          edited_content_text: editedContentText.trim(),
        },
      });
      setEditedContentText("");
      setActionNotice(formatActionResult("已批准编辑后的草稿", result));
    } catch (error) {
      setActionNotice({
        tone: "error",
        title: "编辑并批准失败",
        detail: getErrorMessage(error, "编辑并批准请求失败。"),
      });
    }
  }

  async function handleRewrite() {
    if (!ticketVersion || !selectedDraft || !actorId.trim()) {
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
      const result = await rewriteMutation.mutateAsync({
        actorId: actorId.trim(),
        payload: {
          ticket_version: ticketVersion,
          draft_id: selectedDraft.draft_id,
          comment: operatorComment.trim() || null,
          rewrite_reasons: reasons,
        },
      });
      setActionNotice(formatActionResult("已发起重写请求", result));
    } catch (error) {
      setActionNotice({
        tone: "error",
        title: "重写请求失败",
        detail: getErrorMessage(error, "重写请求失败。"),
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
      setActionNotice(formatActionResult("已记录升级动作", result));
    } catch (error) {
      setActionNotice({
        tone: "error",
        title: "升级失败",
        detail: getErrorMessage(error, "升级请求失败。"),
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

  return (
    <article className="ticket-detail-page">
      <section className="ticket-detail-band">
        <div className="ticket-detail-band-copy">
          <p className="placeholder-eyebrow">工单详情</p>
          <h2>在一个空间里读状态、看草稿、做人工决策。</h2>
          <p>详情页围绕单个案件展开，重点是判断与执行，而不是解释系统实现。</p>
          <div className="ticket-detail-zone-chip-row" aria-label="工单详情区域">
            <span className="ticket-detail-zone-chip">实时快照</span>
            <span className="ticket-detail-zone-chip">草稿阶梯</span>
            <span className="ticket-detail-zone-chip">人工动作</span>
            <span className="ticket-detail-zone-chip">运行历史</span>
            <span className="ticket-detail-zone-chip">Trace 交接</span>
          </div>
        </div>

        <div className="ticket-detail-ident-card">
          <span>案件编号</span>
          <strong>{ticketId || "ticket_pending"}</strong>
          <p>
            {snapshot
              ? `${labelForCode(snapshot.ticket.business_status)}工单，当前版本 ${snapshot.ticket.version}。`
              : "正在等待实时快照数据，以识别当前案件状态。"}
          </p>
          <div className="ticket-detail-ident-meta">
            <div>
              <span>最新运行引用</span>
              <strong>{latestRun ? shortenId(latestRun.run_id) : "暂无运行"}</strong>
            </div>
            <div>
              <span>最新草稿引用</span>
              <strong>{latestDraft ? shortenId(latestDraft.draft_id) : "暂无草稿"}</strong>
            </div>
          </div>
        </div>
      </section>

      {snapshotQuery.isError || runsQuery.isError || draftsQuery.isError ? (
        <section className="ticket-detail-request-alert" role="alert">
          <p className="dashboard-card-label">详情请求异常</p>
          <h3>部分详情数据没有成功返回。</h3>
          <p>{snapshotQuery.isError ? snapshotError : runsQuery.isError ? runsError : draftsError}</p>
        </section>
      ) : null}

      <section className="ticket-detail-summary-grid" aria-label="工单详情摘要">
        {summarySlots.map((slot) => (
          <article
            key={slot.label}
            className={`ticket-detail-summary-card${slot.tone === "accent" ? " ticket-detail-summary-card-accent" : ""}`}
          >
            <span>{slot.label}</span>
            <strong>{slot.value}</strong>
            <p>{slot.note}</p>
          </article>
        ))}
      </section>

      <section className="ticket-detail-main-grid">
        <section className="ticket-detail-panel">
          <div className="ticket-detail-panel-header">
            <div>
              <p className="dashboard-card-label">消息</p>
              <h3>消息与证据区。</h3>
            </div>
            <span className="ticket-detail-panel-chip">尚未暴露线程接口</span>
          </div>

          <div className="ticket-detail-board-stack">
            {messageBoards.map((board) => (
              <article key={board.title} className="ticket-detail-board">
                <p className="ticket-detail-board-label">{board.label}</p>
                <h4>{board.title}</h4>
                <p>{board.copy}</p>
                <ul className="ticket-detail-list">
                  {board.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </section>

        <section className="ticket-detail-panel">
          <div className="ticket-detail-panel-header">
            <div>
              <p className="dashboard-card-label">草稿</p>
              <h3>当前草稿与人工动作。</h3>
            </div>
            <span className="ticket-detail-panel-chip">
              {draftsQuery.isLoading ? "正在加载草稿" : `已加载 ${drafts.length} 个版本`}
            </span>
          </div>

          <div className="ticket-detail-board-stack">
            <article className="ticket-detail-board ticket-detail-board-accent">
              <p className="ticket-detail-board-label">最新草稿</p>
              <h4>{draftLead.title}</h4>
              <p>{draftLead.detail}</p>
              {latestDraft ? (
                <div className="ticket-detail-draft-preview">
                  <p className="ticket-detail-draft-meta">
                    {latestDraft.run_id} · {labelForCode(latestDraft.qa_status)}
                    {latestDraft.gmail_draft_id ? ` · ${latestDraft.gmail_draft_id}` : ""}
                  </p>
                  <pre>{latestDraft.content_text}</pre>
                </div>
              ) : (
                <p className="ticket-detail-empty-copy">
                  当前还没有来自{" "}
                  {`GET /tickets/${ticketId || "{ticket_id}"}/drafts`}。
                </p>
              )}
            </article>

            <article className="ticket-detail-board ticket-detail-board-actions">
              <p className="ticket-detail-board-label">人工动作</p>
              <h4>在当前草稿上下文里完成审核。</h4>
              <p>批准、重写、升级和关闭都从这里发起。</p>

              <div className="ticket-detail-action-chip-row" aria-label="人工动作状态">
                <span className="ticket-detail-action-chip">
                  {selectedDraft ? `草稿 ${shortenId(selectedDraft.draft_id)}` : "未选择草稿"}
                </span>
                <span className="ticket-detail-action-chip">
                  {ticketVersion ? `工单 v${ticketVersion}` : "快照待返回"}
                </span>
                <span className="ticket-detail-action-chip">
                  {actionsBusy ? "正在提交动作" : "动作区已就绪"}
                </span>
              </div>

              {actionNotice ? (
                <div
                  className={`ticket-detail-action-notice ticket-detail-action-notice-${actionNotice.tone}`}
                  role={actionNotice.tone === "error" ? "alert" : "status"}
                >
                  <strong>{actionNotice.title}</strong>
                  <p>{actionNotice.detail}</p>
                </div>
              ) : null}

              <div className="ticket-detail-form-grid">
                <label className="ticket-detail-field">
                  <span>审核人 ID</span>
                  <input
                    value={actorId}
                    onChange={(event) => setActorId(event.target.value)}
                    placeholder="reviewer-console"
                  />
                </label>
                <label className="ticket-detail-field">
                  <span>升级队列</span>
                  <input
                    value={targetQueue}
                    onChange={(event) => setTargetQueue(event.target.value)}
                    placeholder="human_review"
                  />
                </label>
                <label className="ticket-detail-field ticket-detail-field-wide">
                  <span>操作备注</span>
                  <textarea
                    value={operatorComment}
                    onChange={(event) => setOperatorComment(event.target.value)}
                    placeholder="记录这次审核动作的原因。"
                    rows={3}
                  />
                </label>
                <label className="ticket-detail-field ticket-detail-field-wide">
                  <span>编辑后的草稿内容</span>
                  <textarea
                    value={editedContentText}
                    onChange={(event) => setEditedContentText(event.target.value)}
                    placeholder="当需要人工编辑后再批准时填写。"
                    rows={5}
                  />
                </label>
                <label className="ticket-detail-field ticket-detail-field-wide">
                  <span>重写原因</span>
                  <textarea
                    value={rewriteReasons}
                    onChange={(event) => setRewriteReasons(event.target.value)}
                    placeholder="每行一个原因，或用逗号分隔。"
                    rows={3}
                  />
                </label>
                <label className="ticket-detail-field">
                  <span>关闭原因</span>
                  <input
                    value={closeReason}
                    onChange={(event) => setCloseReason(event.target.value)}
                    placeholder="resolved_manually"
                  />
                </label>
              </div>

              <div className="ticket-detail-action-grid">
                <button
                  type="button"
                  className="ticket-detail-action-button ticket-detail-action-button-primary"
                  onClick={() => void handleApprove()}
                  disabled={!ticketVersion || !selectedDraft || !actorId.trim() || actionsBusy}
                >
                  批准
                </button>
                <button
                  type="button"
                  className="ticket-detail-action-button"
                  onClick={() => void handleEditAndApprove()}
                  disabled={
                    !ticketVersion ||
                    !selectedDraft ||
                    !actorId.trim() ||
                    !editedContentText.trim() ||
                    actionsBusy
                  }
                >
                  编辑并批准
                </button>
                <button
                  type="button"
                  className="ticket-detail-action-button"
                  onClick={() => void handleRewrite()}
                  disabled={!ticketVersion || !selectedDraft || !actorId.trim() || actionsBusy}
                >
                  请求重写
                </button>
                <button
                  type="button"
                  className="ticket-detail-action-button"
                  onClick={() => void handleEscalate()}
                  disabled={!ticketVersion || !actorId.trim() || !targetQueue.trim() || actionsBusy}
                >
                  升级
                </button>
                <button
                  type="button"
                  className="ticket-detail-action-button ticket-detail-action-button-danger"
                  onClick={() => void handleClose()}
                  disabled={!ticketVersion || !actorId.trim() || !closeReason.trim() || actionsBusy}
                >
                  关闭
                </button>
              </div>

              {!selectedDraft ? (
                <p className="ticket-detail-empty-copy">
                  在存在草稿产物之前，批准、编辑和重写按钮会保持禁用。
                </p>
              ) : null}
            </article>

            <article className="ticket-detail-board">
              <p className="ticket-detail-board-label">版本阶梯</p>
              <h4>查看草稿版本变化。</h4>
              <div className="ticket-detail-draft-list" aria-label="草稿版本阶梯">
                {drafts.length > 0 ? (
                  drafts.map((draft) => (
                    <article key={draft.draft_id} className="ticket-detail-draft-row">
                      <div>
                        <strong>{draft.draft_id}</strong>
                        <p>
                          版本 {draft.version_index} · {labelForCode(draft.qa_status)}
                        </p>
                      </div>
                      <div>
                        <strong>{labelForCode(draft.draft_type)}</strong>
                        <p>{formatTimestamp(draft.created_at)}</p>
                      </div>
                    </article>
                  ))
                ) : (
                  <p className="ticket-detail-empty-copy">
                    该工单当前没有草稿历史。
                  </p>
                )}
              </div>
            </article>
          </div>
        </section>

        <section className="ticket-detail-panel">
          <div className="ticket-detail-panel-header">
            <div>
              <p className="dashboard-card-label">运行态</p>
              <h3>最新运行与评估。</h3>
            </div>
            <span className="ticket-detail-panel-chip">
              {snapshotQuery.isLoading ? "正在加载快照" : "快照已绑定"}
            </span>
          </div>

          <div className="ticket-detail-board-stack">
            <article className="ticket-detail-board">
              <p className="ticket-detail-board-label">最新运行读数</p>
              <h4>{latestRun ? `${latestRun.run_id} 是当前主运行。` : "当前没有关联运行。"}</h4>
              <p>
                {latestRun
                  ? `${labelForCode(latestRun.status)} · ${latestRun.final_action ? labelForCode(latestRun.final_action) : "最终动作待定"}`
                  : "该工单在当前控制面历史中还没有产生任何记录运行。"}
              </p>
              <ul className="ticket-detail-list">
                {latestRun ? (
                  <>
                    <li>Trace 引用：{latestRun.trace_id}</li>
                    <li>{describeEvalStatus(latestRun.evaluation_summary_ref)}</li>
                    <li>
                      评估状态：{labelForCode(latestRun.evaluation_summary_ref.status)}
                    </li>
                  </>
                ) : (
                  <>
                    <li>当前还没有可交接的 Trace。</li>
                    <li>重试能力仍由 FE-08 人工动作区承接。</li>
                    <li>下方历史卷带已准备好接收第一次执行数据。</li>
                  </>
                )}
              </ul>
            </article>

            <article className="ticket-detail-board">
              <p className="ticket-detail-board-label">评估摘要</p>
              <h4>质量与轨迹结果。</h4>
              <p>
                {latestRun
                  ? describeEvalStatus(latestRun.evaluation_summary_ref)
                  : "至少要有一次运行完成后，评估摘要才会出现。"}
              </p>
              {latestRun ? (
                <div className="ticket-detail-eval-grid">
                  <div className="ticket-detail-eval-card">
                    <span>回复质量</span>
                    <strong>
                      {latestRun.evaluation_summary_ref.has_response_quality
                        ? formatScore(latestRun.evaluation_summary_ref.response_quality_overall_score)
                        : "--"}
                    </strong>
                  </div>
                  <div className="ticket-detail-eval-card">
                    <span>轨迹</span>
                    <strong>
                      {latestRun.evaluation_summary_ref.has_trajectory_evaluation
                        ? formatScore(latestRun.evaluation_summary_ref.trajectory_score)
                        : "--"}
                    </strong>
                  </div>
                  <div className="ticket-detail-eval-card">
                    <span>违规数</span>
                    <strong>{latestRun.evaluation_summary_ref.trajectory_violation_count ?? 0}</strong>
                  </div>
                </div>
              ) : null}
            </article>
          </div>
        </section>
      </section>

      <section className="ticket-detail-history-panel">
        <div className="ticket-detail-panel-header">
          <div>
            <p className="dashboard-card-label">运行历史</p>
            <h3>查看这个工单的全部尝试记录。</h3>
          </div>
          <span className="ticket-detail-panel-chip">
            {runsQuery.isLoading ? "正在加载运行" : `已加载 ${runsQuery.data?.total ?? 0} 次运行`}
          </span>
        </div>

        <div className="ticket-detail-history-head" aria-hidden="true">
          <span>尝试</span>
          <span>触发方式</span>
          <span>状态</span>
          <span>最终动作</span>
          <span>Trace / 评估</span>
        </div>

        <div className="ticket-detail-history-list" aria-label="运行历史卷带">
          {runs.length > 0 ? (
            runs.map((run) => (
              <article
                key={run.run_id}
                className={`ticket-detail-history-row ${getRunTone(run)}`.trim()}
              >
                <div className="ticket-detail-history-cell">
                  <span>尝试 {run.attempt_index}</span>
                  <strong>{run.run_id}</strong>
                </div>
                <div className="ticket-detail-history-cell">
                  <strong>{labelForCode(run.trigger_type)}</strong>
                  <p>{run.triggered_by ?? "系统"}</p>
                </div>
                <div className="ticket-detail-history-cell">
                  <p>{labelForCode(run.status)}</p>
                  <p>{run.started_at ? formatTimestamp(run.started_at) : "开始时间待定"}</p>
                </div>
                <div className="ticket-detail-history-cell">
                  <p>{run.final_action ? labelForCode(run.final_action) : "暂无最终动作"}</p>
                  <p>{run.ended_at ? formatTimestamp(run.ended_at) : "结束时间待定"}</p>
                </div>
                <div className="ticket-detail-history-cell">
                  <p>{run.trace_id}</p>
                  <p>{describeEvalStatus(run.evaluation_summary_ref)}</p>
                </div>
              </article>
            ))
          ) : (
            <section className="ticket-detail-empty-state" role="status">
              <p className="dashboard-card-label">暂无运行历史</p>
              <h3>这个工单还没有任何已记录尝试。</h3>
              <p>只要控制面记录下第一次运行，历史卷带就会自动填充。</p>
            </section>
          )}
        </div>
      </section>
    </article>
  );
}
