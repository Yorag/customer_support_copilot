# Customer Support Copilot API Contract 规格

## 1. 目的

本文档定义 V1 业务 API，不再以 LangServe 默认 runnable API 代替业务接口。

V1 统一使用 JSON over HTTP。

---

## 2. 通用规则

### 2.1 请求头

V1 统一预留：

1. `X-Actor-Id`
2. `X-Request-Id`
3. `Idempotency-Key`

### 2.2 版本控制

所有修改 Ticket 的接口都必须提交：

1. `ticket_version`

版本不匹配统一返回 `409 conflict`。

### 2.3 错误响应格式

```json
{
  "error": {
    "code": "ticket_version_conflict",
    "message": "Ticket version does not match current version.",
    "details": {
      "ticket_id": "t_01JQ...",
      "expected_version": 7,
      "actual_version": 8
    }
  }
}
```

### 2.4 标准错误码

1. `validation_error`
2. `not_found`
3. `ticket_version_conflict`
4. `invalid_state_transition`
5. `lease_conflict`
6. `duplicate_request`
7. `external_dependency_failed`

---

## 3. `POST /tickets/ingest-email`

### 3.1 用途

把外部邮件事件转换为系统内部 Ticket。

### 3.2 请求体

```json
{
  "source_channel": "gmail",
  "source_thread_id": "1978123456789012345",
  "source_message_id": "<abc123@gmail.com>",
  "sender_email_raw": "\"Li Wei\" <liwei@example.com>",
  "subject": "Need refund for duplicate charge",
  "body_text": "I was charged twice this month. Please refund the duplicate charge.",
  "message_timestamp": "2026-03-31T20:55:00+08:00",
  "references": "<prev1@gmail.com>",
  "attachments": []
}
```

### 3.3 行为规则

1. 命中激活 Ticket 时返回现有 Ticket
2. 原 Ticket 已关闭且满足 reopen 规则时创建新 Ticket
3. 入站邮件必须在命中或创建 Ticket 后持久化为 `TicketMessage`
4. 成功入库后 `business_status = new`
5. 成功入库后 `processing_status = queued`

### 3.4 成功响应

`201 created`

```json
{
  "ticket_id": "t_01JQJQJ4D7QMWJ8C5DVBAB4M2T",
  "created": true,
  "business_status": "new",
  "processing_status": "queued",
  "version": 1
}
```

### 3.5 幂等键

`ingest:{source_channel}:{source_thread_id}:{source_message_id}`

---

## 4. `POST /tickets/{ticket_id}/run`

### 4.1 用途

手动触发某个 Ticket 执行。

### 4.2 请求体

```json
{
  "ticket_version": 3,
  "trigger_type": "manual_api",
  "force_retry": false
}
```

### 4.3 规则

1. 接口只负责排队或创建 run，不保证同步跑完
2. Ticket 已被其他 worker 持有且租约未过期时返回 `409 lease_conflict`
3. `business_status in ('approved', 'closed')` 时返回 `409 invalid_state_transition`

### 4.4 成功响应

`202 accepted`

```json
{
  "ticket_id": "t_01JQJQJ4D7QMWJ8C5DVBAB4M2T",
  "run_id": "run_01JQJQK8D5M4Y2TTWZTR8S5M8S",
  "trace_id": "trace_01JQJQK8HK18TYG9PY1S36PK0A",
  "processing_status": "queued"
}
```

---

## 5. `POST /tickets/{ticket_id}/approve`

### 5.1 用途

人工审核通过当前草稿。

### 5.2 请求体

```json
{
  "ticket_version": 7,
  "draft_id": "draft_01JQJQJRXWQ9N2G76G3TX85SV7",
  "comment": "Policy wording looks safe."
}
```

### 5.3 前置状态

1. `business_status = awaiting_human_review`

### 5.4 成功响应

`200 ok`

```json
{
  "ticket_id": "t_01JQJQJ4D7QMWJ8C5DVBAB4M2T",
  "review_id": "review_01JQJQM1A9P3QAB18VN2Y7Z8QF",
  "business_status": "approved",
  "processing_status": "completed",
  "version": 8
}
```

---

## 6. `POST /tickets/{ticket_id}/edit-and-approve`

### 6.1 用途

人工修改草稿后直接通过。

### 6.2 请求体

```json
{
  "ticket_version": 7,
  "draft_id": "draft_01JQJQJRXWQ9N2G76G3TX85SV7",
  "comment": "Softened the refund wording.",
  "edited_content_text": "Hello, we have received your request and will review the duplicate charge according to our billing policy."
}
```

### 6.3 前置状态

1. `business_status = awaiting_human_review`

### 6.4 成功响应

`200 ok`

```json
{
  "ticket_id": "t_01JQJQJ4D7QMWJ8C5DVBAB4M2T",
  "review_id": "review_01JQJQM7B7P0P1TQ70XBRY5DFM",
  "business_status": "approved",
  "processing_status": "completed",
  "version": 8
}
```

---

## 7. `POST /tickets/{ticket_id}/rewrite`

### 7.1 用途

人工驳回并要求系统重写。

### 7.2 请求体

```json
{
  "ticket_version": 7,
  "draft_id": "draft_01JQJQJRXWQ9N2G76G3TX85SV7",
  "comment": "Do not imply refund approval before manual confirmation.",
  "rewrite_reasons": [
    "over_committed_refund_outcome",
    "policy_wording_too_strong"
  ]
}
```

### 7.3 前置状态

1. `business_status = awaiting_human_review`

### 7.4 成功响应

`200 ok`

```json
{
  "ticket_id": "t_01JQJQJ4D7QMWJ8C5DVBAB4M2T",
  "review_id": "review_01JQJQPH0AQN5EXM4G7MNW4F3J",
  "business_status": "rejected",
  "processing_status": "queued",
  "version": 8
}
```

---

## 8. `POST /tickets/{ticket_id}/escalate`

### 8.1 用途

将工单升级给更高等级支持队列。

### 8.2 请求体

```json
{
  "ticket_version": 7,
  "comment": "Security implication needs specialist review.",
  "target_queue": "security_support"
}
```

### 8.3 前置状态

允许前置状态：

1. `triaged`
2. `draft_created`
3. `awaiting_human_review`

### 8.4 成功响应

`200 ok`

```json
{
  "ticket_id": "t_01JQJQJ4D7QMWJ8C5DVBAB4M2T",
  "review_id": "review_01JQJQR1G3EN0ZC1Q0BQ2M5R8M",
  "business_status": "escalated",
  "processing_status": "waiting_external",
  "version": 8
}
```

---

## 9. `POST /tickets/{ticket_id}/close`

### 9.1 用途

显式关闭工单。

### 9.2 请求体

```json
{
  "ticket_version": 8,
  "reason": "draft_sent_manually"
}
```

### 9.3 前置状态

允许前置状态：

1. `approved`
2. `awaiting_customer_input`
3. `escalated`
4. `failed`

### 9.4 成功响应

`200 ok`

```json
{
  "ticket_id": "t_01JQJQJ4D7QMWJ8C5DVBAB4M2T",
  "business_status": "closed",
  "processing_status": "completed",
  "version": 9
}
```

---

## 10. `GET /tickets/{ticket_id}`

成功响应：

```json
{
  "ticket": {
    "ticket_id": "t_01JQJQJ4D7QMWJ8C5DVBAB4M2T",
    "business_status": "awaiting_human_review",
    "processing_status": "waiting_external",
    "priority": "high",
    "primary_route": "commercial_policy_request",
    "multi_intent": false,
    "tags": ["billing_question", "refund_request", "needs_escalation"],
    "version": 7
  },
  "latest_run": {
    "run_id": "run_01JQJQK8D5M4Y2TTWZTR8S5M8S",
    "trace_id": "trace_01JQJQK8HK18TYG9PY1S36PK0A",
    "status": "succeeded",
    "final_action": "handoff_to_human"
  },
  "latest_draft": {
    "draft_id": "draft_01JQJQJRXWQ9N2G76G3TX85SV7",
    "qa_status": "escalated"
  }
}
```

---

## 11. `GET /tickets/{ticket_id}/trace`

查询参数：

1. `run_id` 可选，不传默认最近一次 run

成功响应：

```json
{
  "ticket_id": "t_01JQJQJ4D7QMWJ8C5DVBAB4M2T",
  "run_id": "run_01JQJQK8D5M4Y2TTWZTR8S5M8S",
  "trace_id": "trace_01JQJQK8HK18TYG9PY1S36PK0A",
  "latency_metrics": {
    "end_to_end_ms": 8231,
    "slowest_node": "policy_check"
  },
  "resource_metrics": {
    "total_tokens": 4820,
    "llm_call_count": 4,
    "tool_call_count": 3
  },
  "response_quality": {
    "overall_score": 4.2
  },
  "trajectory_evaluation": {
    "score": 4.7
  },
  "events": []
}
```

---

## 12. `GET /customers/{customer_id}/memory`

成功响应：

```json
{
  "customer_id": "cust_email_liwei_example.com",
  "profile": {
    "preferred_language": "en",
    "preferred_tone": "direct",
    "account_tier": "pro"
  },
  "risk_tags": ["refund_dispute_history"],
  "business_flags": {
    "high_value_customer": false,
    "requires_manual_approval": true
  },
  "historical_case_refs": [
    {
      "ticket_id": "t_01JP...",
      "summary": "Duplicate charge dispute resolved manually."
    }
  ],
  "version": 3
}
```

---

## 13. `GET /metrics/summary`

查询参数：

1. `from`
2. `to`
3. `route` 可选

成功响应：

```json
{
  "window": {
    "from": "2026-03-01T00:00:00+08:00",
    "to": "2026-03-31T23:59:59+08:00"
  },
  "latency": {
    "p50_ms": 6120,
    "p95_ms": 11840
  },
  "resources": {
    "avg_total_tokens": 3560,
    "avg_llm_call_count": 3.8
  },
  "response_quality": {
    "avg_overall_score": 4.1
  },
  "trajectory_evaluation": {
    "avg_score": 4.3
  }
}
```

---

## 14. 对应关系

1. `ingest-email` 负责创建或 reopen Ticket
2. `run` 负责触发执行
3. `approve`、`edit-and-approve`、`rewrite`、`escalate`、`close` 只允许在规定前置状态下调用
4. `GET /tickets/{id}` 返回工单快照
5. `GET /tickets/{id}/trace` 返回执行细节和评测结果

---

## 15. 与当前实现的差距

当前 [deploy_api.py](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/deploy_api.py#L28) 仍然只暴露 LangServe runnable。

V1 必须补充：

1. 业务路由层
2. DTO 校验层
3. Ticket store
4. 版本和幂等处理
