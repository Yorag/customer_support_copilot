# Customer Support Copilot Ticket Snapshot Eval Summary 规格

## 1. 目的

本文档把“`GET /tickets/{ticket_id}` 附带最近一次运行的评估摘要引用”收敛为 V1.1 可执行 API 契约。

本规格的目标不是把 trace 详情搬进 snapshot，而是让 Ticket 详情页、列表页或人工审核页在一次请求内拿到“是否值得进一步点进 trace”的最小评估摘要。

如与以下文档局部冲突，本规格优先：

1. `docs/customer-support-copilot-technical-design.zh-CN.md`
2. `docs/specs/03-api-contract.zh-CN.md`
3. `docs/specs/05-trace-and-eval.zh-CN.md`

---

## 2. 范围与非目标

### 2.1 本规格覆盖

1. `GET /tickets/{ticket_id}` 的新增返回字段
2. 最近 run 的选择规则
3. 评估摘要引用对象的固定结构
4. 空值、部分可用、完全可用的语义

### 2.2 本规格不覆盖

1. trace 详情接口本身
2. 仪表盘 URL
3. 前端跳转逻辑
4. 历史 run 列表接口

---

## 3. 设计原则

1. `GET /tickets/{ticket_id}` 仍然是轻量快照接口
2. snapshot 只返回“评估摘要引用”，不返回完整 trace
3. 评估摘要的权威来源固定为最近一次 `TicketRun`
4. 不允许为 snapshot 单独维护另一份评估缓存表

---

## 4. 最近 run 的选择规则

### 4.1 权威来源

`latest_run` 固定取该 Ticket 最近一次创建的 `TicketRun`。

### 4.2 排序规则

按以下顺序选择：

1. `created_at` 倒序
2. `run_id` 倒序

说明：

1. 不使用 `ended_at` 作为主排序字段
2. 不使用 `status` 过滤后再选

原因：

1. snapshot 需要表达“最近一次尝试”，而不只是“最近一次成功运行”

---

## 5. 响应结构修订

### 5.1 `TicketRunSummary` 必须新增 `evaluation_summary_ref`

`GET /tickets/{ticket_id}` 中的 `latest_run` 固定扩展为：

```json
{
  "run_id": "run_01...",
  "trace_id": "trace_01...",
  "status": "succeeded",
  "final_action": "create_draft",
  "evaluation_summary_ref": {
    "status": "complete",
    "trace_id": "trace_01...",
    "has_response_quality": true,
    "response_quality_overall_score": 4.25,
    "has_trajectory_evaluation": true,
    "trajectory_score": 5.0,
    "trajectory_violation_count": 0
  }
}
```

### 5.2 `evaluation_summary_ref.status`

枚举固定为：

1. `not_available`
2. `partial`
3. `complete`

语义固定如下：

#### `not_available`

满足以下任一项：

1. run 尚未结束
2. `response_quality = null` 且 `trajectory_evaluation = null`

#### `partial`

满足：

1. `response_quality` 与 `trajectory_evaluation` 只有一项存在

#### `complete`

满足：

1. `response_quality` 与 `trajectory_evaluation` 都存在

---

## 6. 字段合同

### 6.1 固定字段

`evaluation_summary_ref` 必须固定包含以下字段：

1. `status`
2. `trace_id`
3. `has_response_quality`
4. `response_quality_overall_score`
5. `has_trajectory_evaluation`
6. `trajectory_score`
7. `trajectory_violation_count`

### 6.2 字段取值规则

#### `trace_id`

1. 固定等于 `latest_run.trace_id`
2. 不得生成额外别名字段

#### `has_response_quality`

1. `response_quality != null` 时为 `true`
2. 否则为 `false`

#### `response_quality_overall_score`

1. 取 `run.response_quality.overall_score`
2. `has_response_quality = false` 时必须为 `null`

#### `has_trajectory_evaluation`

1. `trajectory_evaluation != null` 时为 `true`
2. 否则为 `false`

#### `trajectory_score`

1. 取 `run.trajectory_evaluation.score`
2. `has_trajectory_evaluation = false` 时必须为 `null`

#### `trajectory_violation_count`

1. 取 `len(run.trajectory_evaluation.violations)`
2. `has_trajectory_evaluation = false` 时必须为 `null`

---

## 7. 明确禁止返回的内容

`GET /tickets/{ticket_id}` 明确禁止直接返回以下 trace 细节：

1. `events`
2. `latency_metrics`
3. `resource_metrics`
4. `response_quality.reason`
5. `response_quality.subscores`
6. `trajectory_evaluation.expected_route`
7. `trajectory_evaluation.actual_route`
8. `trajectory_evaluation.violations` 明细

原因：

1. 这些内容属于 trace 详情接口职责
2. snapshot 只承担最小摘要引用职责

---

## 8. 无 run / 空值行为

### 8.1 无 run

如果该 Ticket 尚无任何 `TicketRun`：

1. `latest_run = null`
2. 不得伪造空的 `evaluation_summary_ref`

### 8.2 run 存在但评估未生成

示例：

1. run 仍在 `queued`
2. run 仍在 `running`
3. run 失败且未写入任何评估

此时：

1. `latest_run` 正常返回
2. `evaluation_summary_ref.status = not_available`
3. 各 score 字段为 `null`

---

## 9. Source of Truth 约束

评估摘要引用的权威来源固定为 `TicketRun` 行上的：

1. `trace_id`
2. `response_quality`
3. `trajectory_evaluation`
4. `status`
5. `final_action`

V1.1 禁止：

1. 在 `Ticket` 表再冗余一份最近评估摘要
2. 在 `DraftArtifact` 表冗余最近评估摘要
3. 在 API 服务层手工拼装与 `TicketRun` 不一致的缓存结果

---

## 10. 目录与实现落点约束

后续实现只能落在以下位置：

1. `src/api/schemas.py`：扩展 `TicketRunSummary`
2. `src/api/services.py`：构造 `evaluation_summary_ref`
3. `src/api/routes.py`：保持接口路径不变
4. `tests/test_api_contract.py`：补契约测试

明确禁止：

1. 为此新开一个对外接口
2. 在 `routes.py` 中直接读取数据库拼结果
3. 在 schema 层塞业务计算逻辑

---

## 11. 向后兼容规则

本次变更必须满足：

1. `GET /tickets/{ticket_id}` 路径不变
2. 已有字段保持不变
3. 新增字段为向后兼容的 additive change

因此：

1. 旧客户端忽略新字段也不应报错
2. 新客户端可以直接用 `evaluation_summary_ref` 做入口提示

---

## 12. 测试要求

### 12.1 单元测试

至少覆盖：

1. `not_available` / `partial` / `complete` 三种状态判定
2. `trajectory_violation_count` 计算正确
3. 无 run 时 `latest_run = null`

### 12.2 API 契约测试

至少覆盖：

1. 最近 run 成功且评估齐全时返回 `complete`
2. 最近 run 仅有轨迹评估时返回 `partial`
3. 最近 run 在 `running` 时返回 `not_available`
4. 返回体中不包含完整 trace details

---

## 13. 验收标准

满足以下条件时，本规格视为落地完成：

1. `GET /tickets/{ticket_id}` 已附带 `evaluation_summary_ref`
2. 最近 run 选择规则可预测且固定
3. 摘要只取自 `TicketRun`，无额外冗余缓存
4. snapshot 仍然轻量，没有混入 trace 大对象

