# Customer Support Copilot Short-Term Memory Checkpoint 规格

## 1. 目的

本文档把“短期记忆”从方向性设计收敛为 V1.1 可执行协议。

本规格的目标不是再发明一套自定义状态快照系统，而是把 Ticket workflow 的运行态记忆严格约束到 `LangGraph checkpointer` 上。

如与以下文档局部冲突，本规格优先：

1. `docs/customer-support-copilot-technical-design.zh-CN.md`
2. `docs/specs/01-core-schema.zh-CN.md`
3. `docs/specs/02-ticket-state-machine.zh-CN.md`

---

## 2. 范围与非目标

### 2.1 本规格覆盖

1. `LangGraph checkpointer` 的固定技术选型
2. checkpoint key / namespace 合同
3. 可持久化的短期记忆字段范围
4. 恢复、续跑、重试与新 run 的边界
5. 运行态观测与测试要求

### 2.2 本规格不覆盖

1. 长期记忆 schema
2. `TicketMessage` 历史消息持久化
3. `CustomerMemoryProfile` 合并策略
4. 前端会话态
5. 自定义 checkpoint 管理后台

说明：

1. 短期记忆只服务“当前 Ticket run 的恢复与续跑”。
2. 长期记忆仍由 `CustomerMemoryProfile` / `CustomerMemoryEvent` 负责。
3. 历史消息仍由 `TicketMessage` / `MessageLogService` 负责。

---

## 3. 固定技术选择

### 3.1 Runtime

V1.1 运行时固定使用：

1. `LangGraph checkpointer`
2. 生产与本地开发默认使用 `Postgres` 持久化 checkpoint

### 3.2 Test

测试允许：

1. 单元测试使用内存型 checkpointer
2. 集成测试使用 `Postgres` checkpointer

### 3.3 明确禁止

V1.1 禁止以下实现：

1. 另起一套“自定义 JSON snapshot 表”作为主方案
2. 在 `Ticket.app_metadata` 内塞整份 `GraphState`
3. 在 `TraceEvent.metadata` 内塞整份 `GraphState`
4. 用本地文件、pickle、临时目录文件作为正式恢复机制
5. 用 Redis 替代 `LangGraph checkpointer` 作为首版主实现

说明：

1. `TicketRun.app_metadata` 可以记录 checkpoint 元信息。
2. 但 checkpoint 正文必须由 `LangGraph checkpointer` 承担。

---

## 4. Checkpoint 标识合同

### 4.1 固定配置键

所有 Ticket workflow 调用 `graph.invoke()` / `graph.stream()` / `graph.astream()` 时，`configurable` 必须包含以下键：

1. `thread_id`
2. `checkpoint_ns`

### 4.2 固定取值

固定规则如下：

1. `thread_id = ticket_id`
2. `checkpoint_ns = run_id`

### 4.3 禁止替代 key

以下字段不得作为 checkpoint 主键：

1. `gmail_thread_id`
2. `source_thread_id`
3. `source_message_id`
4. `customer_id`
5. 任意随机 UUID

原因：

1. `ticket_id` 才是系统内稳定主键。
2. `run_id` 才能区分同一 Ticket 的不同执行轮次。
3. 用 Gmail 线程 ID 做恢复 key 会把 reopen/new run 混在一起。

### 4.4 结果约束

因此，V1.1 的 checkpoint 作用域固定为：

1. 同一 `ticket_id` 下按 `run_id` 隔离
2. 同一 run 内可恢复
3. 不同 run 之间不得自动共享 checkpoint 正文

---

## 5. 短期记忆字段合同

### 5.1 原则

进入 checkpoint 的内容必须同时满足：

1. 可 JSON 序列化
2. 对恢复下一节点有业务意义
3. 不包含运行时依赖对象
4. 不包含敏感配置和凭据

### 5.2 必须可恢复的字段

以下 `GraphState` 字段属于短期记忆正式合同，恢复后必须可直接继续执行：

#### A. 基础执行字段

1. `ticket_id`
2. `run_id`
3. `trace_id`
4. `trigger_type`
5. `triggered_by`
6. `current_node`

#### B. 输入上下文字段

1. `raw_email`
2. `normalized_email`
3. `attachments`
4. `thread_summary`

#### C. 路由字段

1. `primary_route`
2. `secondary_routes`
3. `tags`
4. `response_strategy`
5. `multi_intent`
6. `intent_confidence`
7. `priority`
8. `needs_clarification`
9. `needs_escalation`
10. `routing_reason`

#### D. 知识与策略字段

1. `queries`
2. `knowledge_summary`
3. `retrieval_results`
4. `citations`
5. `knowledge_confidence`
6. `policy_notes`
7. `allowed_actions`
8. `disallowed_actions`
9. `knowledge_policy_result`

#### E. 记忆相关字段

1. `customer_profile`
2. `historical_cases`
3. `case_context`
4. `memory_update_candidates`
5. `memory_updates`

#### F. 草稿与审核字段

1. `draft_versions`
2. `qa_feedback`
3. `applied_response_strategy`
4. `rewrite_count`
5. `approval_status`
6. `escalation_reason`
7. `final_action`
8. `human_handoff_summary`
9. `qa_result`

### 5.3 必须新增的短期记忆字段

为避免恢复时丢失关键上下文，`GraphState` 必须新增：

1. `clarification_history`
2. `resume_count`
3. `checkpoint_metadata`

字段语义固定如下：

#### `clarification_history`

类型：

```json
[
  {
    "question": "Please share the exact error text shown in the UI.",
    "asked_at": "2026-04-03T10:00:00+08:00",
    "source": "clarify_request"
  }
]
```

规则：

1. 只记录系统已提出的澄清问题
2. 不记录自由格式内部推理

#### `resume_count`

规则：

1. 首次执行为 `0`
2. 每次从 checkpoint 恢复并继续执行时加 `1`

#### `checkpoint_metadata`

固定结构：

```json
{
  "thread_id": "t_...",
  "checkpoint_ns": "run_...",
  "last_checkpoint_node": "qa_review",
  "last_checkpoint_at": "2026-04-03T10:01:00+08:00"
}
```

### 5.4 明确禁止进入 checkpoint 的内容

以下内容禁止进入 checkpoint：

1. `Session` / DB connection
2. repository 实例
3. `ServiceContainer`
4. Gmail / LangSmith / Chroma / provider client 实例
5. ORM model 实例
6. prompt 模板对象
7. 原始 SDK response 对象
8. secret、token、API key
9. 自由格式 chain-of-thought

---

## 6. 与当前教程兼容字段的边界

当前 `GraphState` 中仍保留若干教程遗留字段。

V1.1 对这些字段的要求如下：

1. `pending_emails`
2. `emails`
3. `current_email`
4. `email_category`
5. `generated_email`
6. `rag_queries`
7. `retrieved_documents`
8. `writer_messages`
9. `sendable`
10. `trials`

规则：

1. 这些字段不得再作为 Ticket workflow 的权威状态来源
2. 如出于兼容需要暂时保留，必须视为过渡字段
3. 新增节点、恢复逻辑、人工动作逻辑不得依赖这些字段决定业务状态

---

## 7. Checkpoint 写入与恢复规则

### 7.1 写入时机

V1.1 固定使用 `LangGraph checkpointer` 的节点级保存能力。

不得自行实现“每个 node 手动 dump state”。

### 7.2 恢复入口

恢复流程固定为：

1. 根据 `ticket_id + run_id` 计算 `thread_id + checkpoint_ns`
2. 读取该 run 最近 checkpoint
3. 恢复后从上一个成功持久化的节点之后继续

### 7.3 新 run 与旧 run 的边界

固定规则：

1. `manual_api` 触发的新 run 使用新的 `run_id`
2. `scheduled_retry` 触发的新 run 使用新的 `run_id`
3. `reject_for_rewrite` 进入的新 run 使用新的 `run_id`
4. 新 run 不得复用旧 run 的 `checkpoint_ns`

因此：

1. 新 run 可以读取消息日志和长期记忆
2. 但不得直接继承旧 run 的中间节点 checkpoint 正文

### 7.4 同一 run 的恢复

以下场景允许恢复同一 run：

1. worker 进程崩溃
2. worker 宿主机重启
3. API 线程提前中断但 run 已创建

恢复时必须满足：

1. `Ticket.current_run_id == run_id`
2. 该 run 尚未结束
3. 当前 worker 已合法持有该 Ticket 的租约

### 7.5 Side effect 与恢复

checkpoint 恢复不得代替副作用幂等控制。

强制规则：

1. Gmail draft 创建仍以幂等键为准
2. `DraftArtifact` 创建仍以幂等键为准
3. `CustomerMemoryEvent` 回写仍以幂等键为准
4. 恢复后若再次进入副作用节点，必须首先检查幂等记录

说明：

1. checkpoint 解决“从哪继续跑”。
2. 幂等控制解决“副作用是否重复执行”。
3. 二者不得混用。

---

## 8. 元信息记录要求

### 8.1 `TicketRun.app_metadata`

`TicketRun.app_metadata` 必须记录以下 checkpoint 元信息：

```json
{
  "checkpoint": {
    "thread_id": "t_...",
    "checkpoint_ns": "run_...",
    "restore_mode": "fresh|resume",
    "last_checkpoint_node": "qa_review"
  }
}
```

### 8.2 TraceEvent

以下事件必须打点：

1. `checkpoint_restore`
2. `checkpoint_resume_decision`

最小 `metadata`：

```json
{
  "thread_id": "t_...",
  "checkpoint_ns": "run_...",
  "restore_mode": "fresh",
  "restored": false
}
```

---

## 9. 目录与实现边界约束

为避免后续实现自由发挥，V1.1 目录落点固定如下：

1. `src/graph.py`：接入 checkpointer 与 compile 配置
2. `src/state.py`：维护正式短期记忆字段合同
3. `src/api/services.py`：决定 fresh / resume 调用模式
4. 新增 `src/checkpointing.py`：统一构造 checkpointer 与 checkpoint config
5. `tests/`：增加恢复、重复副作用、防错用例

明确禁止：

1. 在 `nodes.py` 内零散构造 checkpoint key
2. 每个 node 各自决定是否 resume
3. 多处重复拼 `thread_id` / `checkpoint_ns`

---

## 10. 测试要求

### 10.1 单元测试

至少覆盖：

1. `ticket_id -> thread_id` 映射固定正确
2. `run_id -> checkpoint_ns` 映射固定正确
3. 禁止用 `gmail_thread_id` 生成 checkpoint key
4. `clarification_history` / `resume_count` 序列化正确

### 10.2 集成测试

至少覆盖：

1. `triage` 后崩溃，恢复后从下一节点继续
2. `qa_review` 后崩溃，恢复后不重复创建 draft
3. 新 run 不读取旧 run checkpoint
4. 同一 run 恢复时 `resume_count` 递增

### 10.3 回归测试

必须确认：

1. 未启用恢复时主链路行为不变
2. 人工审核 API 不受 checkpoint 引入影响
3. Trace / metrics 输出不丢 `run_id` / `trace_id`

---

## 11. 验收标准

满足以下条件时，本规格视为落地完成：

1. Ticket workflow 编译时已挂接正式 checkpointer
2. `thread_id = ticket_id`、`checkpoint_ns = run_id` 已全局统一
3. 同一 run 可恢复，不同 run 不串 checkpoint
4. 引入 checkpoint 后不会重复创建 Gmail draft
5. `TicketRun.app_metadata` 和 trace 中可看到 checkpoint 元信息
6. 不存在第二套主状态快照实现

