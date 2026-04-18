import { startTransition, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";

import { ApiClientError } from "@/lib/api/client";
import { labelForCode } from "@/lib/presentation";
import type { TestEmailResponse } from "@/lib/api/types";
import { useCreateTestEmail } from "@/lib/query/testLab";
import { useConsoleUiStore } from "@/state/console-ui-store";

type ScenarioPreset = {
  id: string;
  label: string;
  lane: string;
  scenarioLabel: string;
  senderEmailRaw: string;
  subject: string;
  bodyText: string;
  references?: string;
};

type ActionNotice = {
  tone: "success" | "error";
  title: string;
  detail: string;
};

const SCENARIO_PRESETS: ScenarioPreset[] = [
  {
    id: "billing-refund",
    label: "账单退款",
    lane: "账单",
    scenarioLabel: "billing_refund_follow_up",
    senderEmailRaw: '"Mina Park" <mina.park@example.com>',
    subject: "关于年度套餐重复扣费的退款跟进",
    bodyText:
      "你好，客服团队：\n\n我昨天升级后，年度套餐被扣了两次费用。请确认其中一笔是否会退款，以及大概何时能退回到我的卡上。\n\n谢谢，\nMina",
    references: "客户反馈 4 月 16 日升级后发生年度套餐重复扣费。",
  },
  {
    id: "technical-outage",
    label: "技术故障",
    lane: "技术",
    scenarioLabel: "technical_service_outage",
    senderEmailRaw: '"Elias Chen" <elias.chen@example.com>',
    subject: "凭据轮换后 API 返回 502",
    bodyText:
      "你好，团队：\n\n我们今天早上轮换凭据后，生产集成就开始返回 HTTP 502。Sandbox 依然正常。请帮忙确认是否存在事故，或者我们是否遗漏了某个迁移步骤？\n\n此致，\nElias",
    references: "仅影响生产环境。大约在 UTC 08:30 完成凭据轮换后开始出现。",
  },
  {
    id: "vip-escalation",
    label: "VIP 升级",
    lane: "升级",
    scenarioLabel: "vip_customer_escalation",
    senderEmailRaw: '"Dana Lo" <dana.lo@example.com>',
    subject: "高层升级：上线日队列被阻塞",
    bodyText:
      "客服团队：\n\n距离正式上线不到 24 小时，但我们的 onboarding 队列被卡住了，因为确认邮件完全没有发出。这需要紧急升级，并请工程师给出明确 ETA。\n\nDana",
    references: "高价值客户。要求提供工程 ETA 和升级路径。",
  },
];

function getErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiClientError) {
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return fallback;
}

export function TestLabPage() {
  const draft = useConsoleUiStore((state) => state.testEmailDraft);
  const updateTestEmailDraft = useConsoleUiStore((state) => state.updateTestEmailDraft);
  const resetTestEmailDraft = useConsoleUiStore((state) => state.resetTestEmailDraft);
  const mutation = useCreateTestEmail();

  const [references, setReferences] = useState("");
  const [notice, setNotice] = useState<ActionNotice | null>(null);
  const [submission, setSubmission] = useState<TestEmailResponse | null>(null);

  const activePreset = useMemo(
    () =>
      SCENARIO_PRESETS.find((preset) => preset.scenarioLabel === draft.scenarioLabel) ?? null,
    [draft.scenarioLabel],
  );

  const canSubmit =
    draft.senderEmailRaw.trim().length > 0 &&
    draft.subject.trim().length > 0 &&
    draft.bodyText.trim().length > 0;

  function applyPreset(preset: ScenarioPreset) {
    startTransition(() => {
      updateTestEmailDraft({
        senderEmailRaw: preset.senderEmailRaw,
        subject: preset.subject,
        bodyText: preset.bodyText,
        autoEnqueue: true,
        scenarioLabel: preset.scenarioLabel,
      });
      setReferences(preset.references ?? "");
      setNotice({
        tone: "success",
        title: "场景已装载",
        detail: `${preset.label} 已写入测试信封，随时可以注入。`,
      });
    });
  }

  function handleReset() {
    startTransition(() => {
      resetTestEmailDraft();
      setReferences("");
      setSubmission(null);
      setNotice(null);
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!canSubmit) {
      return;
    }

    try {
      const result = await mutation.mutateAsync({
        sender_email_raw: draft.senderEmailRaw.trim(),
        subject: draft.subject.trim(),
        body_text: draft.bodyText.trim(),
        references: references.trim() || undefined,
        auto_enqueue: draft.autoEnqueue,
        scenario_label: draft.scenarioLabel.trim() || undefined,
      });

      startTransition(() => {
        setSubmission(result);
        setNotice({
          tone: "success",
          title: "注入已接受",
          detail: result.run
            ? `${result.ticket.ticket_id} 已创建运行 ${result.run.run_id}，可直接进入工单或 Trace 交接。`
            : `${result.ticket.ticket_id} 已完成注入，但未自动入队，当前可进入工单检查。`,
        });
      });
    } catch (error) {
      setNotice({
        tone: "error",
        title: "注入失败",
        detail: getErrorMessage(error, "测试邮件注入失败。"),
      });
    }
  }

  return (
    <article className="test-lab-page">
      <section className="test-lab-hero">
        <div className="test-lab-hero-copy">
          <p className="placeholder-eyebrow">测试实验台</p>
          <h2>用受控邮件场景验证整条流程。</h2>
          <p>先加载预设，再微调信封内容，最后直接跳到结果页面。</p>
          <div className="test-lab-chip-row" aria-label="测试实验台区域">
            <span className="test-lab-chip">场景预设</span>
            <span className="test-lab-chip">可编辑信封</span>
            <span className="test-lab-chip">注入回执</span>
            <span className="test-lab-chip">工单 / Trace 交接</span>
          </div>
        </div>

        <div className="test-lab-hero-card">
          <p className="dashboard-card-label">实验状态</p>
          <h3>
            {activePreset
              ? `${activePreset.label} 已准备好，可直接注入。`
              : "请先加载一个预设，或自行编辑一份信封。"}
          </h3>
          <p className="test-lab-hero-copy-note">
            {activePreset
              ? `${activePreset.lane}泳道预设，默认启用自动入队。`
              : "这个实验台不依赖真实 Gmail 流量，只使用 dev 注入合约。"}
          </p>

          <dl className="test-lab-hero-meta">
            <div>
              <dt>场景标签</dt>
              <dd>{draft.scenarioLabel || "自定义实验"}</dd>
            </div>
            <div>
              <dt>发件人</dt>
              <dd>{draft.senderEmailRaw || "尚未设置发件人"}</dd>
            </div>
            <div>
              <dt>运行模式</dt>
              <dd>{draft.autoEnqueue ? "注入并入队" : "仅注入"}</dd>
            </div>
          </dl>
        </div>
      </section>

      {notice ? (
        <section
          className={`test-lab-alert test-lab-alert-${notice.tone}`}
          role={notice.tone === "error" ? "alert" : "status"}
        >
          <p className="dashboard-card-label">实验台通知</p>
          <h3>{notice.title}</h3>
          <p>{notice.detail}</p>
        </section>
      ) : null}

      <section className="test-lab-workbench">
        <section className="test-lab-panel">
          <div className="test-lab-panel-header">
            <div>
              <p className="dashboard-card-label">场景墙</p>
              <h3>先选一个常见场景作为起点。</h3>
            </div>
            <span className="test-lab-chip">
              {activePreset ? activePreset.lane : "自定义草稿"}
            </span>
          </div>

          <div className="test-lab-preset-grid" aria-label="场景预设网格">
            {SCENARIO_PRESETS.map((preset) => (
              <button
                key={preset.id}
                type="button"
                className={`test-lab-preset-card${
                  activePreset?.id === preset.id ? " test-lab-preset-card-active" : ""
                }`}
                onClick={() => applyPreset(preset)}
              >
                <span>{preset.lane}</span>
                <strong>{preset.label}</strong>
                <p>{preset.subject}</p>
              </button>
            ))}
          </div>
        </section>

        <section className="test-lab-panel test-lab-panel-accent">
          <div className="test-lab-panel-header">
            <div>
              <p className="dashboard-card-label">注入信封</p>
              <h3>按需要修改字段后再提交。</h3>
            </div>
            <span className="test-lab-chip">
              {mutation.isPending ? "正在提交" : "就绪"}
            </span>
          </div>

          <form className="test-lab-form" onSubmit={(event) => void handleSubmit(event)}>
            <div className="test-lab-form-grid">
              <label className="test-lab-field">
                <span>发件人信封</span>
                <input
                  value={draft.senderEmailRaw}
                  onChange={(event) =>
                    updateTestEmailDraft({ senderEmailRaw: event.target.value })
                  }
                  placeholder='"Test User" <test.user@example.com>'
                />
              </label>

              <label className="test-lab-field">
                <span>场景标签</span>
                <input
                  value={draft.scenarioLabel}
                  onChange={(event) =>
                    updateTestEmailDraft({ scenarioLabel: event.target.value })
                  }
                  placeholder="billing_refund_follow_up"
                />
              </label>

              <label className="test-lab-field test-lab-field-wide">
                <span>主题行</span>
                <input
                  value={draft.subject}
                  onChange={(event) => updateTestEmailDraft({ subject: event.target.value })}
                  placeholder="描述这次操作员场景"
                />
              </label>

              <label className="test-lab-field test-lab-field-wide">
                <span>邮件正文</span>
                <textarea
                  value={draft.bodyText}
                  onChange={(event) => updateTestEmailDraft({ bodyText: event.target.value })}
                  rows={8}
                  placeholder="粘贴或编辑这次实验使用的正文内容。"
                />
              </label>

              <label className="test-lab-field test-lab-field-wide">
                <span>补充说明</span>
                <textarea
                  value={references}
                  onChange={(event) => setReferences(event.target.value)}
                  rows={4}
                  placeholder="可选的证据或实验设置说明，会随注入请求一并提交。"
                />
              </label>
            </div>

            <label className="test-lab-toggle">
              <input
                type="checkbox"
                checked={draft.autoEnqueue}
                onChange={(event) =>
                  updateTestEmailDraft({ autoEnqueue: event.target.checked })
                }
              />
              <span>工单摄入后自动入队运行</span>
            </label>

            <div className="test-lab-button-row">
              <button
                type="submit"
                className="test-lab-button test-lab-button-primary"
                disabled={mutation.isPending || !canSubmit}
              >
                注入测试邮件
              </button>
              <button
                type="button"
                className="test-lab-button"
                onClick={handleReset}
                disabled={mutation.isPending}
              >
                重置草稿
              </button>
            </div>
          </form>
        </section>
      </section>

      <section className="test-lab-results-grid">
        <section className="test-lab-panel">
          <div className="test-lab-panel-header">
            <div>
              <p className="dashboard-card-label">注入回执</p>
              <h3>每次提交都会生成明确回执。</h3>
            </div>
            <span className="test-lab-chip">
              {submission ? submission.ticket.ticket_id : "尚无回执"}
            </span>
          </div>

          {submission ? (
            <>
              <section className="test-lab-receipt-grid" aria-label="注入回执摘要">
                <article className="test-lab-receipt-card">
                  <span>工单</span>
                  <strong>{submission.ticket.ticket_id}</strong>
                  <p>
                    {submission.ticket.created ? "已创建新工单。" : "复用了已有工单。"}
                  </p>
                </article>
                <article className="test-lab-receipt-card">
                  <span>状态</span>
                  <strong>
                    {labelForCode(submission.ticket.business_status)} /{" "}
                    {labelForCode(submission.ticket.processing_status)}
                  </strong>
                  <p>控制面返回的工单版本为 {submission.ticket.version}。</p>
                </article>
                <article className="test-lab-receipt-card">
                  <span>运行交接</span>
                  <strong>{submission.run?.run_id ?? "未入队运行"}</strong>
                  <p>
                    {submission.run
                      ? `Trace ${submission.run.trace_id} 已可进入 dossier 审查。`
                      : "当前请求已完成，但没有创建入队运行。"}
                  </p>
                </article>
              </section>

              <div className="test-lab-link-row" aria-label="注入结果链接">
                <Link className="test-lab-result-link" to={`/tickets/${submission.ticket.ticket_id}`}>
                  打开工单
                </Link>
                {submission.run ? (
                  <Link
                    className="test-lab-result-link test-lab-result-link-accent"
                    to={`/trace?ticketId=${encodeURIComponent(submission.ticket.ticket_id)}&runId=${encodeURIComponent(submission.run.run_id)}`}
                  >
                    打开 Trace
                  </Link>
                ) : null}
              </div>
            </>
          ) : (
            <section className="test-lab-empty-state" role="status">
              <p className="dashboard-card-label">等待回执</p>
              <h3>当前会话里还没有注入任何测试邮件。</h3>
              <p>
                请选择一个场景，调整信封，然后提交一次，以获取返回的工单 ID 和可选运行 ID。
              </p>
            </section>
          )}
        </section>

        <section className="test-lab-panel">
          <div className="test-lab-panel-header">
            <div>
              <p className="dashboard-card-label">接口边界</p>
              <h3>这里只依赖一次注入接口。</h3>
            </div>
            <span className="test-lab-chip">单一接口</span>
          </div>

          <ul className="test-lab-list">
            <li>这个页面只使用 `POST /dev/test-email` 一个后端合约。</li>
            <li>当关闭自动入队时，`run` 可能为空，因此 Trace 跳转是条件性的。</li>
            <li>场景预设能加速演示，但所有字段在提交前都可以修改。</li>
          </ul>

          <article className="test-lab-inline-card">
            <span>来源渠道</span>
            <strong>{submission?.test_metadata.source_channel ?? "dev_test_email"}</strong>
            <p>
              {submission
                ? `场景 ${submission.test_metadata.scenario_label ?? "custom"} · 自动入队 ${
                    submission.test_metadata.auto_enqueue ? "已启用" : "已禁用"
                  }.`
                : "在第一次提交之后，这里会回显来源渠道和场景标签。"}
            </p>
          </article>
        </section>
      </section>
    </article>
  );
}
