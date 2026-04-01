# Customer Support Copilot Trace And Eval 规格

## 1. 目的

本文档把观测与评估收敛为 V1 可执行协议。

V1 固定技术选择：

1. 运行追踪：`LangSmith`
2. 质量评估：`LLM-as-a-judge`
3. 轨迹评估：规则脚本为主
4. 生成模型与嵌入模型：OpenAI-compatible 协议，支持自定义 `base_url` 和自定义 `model`

不再保留 `LangSmith` 与 `Langfuse` 二选一表述。

---

## 2. Trace 规则

### 2.1 每次 run 必须产生唯一 `trace_id`

并串联以下对象：

1. `TicketRun`
2. `TraceEvent`
3. `DraftArtifact`
4. 评估结果

### 2.2 事件类型

1. `node`
2. `llm_call`
3. `tool_call`
4. `decision`

### 2.3 最小字段

1. `trace_id`
2. `run_id`
3. `ticket_id`
4. `event_type`
5. `event_name`
6. `start_time`
7. `end_time`
8. `latency_ms`
9. `status`
10. `metadata`

---

## 3. 必采集节点

V1 至少采集：

1. `ingest_email`
2. `create_or_load_ticket`
3. `load_memory`
4. `triage`
5. `knowledge_lookup`
6. `policy_check`
7. `customer_history_lookup`
8. `draft_reply`
9. `qa_review`
10. `create_gmail_draft`
11. `clarify_request`
12. `escalate_to_human`
13. `close_ticket`

---

## 4. 决策事件

### 4.1 必采集决策

1. `triage_result`
2. `clarification_decision`
3. `escalation_decision`
4. `final_action`

### 4.2 `decision.metadata`

```json
{
  "primary_route": "technical_issue",
  "secondary_routes": [],
  "response_strategy": "troubleshooting",
  "needs_clarification": true,
  "needs_escalation": false,
  "final_action": "request_clarification"
}
```

---

## 5. 延迟指标

必算：

1. `end_to_end_ms`
2. `node_latencies`
3. `llm_call_latencies`
4. `tool_call_latencies`

计算：

1. `end_to_end_ms = run.end - run.start`
2. `node_latencies` 按 node 名聚合平均值和最大值
3. `slowest_node` 取最大平均延迟节点
4. `slowest_call` 取单次最慢事件

输出：

```json
{
  "end_to_end_ms": 8231,
  "slowest_node": "policy_check",
  "slowest_call": {
    "event_name": "llm.policy_check",
    "latency_ms": 2140
  },
  "node_latencies": {
    "triage": 1180,
    "policy_check": 2620,
    "draft_reply": 1710
  }
}
```

---

## 6. 资源指标

必算：

1. `prompt_tokens_total`
2. `completion_tokens_total`
3. `total_tokens`
4. `llm_call_count`
5. `tool_call_count`

规则：

1. 只统计当前 `run_id`
2. 重试 run 单独统计，不与上一次 run 合并

输出：

```json
{
  "prompt_tokens_total": 3120,
  "completion_tokens_total": 1700,
  "total_tokens": 4820,
  "llm_call_count": 4,
  "tool_call_count": 3
}
```

---

## 7. 响应质量评估

### 7.1 输入

1. 原始邮件主题和正文
2. 最终草稿正文
3. 证据摘要
4. 策略约束摘要
5. 主路由结果

### 7.2 维度

每个维度使用 `1` 到 `5` 分整数：

1. `relevance`
2. `correctness`
3. `intent_alignment`
4. `clarity`

### 7.3 总分

`overall_score = round((relevance + correctness + intent_alignment + clarity) / 4, 2)`

### 7.4 阈值

1. `>= 4.5`：优秀
2. `4.0 - 4.49`：可接受
3. `3.0 - 3.99`：偏弱
4. `< 3.0`：失败

### 7.5 输出

```json
{
  "overall_score": 4.25,
  "subscores": {
    "relevance": 5,
    "correctness": 4,
    "intent_alignment": 4,
    "clarity": 4
  },
  "reason": "The draft addresses the billing concern directly and avoids making an unauthorized refund promise."
}
```

`response_quality` 在落库、接口返回和离线报表中统一使用以下键：

1. `overall_score`
2. `subscores`
3. `reason`

### 7.6 Judge 输出要求

Judge 必须输出严格 JSON：

```json
{
  "relevance": 5,
  "correctness": 4,
  "intent_alignment": 4,
  "clarity": 4,
  "reason": "..."
}
```

不得输出自由文本混排。

---

## 8. 轨迹评估

轨迹评估对象是实际执行路径，而不是模型思维链。

### 8.1 路径模板

`knowledge_request`:

`triage -> knowledge_lookup -> draft_reply -> qa_review -> create_gmail_draft`

`technical_issue` 且需澄清:

`triage -> clarify_request -> create_gmail_draft -> awaiting_customer_input`

`commercial_policy_request` 且高风险:

`triage -> policy_check -> customer_history_lookup -> escalate_to_human`

`feedback_intake`:

`triage -> draft_reply -> qa_review -> create_gmail_draft`

`unrelated`:

`triage -> close_ticket`

### 8.2 违规类型

1. `missing_required_node`
2. `wrong_order`
3. `missed_escalation`
4. `missed_clarification`
5. `unexpected_auto_draft`

### 8.3 评分

初始分 `5.0`，每个违规扣分：

1. `missing_required_node`：`-1.5`
2. `wrong_order`：`-1.0`
3. `missed_escalation`：`-2.0`
4. `missed_clarification`：`-2.0`
5. `unexpected_auto_draft`：`-1.5`

最低分 `0`。

### 8.4 输出

```json
{
  "score": 4.0,
  "expected_route": [
    "triage",
    "policy_check",
    "customer_history_lookup",
    "escalate_to_human"
  ],
  "actual_route": [
    "triage",
    "policy_check",
    "draft_reply",
    "create_gmail_draft"
  ],
  "violations": [
    {
      "type": "missed_escalation",
      "message": "The run created a draft instead of escalating a high-risk policy request."
    }
  ]
}
```

---

## 9. 离线评测样本集

V1 统一使用 `jsonl`。

样本字段：

1. `sample_id`
2. `scenario_type`
3. `email_subject`
4. `email_body`
5. `expected_primary_route`
6. `expected_escalation`
7. `expected_route_template`
8. `reference_answer_or_constraints`

单条样本示例：

```json
{
  "sample_id": "eval_tech_001",
  "scenario_type": "technical_issue_clarification",
  "email_subject": "SSO login keeps failing",
  "email_body": "I configured SSO according to the guide but users still cannot log in.",
  "expected_primary_route": "technical_issue",
  "expected_escalation": false,
  "expected_route_template": "technical_issue_clarify",
  "reference_answer_or_constraints": [
    "Must request steps to reproduce",
    "Must ask for error message",
    "Must not claim root cause without evidence"
  ]
}
```

---

## 10. 首版最小覆盖

必须至少包含以下 8 类样本，每类至少 `3` 条：

1. 产品咨询
2. 技术故障
3. 投诉
4. 需澄清邮件
5. 多意图邮件
6. 退款或其他高风险邮件
7. 知识库缺失邮件
8. “功能建议”和“一般反馈”边界邮件

总量不低于 `24` 条。

---

## 11. 评估运行输出

每条样本至少产出：

1. `trace_id`
2. `primary_route`
3. `needs_escalation`
4. `final_action`
5. `response_quality`
6. `trajectory_evaluation`
7. `latency_metrics`
8. `resource_metrics`

其中：

1. `response_quality.overall_score` 为唯一总分字段
2. 不再使用 `response_quality.score`

汇总报表至少输出：

1. 路由准确率
2. 升级判定准确率
3. 平均响应质量分
4. 平均轨迹评估分
5. 失败样本列表

---

## 12. 与当前实现的关系

当前 [nodes.py](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/src/nodes.py#L12) 只有控制台打印，没有正式 `trace_id` 和评测对象。

V1 必须新增：

1. 统一 trace 包装层
2. token 统计
3. 规则式轨迹比对脚本
4. Judge 输出 schema 校验
