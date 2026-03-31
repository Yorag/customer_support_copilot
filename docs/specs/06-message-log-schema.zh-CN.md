# Customer Support Copilot Message Log Schema 规格

## 1. 目的

本文档定义 V1 的消息持久化模型 `TicketMessage`。

该模型用于解决以下落地问题：

1. 保存完整线程上下文
2. 支撑客户补充信息往返
3. 支撑 reopen 判断
4. 为草稿生成和人工交接提供可追溯消息历史

V1 不允许只依赖 Gmail 在线查询作为唯一消息来源。

---

## 2. 核心规则

1. 每一封客户入站邮件都必须先命中或创建 `Ticket`，再持久化为一条 `TicketMessage`。
2. 同一 `source_message_id` 只能入库一次。
3. `TicketMessage` 是线程级追加日志，不允许覆盖更新正文。
4. 草稿、澄清请求和交接摘要也必须形成消息记录。

---

## 3. TicketMessage

### 3.1 唯一约束

1. 主键：`ticket_message_id`
2. 唯一键：`source_channel + source_message_id`

### 3.2 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `ticket_message_id` | string | 是 | 消息记录 ID，格式 `tm_{ulid}` |
| `ticket_id` | string | 是 | 归属 Ticket |
| `run_id` | string | 否 | 来源 run |
| `draft_id` | string | 否 | 如果来自草稿则关联 draft |
| `source_channel` | enum | 是 | V1 固定 `gmail` |
| `source_thread_id` | string | 是 | 外部线程 ID |
| `source_message_id` | string | 是 | 外部消息 ID |
| `gmail_thread_id` | string | 是 | Gmail 线程 ID |
| `direction` | enum | 是 | 入站或系统生成 |
| `message_type` | enum | 是 | 消息类型 |
| `sender_email` | string | 否 | 发送方邮箱 |
| `recipient_emails` | jsonb | 是 | 接收方邮箱数组 |
| `subject` | string | 否 | 主题 |
| `body_text` | text | 否 | 纯文本正文 |
| `body_html` | text | 否 | HTML 正文 |
| `reply_to_source_message_id` | string | 否 | 回复目标消息 ID |
| `customer_visible` | boolean | 是 | 是否客户可见 |
| `message_timestamp` | timestamptz | 是 | 邮件原始时间 |
| `created_at` | timestamptz | 是 | 入库时间 |
| `metadata` | jsonb | 否 | 扩展字段 |

### 3.3 `direction`

1. `inbound`
2. `outbound_draft`
3. `system`

### 3.4 `message_type`

1. `customer_email`
2. `reply_draft`
3. `clarification_request`
4. `handoff_summary`
5. `internal_note`

---

## 4. 入库规则

### 4.1 入站客户邮件

收到 Gmail 入站消息时必须：

1. 规范化邮箱
2. 检查 `source_message_id` 是否已存在
3. 关联或创建 Ticket
4. 写入 `TicketMessage(direction='inbound', message_type='customer_email')`

### 4.2 草稿类消息

生成以下内容时也必须写入消息日志：

1. `reply_draft`
2. `clarification_request`
3. `handoff_summary`

其目的不是替代 `DraftArtifact`，而是让线程历史完整可追溯。

---

## 5. Reopen 判定规则

当同一 Gmail 线程出现新客户入站消息时：

1. 先查询该线程最近一个激活 Ticket
2. 若存在激活 Ticket，则将消息写入该 Ticket 的 `TicketMessage`
3. 若不存在激活 Ticket，但存在最近关闭 Ticket，且该 `source_message_id` 未在历史消息日志中出现，则创建新 Ticket
4. 新 Ticket 创建后，把该消息写入新 Ticket 的 `TicketMessage`

禁止仅通过比较 `closed_at` 或 Gmail 最新线程状态做 reopen，而不持久化消息日志。

---

## 6. 读取规则

### 6.1 Drafting 和 QA

默认按 `message_timestamp asc` 读取最近线程消息，至少包含：

1. 最近一条客户入站消息
2. 最近一条系统生成的澄清请求或草稿
3. 必要时补充更早的客户消息

### 6.2 记忆回写

长期记忆提炼时，必须基于 `TicketMessage` 和 `DraftArtifact`，而不是只看 Ticket 摘要字段。

---

## 7. 与其他规格的关系

1. `TicketMessage` 属于必须落库对象，见 [01-core-schema.zh-CN.md](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/docs/specs/01-core-schema.zh-CN.md)
2. 入站消息先命中或创建 `Ticket`，再写 `TicketMessage`，见 [02-ticket-state-machine.zh-CN.md](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/docs/specs/02-ticket-state-machine.zh-CN.md)
3. `POST /tickets/ingest-email` 必须持久化消息日志，见 [03-api-contract.zh-CN.md](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/docs/specs/03-api-contract.zh-CN.md)
