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
              title={submission.ticket.ticket_id}
              description="工单与 Trace 交接结果。"
              actions={
                <StatusTag tone="accent">
                  {submission.run ? "已创建运行" : "仅创建工单"}
                </StatusTag>
              }
            >
              <div className="v2-stack">
                <div className="v2-summary-grid" aria-label="注入回执摘要">
                  <Panel title={submission.ticket.ticket_id}>
                    <p>{submission.ticket.created ? "已创建新工单。" : "复用了已有工单。"}</p>
                  </Panel>
                  <Panel
                    title={`状态: ${labelForCode(submission.ticket.business_status)} / ${labelForCode(submission.ticket.processing_status)}`}
                  >
                    <p>工单版本 {submission.ticket.version}。</p>
                  </Panel>
                  <Panel title={submission.run ? `运行: ${submission.run.run_id}` : "运行: 未入队"}>
                    <p>
                      {submission.run
                        ? `Trace ${submission.run.trace_id} 已可进入审查。`
                        : "本次注入未创建运行。"}
                    </p>
                  </Panel>
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
