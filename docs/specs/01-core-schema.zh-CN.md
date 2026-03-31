# Customer Support Copilot Core Schema 规格

## 1. 目的

本文档把方向性设计收敛为 V1 可实现的数据契约。

V1 存储唯一选型固定为 `Postgres`。

---

## 2. 全局规则

### 2.1 ID

1. `ticket_id = t_{ulid}`
2. `run_id = run_{ulid}`
3. `trace_id = trace_{ulid}`
4. `draft_id = draft_{ulid}`
5. `review_id = review_{ulid}`
6. `memory_event_id = me_{ulid}`

### 2.2 时间

1. 所有时间字段统一使用 `timestamptz`
2. API 统一输出 ISO 8601 带时区

### 2.3 版本

1. `Ticket` 和 `CustomerMemoryProfile` 必须带 `version`
2. 所有更新都必须做乐观锁校验
3. 版本冲突统一返回 `409 conflict`

---

## 3. Ticket

一个激活中的 Gmail 线程只能对应一个激活中的 Ticket。

### 3.1 唯一约束

1. 主键：`ticket_id`
2. 唯一键：`source_channel + source_thread_id + is_active`
3. 唯一键：`gmail_thread_id + is_active`

### 3.2 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `ticket_id` | string | 是 | 系统工单 ID |
| `source_channel` | enum | 是 | V1 固定 `gmail` |
| `source_thread_id` | string | 是 | 外部线程 ID |
| `source_message_id` | string | 是 | 触发消息 ID |
| `gmail_thread_id` | string | 是 | Gmail 线程 ID |
| `gmail_draft_id` | string | 否 | 最近有效 Gmail 草稿 ID |
| `customer_id` | string | 否 | 可为空，无法可靠归并时不写长期记忆 |
| `customer_email` | string | 是 | 规范化邮箱 |
| `customer_email_raw` | string | 是 | 原始邮箱 |
| `subject` | string | 是 | 最新主题 |
| `latest_message_excerpt` | string | 否 | 最新摘要 |
| `business_status` | enum | 是 | 业务状态 |
| `processing_status` | enum | 是 | 调度状态 |
| `priority` | enum | 是 | 优先级 |
| `primary_route` | enum | 否 | 主路由 |
| `secondary_routes` | jsonb | 否 | 次路由数组 |
| `tags` | jsonb | 否 | 标签数组 |
| `response_strategy` | enum | 否 | 回复策略 |
| `multi_intent` | boolean | 是 | 是否为多意图邮件 |
| `needs_clarification` | boolean | 是 | 是否待客户补充 |
| `needs_escalation` | boolean | 是 | 是否应升级 |
| `intent_confidence` | numeric(4,3) | 否 | 0 到 1 |
| `routing_reason` | text | 否 | 可读理由 |
| `risk_reasons` | jsonb | 否 | 风险原因数组 |
| `current_run_id` | string | 否 | 当前 run |
| `lease_owner` | string | 否 | 当前 worker |
| `lease_expires_at` | timestamptz | 否 | 租约过期时间 |
| `last_error_code` | string | 否 | 最近错误码 |
| `last_error_message` | text | 否 | 最近错误摘要 |
| `reopen_count` | integer | 是 | reopen 次数 |
| `is_active` | boolean | 是 | 是否激活 |
| `version` | integer | 是 | 乐观锁版本 |
| `created_at` | timestamptz | 是 | 创建时间 |
| `updated_at` | timestamptz | 是 | 更新时间 |
| `closed_at` | timestamptz | 否 | 关闭时间 |

### 3.3 `business_status`

1. `new`
2. `triaged`
3. `draft_created`
4. `awaiting_customer_input`
5. `awaiting_human_review`
6. `approved`
7. `rejected`
8. `escalated`
9. `failed`
10. `closed`

### 3.4 `processing_status`

1. `idle`
2. `queued`
3. `leased`
4. `running`
5. `waiting_external`
6. `completed`
7. `error`

### 3.5 其他枚举

`priority`:

1. `low`
2. `medium`
3. `high`
4. `critical`

`primary_route` / `secondary_routes`:

1. `knowledge_request`
2. `technical_issue`
3. `commercial_policy_request`
4. `feedback_intake`
5. `unrelated`

`tags`:

1. `feature_request`
2. `complaint`
3. `general_feedback`
4. `billing_question`
5. `refund_request`
6. `multi_intent`
7. `needs_clarification`
8. `needs_escalation`

`response_strategy`:

1. `answer`
2. `troubleshooting`
3. `policy_constrained`
4. `acknowledgement`

### 3.6 `multi_intent` 同步规则

1. `multi_intent` 是持久化布尔真值来源。
2. `multi_intent = true` 时，`tags` 中必须包含 `multi_intent`。
3. `multi_intent = false` 时，`tags` 中不得包含 `multi_intent`。
4. `secondary_routes` 非空时，`multi_intent` 必须为 `true`。

### 3.7 示例

```json
{
  "ticket_id": "t_01JQJQJ4D7QMWJ8C5DVBAB4M2T",
  "source_channel": "gmail",
  "source_thread_id": "1978123456789012345",
  "source_message_id": "<abc123@gmail.com>",
  "gmail_thread_id": "1978123456789012345",
  "gmail_draft_id": "r-654321",
  "customer_id": "cust_email_liwei_example.com",
  "customer_email": "liwei@example.com",
  "customer_email_raw": "\"Li Wei\" <liwei@example.com>",
  "subject": "Need refund for duplicate charge",
  "latest_message_excerpt": "I was charged twice this month.",
  "business_status": "awaiting_human_review",
  "processing_status": "waiting_external",
  "priority": "high",
  "primary_route": "commercial_policy_request",
  "secondary_routes": [],
  "tags": ["billing_question", "refund_request", "needs_escalation"],
  "response_strategy": "policy_constrained",
  "multi_intent": false,
  "needs_clarification": false,
  "needs_escalation": true,
  "intent_confidence": 0.93,
  "routing_reason": "Refund-related billing request with policy constraints.",
  "risk_reasons": ["refund_amount_involved"],
  "current_run_id": null,
  "lease_owner": null,
  "lease_expires_at": null,
  "last_error_code": null,
  "last_error_message": null,
  "reopen_count": 0,
  "is_active": true,
  "version": 7,
  "created_at": "2026-03-31T21:00:00+08:00",
  "updated_at": "2026-03-31T21:18:00+08:00",
  "closed_at": null
}
```

---

## 4. TicketRun

每次执行尝试对应一个 `TicketRun`。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `run_id` | string | 是 | 运行 ID |
| `ticket_id` | string | 是 | 关联 Ticket |
| `trace_id` | string | 是 | 关联 Trace |
| `trigger_type` | enum | 是 | 触发来源 |
| `triggered_by` | string | 否 | 用户或 worker |
| `status` | enum | 是 | run 状态 |
| `started_at` | timestamptz | 是 | 开始时间 |
| `ended_at` | timestamptz | 否 | 结束时间 |
| `final_action` | enum | 否 | 最终动作 |
| `final_node` | string | 否 | 最终节点 |
| `attempt_index` | integer | 是 | 第几次 run |
| `error_code` | string | 否 | 错误码 |
| `error_message` | text | 否 | 错误摘要 |
| `latency_metrics` | jsonb | 否 | 延迟聚合 |
| `resource_metrics` | jsonb | 否 | 资源聚合 |
| `response_quality` | jsonb | 否 | 回复质量 |
| `trajectory_evaluation` | jsonb | 否 | 轨迹评估 |
| `created_at` | timestamptz | 是 | 创建时间 |
| `updated_at` | timestamptz | 是 | 更新时间 |

`trigger_type`:

1. `poller`
2. `manual_api`
3. `scheduled_retry`
4. `human_action`
5. `offline_eval`

`status`:

1. `running`
2. `succeeded`
3. `failed`
4. `cancelled`
5. `timed_out`

`final_action`:

1. `create_draft`
2. `request_clarification`
3. `handoff_to_human`
4. `skip_unrelated`
5. `close_ticket`
6. `no_op`

`response_quality` 固定结构：

1. `overall_score`
2. `subscores`
3. `reason`

`trajectory_evaluation` 固定结构：

1. `score`
2. `expected_route`
3. `actual_route`
4. `violations`

---

## 5. DraftArtifact

记录每一轮草稿。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `draft_id` | string | 是 | 草稿记录 ID |
| `ticket_id` | string | 是 | 关联 Ticket |
| `run_id` | string | 是 | 关联 Run |
| `version_index` | integer | 是 | 草稿版本号，从 1 开始 |
| `draft_type` | enum | 是 | 草稿类型 |
| `content_text` | text | 是 | 纯文本正文 |
| `content_html` | text | 否 | HTML 正文 |
| `source_evidence_summary` | text | 否 | 证据摘要 |
| `qa_status` | enum | 是 | QA 状态 |
| `qa_feedback` | jsonb | 否 | 结构化 QA 反馈 |
| `gmail_draft_id` | string | 否 | 外部 Gmail 草稿 ID |
| `idempotency_key` | string | 否 | 外部副作用幂等键 |
| `created_at` | timestamptz | 是 | 创建时间 |

`draft_type`:

1. `reply`
2. `clarification_request`
3. `handoff_summary`
4. `lightweight_template`

`qa_status`:

1. `pending`
2. `passed`
3. `failed`
4. `escalated`

---

## 6. HumanReview

人工动作必须保留为独立记录。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `review_id` | string | 是 | 审核记录 ID |
| `ticket_id` | string | 是 | 关联 Ticket |
| `draft_id` | string | 否 | 被审草稿 |
| `reviewer_id` | string | 是 | 审核人 |
| `action` | enum | 是 | 审核动作 |
| `comment` | text | 否 | 审核意见 |
| `edited_content_text` | text | 否 | 修改后正文 |
| `edited_content_html` | text | 否 | 修改后 HTML |
| `requested_rewrite_reason` | jsonb | 否 | 退回原因 |
| `target_queue` | string | 否 | 升级目标队列 |
| `ticket_version_at_review` | integer | 是 | 审核时版本 |
| `created_at` | timestamptz | 是 | 创建时间 |

`action`:

1. `approve`
2. `edit_and_approve`
3. `reject_for_rewrite`
4. `escalate`

---

## 7. TraceEvent

每个 `run_id` 对应多条 `TraceEvent`。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `event_id` | string | 是 | 事件 ID |
| `trace_id` | string | 是 | 关联 Trace |
| `run_id` | string | 是 | 关联 Run |
| `ticket_id` | string | 是 | 关联 Ticket |
| `event_type` | enum | 是 | 事件类型 |
| `event_name` | string | 是 | 事件名称 |
| `node_name` | string | 否 | 节点名 |
| `start_time` | timestamptz | 是 | 开始时间 |
| `end_time` | timestamptz | 否 | 结束时间 |
| `latency_ms` | integer | 否 | 延迟 |
| `status` | enum | 是 | 状态 |
| `metadata` | jsonb | 否 | 扩展字段 |
| `created_at` | timestamptz | 是 | 创建时间 |

`event_type`:

1. `node`
2. `llm_call`
3. `tool_call`
4. `decision`

`status`:

1. `started`
2. `succeeded`
3. `failed`
4. `skipped`

`metadata` 最小要求：

1. `llm_call` 必须包含 `model`、`prompt_tokens`、`completion_tokens`、`total_tokens`
2. `tool_call` 必须包含 `tool_name`、`input_ref`、`output_ref`
3. `decision` 必须包含 `primary_route`、`response_strategy`、`needs_clarification`、`needs_escalation`、`final_action`

---

## 8. CustomerMemoryProfile

客户当前活跃画像。

### 8.1 `customer_id` 规则

V1 固定：

1. 邮箱转小写并去除首尾空格
2. 命中 alias 映射表时归并到主邮箱
3. `customer_id = cust_email_{normalized_email_with_special_chars_replaced}`
4. 无法可靠解析邮箱时 `customer_id = null`

### 8.2 空 `customer_id` 约束

1. `customer_id = null` 时，禁止创建 `CustomerMemoryProfile`。
2. `customer_id = null` 时，禁止写入 `CustomerMemoryEvent`。
3. 此时系统只允许使用当前 Ticket 的短期上下文，不允许沉淀长期记忆。

### 8.3 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `customer_id` | string | 是 | 客户 ID |
| `primary_email` | string | 是 | 主邮箱 |
| `alias_emails` | jsonb | 是 | 别名邮箱数组 |
| `profile` | jsonb | 是 | 画像字段 |
| `risk_tags` | jsonb | 是 | 风险标签数组 |
| `business_flags` | jsonb | 是 | 业务标记 |
| `historical_case_refs` | jsonb | 是 | 历史 case 引用 |
| `version` | integer | 是 | 乐观锁版本 |
| `created_at` | timestamptz | 是 | 创建时间 |
| `updated_at` | timestamptz | 是 | 更新时间 |

`profile` 固定键：

1. `name`
2. `account_tier`
3. `preferred_language`
4. `preferred_tone`

`business_flags` 固定键：

1. `high_value_customer`
2. `refund_dispute_history`
3. `requires_manual_approval`

---

## 9. CustomerMemoryEvent

追加式记忆事件流。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `memory_event_id` | string | 是 | 事件 ID |
| `customer_id` | string | 是 | 客户 ID |
| `ticket_id` | string | 是 | 来源工单 |
| `run_id` | string | 是 | 来源运行 |
| `source_stage` | enum | 是 | 来源阶段 |
| `event_type` | enum | 是 | 事件类型 |
| `payload` | jsonb | 是 | 更新内容 |
| `idempotency_key` | string | 是 | 幂等键 |
| `created_at` | timestamptz | 是 | 创建时间 |

`source_stage`:

1. `load_memory`
2. `customer_history_lookup`
3. `awaiting_customer_input`
4. `escalate_to_human`
5. `close_ticket`

`event_type`:

1. `profile_update`
2. `risk_tag_add`
3. `risk_tag_remove`
4. `historical_case_append`
5. `business_flag_update`

---

## 10. V1 范围

V1 必须落库：

1. `Ticket`
2. `TicketRun`
3. `DraftArtifact`
4. `HumanReview`
5. `TraceEvent`
6. `CustomerMemoryProfile`
7. `CustomerMemoryEvent`
8. `TicketMessage`，定义见 `docs/specs/06-message-log-schema.zh-CN.md`

V1 可以继续放在 `jsonb`：

1. `tags`
2. `secondary_routes`
3. `risk_reasons`
4. `qa_feedback`
5. `response_quality`
6. `trajectory_evaluation`

---

## 11. 与当前代码的关系

当前 [state.py](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/src/state.py#L15) 只定义了运行态 `GraphState`，不能代替本文档中的持久化实体。

落地时必须遵循：

1. `GraphState` 只保留图执行临时字段
2. 业务状态以 `Ticket` 为准
3. 重试、幂等、人工动作、评测都以落库对象为准
