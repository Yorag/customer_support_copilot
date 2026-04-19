import { startTransition, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";

import { ApiClientError } from "@/lib/api/client";
import { labelForCode } from "@/lib/presentation";
import type { TestEmailResponse } from "@/lib/api/types";
import { useCreateTestEmail } from "@/lib/query/testLab";
import { useConsoleUiStore } from "@/state/console-ui-store";
import {
  Field,
  InlineNotice,
  Panel,
  StatusTag,
} from "@/ui-v2/primitives";

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
    subject: "昨天升级后被扣了两笔年费，想确认退款时间",
    bodyText:
      "我昨天把工作区升级到年度套餐，银行卡这边连续入账了两笔相同金额。\n\n后台现在只看到一个有效订阅，所以看起来像是重复扣费。想确认一下另一笔是不是会原路退回，大概需要多久能到账。\n\n如果你们需要，我可以把账单截图和卡片尾号后四位补过来。",
    references: "客户反馈 4 月 16 日升级到年度套餐后出现重复扣费，当前系统仅显示一个有效订阅。",
  },
  {
    id: "technical-outage",
    label: "技术故障",
    lane: "技术",
    scenarioLabel: "technical_service_outage",
    senderEmailRaw: '"Elias Chen" <elias.chen@example.com>',
    subject: "生产环境从今天早上开始一直返回 502",
    bodyText:
      "我们今天早上轮换了一次 API 凭据，之后生产环境的请求就陆续开始返回 502，现在基本已经全部失败了。\n\n奇怪的是 sandbox 还是正常的，同一套代码打到测试环境也没复现。日志里暂时看不到更明确的错误，只能看到网关层直接返回 502。\n\n想先确认一下你们这边是不是有事故，或者这次凭据轮换之后还有什么额外步骤需要处理。",
    references: "仅影响生产环境，问题大约从 UTC 08:30 之后开始出现。sandbox 与测试环境正常。",
  },
  {
    id: "vip-escalation",
    label: "VIP 升级",
    lane: "升级",
    scenarioLabel: "vip_customer_escalation",
    senderEmailRaw: '"Dana Lo" <dana.lo@example.com>',
    subject: "明天上线，但注册确认邮件现在完全发不出去",
    bodyText:
      "我们明天就要正式上线了，但刚刚发现注册后的确认邮件完全没有发出去，新的用户现在都卡在 onboarding 这一步。\n\n这不是单个账号的问题，我们连续试了几个邮箱都一样，所以需要你们尽快升级处理。团队这边最关心两件事：现在有没有临时绕过方案，以及工程侧能不能给一个明确的 ETA。\n\n如果需要拉群或者电话同步，可以马上配合。",
    references: "高价值客户，明天上线；当前核心诉求是紧急升级、临时绕过方案和工程 ETA。",
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

export function TestLabPageV2() {
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
            ? `${result.ticket.ticket_id} 已创建运行 ${result.run.run_id}，可直接进入工单或 Trace。`
            : `${result.ticket.ticket_id} 已完成注入，但未自动入队。`,
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
    <section className="v2-stack">
      {notice ? (
        <InlineNotice
          tone={notice.tone === "success" ? "success" : "error"}
          title={notice.title}
          detail={notice.detail}
        />
      ) : null}

      <section className="v2-test-lab-layout">
        <Panel
          title="先确认输入，再提交"
          description="主要填写邮件信封、场景标签和运行策略。"
        >
          <form className="v2-stack" onSubmit={(event) => void handleSubmit(event)}>
            <Field label="发件人信封">
              <input
                value={draft.senderEmailRaw}
                onChange={(event) =>
                  updateTestEmailDraft({ senderEmailRaw: event.target.value })
                }
                placeholder='"Test User" <test.user@example.com>'
              />
            </Field>

            <Field
              label="场景标签"
              hint="用于回执和后续检索；可沿用预设值，也可写自定义标签。"
            >
              <input
                value={draft.scenarioLabel}
                onChange={(event) =>
                  updateTestEmailDraft({ scenarioLabel: event.target.value })
                }
                placeholder="billing_refund_follow_up"
              />
            </Field>

            <Field label="主题行">
              <input
                value={draft.subject}
                onChange={(event) => updateTestEmailDraft({ subject: event.target.value })}
                placeholder="描述这次操作员场景"
              />
            </Field>

            <Field label="邮件正文">
              <textarea
                value={draft.bodyText}
                onChange={(event) => updateTestEmailDraft({ bodyText: event.target.value })}
                rows={8}
                placeholder="粘贴或编辑这次实验使用的正文内容。"
              />
            </Field>

            <Field
              label="补充说明"
              hint="仅在需要记录实验上下文、证据来源或特殊设定时填写。"
            >
              <textarea
                value={references}
                onChange={(event) => setReferences(event.target.value)}
                rows={4}
                placeholder="可选的证据或实验设置说明。"
              />
            </Field>

            <Field
              label="运行策略"
              hint="自动入队会直接创建运行并可跳转 Trace；保留则只创建工单。"
            >
              <select
                aria-label="运行策略"
                value={draft.autoEnqueue ? "enqueue" : "hold"}
                onChange={(event) =>
                  updateTestEmailDraft({ autoEnqueue: event.target.value === "enqueue" })
                }
              >
                <option value="enqueue">工单摄入后自动入队运行</option>
                <option value="hold">只注入，不入队</option>
              </select>
            </Field>

            <div className="v2-action-row v2-test-lab-form-actions">
              <button
                type="submit"
                className="v2-button is-primary"
                disabled={mutation.isPending || !canSubmit}
              >
                注入测试邮件
              </button>
              <button
                type="button"
                className="v2-button"
                onClick={handleReset}
                disabled={mutation.isPending}
              >
                重置草稿
              </button>
            </div>
          </form>
        </Panel>

        <div className="v2-test-lab-side">
          <Panel
            title={activePreset ? `${activePreset.label} 已装载` : "选择常见场景"}
            description={activePreset ? `${activePreset.lane} 预设已进入编辑区。` : "这里提供常见工单风格的快速起点。"}
          >
            <section className="v2-summary-grid v2-test-lab-presets" aria-label="场景预设网格">
              {SCENARIO_PRESETS.map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  className="v2-button v2-test-lab-preset"
                  onClick={() => applyPreset(preset)}
                >
                  <span className="v2-test-lab-preset-copy">
                    <strong>{preset.label}</strong>
                    <span>{preset.subject}</span>
                  </span>
                </button>
              ))}
            </section>
          </Panel>

          {submission ? (
            <Panel
              title="注入回执"
              description="工单与 Trace 交接结果。"
              actions={
                <StatusTag tone="accent">
                  {submission.run ? "已创建运行" : "仅创建工单"}
                </StatusTag>
              }
            >
              <div className="v2-stack">
                <div className="v2-summary-grid" aria-label="注入回执摘要">
                  <article className="v2-test-lab-receipt-card">
                    <p className="v2-panel-label">工单</p>
                    <strong className="v2-test-lab-receipt-title v2-code">
                      {submission.ticket.ticket_id}
                    </strong>
                    <p>
                      {submission.ticket.created ? "已创建新工单。" : "复用了已有工单。"}
                    </p>
                  </article>

                  <article className="v2-test-lab-receipt-card">
                    <p className="v2-panel-label">当前状态</p>
                    <strong className="v2-test-lab-receipt-title">
                      {labelForCode(submission.ticket.business_status)} /{" "}
                      {labelForCode(submission.ticket.processing_status)}
                    </strong>
                    <p>工单版本 {submission.ticket.version}。</p>
                  </article>

                  <article className="v2-test-lab-receipt-card">
                    <p className="v2-panel-label">运行与 Trace</p>
                    {submission.run ? (
                      <div className="v2-test-lab-receipt-meta">
                        <div className="v2-test-lab-receipt-meta-item">
                          <span>运行</span>
                          <strong className="v2-code">{submission.run.run_id}</strong>
                        </div>
                        <div className="v2-test-lab-receipt-meta-item">
                          <span>Trace</span>
                          <strong className="v2-code">{submission.run.trace_id}</strong>
                        </div>
                      </div>
                    ) : (
                      <strong className="v2-test-lab-receipt-title">未入队</strong>
                    )}
                    <p>
                      {submission.run
                        ? "运行已创建，Trace 已可进入审查。"
                        : "本次注入未创建运行。"}
                    </p>
                  </article>
                </div>

                <div className="v2-test-lab-receipt-actions" aria-label="注入结果链接">
                  <Link className="v2-button" to={`/tickets/${submission.ticket.ticket_id}`}>
                    打开工单
                  </Link>
                  {submission.run ? (
                    <Link
                      className="v2-button is-primary"
                      to={`/trace?ticketId=${encodeURIComponent(submission.ticket.ticket_id)}&runId=${encodeURIComponent(submission.run.run_id)}`}
                    >
                      打开 Trace
                    </Link>
                  ) : null}
                </div>
              </div>
            </Panel>
          ) : null}
        </div>
      </section>
    </section>
  );
}
