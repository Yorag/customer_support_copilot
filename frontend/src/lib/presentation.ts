const CODE_LABELS: Record<string, string> = {
  new: "新建",
  triaged: "已分诊",
  draft_created: "已生成草稿",
  drafted: "已起草",
  awaiting_customer_input: "待客户回复",
  awaiting_human_review: "待人工审核",
  approved: "已批准",
  rejected: "已拒绝",
  escalated: "已升级",
  failed: "失败",
  closed: "已关闭",
  idle: "空闲",
  queued: "已入队",
  leased: "已持有租约",
  running: "运行中",
  waiting_external: "等待外部处理",
  completed: "已完成",
  error: "错误",
  low: "低",
  medium: "中",
  high: "高",
  critical: "紧急",
  knowledge_request: "知识咨询",
  technical_issue: "技术问题",
  commercial_policy_request: "商业政策请求",
  feedback_intake: "反馈收集",
  unrelated: "无关请求",
  billing_refund: "账单退款",
  order_support: "订单支持",
  compliance_escalation: "合规升级",
  poller: "轮询器",
  manual_api: "手动接口",
  scheduled_retry: "定时重试",
  human_action: "人工动作",
  succeeded: "成功",
  cancelled: "已取消",
  timed_out: "超时",
  create_draft: "生成草稿",
  request_clarification: "请求澄清",
  handoff_to_human: "转人工处理",
  skip_unrelated: "跳过无关请求",
  close_ticket: "关闭工单",
  no_op: "无操作",
  reply: "回复草稿",
  clarification_request: "澄清请求",
  handoff_summary: "交接摘要",
  lightweight_template: "轻量模板",
  pending: "待处理",
  pending_review: "待审核",
  drafting: "起草中",
  passed: "已通过",
  ok: "正常",
  unknown: "未知",
  disabled: "已禁用",
  degraded: "降级",
  no_signal: "无信号",
  route_pending: "路由待定",
  no_run: "暂无运行",
  no_draft: "暂无草稿",
  inbound: "入站",
  outbound: "出站",
  outbound_draft: "外发草稿",
  customer_email: "客户邮件",
  reply_draft: "回复草稿",
  internal_note: "内部备注",
  load_ticket_context: "装载工单上下文",
  load_memory: "装载记忆",
  node: "节点",
  llm_call: "模型调用",
  tool_call: "工具调用",
  decision: "决策",
  checkpoint: "检查点",
  worker: "Worker",
  triage: "分诊",
  knowledge_lookup: "知识检索",
  policy_check: "策略检查",
  customer_history_lookup: "客户历史检索",
  collect_case_context: "汇总案件上下文",
  extract_memory_updates: "提取记忆更新",
  validate_memory_updates: "校验记忆更新",
  draft_reply: "起草回复",
  qa_handoff: "质量交接",
  qa_review: "质量复核",
  clarify_request: "发起澄清",
  create_gmail_draft: "创建 Gmail 草稿",
  escalate_to_human: "转人工处理",
  run_ticket: "运行入口",
  ticket_worker: "Worker 执行器",
  triage_decision: "分诊决策",
  response_quality_judge: "回复质量评估",
  started: "已开始",
  skipped: "已跳过",
  partial: "部分完成",
  complete: "完成",
  not_available: "不可用",
  existing_draft: "已有草稿",
  run_execution_failed: "运行执行失败",
  unknown_error: "未知错误",
  resolved_manually: "人工已解决",
  dev_test_email: "开发测试注入",
};

function humanizeCode(value: string) {
  return value
    .split("_")
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

export function labelForCode(value?: string | null, fallback = "--") {
  if (!value) {
    return fallback;
  }

  return CODE_LABELS[value] ?? humanizeCode(value);
}

export function formatTimestampZh(value?: string | null, options?: Intl.DateTimeFormatOptions) {
  if (!value) {
    return "暂无时间";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "时间不可用";
  }

  return new Intl.DateTimeFormat(
    "zh-CN",
    options ?? {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    },
  ).format(date);
}

export function formatRelativeTimeZh(value?: string | null) {
  if (!value) {
    return "暂无信号";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "时间不可用";
  }

  const deltaMs = Date.now() - date.getTime();
  const deltaMinutes = Math.max(0, Math.round(deltaMs / 60_000));
  if (deltaMinutes < 1) {
    return "刚刚";
  }
  if (deltaMinutes < 60) {
    return `${deltaMinutes} 分钟前`;
  }

  const deltaHours = Math.round(deltaMinutes / 60);
  if (deltaHours < 24) {
    return `${deltaHours} 小时前`;
  }

  const deltaDays = Math.round(deltaHours / 24);
  return `${deltaDays} 天前`;
}

export function formatNumberZh(value?: number | null, digits = 0, fallback = "--") {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return fallback;
  }

  return new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value);
}

export function formatScoreZh(value?: number | null, fallback = "--") {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return fallback;
  }

  return value.toFixed(1);
}

export function formatPercentZh(value?: number | null, fallback = "--") {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return fallback;
  }

  return `${Math.round(value * 100)}%`;
}

export function pluralizeZh(value: number, singular: string, plural = singular) {
  return `${value} ${value === 1 ? singular : plural}`;
}
