# Customer Support Copilot Worker Runtime Contract 规格

## 1. 目的

本文档把“独立 worker + 领取与租约合同”收敛为 V1.1 可执行协议。

本规格重点解决 4 件事：

1. API 与 worker 职责分离
2. Ticket 领取与租约续期标准化
3. 运行态字段命名对齐
4. 崩溃恢复、重试与重复执行边界清晰化

如与以下文档局部冲突，本规格优先：

1. `docs/customer-support-copilot-technical-design.zh-CN.md`
2. `docs/specs/01-core-schema.zh-CN.md`
3. `docs/specs/02-ticket-state-machine.zh-CN.md`
4. `docs/specs/03-api-contract.zh-CN.md`

---

## 2. 固定原则

### 2.1 API 不直接跑图

`POST /tickets/{ticket_id}/run` 在 V1.1 中固定为：

1. 创建或登记待执行 run
2. 把 Ticket 置为可被 worker 消费的状态
3. 立即返回 `202 accepted`

明确禁止：

1. 在 FastAPI 请求线程内直接执行完整 graph
2. 让 `run` 接口“有时同步执行，有时异步执行”
3. 把 API 线程同时当作 worker 使用

### 2.2 Worker 是唯一正式执行者

V1.1 中，正式执行 Ticket workflow 的主体固定为独立 worker 进程。

`run_poller.py` 的角色固定为：

1. Gmail 轮询与入库
2. 可选地触发 enqueue

`run_poller.py` 不承担正式 graph 执行职责。

---

## 3. 组件边界

V1.1 固定拆成以下 3 类进程角色：

1. API Server
2. Gmail Poller
3. Ticket Worker

职责如下：

### 3.1 API Server

只负责：

1. 入站接口
2. 人工动作接口
3. 查询接口
4. enqueue run

### 3.2 Gmail Poller

只负责：

1. 拉取 Gmail 新线程
2. 调用 `ingest_email`
3. 触发 enqueue

### 3.3 Ticket Worker

只负责：

1. 领取 Ticket
2. 创建或接管 run
3. 恢复 checkpoint 或 fresh 执行
4. 续租
5. 成功 / 失败收尾

---

## 4. 持久层字段与投影字段合同

### 4.1 DB 权威字段

V1.1 的数据库权威字段固定为：

1. `current_run_id`
2. `lease_owner`
3. `lease_expires_at`

### 4.2 Runtime / API 投影字段

为对齐技术设计中的命名，运行态与 API 层允许暴露以下投影字段：

1. `claimed_by`
2. `claimed_at`
3. `lease_until`

映射规则固定为：

1. `claimed_by = lease_owner`
2. `lease_until = lease_expires_at`
3. `claimed_at = TicketRun.started_at`，前提是 `Ticket.current_run_id` 指向该 run 且 run 已开始

### 4.3 明确禁止

V1.1 禁止：

1. 在 DB 再新增一套与 `lease_owner/lease_expires_at` 并存的重复列
2. 让 `claimed_by` 与 `lease_owner` 双写
3. 让 `lease_until` 与 `lease_expires_at` 双写

说明：

1. 数据库存储只保留一套权威列。
2. 对外命名由 projection 层完成。

---

## 5. `TicketRun` 创建与状态合同

### 5.1 对 `RunStatus` 的增补

为支持 enqueue-only 模式，`RunStatus` 必须增补：

1. `queued`

因此 `RunStatus` 固定为：

1. `queued`
2. `running`
3. `succeeded`
4. `failed`
5. `cancelled`
6. `timed_out`

### 5.2 创建时机

`POST /tickets/{ticket_id}/run` 必须：

1. 创建 `TicketRun`
2. `status = queued`
3. 分配唯一 `run_id`
4. 分配唯一 `trace_id`

### 5.3 Worker 接管时机

worker 成功领取 Ticket 后，必须把该 run 更新为：

1. `status = running`
2. `started_at = now()`

### 5.4 禁止行为

1. API 创建 run 时直接写成 `running`
2. worker 开跑后仍然没有 `started_at`
3. 复用旧 `run_id`

---

## 6. `POST /tickets/{ticket_id}/run` 合同修订

### 6.1 输入规则

保留现有请求体：

```json
{
  "ticket_version": 3,
  "trigger_type": "manual_api",
  "force_retry": false
}
```

### 6.2 行为规则

V1.1 固定规则：

1. 只创建 `queued` run，不同步执行 graph
2. 把 Ticket 置为 `processing_status = queued`
3. 若 Ticket 已被有效租约持有，则返回 `409 lease_conflict`
4. 若 Ticket 处于不可运行状态，则返回 `409 invalid_state_transition`

### 6.3 成功响应

响应体仍为：

```json
{
  "ticket_id": "t_...",
  "run_id": "run_...",
  "trace_id": "trace_...",
  "processing_status": "queued"
}
```

含义固定为：

1. 已排队
2. 尚未真正执行
3. 不是“已经跑完”

---

## 7. Worker 领取合同

### 7.1 可领取条件

worker 只允许领取满足以下条件的 Ticket：

1. `processing_status in ('queued', 'error')`
2. `lease_expires_at is null` 或 `lease_expires_at <= now()`
3. `business_status not in ('approved', 'closed')`
4. `current_run_id` 指向一个 `status = queued` 的 `TicketRun`

### 7.2 固定领取顺序

worker 选择候选 Ticket 的排序固定为：

1. `priority`：`critical > high > medium > low`
2. `created_at` 升序
3. `ticket_id` 升序

禁止自由替换为：

1. 随机顺序
2. 仅按更新时间排序
3. 仅按 run 创建时间排序

### 7.3 原子领取动作

领取成功时必须在同一事务中完成：

1. `processing_status = leased`
2. `lease_owner = worker_id`
3. `lease_expires_at = now() + 5 minutes`
4. `current_run_id = run_id`
5. `version += 1`

### 7.4 进入运行态

worker 在真正启动 graph 之前必须再执行：

1. `processing_status = running`
2. `run.status = running`
3. `run.started_at = now()`

---

## 8. 续租与失租规则

### 8.1 固定租约时长

V1.1 固定租约时长：

1. `5 minutes`

### 8.2 固定续租周期

worker 在 run 处于 `running` 状态时，固定每 `60 seconds` 续租一次。

### 8.3 续租权限

只有满足以下条件才允许续租：

1. 当前 `lease_owner == worker_id`
2. `current_run_id == run_id`
3. `processing_status == running`

### 8.4 失租处理

如果 worker 发现：

1. `lease_owner != worker_id`
2. 或 `lease_expires_at <= now()`

则必须：

1. 立即停止继续执行后续节点
2. 不得再提交 Ticket 状态更新
3. 记录失租 trace 事件

---

## 9. 过期租约回收规则

### 9.1 回收动作

当其他 worker 发现租约已过期时，回收动作固定为：

1. `processing_status = queued`
2. `lease_owner = null`
3. `lease_expires_at = null`
4. `version += 1`

### 9.2 是否新建 run

回收后默认先尝试恢复同一个 `run_id`。

只有在以下场景才新建 run：

1. 人工驳回重写
2. 明确人工重试
3. 业务要求以新 run 重跑

说明：

1. “崩溃恢复”优先复用同一 `run_id`
2. “新一轮自动处理”才新建 `run_id`

---

## 10. Worker 执行入口与目录约束

V1.1 worker 实现路径固定为：

1. 新增 `src/workers/ticket_worker.py`

允许再新增：

1. `src/workers/__init__.py`
2. `src/workers/runner.py`

明确禁止：

1. 把 worker 主循环塞回 `run_poller.py`
2. 把 worker 主循环塞进 `api/services.py`
3. 在 `serve_api.py` 启动时顺带开后台线程跑 worker

### 10.1 CLI 合同

worker CLI 固定支持：

1. `--once`
2. `--loop`
3. `--poll-interval-seconds`

默认行为固定为：

1. 未传参数时等价于 `--loop`

---

## 11. Graph 调用合同

worker 调用 graph 时必须：

1. 传入 `run_id`
2. 传入 `worker_id`
3. 传入 checkpoint config
4. 在 fresh / resume 之间显式决策

不得：

1. 让 graph 自己猜当前是不是 resume
2. 在 node 内部自己领取 Ticket
3. 在 node 内部自己续租

说明：

1. 领取、续租、恢复决策属于 worker orchestration
2. node 只消费已经准备好的状态

---

## 12. 观测要求

### 12.1 必采集 worker 事件

新增必采集 trace 事件：

1. `worker_claim_ticket`
2. `worker_start_run`
3. `worker_renew_lease`
4. `worker_reclaim_expired_lease`
5. `worker_resume_run`
6. `worker_lose_lease`

### 12.2 最小 metadata

```json
{
  "ticket_id": "t_...",
  "run_id": "run_...",
  "worker_id": "worker-1",
  "lease_owner": "worker-1",
  "lease_expires_at": "2026-04-03T10:05:00+08:00"
}
```

---

## 13. 测试要求

### 13.1 单元测试

至少覆盖：

1. `RunStatus.queued` 新增后的枚举校验
2. `claimed_by/claimed_at/lease_until` 投影计算正确
3. 只有持有租约的 worker 可续租
4. 失租后继续提交会失败

### 13.2 集成测试

至少覆盖：

1. `POST /run` 只排队，不同步跑图
2. worker 成功领取后 run 进入 `running`
3. worker 崩溃后可恢复同一 run
4. 租约过期后其他 worker 可回收并接管
5. Gmail poller 不再直接执行 graph

### 13.3 并发测试

至少覆盖：

1. 两个 worker 同时抢同一 Ticket，只能一个成功
2. 失租旧 worker 的状态提交被拒绝
3. 同一 `run_id` 不会被两个 worker 同时推进

---

## 14. 验收标准

满足以下条件时，本规格视为落地完成：

1. API 请求线程内不再直接执行 graph
2. 独立 worker 已成为唯一正式执行者
3. `RunStatus.queued` 与 enqueue-only 语义成立
4. `claimed_by/claimed_at/lease_until` 有固定投影规则
5. 崩溃恢复、租约回收、失租拒绝写入可验证
6. 不存在第二套领取逻辑入口
