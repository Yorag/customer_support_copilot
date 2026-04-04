# Customer Support Copilot 实施任务与进度跟踪

## 1. 目的

本文档改为 `spec-first` 跟踪方式。

后续实施默认遵循以下原则：

1. 以 `spec` 作为主要推进单位。
2. 以技术设计文档决定实施顺序和集成方式。
3. 只保留少量非 `spec` 的工程前置任务，避免基础设施工作失踪。

这意味着后续每次继续推进时，不再优先说“做 A/B/C 阶段”，而是优先说：

1. 正在推进哪一份 `spec`
2. 这份 `spec` 下面的哪个子任务
3. 该任务当前状态是什么

---

## 2. 当前实施方法

### 2.1 唯一事实来源

实施优先级固定如下：

1. `docs/specs/*.md`
2. `docs/customer-support-copilot-technical-design.zh-CN.md`
3. 当前代码现状

解释：

1. `spec` 决定“必须实现什么”。
2. 技术设计文档决定“建议按什么顺序落地”。
3. 当前代码只用于判断差距，不作为目标定义来源。

### 2.2 跟踪单元

进度分为 3 类：

1. `P0`
   非 `spec` 的基础设施前置任务，例如配置层、provider 抽象、测试骨架、数据库 migration 基础设施。
2. `Sxx`
   直接对应 `spec` 文档，例如 `S01` 对应 `01-core-schema`。
3. `X`
   跨多个 `spec` 的集成和交付任务，例如 Graph/Agent 集成、README、Demo。

### 2.3 范围边界

当前仅推进 `V1`，明确不纳入本轮：

1. 人工审核动作与自动流程并发写同一工单的复杂冲突控制。
2. `RAG MCP` 外部知识接入。
3. 多渠道接入。
4. 控制台或后台页面。
5. 图片附件理解。

### 2.4 状态定义

统一使用以下状态：

1. `未开始`
2. `进行中`
3. `阻塞`
4. `已完成`
5. `已跳过`

顶层任务状态按子任务聚合：

1. 全部子任务 `未开始` 时，顶层任务记为 `未开始`
2. 至少一个子任务 `进行中`，或已有完成项但未全部完成时，顶层任务记为 `进行中`
3. 全部子任务 `已完成` 时，顶层任务记为 `已完成`
4. 若存在关键阻塞且无法继续推进，顶层任务记为 `阻塞`

---

## 3. 当前代码基线

当前代码已完成 V1 与 `S11` 目录迁移目标态，基线如下：

1. 正式 workflow、状态与 checkpoint 已收敛到 `src/orchestration/`。
2. 正式 Agent、LLM runtime、记忆、RAG、telemetry、evaluation 与 worker 已分别收敛到 `src/agents/`、`src/llm/`、`src/memory/`、`src/rag/`、`src/telemetry/`、`src/evaluation/`、`src/workers/`。
3. 旧平铺文件 `src/graph.py`、`src/state.py`、`src/agents.py`、`src/customer_memory.py`、`src/observability.py`、`src/llm.py` 及相关薄兼容层已全部删除，仓库内部导入已统一切换到正式目录落点。
4. `serve_api.py` 已是业务 API 入口，`POST /tickets/{ticket_id}/run` 已是 enqueue-only 语义，真正 graph 执行只由 worker 承担。
5. `run_poller.py` 已收口为 Gmail poller，只负责 `ingest + enqueue`，不再同步执行 graph。

后续若继续推进，应继续按 `spec -> 子任务 -> 代码落地 -> 回填进度表` 的方式执行。

---

## 4. 主跟踪表

| ID | 类型 | 对应文档 | 当前目标 | 状态 | 前置项 | 主代码范围 |
| --- | --- | --- | --- | --- | --- | --- |
| P0 | 基础设施 | 非 spec | 立住配置、provider、测试、DB 基础设施 | 已完成 | 无 | `src/`, `tests/`, 启动与配置文件 |
| S01 | Spec | `docs/specs/01-core-schema.zh-CN.md` | 落地核心实体和 repository | 已完成 | P0 | 数据模型、repository |
| S06 | Spec | `docs/specs/06-message-log-schema.zh-CN.md` | 落地消息日志与 reopen 读写规则 | 已完成 | S01 | 消息模型、消息读写 |
| S02 | Spec | `docs/specs/02-ticket-state-machine.zh-CN.md` | 落地状态机、lease、重试、draft 幂等 | 已完成 | S01, S06 | 状态迁移、worker 控制 |
| S04 | Spec | `docs/specs/04-routing-decision-table.zh-CN.md` | 落地 triage 输出和路由决策 | 已完成 | P0, S01 | 结构化输出、triage agent |
| S03 | Spec | `docs/specs/03-api-contract.zh-CN.md` | 落地业务 API、memory 查询、trace 查询和 metrics 汇总接口 | 已完成 | S01, S02, S06 | `FastAPI` 路由、请求响应模型 |
| S05 | Spec | `docs/specs/05-trace-and-eval.zh-CN.md` | 落地 trace、指标和离线评测 | 已完成 | S03, X1 | trace、metrics、eval |
| S07 | Spec | `docs/specs/07-short-term-memory-checkpoint.zh-CN.md` | 落地 `LangGraph checkpointer`、短期记忆字段合同和 crash-resume 机制 | 已完成 | S02, S03, S05, X1 | `graph/state/run` 恢复链路 |
| S08 | Spec | `docs/specs/08-worker-runtime-contract.zh-CN.md` | 落地独立 worker、enqueue-only run、租约续期和失租恢复 | 已完成 | S02, S03, S07 | worker、run、API 触发链路 |
| S09 | Spec | `docs/specs/09-ticket-snapshot-eval-summary.zh-CN.md` | 为 ticket snapshot 增加最近 run 的评估摘要引用 | 已完成 | S03, S05 | ticket 查询接口与 DTO |
| S10 | Spec | `docs/specs/10-llm-usage-and-judge.zh-CN.md` | 落地统一 LLM runtime、真实 usage 采集和正式 LLM judge | 已完成 | S05 | LLM 调用、评测与 metrics |
| S11 | Spec | `docs/specs/11-directory-migration.zh-CN.md` | 按新目录结构完成全量一次性重构，并按阶段强制测试门禁 | 已完成 | S07, S08, S09, S10 | `src/` 目录迁移、旧残留清理、文档回填 |
| X1 | 集成 | 跨 spec | 完成 state、agent、graph、记忆、审核集成 | 已完成 | S01, S02, S04 | `src/orchestration/`, `src/agents/`, `src/orchestration/nodes.py`, `src/memory/`, `src/telemetry/` |
| X2 | 交付 | 跨 spec | 完成 README、流程图、Demo | 已完成 | S03, S05, X1 | `README.md`, `docs/`, 演示材料 |

说明：

1. 主跟踪表用于表达 `spec` 覆盖关系和顶层状态，不用于决定精确执行顺序。
2. 实际执行顺序一律以“第 6 节 推荐执行顺序”里的子任务顺序为准。

---

## 5. Spec 覆盖矩阵

| 文档 | 覆盖任务 | 当前覆盖状态 | 说明 |
| --- | --- | --- | --- |
| `01-core-schema` | `S01`, `S06`, `S02`, `S03`, `X1` | `S01` 已完成，后续依赖可继续推进 | 这是所有后续实现的基础契约 |
| `02-ticket-state-machine` | `S02`, `S03`, `X1` | `S02` 已完成，相关 API 与 graph 集成已完成 | 状态迁移、lease、幂等、重试都已落地 |
| `03-api-contract` | `S03`, `S05`, `X1` | `S03` 已完成，`S05/X1` 已完成 | ticket、memory、trace、metrics 接口已对齐当前 V1 契约 |
| `04-routing-decision-table` | `S04`, `X1` | `S04` 已完成，`X1` 已完成 | 已产出 triage 结构化输出、规则决策服务、prompt 与样例测试 |
| `05-trace-and-eval` | `S05`, `X2` | `S05` 已完成，`X2` 已完成 | trace、指标和离线评测已可用于交付展示和失败案例说明 |
| `06-message-log-schema` | `S06`, `S02`, `S03` | `S06` 已完成，消息持久化基础已具备 | 消息持久化、draft 幂等、reopen 判定都依赖它 |
| `07-short-term-memory-checkpoint` | `S07`, `S08`, `S11` | `S07` 已完成，可继续推进 `S10/S08/S11` | 短期记忆、checkpoint key、resume 和目录迁移都要以它为准 |
| `08-worker-runtime-contract` | `S08`, `S11` | `S08` 已完成，可继续推进 `S11` | enqueue-only run、worker、租约、失租和恢复的正式契约 |
| `09-ticket-snapshot-eval-summary` | `S09`, `S11` | `S09` 已完成 | `GET /tickets/{id}` 的轻量评估摘要引用契约 |
| `10-llm-usage-and-judge` | `S10`, `S11` | `S10` 已完成，可继续推进 `S11` | LLM runtime、usage 来源、judge 和资源指标的正式契约 |
| `11-directory-migration` | `S11` | 已完成 | 目标目录结构、阶段门禁、分段测试和旧平铺残留收尾规则 |

结论：

1. 进度表现在是以 `spec` 为主组织的。
2. 每份 `spec` 都有明确对应任务。
3. `07` 到 `11` 已补齐为下一轮主线 spec，其中 `S07/S09/S10` 已完成，后续主线收敛到 `S08/S11`。
4. 非 `spec` 工作只保留在 `P0` 和 `X`，避免纯工程项淹没 `spec` 主线。

---

## 6. 推荐执行顺序

虽然进度表以 `spec` 为主，但实施顺序仍按依赖执行。为避免 `API` 与 `Graph` 互相等待，建议按以下子任务顺序推进：

1. `P0`
2. `S01`
3. `S06`
4. `S02`
5. `S04`
6. `S03.1`
7. `S03.2`
8. `X1.1`
9. `X1.2`
10. `X1.3`
11. `S03.3`
12. `X1.4`
13. `S03.4`
14. `S03.5`
15. `S05`
16. `S03.6`
17. `S03.7`
18. `X2`
19. `S07.1`
20. `S07.2`
21. `S07.3`
22. `S07.4`
23. `S10.1`
24. `S10.2`
25. `S10.3`
26. `S10.4`
27. `S09.1`
28. `S09.2`
29. `S08.1`
30. `S08.2`
31. `S08.3`
32. `S08.4`
33. `S11.1`
34. `S11.2`
35. `S11.3`
36. `S11.4`
37. `S11.5`
38. `S11.6`
39. `S11.7`

说明：

1. `S03.1/S03.2` 先把 API 骨架、入库接口和工单查询接口立起来。
2. `X1.3` 先把真实 ticket 执行流做出来，再由 `S03.3` 暴露 `run`。
3. `X1.4` 先把记忆、审核和升级分支接入，再由 `S03.4` 暴露人工动作接口。
4. `S05` 先产出真实 trace 与 metrics 数据，再由 `S03.6/S03.7` 暴露 trace 和汇总查询接口。
5. `S07` 先固定 checkpoint 与短期记忆合同，后续 worker 与目录迁移都必须服从这个恢复模型。
6. `S10` 先固定 LLM runtime 和 judge 合同，后续 telemetry 与目录迁移不得再各自实现一套调用路径。
7. `S09` 在现有 API 契约上做轻量增量，先补齐 snapshot 引用能力，再让 telemetry 迁移时有稳定对外语义。
8. `S08` 在 `S07` 之后推进，避免 worker/runtime 和恢复模型出现双重来源。
9. `S11` 最后执行，作为一次性目标目录迁移的总集成任务，并严格按 spec 中的阶段门禁推进。

并行原则仍然是：

1. 主链路串行。
2. `P0.3` 测试骨架可以和 `P0.1/P0.2` 局部并行。
3. 文档类更新只能在 `X2` 阶段作为主任务，不提前分散注意力。
4. `S11` 虽然是全量一次性重构目标，但其内部阶段执行仍然严格串行，且每阶段都必须先过本阶段测试和 `pytest -q` 全量回归。

---

## 7. 详细任务清单

### P0. 基础设施前置项

目标：

1. 为后续所有 `spec` 提供稳定的工程骨架。
2. 不让配置、provider、测试、数据库初始化这些工作散落到后面返工。

| 子任务 | 内容 | 状态 | 前置项 | 主要产出 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| P0.0 | 冻结本轮实施边界并建立跟踪文档 | 已完成 | 无 | 本文档初版与 spec-first 重排 | 已明确仅做 V1，已建立主跟踪表 |
| P0.1 | 引入统一配置层 | 已完成 | P0.0 | 配置模块、环境变量校验 | 代码不再到处直接读取环境变量，并为 Gmail、LLM、DB、`LangSmith` 预留统一配置入口 |
| P0.2 | 引入 provider 接口骨架 | 已完成 | P0.1 | `gmail_client`、`knowledge_provider`、`policy_provider`、`ticket_store` 抽象 | Graph/Agent 不直接依赖 Gmail/Chroma 细节，`knowledge_provider` 默认保留当前本地 RAG，实现上预留未来 `RAG MCP` 接口而不重写知识层 |
| P0.3 | 建立测试骨架与样本目录 | 已完成 | P0.0 | `tests/`、fixture、假数据 | 最小 `pytest` 可运行，后续测试有落点 |
| P0.4 | 建立数据库和 migration 基础设施 | 已完成 | P0.1, P0.2 | `Postgres` 初始化、migration 工具与首个 migration | V1 存储唯一选型固定为 `Postgres`，本地可以初始化数据库，不靠手工 SQL 粘贴 |

### S01. Core Schema

对应文档：

1. `docs/specs/01-core-schema.zh-CN.md`

目标：

1. 把核心业务实体真正落到代码和数据库里。
2. 让后续状态机、API、graph 都有稳定的数据契约。

| 子任务 | 对应章节 | 内容 | 状态 | 前置项 | 主要产出 | 验收标准 |
| --- | --- | --- | --- | --- | --- | --- |
| S01.1 | `2`, `3`, `4`, `5`, `6`, `7` | 落地全局规则、枚举、ID、时间、版本约束 | 已完成 | P0.4 | 公共类型、枚举、校验逻辑 | 字段和枚举与 spec 对齐，`source_channel` 固定为 `gmail`，并落实 `multi_intent/tags/secondary_routes` 同步规则 |
| S01.2 | `3`, `4`, `5`, `6`, `7` | 落地 `Ticket`、`TicketRun`、`DraftArtifact`、`HumanReview`、`TraceEvent` | 已完成 | S01.1 | ORM 或 schema 定义 | 唯一约束和必填字段符合 spec，且 `response_quality`、`trajectory_evaluation` 使用 spec 固定结构键，不引入自定义总分键 |
| S01.3 | `8`, `9` | 落地 `CustomerMemoryProfile`、`CustomerMemoryEvent` 和 `customer_id` 规则 | 已完成 | S01.1 | 记忆数据模型和生成规则 | `customer_id` 推导和空值规则正确，`profile`、`business_flags`、`historical_case_refs` 固定键与结构符合 spec |
| S01.4 | `10`, `11` | 为核心实体建立 repository 接口与实现 | 已完成 | S01.2, S01.3 | repositories | 上层模块不直接写 SQL |

### S06. Message Log Schema

对应文档：

1. `docs/specs/06-message-log-schema.zh-CN.md`

目标：

1. 把消息日志从 Gmail 在线查询中剥离出来。
2. 为 reopen、draft 幂等和 QA 读取建立持久化基础。

| 子任务 | 对应章节 | 内容 | 状态 | 前置项 | 主要产出 | 验收标准 |
| --- | --- | --- | --- | --- | --- | --- |
| S06.1 | `2`, `3` | 落地 `TicketMessage` schema、唯一约束、字段和枚举 | 已完成 | S01.4 | `TicketMessage` 模型 | 消息模型可独立持久化 |
| S06.2 | `4` | 实现入站客户邮件和草稿消息入库规则 | 已完成 | S06.1 | 消息写入服务 | 同一消息可幂等入库，并保留 `attachments` 元数据或可复用引用，不在 V1 引入图片内容理解 |
| S06.3 | `5`, `6`, `7` | 实现 reopen 判定和 Drafting/QA/Memory 的消息读取规则 | 已完成 | S06.2 | 消息查询接口 | 不再把 Gmail 当唯一消息来源 |

### S02. Ticket State Machine

对应文档：

1. `docs/specs/02-ticket-state-machine.zh-CN.md`

目标：

1. 用显式状态机接管当前原型的隐式流程。
2. 建立 lease、重试、失败恢复和 draft 幂等规则。

| 子任务 | 对应章节 | 内容 | 状态 | 前置项 | 主要产出 | 验收标准 |
| --- | --- | --- | --- | --- | --- | --- |
| S02.1 | `2`, `3`, `6` | 实现 `business_status` 迁移校验 | 已完成 | S01.4, S06.3 | 业务状态机服务 | 非法迁移会被拒绝 |
| S02.2 | `4`, `5`, `7` | 实现 `processing_status`、lease、领取、续租、回收 | 已完成 | S02.1 | worker 状态控制 | 中断后能重新领取 |
| S02.3 | `10`, `11` | 实现重试、失败恢复和 reopen 状态转换 | 已完成 | S02.1, S02.2, S06.3 | retry/reopen 逻辑 | 自动重试边界符合 spec |
| S02.4 | `8`, `9` | 实现 Gmail draft 幂等和人工动作前置状态校验 | 已完成 | S02.1, S06.2 | draft idempotency 与前置校验 | 同一轮执行不重复造草稿 |

### S04. Routing Decision Table

对应文档：

1. `docs/specs/04-routing-decision-table.zh-CN.md`

目标：

1. 让 triage 输出和决策规则完全由 `spec` 驱动。
2. 不再沿用原项目的粗分类标签。

| 子任务 | 对应章节 | 内容 | 状态 | 前置项 | 主要产出 | 验收标准 |
| --- | --- | --- | --- | --- | --- | --- |
| S04.1 | `2`, `3`, `4`, `5`, `6`, `7`, `8`, `9`, `11` | 定义 triage 结构化输出模型 | 已完成 | P0.2, S01.2 | 新输出模型 | 输出字段与 JSON 模板一致 |
| S04.2 | `3`, `4`, `5`, `6`, `7`, `8`, `9` | 实现决策服务和规则解释层 | 已完成 | S04.1 | 路由决策服务 | 主路由、优先级、澄清、升级判断一致 |
| S04.3 | `10`, `11`, `12` | 改造 `Triage Agent` prompt 与结构化输出 | 已完成 | S04.1, S04.2 | 新 triage agent | 边界样例可跑通 |
| S04.4 | `10`, `12` | 增加 triage 样例测试和冲突优先级测试 | 已完成 | S04.3, P0.3 | 路由测试 | 多条件冲突时路径稳定 |

### S03. API Contract

对应文档：

1. `docs/specs/03-api-contract.zh-CN.md`

目标：

1. 用业务 API 接管当前 `LangServe` 默认暴露模式。
2. 把工单系统的对外语义固定下来。

| 子任务 | 对应章节 | 内容 | 状态 | 前置项 | 主要产出 | 验收标准 |
| --- | --- | --- | --- | --- | --- | --- |
| S03.1 | `2`, `15` | 搭建 `FastAPI` 业务骨架、DTO 校验、请求头处理、错误格式、版本控制与幂等处理约定 | 已完成 | S01.4, S02.1 | API 基础框架 | 不再把 runnable API 作为主入口，`X-Actor-Id`、`X-Request-Id`、`Idempotency-Key` 统一处理，`validation_error`、`not_found`、`ticket_version_conflict`、`invalid_state_transition`、`lease_conflict`、`duplicate_request`、`external_dependency_failed` 等标准错误码明确 |
| S03.2 | `3`, `10`, `14` | 实现 `POST /tickets/ingest-email`、`GET /tickets/{ticket_id}` | 已完成 | S03.1, S06.2, S06.3 | 入库与工单快照接口 | 邮件先入库成 ticket，`ingest` 幂等键与 `new/queued` 状态符合 spec，`attachments` 请求字段被接收并以元数据方式持久化 |
| S03.3 | `4`, `14` | 实现 `POST /tickets/{ticket_id}/run` | 已完成 | S03.1, S02.2, X1.3 | run 接口 | 可以触发真正的 ticket 执行流，并返回 run 结果摘要 |
| S03.4 | `5`, `6`, `7`, `8`, `9`, `14` | 实现人工动作接口：`approve`、`edit-and-approve`、`rewrite`、`escalate`、`close` | 已完成 | S03.2, S03.3, S02.4, X1.4 | 人工动作接口 | 所有前置状态、版本与返回体符合契约 |
| S03.5 | `12` | 实现 `GET /customers/{customer_id}/memory` | 已完成 | S01.3, X1.4, S03.1 | memory 查询接口 | 返回 `profile`、`risk_tags`、`business_flags`、`historical_case_refs`、`version` |
| S03.6 | `11`, `14` | 实现 `GET /tickets/{ticket_id}/trace` | 已完成 | S03.1, S05.2 | trace 查询接口 | 返回 `trace_id`、延迟、资源、质量、轨迹评估和事件明细 |
| S03.7 | `13` | 实现 `GET /metrics/summary` | 已完成 | S03.1, S05.3 | metrics 汇总接口 | 可按时间窗口和 route 输出 latency、resources、response_quality、trajectory_evaluation 汇总 |

### S05. Trace And Eval

对应文档：

1. `docs/specs/05-trace-and-eval.zh-CN.md`

目标：

1. 让系统执行路径可追踪、可评估、可解释。
2. 把演示和验证建立在真实轨迹上，而不是口头说明上。

| 子任务 | 对应章节 | 内容 | 状态 | 前置项 | 主要产出 | 验收标准 |
| --- | --- | --- | --- | --- | --- | --- |
| S05.1 | `1`, `2`, `3`, `4`, `12` | 接入 `LangSmith`，并实现统一 trace 包装层、`trace_id`、事件类型、最小字段和事件写入 | 已完成 | S03.2, X1.3 | trace 写入器与 `LangSmith` 集成 | V1 追踪固定使用 `LangSmith`，每次 run 都有唯一 `trace_id`，并串联 `TicketRun/TraceEvent/DraftArtifact/评估结果` |
| S05.2 | `3`, `4`, `5`, `6`, `7`, `8`, `12` | 为必采集节点、决策、延迟、资源、质量打点，并补 token 统计 | 已完成 | S05.1 | 指标与决策事件采集 | `13` 个必采集节点、`4` 个必采集决策、`end_to_end_ms`、`node/llm/tool latencies`、token 与调用数全部可观测 |
| S05.3 | `9`, `10`, `11`, `12` | 建立 `jsonl` 离线评测样本、规则式轨迹评估、Judge 输出 schema 校验和报表输出 | 已完成 | S05.2, P0.3 | eval 样本与脚本 | 样本至少 `24` 条、覆盖 `8` 类场景，输出字段和汇总报表字段与 spec 一致 |

### X1. Graph/Agent 集成重构

对应文档：

1. `docs/customer-support-copilot-technical-design.zh-CN.md`
2. `S01`, `S02`, `S04`, `S03` 对应 `spec`

目标：

1. 把原型流重构成 ticket 执行流。
2. 把多个 `spec` 组合成真实可运行系统。

| 子任务 | 内容 | 状态 | 前置项 | 主要产出 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| X1.1 | 将 `GraphState` 从邮件处理态改为 ticket run 执行态 | 已完成 | S01.4, S02.1 | 新 state 模型 | state 字段与业务状态一致 |
| X1.2 | 将现有 agent 重构为 `Triage`、`Knowledge & Policy`、`Drafting`、`QA & Handoff` 四个核心角色 | 已完成 | S04.3, X1.1 | 新 agent 结构 | agent 分工与决策表对齐 |
| X1.3 | 将 graph 从 `load inbox -> categorize -> rag -> writer -> proofreader` 改为 ticket 执行流 | 已完成 | X1.1, X1.2, S03.2 | 新 graph | 明确区分“邮件发现/入库”和“ticket 执行” |
| X1.4 | 接入短期记忆、长期记忆、人工审核与升级分支，并实现 `collect_case_context -> extract_memory_updates -> validate_memory_updates` | 已完成 | X1.3, S01.3, S02.4 | 记忆和审核集成 | 等待客户补充、审核、升级路径闭环，且工单收尾时能生成并校验结构化 `memory_updates` |

### X2. 交付与展示

目标：

1. 让仓库能够清晰表达“现在这个系统是什么”。
2. 把文档、流程图和 demo 统一成可展示版本。

| 子任务 | 内容 | 状态 | 前置项 | 主要产出 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| X2.1 | 重写 README，更新定位、架构、启动方式、V1/V2 边界 | 已完成 | S03.3, S05.2, X1.3 | 新 README | README 不再停留在原教程项目 |
| X2.2 | 输出新的系统流程图 | 已完成 | X2.1 | 流程图 | 演示路径清晰可说明 |
| X2.3 | 准备成功样例、失败样例、可重复 demo case | 已完成 | X2.1, X2.2, S05.3 | demo 材料 | 有至少一条失败案例可解释系统边界 |

### S07. Short-Term Memory Checkpoint

对应文档：

1. `docs/specs/07-short-term-memory-checkpoint.zh-CN.md`

目标：

1. 为 ticket workflow 建立正式 `LangGraph checkpointer` 方案。
2. 让 run 具备 crash-resume 能力，并与副作用幂等解耦。

| 子任务 | 对应章节 | 内容 | 状态 | 前置项 | 主要产出 | 验收标准 |
| --- | --- | --- | --- | --- | --- | --- |
| S07.1 | `3`, `4`, `9` | 落地统一 checkpoint 构造层、`thread_id=ticket_id`、`checkpoint_ns=run_id` 与编译接入点 | 已完成 | S02.2, X1.3, S05.1 | `graph/checkpointing` 与 graph 编译接入 | 不存在第二套 checkpoint key 生成逻辑，compile 时已挂正式 checkpointer |
| S07.2 | `5`, `6` | 收紧 `GraphState` 为正式短期记忆合同，补 `clarification_history`、`resume_count`、`checkpoint_metadata` | 已完成 | S07.1 | 新 state 合同 | checkpoint 中字段可 JSON 序列化，教程遗留字段不再作为权威状态来源 |
| S07.3 | `7`, `8` | 实现 fresh/resume 决策、run 级 checkpoint 元信息与 trace 事件 | 已完成 | S07.1, S07.2, S03.3 | 恢复入口与元信息记录 | `TicketRun.app_metadata`、trace 中可见 checkpoint 元信息，fresh/resume 语义固定 |
| S07.4 | `7`, `10`, `11` | 覆盖 crash-resume、跨 run 隔离和副作用防重测试 | 已完成 | S07.3, P0.3 | checkpoint 测试集 | 同一 run 可恢复、不同 run 不串 checkpoint、恢复后不重复创建 draft |

### S08. Worker Runtime Contract

对应文档：

1. `docs/specs/08-worker-runtime-contract.zh-CN.md`

目标：

1. 让 API、poller、worker 三类角色边界清晰。
2. 把 run 触发从“直接执行”切换为 enqueue-only 正式模型。

| 子任务 | 对应章节 | 内容 | 状态 | 前置项 | 主要产出 | 验收标准 |
| --- | --- | --- | --- | --- | --- | --- |
| S08.1 | `4`, `5`, `6` | 扩展 `RunStatus=queued`、收紧 `POST /tickets/{ticket_id}/run` 为 enqueue-only 语义 | 已完成 | S02.2, S03.3, S07.3 | run 创建与 API 契约修订 | API 不再直接执行 graph，run 创建时固定为 `queued` |
| S08.2 | `7`, `8`, `9` | 落地独立 worker 的领取、续租、失租、回收与恢复规则 | 已完成 | S08.1, S07.4 | worker runtime 与 lease 流程 | 只有 worker 执行 graph，失租后禁止继续提交，过期租约可回收接管 |
| S08.3 | `4`, `10`, `11`, `12` | 打通 `claimed_by/claimed_at/lease_until` 投影、worker CLI 与观测事件 | 已完成 | S08.2, S05.1 | worker 入口和 trace 事件 | 对外字段投影固定，worker 事件可追踪，CLI 入口稳定 |
| S08.4 | `13`, `14` | 覆盖 enqueue、worker 接管、续租、失租拒写和并发抢占测试 | 已完成 | S08.3, P0.3 | worker 测试集 | 双 worker 不会并行推进同一 run，`POST /run` 只排队不直跑 |

### S09. Ticket Snapshot Eval Summary

对应文档：

1. `docs/specs/09-ticket-snapshot-eval-summary.zh-CN.md`

目标：

1. 让 ticket snapshot 附带最近 run 的最小评估摘要引用。
2. 保持 snapshot 轻量，不混入完整 trace 细节。

| 子任务 | 对应章节 | 内容 | 状态 | 前置项 | 主要产出 | 验收标准 |
| --- | --- | --- | --- | --- | --- | --- |
| S09.1 | `4`, `5`, `6` | 扩展 `TicketRunSummary` 与 `evaluation_summary_ref` DTO、最近 run 选择规则 | 已完成 | S03.2, S05.3 | 新 snapshot DTO | `complete/partial/not_available` 三态明确，最近 run 选择规则固定 |
| S09.2 | `7`, `8`, `9`, `10`, `12`, `13` | 在 API 服务层构造摘要引用并补契约测试 | 已完成 | S09.1, P0.3 | snapshot 查询实现与测试 | `GET /tickets/{id}` 只返回摘要引用，不返回完整 trace 明细 |

### S10. LLM Usage And Judge

对应文档：

1. `docs/specs/10-llm-usage-and-judge.zh-CN.md`

目标：

1. 为所有业务 LLM 调用建立统一 runtime 封装。
2. 让资源指标具备真实 usage 来源标记，并以正式 LLM judge 取代线上规则式质量评估。

| 子任务 | 对应章节 | 内容 | 状态 | 前置项 | 主要产出 | 验收标准 |
| --- | --- | --- | --- | --- | --- | --- |
| S10.1 | `3`, `4`, `5`, `6` | 落地统一 `llm_runtime` 封装、usage 提取优先级和 `token_source` 合同 | 已完成 | S05.2 | LLM runtime 基础层 | 所有业务 LLM 调用都经统一 wrapper，`llm_call.metadata` 含 `token_source` |
| S10.2 | `7` | 扩展资源指标聚合，补 `actual/estimated/unavailable` 与 `token_coverage_ratio` | 已完成 | S10.1, S05.2 | 新资源指标 | metrics 能区分真实 usage、估算 usage 与不可用 usage |
| S10.3 | `8`, `9`, `11` | 落地正式 `LLM-as-a-judge`、配置项、失败降级与结构化输出校验 | 已完成 | S10.1, S05.3 | judge 实现与配置 | 线上 `response_quality` 来自正式 judge，失败不阻塞主流程但可观测 |
| S10.4 | `10`, `12`, `13` | 把旧规则评测降级为 baseline，并补 usage/judge 的单测、集成测和回归测 | 已完成 | S10.2, S10.3, P0.3 | usage/judge 测试集 | 不再由旧规则实现承担正式线上质量评测职责 |

### S11. Directory Migration

对应文档：

1. `docs/specs/11-directory-migration.zh-CN.md`

目标：

1. 按目标目录结构完成一次性全量重构。
2. 严格执行“每阶段必测 + 未通过不得进入下一阶段”的门禁规则。

| 子任务 | 对应章节 | 内容 | 状态 | 前置项 | 主要产出 | 验收标准 |
| --- | --- | --- | --- | --- | --- | --- |
| S11.1 | `4`, `6`, `7.2` | 阶段 A：建立新目录骨架、`__init__.py`、最小 import 基础，并执行阶段测试 | 已完成 | S07.4, S08.4, S09.2, S10.4 | 新目录骨架 | 阶段 A 测试与 `pytest -q` 全量通过后才能进入阶段 B |
| S11.2 | `6`, `7.3`, `8` | 阶段 B：迁移 `graph/state/checkpointing` 并执行阶段测试 | 已完成 | S11.1 | `src/orchestration/` 新结构 | `graph/state` import 在本阶段结束时已统一，阶段测试与全量回归通过 |
| S11.3 | `6`, `7.4`, `8` | 阶段 C：迁移 `agents/llm` 并执行阶段测试 | 已完成 | S11.2 | `src/agents/`、`src/llm/` | 所有业务 LLM 调用已切至新路径，阶段测试与全量回归通过 |
| S11.4 | `6`, `7.5`, `8` | 阶段 D：迁移 `memory/rag` 并执行阶段测试 | 已完成 | S11.3 | `src/memory/`、`src/rag/` | memory 与 rag import 已统一，阶段测试与全量回归通过 |
| S11.5 | `6`, `7.6`, `8` | 阶段 E：迁移 `telemetry` 并执行阶段测试 | 已完成 | S11.4 | `src/telemetry/` | trace/metrics/eval 路径已统一，阶段测试与全量回归通过 |
| S11.6 | `6`, `7.7`, `8` | 阶段 F：落地 `workers` 并完成 API 到 worker 的切换，执行阶段测试 | 已完成 | S11.5 | `src/workers/` 与 enqueue-only 链路 | API 不再直接执行 graph，阶段测试与全量回归通过 |
| S11.7 | `5`, `6`, `7.8`, `11`, `12`, `13`, `14` | 阶段 G：旧文件完成收口、README/技术文档/跟踪表回填并做最终验收 | 已完成 | S11.6 | 最终目录结构与文档回填 | 旧平铺文件已完成迁移，后续目录清理后只保留正式落点，最终 `pytest -q` 全量通过 |

---

## 8. 下一步默认执行规则

后续如果用户只说“继续推进”，默认规则如下：

1. 不按主跟踪表的显示顺序选任务，主跟踪表只用于看覆盖和总状态。
2. 严格按“第 6 节 推荐执行顺序”从前到后寻找第一个前置项已满足、且状态不是 `已完成` 的子任务。
3. 开工前把该子任务状态改为 `进行中`。
4. 完成后把状态改为 `已完成`，并回填“最近变更记录”。

按当前进度，默认下一任务是：

1. 当前 `spec-first` 主线已全部完成；如继续推进，应先新增后续 `spec` 或非 `V1` 范围任务。

---

## 9. 每次协作时的更新规则

每轮结束必须更新两处：

1. 对应子任务状态
2. 最近变更记录

如果实施过程中发现需要进一步拆分，命名规则固定为：

1. `S01.2a`
2. `S01.2b`
3. `X1.3a`

如果出现阻塞，记录格式固定为：

1. 阻塞项
2. 阻塞原因
3. 解法或待确认项

---

## 10. 最近变更记录

| 日期 | 变更 |
| --- | --- |
| 2026-04-04 | 完成 `11-directory-migration` 阶段 4 收口：先将 `main.py`、`scripts/run_real_eval.py`、`scripts/run_offline_eval.py`、`tests/test_checkpoint_resume.py` 以及 `src/tools/__init__.py` 的残留旧导入切换到 `src.orchestration.*`、`src.contracts.*`、`src.tickets.*`、`src.bootstrap.*`、`src.evaluation.*` 正式路径，然后删除旧兼容壳 `src/graph/`、`src/core_schema.py`、`src/structure_outputs.py`、`src/message_log.py`、`src/ticket_state_machine.py`、`src/tools/service_container.py`、`src/tools/types.py`、`src/telemetry/evaluation.py` 与 `src/prompts.py`；同步回填技术设计文档中的目录与 workflow 路径说明，阶段验收改为“仓库内部运行链路已不再依赖旧路径”。 |
| 2026-04-04 | 继续清理 `S11` 后续残留：删除已不再提供内部价值的薄兼容层与死代码文件 `src/graph.py`、`src/state.py`、`src/agents.py`、`src/customer_memory.py`、`src/observability.py`、`src/llm.py`、`src/checkpointing.py`、`src/llm_runtime.py`、`src/_compat.py`、`src/tools/GmailTools.py`，并继续将 `src/nodes.py` 重构进 `src/graph/nodes*.py`、将 `src/triage.py`/`src/triage_policy.py` 重构进 `src/triage/` 包；同步更新 [README.md](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/README.md)、[customer-support-copilot-technical-design.zh-CN.md](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/docs/customer-support-copilot-technical-design.zh-CN.md) 与本跟踪表中的当前状态说明，并确认仓库内部导入已全部统一到正式目录落点，最终 `pytest -q` 全量回归 `179 passed`。 |
| 2026-04-03 | 完成 `S11.7`：确认 `src/graph.py`、`src/state.py`、`src/agents.py`、`src/customer_memory.py`、`src/observability.py`、`src/llm.py` 已完成从真实逻辑到目录迁移落点的阶段性收口；当时以不承载真实逻辑的薄兼容层通过阶段 G 验收，并同步回填 [README.md](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/README.md)、[customer-support-copilot-technical-design.zh-CN.md](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/docs/customer-support-copilot-technical-design.zh-CN.md)、[demo-cases.zh-CN.md](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/docs/demo-cases.zh-CN.md) 与本跟踪表中的最终目录结构和 enqueue-only + worker 运行语义；这些兼容层已在后续清理中删除。 |
| 2026-04-03 | 完成 `S11.6`：将 worker orchestration 的真实实现从 `src/api/services.py` 迁入 `src/workers/runner.py`，并在 `src/workers/__init__.py` 统一导出 `TicketRunner/RunEnqueueResult/RunExecutionResult`，确保阶段 F 结束时正式 worker runtime 只由 `src/workers/` 承载；同步把 `src/workers/ticket_worker.py`、`tests/test_ticket_worker.py`、`tests/test_checkpoint_resume.py` 的导入与 monkeypatch 路径切换到 `src.workers.runner`，避免旧 API 模块继续承载真实 worker 逻辑。另将 `main.py` 收口为 Gmail poller 角色，保留 `ingest + enqueue`，并将输出语义改为 `Enqueued run...`，明确不再暗示同步执行 graph。阶段测试 `pytest -q tests/test_api_contract.py tests/test_nodes.py tests/test_ticket_state_machine.py` 通过，随后 `pytest -q` 全量回归 `175 passed`，默认下一任务推进到 `S11.7`。 |
| 2026-04-03 | 完成 `S11.5`：将 trace 录制真实实现从旧平铺 `src/observability.py` 迁入 `src/telemetry/trace.py`，将延迟/资源指标计算迁入 `src/telemetry/metrics.py`，并将正式 judge、规则 baseline 与轨迹评估迁入 `src/telemetry/evaluation.py`；同步把 `src/api/services.py`、`src/nodes.py`、`scripts/run_real_eval.py` 与阶段相关测试切换到 `src.telemetry.*` 新路径，确保阶段 E 结束时不再由旧平铺 `src/observability.py` 承载真实逻辑。该旧文件在阶段收口后曾短暂保留为薄兼容层，后续已删除。阶段测试 `pytest -q tests/test_observability.py tests/test_offline_eval.py tests/test_api_contract.py` 通过，随后 `pytest -q` 全量回归 `175 passed`，默认下一任务推进到 `S11.6`。 |
| 2026-04-03 | 完成 `S11.4`：将长期记忆真实实现从旧平铺 `src/customer_memory.py` 迁入 `src/memory/long_term.py`，并新增 `src/memory/short_term.py` 作为短期记忆合同的统一导出落点；同时将本地知识检索与 MCP 适配的真实实现迁入 `src/rag/local_provider.py`、`src/rag/mcp_adapter.py`，并在 `src/rag/provider.py` 收敛 `KnowledgeAnswer/KnowledgeProviderProtocol`。同步把 `src/nodes.py`、`src/api/services.py`、`src/tools/service_container.py` 及相关测试切换到 `src.memory.*` / `src.rag.*` 新路径，确保阶段 D 结束时不再由旧平铺 `src/customer_memory.py` 与旧 `src/tools/knowledge_provider.py` 承载真实逻辑；其中 `src/customer_memory.py` 在阶段收口后曾短暂保留为薄兼容层，后续已删除。阶段测试 `pytest -q tests/test_customer_memory.py tests/test_message_log_service.py tests/test_ticket_messages.py` 通过，随后 `pytest -q` 全量回归 `175 passed`，默认下一任务推进到 `S11.5`。 |
| 2026-04-03 | 完成 `S11.3`：将 `Agents` 主实现按职责拆入 `src/agents/__init__.py`、`src/agents/triage_agent.py`、`src/agents/knowledge_policy_agent.py`、`src/agents/drafting_agent.py`、`src/agents/qa_handoff_agent.py`，并将聊天模型、embedding、judge 与 usage runtime 真实实现迁入 `src/llm/models.py`、`src/llm/judge.py`、`src/llm/runtime.py`；同时把当时的 `src/nodes.py`、`src/triage.py`、`src/observability.py`、`src/tools/knowledge_provider.py` 及阶段相关测试统一切换到 `src.llm.*` 新路径，确保阶段 C 结束时不再由旧平铺 `src/agents.py`、`src/llm.py`、`src/llm_runtime.py` 承载真实逻辑。这些旧文件在阶段收口后曾短暂保留为薄兼容层，后续已删除或迁入正式包目录。阶段测试 `pytest -q tests/test_agents.py tests/test_triage_service.py tests/test_triage_outputs.py tests/test_llm.py` 通过，随后 `pytest -q` 全量回归 `175 passed`，默认下一任务推进到 `S11.4`。 |
| 2026-04-03 | 完成 `S11.2`：将 `GraphState`、checkpoint 构造与 workflow 编译的真实实现正式迁入 `src/graph/state.py`、`src/graph/checkpointing.py`、`src/graph/workflow.py`，并新增 `src/graph/routes.py` 收敛条件路由映射；同时将 `src/api/services.py`、`src/nodes.py` 及阶段相关测试统一切换到 `src.graph.*` 新路径，确保阶段 B 结束时不再依赖旧平铺 `src/state.py`、`src/checkpointing.py`、`src/graph.py` 承载真实逻辑。这些旧文件在阶段收口后曾短暂保留为薄兼容层，后续已删除。阶段测试 `pytest -q tests/test_state.py`、`pytest -q tests/test_nodes.py`、`pytest -q tests/test_ticket_state_machine.py` 通过，随后 `pytest -q` 全量回归 `175 passed`，默认下一任务推进到 `S11.3`。 |
| 2026-04-03 | 完成 `S11.1`：按 `11-directory-migration` 阶段 A 新增 `src/agents/`、`src/graph/`、`src/llm/`、`src/memory/`、`src/rag/`、`src/telemetry/` 目标目录骨架与最小 `__init__.py`/占位模块；当时还通过 `src/_compat.py` 为 `src.agents`、`src.graph.workflow`、`src.llm.models`/`judge` 建立过薄兼容导出，以避免同名包遮蔽旧平铺实现后破坏现有行为。随后已完成内部导入统一，并在后续目录清理中删除 `src/_compat.py` 与相关薄兼容层文件。阶段测试 `pytest -q tests/test_config.py`、`pytest -q tests/test_service_container.py` 通过，随后 `pytest -q` 全量回归 `175 passed`，默认下一任务推进到 `S11.2`。 |
| 2026-04-03 | 完成 `S08.3/S08.4`：在 `src/state.py` 新增统一 `claimed_by/claimed_at/lease_until` 投影构造，收敛 `claimed_at = current_run.started_at`、`lease_until = lease_expires_at` 的固定规则，并在 `src/api/services.py`/`src/api/routes.py`/`src/api/schemas.py` 将该投影正式暴露到 `GET /tickets/{ticket_id}` 的 snapshot；同时在 `src/api/services.py` 将 fresh run 初始状态接入同一投影，避免 API 与 graph 状态双重来源。新增 `src/workers/ticket_worker.py` 正式 CLI 入口，固定支持 `--once`、`--loop`、`--poll-interval-seconds`，默认无参数等价于循环 worker。同步扩展 `tests/test_state.py`、`tests/test_api_contract.py`、`tests/test_ticket_worker.py`、`tests/test_ticket_state_machine.py` 覆盖 claim 投影、CLI 默认行为、worker 接管、双 worker 抢占同一 ticket 仅一方成功、以及失租后写入 `worker_lose_lease` 事件并拒绝继续提交，最终 `pytest -q` 全量 `175 passed`。 |
| 2026-04-03 | 完成 `S08.2`：新增正式 worker runtime `src/workers/ticket_worker.py` 与 `src/workers/__init__.py`，将 Ticket 领取入口收敛为按 `priority > created_at > ticket_id` 固定顺序挑选候选、回收过期租约并优先复用同一 `run_id` 的单一流程；同时在 `src/db/repositories.py` 增补 worker 候选查询，在 `src/ticket_state_machine.py` 收紧 `claim/start/renew/fail/mark_waiting_external/complete_run` 的租约校验为同时校验 `worker_id + run_id`，并允许失租回收的 `leased/running -> queued` 正式迁移、回收时将未结束 run 重新置回 `queued`；在 `src/api/services.py` 将 graph 执行入口收敛为 `execute_claimed_run`，补齐流式执行中的续租与失租拒写防护，并记录 `worker_claim_ticket`、`worker_start_run`、`worker_renew_lease`、`worker_reclaim_expired_lease`、`worker_resume_run`、`worker_lose_lease` trace 事件；同步新增 `tests/test_ticket_worker.py` 并更新状态机/节点相关测试，最终 `pytest -q` 全量 `166 passed`。 |
| 2026-04-03 | 完成 `S08.1`：在 `src/core_schema.py` 为 `RunStatus` 增补 `queued`，在 `src/ticket_state_machine.py` 新增统一 `enqueue_ticket_run` 入口，收紧 `src/api/services.py`/`src/api/routes.py` 中 `POST /tickets/{ticket_id}/run` 为 enqueue-only 语义，不再在 API 请求线程内直接执行 graph；同时将 `src/db/models.py` 的 `ticket_runs.started_at` 调整为 worker 接管前可为空，并新增 migration `20260403_0006_ticket_run_started_at_nullable.py`；同步更新 API/状态机/核心模型测试覆盖排队成功、重复排队冲突与高风险工单仅排队语义，最终 `pytest -q` 全量 `162 passed`。 |
| 2026-03-31 | 新增实施任务与进度跟踪文档。 |
| 2026-03-31 | 将跟踪文档重构为 `spec-first` 版本，主线改为 `P0/S01/S06/S02/S04/S03/S05/X1/X2`。 |
| 2026-03-31 | 补齐 `03-api-contract` 的 memory/trace/metrics 接口任务，拆开 `S03/X1` 依赖环，并细化 `S05` 验收标准。 |
| 2026-04-03 | 新增 `07-short-term-memory-checkpoint`、`08-worker-runtime-contract`、`09-ticket-snapshot-eval-summary`、`10-llm-usage-and-judge`、`11-directory-migration` 五份新 spec，并将其纳入主跟踪表、覆盖矩阵、推荐执行顺序与详细子任务清单；默认下一任务更新为 `S07.1`。 |
| 2026-03-31 | 补齐 `LangSmith` 固定选型、API 通用请求头与标准错误码、以及 `memory_updates` 抽取/校验链路要求。 |
| 2026-03-31 | 明确主跟踪表不作为执行顺序来源，默认推进改为按第 6 节子任务顺序；同时把 `Postgres`、本地 RAG 默认实现和剩余标准错误码补成硬约束。 |
| 2026-03-31 | 将 `attachments`、`multi_intent` 同步规则，以及 `response_quality`、`trajectory_evaluation`、`profile`、`business_flags` 等固定结构补入验收标准。 |
| 2026-04-03 | 完成 `S07.1`：新增统一 checkpoint 构造层 `src/checkpointing.py`，固定 `thread_id=ticket_id`、`checkpoint_ns=run_id`，并将 `Workflow.compile()` 与 ticket run 执行入口接入正式 LangGraph checkpointer；测试覆写统一使用内存 saver。 |
| 2026-04-03 | 完成 `S07.2`：收紧 `src/state.py` 为正式短期记忆合同，将 `raw_email/current_email/pending_emails` 统一为可 JSON 序列化 payload，新增 `clarification_history`、`resume_count`、`checkpoint_metadata` 默认结构，并在澄清节点回填澄清历史；同步补齐状态/节点/checkpoint 测试并修复离线评测汇总对空 `response_quality` 的兼容性。 |
| 2026-04-03 | 完成 `S07.3`：为 `TicketRunner` 增加 fresh/resume 决策与 `current_run_id` 复用入口，新增 `ticket_runs.app_metadata` 持久化字段记录 `checkpoint` 元信息，并在 trace 中补齐 `checkpoint_resume_decision` / `checkpoint_restore` 事件；同时在 `src/checkpointing.py` 增加 namespace 适配层，修正当前 LangGraph 版本下 `checkpoint_ns` 丢失问题，并补齐 checkpoint/resume/API/lease 相关测试。 |
| 2026-04-03 | 完成 `S07.4`：在 `src/api/services.py` 将 resume 决策正式回写到 checkpoint 状态，恢复时递增 `resume_count` 并补齐 `checkpoint_metadata.last_checkpoint_*`；同时修复 `src/nodes.py` 中命中既有 `DraftArtifact` 幂等记录后仍重复调用 Gmail 创建草稿的问题，并在 `tests/test_checkpoint_resume.py` 补齐 crash-resume、跨 run 隔离和恢复后 draft 副作用防重测试。 |
| 2026-04-03 | 完成 `S10.1`：新增统一 LLM 调用封装 `src/llm_runtime.py`，固定 structured output 调用、usage 提取优先级与 `token_source` 枚举；将 `src/agents.py` 和 `scripts/run_offline_eval.py` 的真实业务 LLM 调用切到 runtime，收紧 `src/nodes.py`/`src/db/models.py`/`src/observability.py` 的 `llm_call` metadata 合同，补齐 `provider` 与 `token_source` 字段，并停止将确定性角色步骤误记为 `llm_call`；同步新增 usage 提取、trace metadata 和 API/节点兼容测试，最终 `pytest -q` 全量 `150 passed`。 |
| 2026-04-03 | 完成 `S10.2`：扩展 `src/observability.py` 的资源指标聚合与 `src/api/services.py` 的 `/metrics/summary` 汇总口径，新增 `actual_token_call_count`、`estimated_token_call_count`、`unavailable_token_call_count` 与 `token_coverage_ratio`，并补齐 API/观测测试断言；最终 `pytest -q` 全量 `151 passed`。 |
| 2026-04-03 | 完成 `S10.3`：新增 `LLM_JUDGE_MODEL/LLM_JUDGE_TIMEOUT_SECONDS` 配置与 `src/llm.py` judge 模型构造入口，将 `src/observability.py` 中的 `ResponseQualityJudge` 切换为正式 `LLM-as-a-judge` 结构化输出实现，并通过 `ServiceContainer` 注入到 `src/api/services.py`；在线 judge 失败时不阻塞主流程，但会写入 `response_quality_judge` 失败事件、`response_quality_failed` 决策事件及 `run.app_metadata.response_quality_status`，同时为 API/离线评测引入假 judge 夹具，最终 `pytest -q` 全量 `153 passed`。 |
| 2026-04-03 | 完成 `S10.4`：将 `scripts/run_real_eval.py` 中缺失 `response_quality` 时的伪造补位移除，改为显式记录 `response_quality_status` 并把旧规则评测收口为 `RuleBasedResponseQualityBaseline` 对照字段；同时扩展 `scripts/run_offline_eval.py` 报表区分 judge 成功/失败，补齐 usage `total_tokens` 一致性、judge/token 覆盖率、离线/真实评测报表回归测试，并修正 `src/api/services.py` 中 quality judge 事件未计入最终 `resource_metrics` 的汇总顺序问题。 |
| 2026-04-03 | 完成 `S09.1/S09.2`：在 `src/api/schemas.py` 为 `TicketRunSummary` 新增固定结构的 `evaluation_summary_ref`，在 `src/api/services.py` 固定 snapshot 最近 run 选择规则为 `created_at desc, run_id desc` 并基于 `TicketRun` 构造 `complete/partial/not_available` 三态摘要引用，在 `src/api/routes.py` 保持 `GET /tickets/{id}` 路径不变并继续只返回轻量 snapshot；同步扩展 `tests/test_api_contract.py` 覆盖无 run、partial、not_available、最近 run 选择和禁止返回 trace 大对象，最终 `pytest -q` 全量 `160 passed`。 |
| 2026-03-31 | 完成 `P0.1`：新增统一配置层 `src/config.py`，集中管理 Gmail、LLM、知识库、Postgres、LangSmith、API 配置，并将 `main.py`、`deploy_api.py`、`create_index.py` 以及当时的 `src/tools/GmailTools.py`、`src/agents.py` 切换为通过配置模块读取；其中后两者已在后续目录迁移与清理中删除。 |
| 2026-03-31 | 完成 `P0.2/P0.3/P0.4`：新增 `gmail_client`、`knowledge_provider`、`policy_provider`、`ticket_store` provider 骨架与服务容器；将 `Nodes` 改为通过 provider 访问 Gmail/知识/策略/存储；新增 `tests/`、fixture、样本与最小 `pytest` 测试；引入 `SQLAlchemy + Alembic + psycopg` 的 Postgres 基础设施、首个 bootstrap migration 和 `scripts/init_db.py`。 |
| 2026-04-01 | 将 LLM 接入统一切换为 OpenAI-compatible 协议：配置改为 `LLM_API_KEY/LLM_BASE_URL/LLM_CHAT_MODEL/LLM_EMBEDDING_MODEL`，生成与嵌入都支持自定义模型；同步更新 `.env.example`、`README.md`、需求文档和技术设计文档，并移除对 `GROQ_API_KEY`、`GOOGLE_API_KEY` 的实现依赖。 |
| 2026-04-01 | 完成 `S01.1`：新增 `src/core_schema.py`，集中定义 V1 核心枚举、`t_/run_/trace_/draft_/review_/me_` 前缀 ID 生成与校验、时区感知时间工具、版本校验与乐观锁冲突异常；同时补充 `multi_intent/tags/secondary_routes` 同步校验测试，并将默认下一任务推进到 `S01.2`。 |
| 2026-04-01 | 完成 `S01.2`：在 `src/db/models.py` 新增 `Ticket`、`TicketRun`、`DraftArtifact`、`HumanReview`、`TraceEvent` 五个核心实体及其唯一约束、必填字段、固定 JSON 结构和最小事件元数据校验；新增 Alembic migration `20260401_0002_core_schema_entities.py`，并补充 `tests/test_core_models.py` 覆盖唯一约束、路由同步规则和端到端持久化。 |
| 2026-04-01 | 完成 `S01.3`：在 `src/core_schema.py` 新增邮箱规范化、alias 归并和 `customer_id` 推导工具；在 `src/db/models.py` 新增 `CustomerMemoryProfile`、`CustomerMemoryEvent` 及固定键/幂等约束；新增 migration `20260401_0003_customer_memory_entities.py`，并通过 `tests/test_customer_memory.py` 验证长期记忆结构、alias 归并和空 `customer_id` 场景。 |
| 2026-04-01 | 完成 `S01.4`：新增 `src/db/repositories.py`，为 `Ticket`、`TicketRun`、`DraftArtifact`、`HumanReview`、`TraceEvent`、`CustomerMemoryProfile`、`CustomerMemoryEvent` 提供最小可复用 repository 接口与 SQLAlchemy 实现；同时扩展 `TicketStoreProtocol` 和 `SqlAlchemyTicketStore` 暴露 repository bundle，并通过 `tests/test_repositories.py` 验证上层可以不直接写 SQL。 |
| 2026-04-01 | 完成 `S06.1`：在 `src/core_schema.py` 新增消息方向与消息类型枚举以及 `tm_` 前缀；在 `src/db/models.py` 新增 `TicketMessage` 持久化模型、唯一约束和字段校验，并把 `ticket_messages` repository 接入 `RepositoryBundle`；新增 migration `20260401_0004_ticket_message_schema.py` 与 `tests/test_ticket_messages.py`，验证消息模型可独立持久化。 |
| 2026-04-01 | 完成 `S06.2/S06.3`：新增 `src/message_log.py`，实现入站客户邮件与草稿类消息的幂等入库、`attachments` 元数据持久化、关闭线程 reopen 时创建新 Ticket 并递增 `reopen_count`，以及按 `message_timestamp asc` 读取 Drafting/QA/Memory 所需消息上下文；通过 `tests/test_message_log_service.py` 覆盖命中激活 Ticket、reopen、新老消息读取与草稿消息日志。 |
| 2026-04-01 | 完成 `S02.1`：新增 `src/ticket_state_machine.py`，落地 `business_status` 迁移图、非法迁移异常、版本递增、`closed_at` 收口和 `failed -> triaged` 清错规则，并补充 `TicketStateService` 作为后续 API/Graph 的统一迁移入口；通过 `tests/test_ticket_state_machine.py` 覆盖允许迁移、拒绝非法迁移、乐观锁版本校验与服务层按 `ticket_id` 迁移。 |
| 2026-04-01 | 完成 `S02.2/S02.3/S02.4`：扩展 `src/ticket_state_machine.py`，补齐 `processing_status` 迁移图、领取/续租/启动/租约回收、失败收口与自动重试边界、`failed -> triaged` 恢复、Gmail draft 幂等键复用、以及 `approve/edit_and_approve/reject_for_rewrite/escalate/close` 的前置状态校验与人工动作副作用；同时把路由同步规则收进状态服务，避免只在 ORM flush 时生效。通过 `tests/test_ticket_state_machine.py` 覆盖 lease 冲突、过期回收、失败恢复、自动重试上限、draft 幂等、人工审核动作和编辑后批准新增草稿，最终 `pytest -q` 全量 `64 passed`。 |
| 2026-04-01 | 完成 `S04.1`：重写 `src/structure_outputs.py`，新增 `TriageOutput` 结构化输出模型并复用 `src/core_schema.py` 中的 `primary_route/secondary_routes/tags/response_strategy/priority` 枚举；补齐 `secondary_routes <= 2`、`tags <= 5`、`intent_confidence` 区间、`multi_intent` 与 `multi_intent` 标签同步、`needs_clarification/needs_escalation` 标签同步、低置信强制升级、以及 `needs_clarification` 仅适用于 `technical_issue` 等校验；新增 `tests/test_triage_outputs.py` 覆盖 spec 示例、多意图去重与关键非法样例，并通过 `pytest -q` 全量 `71 passed`。 |
| 2026-04-02 | 完成 `S04.2/S04.3/S04.4`：新增当时的 `src/triage.py`，实现基于 spec 的 `TriageDecisionService`、冲突优先级、标签生成、`needs_clarification`/`needs_escalation`/`priority` 规则与解释层；在 `src/prompts.py`/`src/agents.py` 增加 `Triage Agent` prompt、`triage_email` 结构化输出链和本地规则兜底入口；在当时的 `src/nodes.py`/`src/state.py` 增加最小 triage 挂点与旧分类兼容映射，并扩展 `src/tools/policy_provider.py` 支持新路由枚举；新增 `tests/samples/triage_cases.json`、`tests/test_triage_service.py`、`tests/test_triage_outputs.py` 和 `tests/test_nodes.py` 覆盖边界样例、冲突优先级与挂点兼容性，最终 `pytest -q` 全量 `86 passed`。该 triage 实现后续已迁入 `src/triage/` 包。 |
| 2026-04-02 | 推进 `S03`：新增 `src/api/` 业务 API 层，包含 `FastAPI` 应用工厂、请求头依赖、统一错误响应、DTO 和路由；将 `deploy_api.py` 从 LangServe runnable 切换为业务 API 入口；新增 `TicketApiService`/`TicketRunner`，复用现有 `MessageLogService`、`TicketStateService` 和 repositories，落地 `ingest-email`、ticket 快照、`run`、人工动作、memory、trace 和 metrics 汇总接口，并使用 `app_metadata` 记录轻量幂等键；新增 `tests/test_api_contract.py` 覆盖业务接口主路径，最终 `pytest -q` 全量 `93 passed`。由于 `X1.3/X1.4/S05` 仍未完成，`S03` 顶层及 `S03.3-S03.7` 状态保持为 `进行中`。 |
| 2026-04-02 | 完成 `X1.1`：重写 `src/state.py`，将 `GraphState` 从邮件批处理字段升级为按基础工单、输入、路由、知识、记忆、草稿审核、观测、并发恢复分组的 ticket run 执行态，并提供 `build_initial_graph_state`、`build_ticket_run_state` 与 active email 兼容辅助函数；同步调整 `main.py` 和 `src/nodes.py`，使现有 triage/RAG/写作节点优先读写新状态键，同时保留旧教程图可运行；新增 `tests/test_state.py` 并扩展 `tests/test_nodes.py` 覆盖状态构造、active email 兼容和草稿版本/重写计数同步，最终 `pytest -q` 全量 `98 passed`。 |
| 2026-04-02 | 完成 `X1.2/X1.3`：在 `src/structure_outputs.py` 增加 `KnowledgePolicyOutput`、`DraftingOutput`、`QaHandoffOutput`，并在 `src/agents.py` 将能力边界明确收敛为 `Triage`、`Knowledge & Policy`、`Drafting`、`QA & Handoff` 四个核心角色，其中后三者先以确定性实现落地，避免新的 ticket 执行流依赖远端模型；重写 `src/graph.py` 为 ticket execution workflow，并在 `src/nodes.py` 新增 `load_ticket_context/load_memory/triage/knowledge_lookup/policy_check/customer_history_lookup/draft_reply/qa_review/clarify_request/create_gmail_draft/escalate_to_human/close_ticket` 节点与条件边；将 `src/api/services.py` 中 `TicketRunner` 改为创建 run、领取租约并调用新图执行，`src/api/routes.py` 改为向 `TicketApiService` 注入完整 `ServiceContainer`，`main.py` 切换为 `ingest -> run` 的批处理入口；同时扩展 `tests/test_agents.py`、`tests/test_nodes.py`、`tests/test_api_contract.py` 覆盖四角色输出、新图知识/澄清/人工升级分支和 API `run` 主路径，最终 `pytest -q` 全量 `104 passed`。 |
| 2026-04-02 | 完成 `S03.3/X1.4`：确认 `POST /tickets/{ticket_id}/run` 已触发真实 ticket workflow 后，将跟踪状态回填为 `S03.3 已完成`；新增 `src/customer_memory.py`，实现 `collect_case_context -> extract_memory_updates -> validate_memory_updates -> apply_memory_updates`，并在 `src/graph.py`/`src/nodes.py` 将其接入 `create_gmail_draft`、`clarify_request`、`escalate_to_human`、`close_ticket` 收尾路径，同时在 `src/api/services.py` 为 `escalate` 与 `close` 动作补充长期记忆回写；同步扩展 `tests/test_nodes.py`、`tests/test_api_contract.py` 覆盖 `memory_updates` 与 memory 演进行为，最终 `pytest -q` 全量 `104 passed`。 |
| 2026-04-02 | 完成 `S03.4/S03.5`：收紧人工动作 API 契约，要求 `approve/edit-and-approve/rewrite/escalate/close` 显式提供 `X-Actor-Id`，为人工动作补齐 `Idempotency-Key` 去重与标准 `duplicate_request` 返回，并让 `close` 也以真实 actor 记录 `human_action` run；同时在 DTO 层增加空字符串/空列表校验，避免宽松请求体绕过契约。补强 `GET /customers/{customer_id}/memory` 的 API 断言，确保固定返回 `profile`、`risk_tags`、`business_flags`、`historical_case_refs`、`version` 结构。同步修复 `validation_error` 的 JSON 序列化兜底，并扩展 `tests/test_api_contract.py` 覆盖人工动作主路径、缺失 actor、重复幂等键和 memory 查询；最终 `pytest -q tests/test_api_contract.py tests/test_ticket_state_machine.py tests/test_customer_memory.py` 全量 `39 passed`。 |
| 2026-04-02 | 完成 `S05`：新增 `src/observability.py` 统一 trace/metrics/eval 层，接入可选 `LangSmith` `RunTree` 上报，并将 `src/nodes.py`/`src/graph.py`/`src/api/services.py` 串到同一条 trace 生命周期；为 ticket workflow 补齐 `13` 个必采集节点、`4` 个必采集决策、`node/llm/tool` 延迟、token 统计、固定 schema 的响应质量评估和规则式轨迹评估，使 `/tickets/{id}/trace` 与 `/metrics/summary` 读取的都是实际 run 数据；新增 `tests/samples/eval/customer_support_eval.jsonl`、`scripts/run_offline_eval.py`、`tests/test_observability.py`，并将 `.env.example`/`requirements.txt` 补齐 `LangSmith` 配置与依赖，最终 `pytest -q` 全量 `111 passed`。 |
| 2026-04-02 | 完成 `S03.6/S03.7`：收紧 `GET /metrics/summary` 查询契约，新增时间窗口先后校验与 `route` 固定枚举校验，避免非法过滤条件绕过 API 层；同时扩展 `tests/test_api_contract.py` 覆盖最近 run 与显式 `run_id` 的 trace 查询、跨工单 `run_id` 拒绝、`route` 过滤生效、非法 `route` 与反向时间窗口返回 `validation_error`。同步将主跟踪表中的 `S03`、`X1` 状态回填为 `已完成`，并确认 `pytest -q tests/test_api_contract.py tests/test_observability.py` 全量 `17 passed`。 |
| 2026-04-02 | 完成 `X2`：重写 `README.md`，将仓库定位改为 `Customer Support Copilot`，补齐当前架构、运行方式、业务 API、V1/V2 边界和演示入口；新增 `docs/system-workflow.mmd` 作为可维护的系统流程图文本源，新增 `docs/demo-cases.zh-CN.md` 整理成功主路径 demo 与基于离线评测报告的失败案例；同步更新 `.env.example` 和 `src/config.py` 中的默认 API 标题/描述，并通过 `pytest -q tests/test_config.py tests/test_api_contract.py` 验证 `19 passed`。 |
| 2026-04-02 | 清理 `LangSmith` 配置兼容层：移除 `.env.example` 中的 `LANGCHAIN_TRACING_V2/LANGCHAIN_API_KEY/LANGCHAIN_ENDPOINT`，并在 `src/config.py` 中删除对 `LANGCHAIN_*` 的 fallback，只保留 `LANGSMITH_*` 作为正式配置入口；同步更新 `README.md` 配置说明，并在 `tests/test_config.py` 新增断言确保旧 `LANGCHAIN_*` 环境变量不再影响配置结果，最终 `pytest -q tests/test_config.py tests/test_api_contract.py` 全量 `20 passed`。 |
