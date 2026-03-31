# Customer Support Copilot Ticket State Machine 规格

## 1. 目的

本文档定义 V1 工单状态机。

V1 强制采用双层状态模型：

1. `business_status`
2. `processing_status`

两者不得合并。

---

## 2. 原则

1. `business_status` 描述业务阶段。
2. `processing_status` 描述调度状态。
3. 所有状态迁移都必须递增 `version`。
4. 所有带副作用的迁移都必须记录 `TicketRun` 和 `TraceEvent`。
5. 外部副作用先落幂等键，再执行外部调用，再提交状态。
6. 所有客户入站邮件必须先命中或创建 `Ticket`，再写入 `TicketMessage`。

---

## 3. `business_status`

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

## 4. `processing_status`

1. `idle`
2. `queued`
3. `leased`
4. `running`
5. `waiting_external`
6. `completed`
7. `error`

---

## 5. 领取与租约

### 5.1 可领取条件

只有满足以下条件的 Ticket 可被领取：

1. `processing_status in ('queued', 'error')`
2. `lease_expires_at is null` 或 `lease_expires_at <= now()`
3. `business_status not in ('approved', 'closed')`

### 5.2 领取动作

原子更新：

1. `processing_status = 'leased'`
2. `lease_owner = {worker_id}`
3. `lease_expires_at = now() + 5 minutes`
4. `current_run_id = {run_id}`

### 5.3 进入运行态

worker 真正开始执行前必须更新：

1. `processing_status = 'running'`

### 5.4 续租

1. 运行超过 2 分钟时，每 60 秒续租一次
2. 只有当前 `lease_owner` 能续租

### 5.5 租约回收

如果 `lease_expires_at <= now()`：

1. 其他 worker 可重新领取
2. 原 worker 后续提交必须因 `version` 或 `lease_owner` 校验失败

---

## 6. 业务状态迁移

### 6.1 `new -> triaged`

触发条件：

1. 邮件已入库成 Ticket
2. Triage 成功输出主路由和标签

副作用：

1. 写入 `primary_route`
2. 写入 `secondary_routes`
3. 写入 `tags`
4. 写入 `priority`
5. 写入 `intent_confidence`
6. 写入 `routing_reason`

### 6.2 `triaged -> draft_created`

触发条件：

1. 路由允许自动生成草稿
2. 所需知识检索或政策检查已完成
3. `Drafting Agent` 已产出草稿
4. `QA & Handoff Agent` 判定可进入草稿阶段

副作用：

1. 新增 `DraftArtifact`
2. 如需 Gmail draft，调用 `create_or_update_draft`
3. 更新 `gmail_draft_id`

### 6.3 `triaged -> awaiting_customer_input`

触发条件：

1. `primary_route = technical_issue`
2. `needs_clarification = true`

副作用：

1. 生成 `clarification_request` 类型草稿
2. 写 Gmail draft

### 6.4 `triaged -> awaiting_human_review`

满足以下任一项：

1. 涉及退款金额
2. 涉及补偿或 SLA 承诺
3. 涉及安全事故或数据丢失
4. 涉及法律、合同、政策解释
5. `intent_confidence < 0.60`
6. QA 多轮失败
7. 知识证据不足但主路由非 `unrelated`

副作用：

1. 写入 `risk_reasons`
2. 如已有草稿，保留草稿
3. 不允许自动关闭

### 6.5 `draft_created -> awaiting_human_review`

触发条件：

1. 草稿已生成
2. 风险检查需要人工确认

### 6.6 `triaged -> escalated`

触发条件：

1. 尚未生成草稿
2. 系统或人工已确认该工单必须直接升级

副作用：

1. 记录 `target_queue`
2. 可选生成 `handoff_summary`

### 6.7 `draft_created -> escalated`

触发条件：

1. 草稿已生成
2. 系统或人工确认该工单不能继续自动流转

副作用：

1. 保留现有草稿
2. 记录 `target_queue`
3. 可选生成 `handoff_summary`

### 6.8 `awaiting_human_review -> approved`

触发条件：

1. 人工执行 `approve` 或 `edit_and_approve`
2. 请求中的 `ticket_version_at_review` 与当前版本一致

副作用：

1. 新增 `HumanReview`
2. 如为 `edit_and_approve`，新增一条 `DraftArtifact`

### 6.9 `awaiting_human_review -> rejected`

触发条件：

1. 人工执行 `reject_for_rewrite`

副作用：

1. 记录 `requested_rewrite_reason`
2. 保留已有草稿

### 6.10 `rejected -> triaged`

触发条件：

1. 系统根据人工意见重新进入自动改写

副作用：

1. 保留原有草稿和审核记录
2. 新 run 的 `attempt_index` 递增

### 6.11 `awaiting_human_review -> escalated`

触发条件：

1. 人工执行 `escalate`
2. 或系统明确判断为高风险不可自动回复

副作用：

1. 记录 `target_queue`
2. 生成 `handoff_summary` 草稿或内部摘要

### 6.12 `approved -> closed`

触发条件：

1. 草稿已交付人工发送链路或人工确认无需后续动作

说明：

1. V1 只生成 Gmail draft，不负责自动发送
2. 因此 `approved -> closed` 应通过显式动作完成

### 6.13 `awaiting_customer_input -> closed`

触发条件：

1. 等待超过 TTL 且决定不再继续
2. 人工手动关闭

V1 默认 TTL：

1. `14 days`

### 6.14 `* -> failed`

触发条件：

1. 节点异常且当前 run 终止
2. 外部工具失败且无法在当前 run 内恢复

副作用：

1. 记录 `last_error_code`
2. 记录 `last_error_message`
3. `processing_status = 'error'`

### 6.15 `failed -> triaged`

触发条件：

1. 重试前确认 Ticket 仍有效
2. 重试动作成功领取 Ticket

---

## 7. 调度状态迁移

### 7.1 `idle -> queued`

1. Ticket 创建后立即进入 `queued`

### 7.2 `queued -> leased`

1. worker 原子领取成功

### 7.3 `leased -> running`

1. run 已创建并开始执行

### 7.4 `running -> waiting_external`

1. 进入 `awaiting_customer_input`
2. 或进入 `awaiting_human_review`

### 7.5 `running -> completed`

1. 当前 run 成功结束
2. 业务状态进入 `draft_created`、`approved`、`escalated`、`closed` 之一

### 7.6 `running -> error`

1. 当前 run 失败

### 7.7 `error -> queued`

1. 系统或人工触发重试

---

## 8. Gmail draft 幂等规则

### 8.1 幂等键

V1 固定：

`draft:{ticket_id}:{draft_type}:{version_index}`

### 8.2 规则

1. 先查本地是否已有相同幂等键对应的 `DraftArtifact`
2. 如已有且已有 `gmail_draft_id`，禁止再次创建新 Gmail draft
3. 如需覆盖内容，只允许更新同一 Gmail draft

### 8.3 禁止情况

以下情况禁止创建新 Gmail draft：

1. 同一 `ticket_id` 同一 `version_index` 已成功写出
2. 当前 `business_status = closed`

---

## 9. 人工动作前置状态

`approve`:

1. 只允许 `awaiting_human_review`

`edit_and_approve`:

1. 只允许 `awaiting_human_review`

`reject_for_rewrite`:

1. 只允许 `awaiting_human_review`

`escalate`:

1. 允许 `triaged`
2. 允许 `draft_created`
3. 允许 `awaiting_human_review`

`close`:

1. 允许 `approved`
2. 允许 `awaiting_customer_input`
3. 允许 `escalated`
4. 允许 `failed`

---

## 10. 重试规则

### 10.1 可自动重试

1. LLM 瞬时调用失败
2. 网络超时
3. Gmail API 5xx

### 10.2 不自动重试

1. 版本冲突
2. 数据校验失败
3. 缺少必需输入
4. 人工动作前置状态不满足

### 10.3 上限

1. 每个 Ticket 自动重试上限 `3`
2. 超过后进入 `failed`

---

## 11. Reopen 规则

V1 允许线程 reopen，但必须满足：

1. 原 Ticket `business_status = closed`
2. Gmail 线程中出现新的客户入站 `TicketMessage`
3. 系统创建新 Ticket
4. 旧 Ticket 设为 `is_active = false`
5. 新 Ticket 的 `reopen_count = old.reopen_count + 1`

不得直接复活已关闭 Ticket。

---

## 12. 与当前代码的关系

当前 [graph.py](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/src/graph.py#L27) 和 [nodes.py](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/src/nodes.py#L121) 还是内存流转。

落地后必须改为：

1. `load_inbox_emails` 只负责发现消息并入队
2. `run_ticket` 负责领取指定 Ticket 并执行
3. `must_rewrite` 不再直接 `pop()`，而是更新 Ticket 状态
