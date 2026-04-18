# Customer Support Copilot Control Plane API 规格

## 1. 目的

本文档定义“前端控制台”所需的新增控制面 API 规格。

目标不是替换现有业务 API，而是在现有 V1 业务接口基础上补齐：

1. Gmail 运维控制
2. Ticket 列表查询
3. Run 历史查询
4. Draft 历史查询
5. 本地测试注入
6. 系统运行状态查询

这些接口主要服务于控制台前端，不承担 LangGraph 同步执行职责。

---

## 2. 与现有规格的关系

本文档是以下文档的增量补充：

1. `docs/specs/03-api-contract.zh-CN.md`
2. `docs/specs/05-trace-and-eval.zh-CN.md`
3. `docs/specs/09-ticket-snapshot-eval-summary.zh-CN.md`

若有局部冲突：

1. 对已有接口，以已有规格为准
2. 对新增控制面接口，以本文档为准

---

## 3. 设计原则

1. 控制面 API 只负责控制和查询，不负责同步跑完 workflow
2. 现有 `POST /tickets/{ticket_id}/run` 仍然是正式入队入口
3. Ticket 详情仍以 `GET /tickets/{ticket_id}` 和 `GET /tickets/{ticket_id}/trace` 为核心
4. 新增接口返回结构应尽量贴合现有 schema 风格
5. 前端展示用摘要对象可以适度冗余，但必须有明确权威来源

---

## 4. 通用规则

### 4.1 请求头

控制面 API 延续现有预留请求头：

1. `X-Actor-Id`
2. `X-Request-Id`
3. `Idempotency-Key`

### 4.2 错误响应

错误结构复用 V1 统一格式：

```json
{
  "error": {
    "code": "validation_error",
    "message": "Invalid query parameter.",
    "details": {
      "query": "page"
    }
  }
}
```

### 4.3 分页规则

所有列表接口统一建议支持：

1. `page`
2. `page_size`

返回：

1. `items`
2. `page`
3. `page_size`
4. `total`

默认：

1. `page = 1`
2. `page_size = 20`

限制：

1. `page >= 1`
2. `1 <= page_size <= 100`

---

## 5. `GET /tickets`

## 5.1 用途

提供控制台 Ticket 列表页数据。

## 5.2 查询参数

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `page` | int | 否 | 页码 |
| `page_size` | int | 否 | 每页条数 |
| `business_status` | string | 否 | 业务状态过滤 |
| `processing_status` | string | 否 | 处理状态过滤 |
| `primary_route` | string | 否 | 主路由过滤 |
| `has_draft` | bool | 否 | 是否存在 draft |
| `awaiting_review` | bool | 否 | 是否处于待人工审核 |
| `query` | string | 否 | 关键字搜索 |

## 5.3 响应结构

```json
{
  "items": [
    {
      "ticket_id": "t_01...",
      "customer_id": "cust_01...",
      "customer_email_raw": "\"Li Wei\" <liwei@example.com>",
      "subject": "Need refund for duplicate charge",
      "business_status": "awaiting_human_review",
      "processing_status": "waiting_external",
      "priority": "high",
      "primary_route": "billing_support",
      "multi_intent": false,
      "version": 8,
      "updated_at": "2026-04-17T10:33:00Z",
      "latest_run": {
        "run_id": "run_01...",
        "trace_id": "trace_01...",
        "status": "succeeded",
        "final_action": "handoff_to_human",
        "evaluation_summary_ref": {
          "status": "complete",
          "trace_id": "trace_01...",
          "has_response_quality": true,
          "response_quality_overall_score": 4.25,
          "has_trajectory_evaluation": true,
          "trajectory_score": 4.5,
          "trajectory_violation_count": 1
        }
      },
      "latest_draft": {
        "draft_id": "draft_01...",
        "qa_status": "pending"
      }
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 248
}
```

## 5.4 规则

1. `latest_run` 选择规则与 `GET /tickets/{ticket_id}` 保持一致
2. `latest_draft` 选择规则与 snapshot 保持一致
3. `awaiting_review = true` 等价于 `business_status = awaiting_human_review`
4. `query` 应至少匹配：
   1. `ticket_id`
   2. `subject`
   3. `customer_email_raw`

---

## 6. `GET /tickets/{ticket_id}/runs`

## 6.1 用途

返回某个 ticket 的全部 run 历史，供详情页与 trace 列表页使用。

## 6.2 查询参数

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `page` | int | 否 | 页码 |
| `page_size` | int | 否 | 每页条数 |

## 6.3 响应结构

```json
{
  "ticket_id": "t_01...",
  "items": [
    {
      "run_id": "run_01...",
      "trace_id": "trace_01...",
      "trigger_type": "manual_api",
      "triggered_by": "system:poller",
      "status": "succeeded",
      "final_action": "create_draft",
      "started_at": "2026-04-17T10:30:00Z",
      "ended_at": "2026-04-17T10:30:08Z",
      "attempt_index": 1,
      "is_human_action": false,
      "evaluation_summary_ref": {
        "status": "complete",
        "trace_id": "trace_01...",
        "has_response_quality": true,
        "response_quality_overall_score": 4.6,
        "has_trajectory_evaluation": true,
        "trajectory_score": 5.0,
        "trajectory_violation_count": 0
      }
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 3
}
```

## 6.4 规则

1. 默认按 `created_at` 倒序返回
2. `is_human_action = true` 等价于 `trigger_type = human_action`
3. `evaluation_summary_ref` 的结构复用 snapshot 规格

---

## 7. `GET /tickets/{ticket_id}/drafts`

## 7.1 用途

返回某个 ticket 的所有草稿版本，供详情页展示。

## 7.2 响应结构

```json
{
  "ticket_id": "t_01...",
  "items": [
    {
      "draft_id": "draft_01...",
      "run_id": "run_01...",
      "version_index": 1,
      "draft_type": "reply",
      "qa_status": "pending",
      "content_text": "Hello, we have received your request...",
      "source_evidence_summary": "Billing policy allows review of duplicate charges.",
      "gmail_draft_id": "r-1234567890",
      "created_at": "2026-04-17T10:30:07Z"
    },
    {
      "draft_id": "draft_02...",
      "run_id": "run_02...",
      "version_index": 2,
      "draft_type": "reply",
      "qa_status": "approved",
      "content_text": "Hello, we reviewed your duplicate charge request...",
      "source_evidence_summary": "Updated wording after human review.",
      "gmail_draft_id": "r-1234567899",
      "created_at": "2026-04-17T10:42:11Z"
    }
  ]
}
```

## 7.3 规则

1. 默认按 `version_index` 升序返回
2. `content_text` 是详情页主展示内容
3. `gmail_draft_id` 可为空
4. 本接口的权威来源是本地 `draft_artifacts`
5. 不要求每次查询都回源 Gmail

---

## 8. `POST /ops/gmail/scan`

## 8.1 用途

手动触发一次 Gmail 扫描、摄入与入队。

## 8.2 请求体

```json
{
  "max_results": 20,
  "enqueue": true
}
```

## 8.3 请求字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `max_results` | int | 否 | 覆盖默认抓取上限 |
| `enqueue` | bool | 否 | 是否自动为 ingest 后 ticket 创建 run，默认 `true` |

## 8.4 成功响应

`202 accepted`

```json
{
  "scan_id": "scan_20260417104201",
  "status": "accepted",
  "gmail_enabled": true,
  "requested_max_results": 20,
  "enqueue": true,
  "summary": {
    "fetched_threads": 8,
    "ingested_tickets": 3,
    "queued_runs": 3,
    "skipped_existing_draft_threads": 4,
    "skipped_self_sent_threads": 1,
    "errors": 0
  },
  "items": [
    {
      "source_thread_id": "1978123456789012345",
      "ticket_id": "t_01...",
      "created_ticket": true,
      "queued_run_id": "run_01..."
    }
  ]
}
```

## 8.5 规则

1. 若 `GMAIL_ENABLED = false`，返回 `409 invalid_state_transition` 或 `422 validation_error`
2. 该接口可以同步完成一次批处理，但语义上仍是“操作型接口”，不是工作流执行接口
3. 成功响应中的 `queued_run_id` 可为空，当 `enqueue = false` 时必须为空

---

## 9. `POST /ops/gmail/scan-preview`

## 9.1 用途

预览本次 Gmail 扫描会命中的候选邮件，但不落库、不入队。

## 9.2 请求体

```json
{
  "max_results": 20
}
```

## 9.3 成功响应

```json
{
  "gmail_enabled": true,
  "requested_max_results": 20,
  "summary": {
    "candidate_threads": 8,
    "skipped_existing_draft_threads": 4,
    "skipped_self_sent_threads": 1
  },
  "items": [
    {
      "source_thread_id": "1978123456789012345",
      "source_message_id": "<abc123@gmail.com>",
      "sender_email_raw": "\"Li Wei\" <liwei@example.com>",
      "subject": "Need refund for duplicate charge",
      "skip_reason": null
    }
  ]
}
```

## 9.4 规则

1. 不产生 ticket
2. 不创建 run
3. 适用于前端“预览扫描结果”按钮

---

## 10. `GET /ops/status`

## 10.1 用途

返回控制台首页和系统状态页需要的运行时摘要。

## 10.2 成功响应

```json
{
  "gmail": {
    "enabled": true,
    "account_email": "support@example.com",
    "last_scan_at": "2026-04-17T10:42:01Z",
    "last_scan_status": "succeeded"
  },
  "worker": {
    "healthy": true,
    "worker_count": 1,
    "last_heartbeat_at": "2026-04-17T10:42:05Z"
  },
  "queue": {
    "queued_runs": 12,
    "running_runs": 3,
    "waiting_external_tickets": 7,
    "error_tickets": 2
  },
  "dependencies": {
    "database": "ok",
    "gmail": "ok",
    "llm": "unknown",
    "checkpointing": "ok"
  },
  "recent_failure": {
    "ticket_id": "t_01...",
    "run_id": "run_09...",
    "trace_id": "trace_09...",
    "error_code": "run_execution_failed",
    "occurred_at": "2026-04-17T10:35:10Z"
  }
}
```

## 10.3 规则

1. `worker` 心跳若尚未实现，字段可先返回 `null`
2. `dependencies` 是展示用摘要，不要求做深度探活
3. `recent_failure` 可为 `null`

---

## 11. `POST /dev/test-email`

## 11.1 用途

注入一封测试邮件，不依赖真实 Gmail，用于本地演示和前端测试。

## 11.2 请求体

```json
{
  "sender_email_raw": "\"Test User\" <test.user@example.com>",
  "subject": "I was charged twice this month",
  "body_text": "Please help me review a possible duplicate charge.",
  "references": null,
  "auto_enqueue": true,
  "scenario_label": "billing_refund"
}
```

## 11.3 成功响应

```json
{
  "ticket": {
    "ticket_id": "t_01...",
    "created": true,
    "business_status": "new",
    "processing_status": "queued",
    "version": 1
  },
  "run": {
    "run_id": "run_01...",
    "trace_id": "trace_01...",
    "processing_status": "queued"
  },
  "test_metadata": {
    "scenario_label": "billing_refund",
    "auto_enqueue": true,
    "source_channel": "gmail_test"
  }
}
```

## 11.4 规则

1. 该接口应复用 `ingest_email` 和 `run_ticket` 逻辑，不应另起一套 ticket 创建流程
2. `auto_enqueue = false` 时，`run = null`
3. `source_channel` 可以在内部映射为受控测试来源，但对外响应允许单独声明 `gmail_test`

---

## 12. `POST /tickets/{ticket_id}/retry`

## 12.1 用途

为失败或可重试 ticket 提供显式重跑入口。

## 12.2 请求体

```json
{
  "ticket_version": 5
}
```

## 12.3 成功响应

`202 accepted`

```json
{
  "ticket_id": "t_01...",
  "run_id": "run_10...",
  "trace_id": "trace_10...",
  "processing_status": "queued"
}
```

## 12.4 规则

1. 本接口可视为 `POST /tickets/{ticket_id}/run` 的语义化别名
2. 服务端应等价于调用现有 `run_ticket(force_retry=true)`
3. 若 ticket 当前不可重试，应返回 `409 invalid_state_transition`

---

## 13. 前端实现建议

控制台前端可以按以下映射消费这些接口：

| 页面 | 接口 |
| --- | --- |
| Dashboard | `GET /ops/status`, `GET /metrics/summary`, `GET /tickets` |
| Tickets | `GET /tickets` |
| Ticket Detail | `GET /tickets/{ticket_id}`, `GET /tickets/{ticket_id}/runs`, `GET /tickets/{ticket_id}/drafts` |
| Trace & Eval | `GET /tickets/{ticket_id}/trace` |
| Gmail Ops | `GET /ops/status`, `POST /ops/gmail/scan`, `POST /ops/gmail/scan-preview` |
| Test Lab | `POST /dev/test-email` |

---

## 14. 最小落地优先级

若只做第一批最关键接口，推荐顺序如下：

1. `GET /tickets`
2. `GET /tickets/{ticket_id}/runs`
3. `GET /tickets/{ticket_id}/drafts`
4. `POST /ops/gmail/scan`
5. `GET /ops/status`
6. `POST /dev/test-email`

这六个接口补齐后，控制台前端就可以开始真实联调。

---

## 15. 结论

当前项目的后端基础已经足够支撑控制台前端。

真正缺的不是核心业务能力，而是“控制面接口层”。

把本文档中的新增接口补齐之后，前端就可以用统一方式展示：

1. Gmail 接入
2. Ticket 化
3. Run 异步执行
4. Draft 与人工协同
5. Trace 与评估
6. 测试注入与演示路径

这样项目的外部表达会比当前脚本式入口清楚得多。
