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

当前代码仍是教程型原型，和目标 `spec` 的差距主要在这几处：

1. `src/graph.py` 仍是单批次邮件流，不是工单执行流。
2. `src/state.py` 仍是邮件处理态，不是 ticket run 状态。
3. `src/nodes.py` 和 `src/agents.py` 仍围绕分类、RAG、写草稿，没有对齐状态机、人工动作、trace。
4. `src/tools/GmailTools.py` 直接耦合 Gmail SDK，没有 provider 边界。
5. `deploy_api.py` 仍暴露 LangServe runnable，不符合业务 API 契约。

因此，后续实施必须按照 `spec -> 子任务 -> 代码落地 -> 回填进度表` 的方式推进。

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
| S05 | Spec | `docs/specs/05-trace-and-eval.zh-CN.md` | 落地 trace、指标和离线评测 | 未开始 | S03, X1 | trace、metrics、eval |
| X1 | 集成 | 跨 spec | 完成 state、agent、graph、记忆、审核集成 | 未开始 | S01, S02, S04 | `src/state.py`, `src/agents.py`, `src/nodes.py`, `src/graph.py` |
| X2 | 交付 | 跨 spec | 完成 README、流程图、Demo | 未开始 | S03, S05, X1 | `README.md`, `docs/`, 演示材料 |

说明：

1. 主跟踪表用于表达 `spec` 覆盖关系和顶层状态，不用于决定精确执行顺序。
2. 实际执行顺序一律以“第 6 节 推荐执行顺序”里的子任务顺序为准。

---

## 5. Spec 覆盖矩阵

| 文档 | 覆盖任务 | 当前覆盖状态 | 说明 |
| --- | --- | --- | --- |
| `01-core-schema` | `S01`, `S06`, `S02`, `S03`, `X1` | `S01` 已完成，后续依赖可继续推进 | 这是所有后续实现的基础契约 |
| `02-ticket-state-machine` | `S02`, `S03`, `X1` | 已建任务，未开始实施 | 状态迁移、lease、幂等、重试都在这里落地 |
| `03-api-contract` | `S03`, `S05`, `X1` | `S03` 已完成，`S05/X1` 可继续推进 | 覆盖 ticket、memory、trace、metrics 接口，部分接口依赖 graph 和 trace 成型 |
| `04-routing-decision-table` | `S04`, `X1` | `S04` 已完成，`X1` 可继续推进 | 已产出 triage 结构化输出、规则决策服务、prompt 与样例测试 |
| `05-trace-and-eval` | `S05`, `X2` | 已建任务，未开始实施 | trace 依赖 API 和 graph 成型后接入 |
| `06-message-log-schema` | `S06`, `S02`, `S03` | `S06` 已完成，消息持久化基础已具备 | 消息持久化、draft 幂等、reopen 判定都依赖它 |

结论：

1. 进度表现在是以 `spec` 为主组织的。
2. 每份 `spec` 都有明确对应任务。
3. 非 `spec` 工作只保留在 `P0` 和 `X`，避免纯工程项淹没 `spec` 主线。

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

说明：

1. `S03.1/S03.2` 先把 API 骨架、入库接口和工单查询接口立起来。
2. `X1.3` 先把真实 ticket 执行流做出来，再由 `S03.3` 暴露 `run`。
3. `X1.4` 先把记忆、审核和升级分支接入，再由 `S03.4` 暴露人工动作接口。
4. `S05` 先产出真实 trace 与 metrics 数据，再由 `S03.6/S03.7` 暴露 trace 和汇总查询接口。

并行原则仍然是：

1. 主链路串行。
2. `P0.3` 测试骨架可以和 `P0.1/P0.2` 局部并行。
3. 文档类更新只能在 `X2` 阶段作为主任务，不提前分散注意力。

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
| S05.1 | `1`, `2`, `3`, `4`, `12` | 接入 `LangSmith`，并实现统一 trace 包装层、`trace_id`、事件类型、最小字段和事件写入 | 未开始 | S03.2, X1.3 | trace 写入器与 `LangSmith` 集成 | V1 追踪固定使用 `LangSmith`，每次 run 都有唯一 `trace_id`，并串联 `TicketRun/TraceEvent/DraftArtifact/评估结果` |
| S05.2 | `3`, `4`, `5`, `6`, `7`, `8`, `12` | 为必采集节点、决策、延迟、资源、质量打点，并补 token 统计 | 未开始 | S05.1 | 指标与决策事件采集 | `13` 个必采集节点、`4` 个必采集决策、`end_to_end_ms`、`node/llm/tool latencies`、token 与调用数全部可观测 |
| S05.3 | `9`, `10`, `11`, `12` | 建立 `jsonl` 离线评测样本、规则式轨迹评估、Judge 输出 schema 校验和报表输出 | 未开始 | S05.2, P0.3 | eval 样本与脚本 | 样本至少 `24` 条、覆盖 `8` 类场景，输出字段和汇总报表字段与 spec 一致 |

### X1. Graph/Agent 集成重构

对应文档：

1. `docs/customer-support-copilot-technical-design.zh-CN.md`
2. `S01`, `S02`, `S04`, `S03` 对应 `spec`

目标：

1. 把原型流重构成 ticket 执行流。
2. 把多个 `spec` 组合成真实可运行系统。

| 子任务 | 内容 | 状态 | 前置项 | 主要产出 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| X1.1 | 将 `GraphState` 从邮件处理态改为 ticket run 执行态 | 未开始 | S01.4, S02.1 | 新 state 模型 | state 字段与业务状态一致 |
| X1.2 | 将现有 agent 重构为 `Triage`、`Knowledge & Policy`、`Drafting`、`QA & Handoff` 四个核心角色 | 未开始 | S04.3, X1.1 | 新 agent 结构 | agent 分工与决策表对齐 |
| X1.3 | 将 graph 从 `load inbox -> categorize -> rag -> writer -> proofreader` 改为 ticket 执行流 | 未开始 | X1.1, X1.2, S03.2 | 新 graph | 明确区分“邮件发现/入库”和“ticket 执行” |
| X1.4 | 接入短期记忆、长期记忆、人工审核与升级分支，并实现 `collect_case_context -> extract_memory_updates -> validate_memory_updates` | 未开始 | X1.3, S01.3, S02.4 | 记忆和审核集成 | 等待客户补充、审核、升级路径闭环，且工单收尾时能生成并校验结构化 `memory_updates` |

### X2. 交付与展示

目标：

1. 让仓库能够清晰表达“现在这个系统是什么”。
2. 把文档、流程图和 demo 统一成可展示版本。

| 子任务 | 内容 | 状态 | 前置项 | 主要产出 | 验收标准 |
| --- | --- | --- | --- | --- | --- |
| X2.1 | 重写 README，更新定位、架构、启动方式、V1/V2 边界 | 未开始 | S03.3, S05.2, X1.3 | 新 README | README 不再停留在原教程项目 |
| X2.2 | 输出新的系统流程图 | 未开始 | X2.1 | 流程图 | 演示路径清晰可说明 |
| X2.3 | 准备成功样例、失败样例、可重复 demo case | 未开始 | X2.1, X2.2, S05.3 | demo 材料 | 有至少一条失败案例可解释系统边界 |

---

## 8. 下一步默认执行规则

后续如果用户只说“继续推进”，默认规则如下：

1. 不按主跟踪表的显示顺序选任务，主跟踪表只用于看覆盖和总状态。
2. 严格按“第 6 节 推荐执行顺序”从前到后寻找第一个前置项已满足、且状态不是 `已完成` 的子任务。
3. 开工前把该子任务状态改为 `进行中`。
4. 完成后把状态改为 `已完成`，并回填“最近变更记录”。

按当前进度，默认下一任务是：

1. `X1.1 将 GraphState 从邮件处理态改为 ticket run 执行态`

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
| 2026-03-31 | 新增实施任务与进度跟踪文档。 |
| 2026-03-31 | 将跟踪文档重构为 `spec-first` 版本，主线改为 `P0/S01/S06/S02/S04/S03/S05/X1/X2`。 |
| 2026-03-31 | 补齐 `03-api-contract` 的 memory/trace/metrics 接口任务，拆开 `S03/X1` 依赖环，并细化 `S05` 验收标准。 |
| 2026-03-31 | 补齐 `LangSmith` 固定选型、API 通用请求头与标准错误码、以及 `memory_updates` 抽取/校验链路要求。 |
| 2026-03-31 | 明确主跟踪表不作为执行顺序来源，默认推进改为按第 6 节子任务顺序；同时把 `Postgres`、本地 RAG 默认实现和剩余标准错误码补成硬约束。 |
| 2026-03-31 | 将 `attachments`、`multi_intent` 同步规则，以及 `response_quality`、`trajectory_evaluation`、`profile`、`business_flags` 等固定结构补入验收标准。 |
| 2026-03-31 | 完成 `P0.1`：新增统一配置层 `src/config.py`，集中管理 Gmail、LLM、知识库、Postgres、LangSmith、API 配置，并将 `main.py`、`deploy_api.py`、`create_index.py`、`src/tools/GmailTools.py`、`src/agents.py` 切换为通过配置模块读取。 |
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
| 2026-04-02 | 完成 `S04.2/S04.3/S04.4`：新增 `src/triage.py`，实现基于 spec 的 `TriageDecisionService`、冲突优先级、标签生成、`needs_clarification`/`needs_escalation`/`priority` 规则与解释层；在 `src/prompts.py`/`src/agents.py` 增加 `Triage Agent` prompt、`triage_email` 结构化输出链和本地规则兜底入口；在 `src/nodes.py`/`src/state.py` 增加最小 triage 挂点与旧分类兼容映射，并扩展 `src/tools/policy_provider.py` 支持新路由枚举；新增 `tests/samples/triage_cases.json`、`tests/test_triage_service.py`、`tests/test_triage_outputs.py` 和 `tests/test_nodes.py` 覆盖边界样例、冲突优先级与挂点兼容性，最终 `pytest -q` 全量 `86 passed`。 |
| 2026-04-02 | 完成 `S03.1-S03.7`：新增 `src/api/` 业务 API 层，包含 `FastAPI` 应用工厂、请求头依赖、统一错误响应、DTO 和路由；将 `deploy_api.py` 从 LangServe runnable 切换为业务 API 入口；新增 `TicketApiService`/`TicketRunner`，复用现有 `MessageLogService`、`TicketStateService` 和 repositories，落地 `ingest-email`、ticket 快照、`run`、人工动作、memory、trace 和 metrics 汇总接口，并使用 `app_metadata` 记录轻量幂等键；新增 `tests/test_api_contract.py` 覆盖业务接口主路径，最终 `pytest -q` 全量 `93 passed`。 |
