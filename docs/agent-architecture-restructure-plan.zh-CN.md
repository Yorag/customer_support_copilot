# Agent 架构目录重构技术方案

## 1. 文档目标

本文档用于把当前仓库从“功能逐步堆叠后的可运行结构”整理为“以 Agent 架构为核心、目录语义清晰、后续演进成本更低”的目标结构。

本文档关注四件事：

1. 明确当前结构与目标结构的差异。
2. 给出逐目录、逐文件、逐类、逐变量的改动清单。
3. 固化迁移期间的兼容策略、导入策略和验证策略。
4. 解释 `trace / metrics / evaluation` 在 Agent 系统中的定位与拆分原则。

本文档不直接修改业务逻辑，不要求一次性完成所有迁移。推荐采用“兼容导出 + 分阶段迁移 + 最后清理旧路径”的方式推进。

---

## 2. 重构目标

### 2.1 核心表达目标

重构后的目录需要直接表达下面这句话：

> 本项目是一个以 Agent 为核心的客服工单执行系统；`agents` 放 Agent 本体，`orchestration` 放编排，`memory / tools / rag / llm` 放共享能力，`telemetry` 放运行时观测，`evaluation` 放结果评估。

### 2.2 目录设计原则

1. `agents/` 只放具体 Agent，不放所有 Agent 依赖。
2. 编排层与 Agent 本体分离，避免把 workflow 和 node 逻辑误认为单个 Agent 私有实现。
3. 共享能力平铺：`memory`、`tools`、`rag`、`llm`、`db`、`api`、`telemetry`、`evaluation`。
4. 公共契约集中：枚举、结构化输出、协议定义统一放入 `contracts/`。
5. 引导与组装独立：容器、默认 provider 组装放入 `bootstrap/`。
6. 入口脚本与业务模块分离：脚本进入 `scripts/`，`src/` 仅保留可导入模块。
7. 迁移优先级服从“认知收益 / 风险比”，先做高收益低风险调整。

---

## 3. 目标目录结构

```text
langgraph-email-automation/
├─ scripts/
│  ├─ run_poller.py
│  ├─ serve_api.py
│  └─ build_index.py
├─ src/
│  ├─ agents/
│  │  ├─ triage_agent.py
│  │  ├─ knowledge_policy_agent.py
│  │  ├─ drafting_agent.py
│  │  ├─ qa_handoff_agent.py
│  │  └─ __init__.py
│  ├─ orchestration/
│  │  ├─ workflow.py
│  │  ├─ routes.py
│  │  ├─ state.py
│  │  ├─ checkpointing.py
│  │  ├─ nodes_base.py
│  │  ├─ nodes_ticket.py
│  │  └─ __init__.py
│  ├─ triage/
│  │  ├─ models.py
│  │  ├─ rules.py
│  │  ├─ policy.py
│  │  ├─ signals.py
│  │  ├─ service.py
│  │  └─ __init__.py
│  ├─ tickets/
│  │  ├─ state_machine.py
│  │  ├─ message_log.py
│  │  └─ __init__.py
│  ├─ memory/
│  │  ├─ long_term.py
│  │  └─ __init__.py
│  ├─ tools/
│  │  ├─ gmail_client.py
│  │  ├─ null_gmail_client.py
│  │  ├─ policy_provider.py
│  │  └─ __init__.py
│  ├─ rag/
│  │  ├─ provider.py
│  │  ├─ local_provider.py
│  │  └─ __init__.py
│  ├─ llm/
│  │  ├─ runtime.py
│  │  ├─ models.py
│  │  ├─ judge.py
│  │  └─ __init__.py
│  ├─ prompts/
│  │  ├─ triage.py
│  │  ├─ drafting.py
│  │  ├─ knowledge_policy.py
│  │  ├─ qa_handoff.py
│  │  └─ __init__.py
│  ├─ contracts/
│  │  ├─ core.py
│  │  ├─ outputs.py
│  │  ├─ protocols.py
│  │  └─ __init__.py
│  ├─ telemetry/
│  │  ├─ trace.py
│  │  ├─ metrics.py
│  │  ├─ exporters/
│  │  │  ├─ langsmith.py
│  │  │  └─ __init__.py
│  │  └─ __init__.py
│  ├─ evaluation/
│  │  ├─ response_quality.py
│  │  ├─ trajectory.py
│  │  └─ __init__.py
│  ├─ db/
│  │  ├─ base.py
│  │  ├─ models.py
│  │  ├─ repositories.py
│  │  ├─ session.py
│  │  ├─ ticket_store.py
│  │  └─ __init__.py
│  ├─ api/
│  │  ├─ app.py
│  │  ├─ routes.py
│  │  ├─ schemas.py
│  │  ├─ dependencies.py
│  │  ├─ errors.py
│  │  ├─ service_errors.py
│  │  ├─ services/
│  │  │  ├─ base.py
│  │  │  ├─ commands.py
│  │  │  ├─ queries.py
│  │  │  ├─ manual_actions.py
│  │  │  ├─ common.py
│  │  │  └─ __init__.py
│  │  └─ __init__.py
│  ├─ bootstrap/
│  │  ├─ container.py
│  │  └─ __init__.py
│  └─ config.py
└─ tests/
```

---

## 4. 模块定位说明

### 4.1 `agents/`

职责：仅存放 Agent 本体实现。

包含：

1. `triage_agent.py`：负责 triage LLM/规则合并与统一调用面。
2. `knowledge_policy_agent.py`：负责知识与策略约束聚合。
3. `drafting_agent.py`：负责草稿生成。
4. `qa_handoff_agent.py`：负责 QA 决策与升级判断。

不应再放入：

1. graph workflow。
2. trace recorder。
3. Gmail / RAG / store provider。
4. 通用枚举、协议、输出 schema。

### 4.2 `orchestration/`

职责：负责 Agent 之间的运行顺序、状态流转、路由、checkpoint 和节点装配。

包含：

1. workflow 构造。
2. route map。
3. graph state 定义。
4. node 执行逻辑。
5. checkpoint 构造与恢复。

### 4.3 `triage/`

职责：负责 triage 领域规则，而不是 triage Agent 本体。

包含：

1. triage 上下文模型。
2. triage 规则集。
3. route / priority / response strategy 策略表。
4. triage service。

原则：

1. `triage/` 负责“如何判定”。
2. `agents/triage_agent.py` 负责“如何调用 triage 能力并对接 runtime”。

### 4.4 `tickets/`

职责：负责工单领域对象与工单过程服务。

包含：

1. ticket 状态机。
2. message log。

### 4.5 `contracts/`

职责：统一维护跨模块共享的数据契约。

包含：

1. `core.py`：核心枚举、标识符、通用领域值对象、基础函数。
2. `outputs.py`：结构化输出模型。
3. `protocols.py`：Gmail、TicketStore、PolicyProvider 等协议接口。

### 4.6 `telemetry/`

职责：运行时观测，不做业务判分。

包含：

1. trace event 记录。
2. LangSmith exporter。
3. latency / resource metrics 聚合。

### 4.7 `evaluation/`

职责：结果评估，不做运行时事件采集。

包含：

1. 回复质量评估。
2. 轨迹合理性评估。

原则：

1. `telemetry` 解决“发生了什么”。
2. `evaluation` 解决“结果好不好”。

---

## 5. 目录级改动清单

## 5.1 顶层入口脚本

### 现状

1. `main.py`
2. `deploy_api.py`
3. `create_index.py`

### 目标

1. `scripts/run_poller.py`
2. `scripts/serve_api.py`
3. `scripts/build_index.py`

### 改动要求

1. 保留原脚本一段过渡期。
2. 原文件改成薄包装，只做导入转发。
3. 所有 README、docs、测试中的命令引用逐步切换到 `scripts/`。

### 兼容策略

原 `main.py` 保留：

```python
from scripts.run_poller import main

if __name__ == "__main__":
    main()
```

`deploy_api.py`、`create_index.py` 同理。

## 5.2 `graph` 重命名为 `orchestration`

### 现状

目录：`src/graph/`

### 目标

目录：`src/orchestration/`

### 原因

`graph` 强调技术实现；`orchestration` 更能表达“Agent 编排层”。

### 改动文件

1. `src/graph/workflow.py` -> `src/orchestration/workflow.py`
2. `src/graph/routes.py` -> `src/orchestration/routes.py`
3. `src/graph/state.py` -> `src/orchestration/state.py`
4. `src/graph/checkpointing.py` -> `src/orchestration/checkpointing.py`
5. `src/graph/nodes_base.py` -> `src/orchestration/nodes_base.py`
6. `src/graph/nodes_ticket.py` -> `src/orchestration/nodes_ticket.py`
7. `src/graph/__init__.py` -> `src/orchestration/__init__.py`

### 兼容策略

过渡期保留 `src/graph/__init__.py` 和若干旧模块壳文件，内部 re-export 新路径。

示例：

```python
from src.orchestration.workflow import Workflow

__all__ = ["Workflow"]
```

## 5.3 `ticket_state_machine.py` 和 `message_log.py` 归档到 `tickets/`

### 现状

1. `src/ticket_state_machine.py`
2. `src/message_log.py`

### 目标

1. `src/tickets/state_machine.py`
2. `src/tickets/message_log.py`

### 原因

二者都是 ticket 领域服务，不应平铺在 `src/` 根目录。

### 兼容策略

原路径保留壳文件：

1. `src/ticket_state_machine.py` re-export `src.tickets.state_machine`
2. `src/message_log.py` re-export `src.tickets.message_log`

## 5.4 `core_schema.py`、`structure_outputs.py`、`tools/types.py` 统一进入 `contracts/`

### 现状

1. `src/core_schema.py`
2. `src/structure_outputs.py`
3. `src/tools/types.py`

### 目标

1. `src/contracts/core.py`
2. `src/contracts/outputs.py`
3. `src/contracts/protocols.py`

### 原因

这三者都是跨模块共享契约，不属于某个具体运行时目录。

## 5.5 `service_container` 迁移到 `bootstrap/`

### 现状

1. `src/tools/service_container.py`
2. `src/tools/__init__.py` 导出 `ServiceContainer`、`get_service_container`

### 目标

1. `src/bootstrap/container.py`
2. `src/bootstrap/__init__.py`

### 原因

容器负责应用装配，不是业务 tool。

### 兼容策略

1. `src/tools/service_container.py` 过渡期 re-export。
2. `src/tools/__init__.py` 过渡期继续 re-export，但文档与新代码不再从 `src.tools` 导入容器。

## 5.6 `telemetry/evaluation.py` 拆分

### 现状

`src/telemetry/evaluation.py` 同时承载：

1. 回复质量评估。
2. 轨迹评估。
3. rule-based baseline。
4. judge schema。

### 目标

1. `src/evaluation/response_quality.py`
2. `src/evaluation/trajectory.py`

### 原因

评估不属于运行时观测。

### `telemetry/__init__.py` 目标

重构后只暴露：

1. `TraceRecorder`
2. trace exporter 相关对象
3. metrics helper

### `evaluation/__init__.py` 目标

暴露：

1. `ResponseQualityJudge`
2. `RuleBasedResponseQualityBaseline`
3. `build_trajectory_evaluation`
4. `validate_judge_output`

---

## 6. 逐文件迁移清单

下表中的“迁移方式”分为四类：

1. `move`：直接迁移文件并修改导入。
2. `split`：拆分为多个文件。
3. `keep`：路径不变，仅调整内部导入。
4. `re-export`：旧路径保留一层兼容转发。

| 当前路径 | 目标路径 | 迁移方式 | 说明 |
| --- | --- | --- | --- |
| `main.py` | `scripts/run_poller.py` | `move + re-export` | 根目录只保留兼容入口 |
| `deploy_api.py` | `scripts/serve_api.py` | `move + re-export` | 同上 |
| `create_index.py` | `scripts/build_index.py` | `move + re-export` | 同上 |
| `src/graph/workflow.py` | `src/orchestration/workflow.py` | `move + re-export` | workflow 构造器 |
| `src/graph/routes.py` | `src/orchestration/routes.py` | `move + re-export` | route map 常量 |
| `src/graph/state.py` | `src/orchestration/state.py` | `move + re-export` | graph state 契约 |
| `src/graph/checkpointing.py` | `src/orchestration/checkpointing.py` | `move + re-export` | checkpoint 工具 |
| `src/graph/nodes_base.py` | `src/orchestration/nodes_base.py` | `move + re-export` | node 基类 |
| `src/graph/nodes_ticket.py` | `src/orchestration/nodes_ticket.py` | `move + re-export` | ticket 节点集 |
| `src/agents/triage_agent.py` | `src/agents/triage_agent.py` | `keep` | 保留，但改内部导入 |
| `src/agents/pipeline_agents.py` | `src/agents/knowledge_policy_agent.py` | `split` | 拆出 `KnowledgePolicyAgentMixin` |
| `src/agents/pipeline_agents.py` | `src/agents/drafting_agent.py` | `split` | 拆出 `DraftingAgentMixin` |
| `src/agents/pipeline_agents.py` | `src/agents/qa_handoff_agent.py` | `split` | 拆出 `QaHandoffAgentMixin` |
| `src/agents/__init__.py` | `src/agents/__init__.py` | `keep` | 聚合导出面，去掉对 `pipeline_agents.py` 的依赖 |
| `src/triage/models.py` | `src/triage/models.py` | `keep` | 规则上下文保留 |
| `src/triage/policy.py` | `src/triage/policy.py` | `keep` | 策略表保留 |
| `src/triage/rules.py` | `src/triage/rules.py` | `keep` | 规则引擎保留 |
| `src/triage/service.py` | `src/triage/service.py` | `keep` | triage 领域服务保留 |
| `src/ticket_state_machine.py` | `src/tickets/state_machine.py` | `move + re-export` | 工单状态机 |
| `src/message_log.py` | `src/tickets/message_log.py` | `move + re-export` | 工单消息日志 |
| `src/core_schema.py` | `src/contracts/core.py` | `move + re-export` | 核心枚举与工具函数 |
| `src/structure_outputs.py` | `src/contracts/outputs.py` | `move + re-export` | 输出 schema |
| `src/tools/types.py` | `src/contracts/protocols.py` | `move + re-export` | provider 协议 |
| `src/tools/service_container.py` | `src/bootstrap/container.py` | `move + re-export` | 依赖装配 |
| `src/tools/ticket_store.py` | `src/db/ticket_store.py` | `move + re-export` | store 归入 db |
| `src/prompts.py` | `src/prompts/triage.py` 等 | `split` | 按 agent / capability 切分 |
| `src/telemetry/trace.py` | `src/telemetry/trace.py` | `keep` | 继续保留 |
| `src/telemetry/metrics.py` | `src/telemetry/metrics.py` | `keep` | 继续保留 |
| `src/telemetry/evaluation.py` | `src/evaluation/response_quality.py` | `split` | 回复质量相关 |
| `src/telemetry/evaluation.py` | `src/evaluation/trajectory.py` | `split` | 轨迹评估相关 |
| `src/workers/runner.py` | `src/workers/runner.py` | `keep` | 只改导入路径 |
| `src/workers/ticket_worker.py` | `src/workers/ticket_worker.py` | `keep` | 只改导入路径 |

---

## 7. 逐模块、逐类、逐变量改动规范

## 7.1 `contracts/core.py`

### 来自 `src/core_schema.py`

以下符号迁移到 `src/contracts/core.py`：

#### 常量

1. `INITIAL_VERSION`

#### 基础枚举类

1. `StringEnum`

#### 异常类

1. `CoreSchemaError`
2. `VersionConflictError`
3. `InvalidStateTransitionError`
4. `LeaseConflictError`

#### 业务枚举

1. `EntityIdPrefix`
2. `SourceChannel`
3. `TicketBusinessStatus`
4. `TicketProcessingStatus`
5. `TicketPriority`
6. `TicketRoute`
7. `TicketTag`
8. `ResponseStrategy`
9. `RunTriggerType`
10. `RunStatus`
11. `RunFinalAction`
12. `DraftType`
13. `DraftQaStatus`
14. `HumanReviewAction`
15. `TraceEventType`
16. `TraceEventStatus`
17. `MemorySourceStage`
18. `MemoryEventType`
19. `MessageDirection`
20. `MessageType`

#### 值对象

1. `TicketRoutingSelection`
2. `CustomerIdentity`

#### 工具函数

1. `utc_now`
2. `ensure_timezone_aware`
3. `to_api_timestamp`
4. `validate_version`
5. `next_version`
6. `assert_expected_version`
7. `validate_source_channel`
8. `normalize_ticket_routing`
9. `generate_prefixed_id`
10. `validate_prefixed_id`
11. `normalize_email_address`
12. `build_customer_identity`
13. `generate_ulid`

#### 私有函数

以下私有函数继续保留在 `core.py` 内部，不导出：

1. `_encode_base32`
2. `_coerce_enum`
3. `_coerce_unique_enum_sequence`

### 变量与名称规范

1. 不改动已有业务常量名和值。
2. 不改动枚举成员名和值。
3. 不改动公开函数签名。
4. 迁移后必须保留 `src/core_schema.py` 的兼容导出，直到所有 import 清理完成。

## 7.2 `contracts/outputs.py`

### 来自 `src/structure_outputs.py`

迁移以下类型：

1. `EmailCategory`
2. `CategorizeEmailOutput`
3. `TriageOutput`
4. `RAGQueriesOutput`
5. `WriterOutput`
6. `ProofReaderOutput`
7. `RiskLevel`
8. `KnowledgePolicyOutput`
9. `DraftingOutput`
10. `QaHandoffOutput`

### 字段级约束

#### `TriageOutput`

保留字段：

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

#### `KnowledgePolicyOutput`

保留字段：

1. `queries`
2. `knowledge_summary`
3. `citations`
4. `knowledge_confidence`
5. `risk_level`
6. `allowed_actions`
7. `disallowed_actions`
8. `policy_notes`

#### `DraftingOutput`

保留字段：

1. `draft_text`
2. `draft_rationale`
3. `applied_response_strategy`

#### `QaHandoffOutput`

保留字段：

1. `approved`
2. `issues`
3. `rewrite_guidance`
4. `quality_scores`
5. `escalate`
6. `reason`
7. `human_handoff_summary`

### 迁移要求

1. 所有 `BaseModel` 配置和字段约束保持不变。
2. `_sync_boolean_tag` 保留为模块内私有辅助函数。
3. 旧路径 `src.structure_outputs` 必须继续可导入。

## 7.3 `contracts/protocols.py`

### 来自 `src/tools/types.py`

迁移以下协议：

1. `GmailClientProtocol`
2. `PolicyProviderProtocol`
3. `TicketStoreProtocol`

### 方法签名保持不变

#### `GmailClientProtocol`

1. `fetch_unanswered_emails(max_results: int | None = None) -> list[dict[str, Any]]`
2. `create_draft_reply(initial_email: Any, reply_text: str) -> Any`
3. `send_reply(initial_email: Any, reply_text: str) -> Any`

#### `PolicyProviderProtocol`

1. `get_policy(category: str | None = None) -> str`

#### `TicketStoreProtocol`

1. `ping() -> bool`
2. `session_scope() -> ContextManager[Session]`
3. `repositories(session: Session) -> RepositoryBundle`

## 7.4 `agents/` 拆分方案

### 当前情况

1. `src/agents/triage_agent.py` 已经是单独文件。
2. `src/agents/pipeline_agents.py` 同时承载三个 Agent Mixin。

### 目标拆分

#### `src/agents/triage_agent.py`

保留以下公开符号：

1. `TriageAgentMixin`
2. `TriageMergeResult`
3. `triage_email_with_rules_detailed`
4. `invoke_triage_email`

#### `src/agents/knowledge_policy_agent.py`

从 `pipeline_agents.py` 拆出：

1. `KnowledgePolicyAgentMixin`
2. `knowledge_policy_agent`

#### `src/agents/drafting_agent.py`

从 `pipeline_agents.py` 拆出：

1. `DraftingAgentMixin`
2. `drafting_agent`

#### `src/agents/qa_handoff_agent.py`

从 `pipeline_agents.py` 拆出：

1. `QaHandoffAgentMixin`
2. `qa_handoff_agent`

### `src/agents/__init__.py` 目标导出

保留：

1. `Agents`
2. `LlmInvocationResult`
3. `LlmRuntime`
4. `TriageMergeResult`

内部导入改为：

1. 从 `knowledge_policy_agent` 导入 `KnowledgePolicyAgentMixin`
2. 从 `drafting_agent` 导入 `DraftingAgentMixin`
3. 从 `qa_handoff_agent` 导入 `QaHandoffAgentMixin`
4. 从 `triage_agent` 导入 `TriageAgentMixin`、`TriageMergeResult`

### 变量级要求

#### `KnowledgePolicyAgentMixin.knowledge_policy_agent`

保留参数名：

1. `primary_route`
2. `response_strategy`
3. `normalized_email`
4. `knowledge_answers`
5. `policy_notes`
6. `knowledge_confidence`
7. `needs_escalation`

保留内部关键变量语义：

1. `answers`
2. `allowed_actions`
3. `disallowed_actions`
4. `inferred_confidence`
5. `risk_level`
6. `knowledge_summary`
7. `citations`

#### `DraftingAgentMixin.drafting_agent`

保留参数名：

1. `customer_email`
2. `subject`
3. `primary_route`
4. `response_strategy`
5. `normalized_email`
6. `knowledge_summary`
7. `policy_notes`
8. `rewrite_guidance`

保留内部关键变量语义：

1. `guidance_text`
2. `greeting`
3. `closing`
4. `body`
5. `rationale`
6. `draft_text`

#### `QaHandoffAgentMixin.qa_handoff_agent`

保留参数名：

1. `primary_route`
2. `draft_text`
3. `knowledge_confidence`
4. `needs_escalation`
5. `rewrite_count`
6. `policy_notes`

保留内部关键变量语义：

1. `quality_scores`

## 7.5 `orchestration/state.py` 字段分组整理规范

当前 `GraphState` 同时承载新旧两套字段，必须在迁移中分为三类：

### A 类：保留为正式字段

1. `ticket_id`
2. `channel`
3. `customer_id`
4. `thread_id`
5. `business_status`
6. `processing_status`
7. `ticket_version`
8. `ticket_created_at`
9. `ticket_updated_at`
10. `run_id`
11. `trigger_type`
12. `triggered_by`
13. `current_node`
14. `clarification_history`
15. `resume_count`
16. `checkpoint_metadata`
17. `raw_email`
18. `normalized_email`
19. `attachments`
20. `primary_route`
21. `secondary_routes`
22. `tags`
23. `response_strategy`
24. `multi_intent`
25. `intent_confidence`
26. `priority`
27. `needs_clarification`
28. `needs_escalation`
29. `routing_reason`
30. `queries`
31. `knowledge_summary`
32. `retrieval_results`
33. `citations`
34. `knowledge_confidence`
35. `policy_notes`
36. `allowed_actions`
37. `disallowed_actions`
38. `thread_summary`
39. `customer_profile`
40. `historical_cases`
41. `case_context`
42. `memory_update_candidates`
43. `memory_updates`
44. `draft_versions`
45. `qa_feedback`
46. `applied_response_strategy`
47. `rewrite_count`
48. `approval_status`
49. `escalation_reason`
50. `final_action`
51. `human_handoff_summary`
52. `qa_result`
53. `trace_id`
54. `latency_metrics`
55. `resource_metrics`
56. `response_quality`
57. `trajectory_evaluation`
58. `claimed_by`
59. `claimed_at`
60. `lease_until`
61. `retry_count`
62. `last_error`
63. `side_effect_records`
64. `idempotency_keys`

### B 类：兼容期字段，后续删除

1. `pending_emails`
2. `emails`
3. `current_email`
4. `email_category`
5. `triage_result`
6. `generated_email`
7. `rag_queries`
8. `retrieved_documents`
9. `writer_messages`
10. `sendable`
11. `trials`
12. `trace_events`
13. `extra_metrics`
14. `knowledge_policy_result`

### C 类：需要重新命名或在文档中标注别名关系

1. `queries` <-> `rag_queries`
2. `knowledge_summary` <-> `retrieved_documents`
3. `draft_versions[-1].content_text` / draft artifact <-> `generated_email`
4. `rewrite_count` <-> `trials`
5. `qa_result` / `qa_feedback` <-> `sendable`

### 迁移要求

1. 先保留 B 类字段，禁止立刻删除。
2. 在 `build_initial_graph_state` 中明确注释哪些是兼容字段。
3. 在 `build_ticket_run_state` 中优先写入 A 类字段，再镜像填充 B 类兼容字段。
4. 待 `nodes_ticket.py`、测试、API 查询逻辑全部改完后，再删除 B 类字段。

## 7.6 `prompts/` 拆分方案

### 当前常量

来自 `src/prompts.py`：

1. `CATEGORIZE_EMAIL_PROMPT`
2. `TRIAGE_EMAIL_PROMPT`
3. `GENERATE_RAG_QUERIES_PROMPT`
4. `GENERATE_RAG_ANSWER_PROMPT`
5. `EMAIL_WRITER_PROMPT`
6. `EMAIL_PROOFREADER_PROMPT`

### 目标拆分

1. `src/prompts/triage.py`
   - `TRIAGE_EMAIL_PROMPT`
2. `src/prompts/knowledge_policy.py`
   - `GENERATE_RAG_QUERIES_PROMPT`
   - `GENERATE_RAG_ANSWER_PROMPT`
3. `src/prompts/drafting.py`
   - `EMAIL_WRITER_PROMPT`
4. `src/prompts/qa_handoff.py`
   - `EMAIL_PROOFREADER_PROMPT`
5. `src/prompts/legacy.py`
   - `CATEGORIZE_EMAIL_PROMPT`，仅兼容旧测试与旧流程

### 变量命名要求

1. 所有 prompt 常量继续使用全大写。
2. 常量名保持不变，避免大面积改测试。
3. `src/prompts/__init__.py` 统一 re-export，避免业务层直接依赖文件物理位置。

## 7.7 `bootstrap/container.py`

### 来自 `src/tools/service_container.py`

保留以下构建函数：

1. `_build_agents`
2. `_build_response_quality_judge`
3. `_build_gmail_client`
4. `_build_knowledge_provider`
5. `_build_policy_provider`
6. `_build_ticket_store`
7. `_build_checkpointer`

保留以下公开对象：

1. `ServiceContainer`
2. `create_default_service_container`
3. `get_service_container`

### `ServiceContainer` 字段级清单

#### factory 字段

1. `agents_factory`
2. `response_quality_judge_factory`
3. `gmail_client_factory`
4. `knowledge_provider_factory`
5. `policy_provider_factory`
6. `ticket_store_factory`
7. `checkpointer_factory`

#### 缓存实例字段

1. `_gmail_client`
2. `_knowledge_provider`
3. `_policy_provider`
4. `_ticket_store`
5. `_agents`
6. `_response_quality_judge`
7. `_checkpointer`

#### 方法与属性

1. `_get_or_create`
2. `agents`
3. `response_quality_judge`
4. `gmail_client`
5. `knowledge_provider`
6. `policy_provider`
7. `ticket_store`
8. `checkpointer`

### 迁移要求

1. 所有字段名保持不变。
2. 仅修改模块路径，不修改容器协议。
3. 新代码统一从 `src.bootstrap.container` 导入。

## 7.8 `telemetry/` 与 `evaluation/` 拆分细则

### 保留在 `src/telemetry/trace.py`

#### 公开类

1. `LangSmithTraceClient`
2. `TraceRecorder`

#### `LangSmithTraceClient` 方法

1. `create_root_run`
2. `create_child_run`
3. `finalize_run`

#### `TraceRecorder` 方法

1. `start_run`
2. `finalize_run`
3. `record_event`
4. `node_span`
5. `record_decision`
6. `record_tool_call`
7. `record_llm_call`
8. `list_run_events`
9. `build_latency_metrics`
10. `build_resource_metrics`

### 保留在 `src/telemetry/metrics.py`

#### 函数

1. `duration_ms`
2. `build_latency_metrics`
3. `build_resource_metrics`
4. `estimate_token_usage`

### 迁移到 `src/evaluation/response_quality.py`

#### 类型

1. `JudgeResult`
2. `JudgeSchemaError`
3. `ResponseQualityJudgeOutput`
4. `JudgeEvaluationResult`
5. `RuleBasedResponseQualityBaseline`
6. `ResponseQualityJudge`
7. `_ResponseQualityJudgeRuntime`

#### 函数

1. `validate_judge_output`

### 迁移到 `src/evaluation/trajectory.py`

#### 函数与常量

1. `build_trajectory_evaluation`
2. `_select_expected_template_key`
3. `_REQUIRED_ROUTE_TEMPLATES`
4. `_TRAJECTORY_PENALTIES`
5. `_TRAJECTORY_NODE_SET`

### 数据结构级约束

#### `TraceEvent.event_metadata`

在 `src/db/models.py` 中保持要求不变：

1. `llm_call` 必须包含：
   - `model`
   - `provider`
   - `prompt_tokens`
   - `completion_tokens`
   - `total_tokens`
   - `token_source`
2. `tool_call` 必须包含：
   - `tool_name`
   - `input_ref`
   - `output_ref`
3. `decision` 必须包含：
   - `primary_route`
   - `response_strategy`
   - `needs_clarification`
   - `needs_escalation`
   - `final_action`
4. `checkpoint` 必须包含：
   - `thread_id`
   - `checkpoint_ns`
   - `restore_mode`
   - `restored`
5. `worker` 必须包含：
   - `ticket_id`
   - `run_id`
   - `worker_id`
   - `lease_owner`
   - `lease_expires_at`

#### `TicketRun` 聚合字段

以下字段继续保留在 `src/db/models.py` 的 `TicketRun` 中：

1. `latency_metrics`
2. `resource_metrics`
3. `response_quality`
4. `trajectory_evaluation`

这四个字段是运行结果聚合字段，不做目录迁移。

## 7.9 `config.py` 配置模型文档化

`src/config.py` 路径保留不变，但文档必须把配置层也纳入重构说明。

### 配置 dataclass

1. `GmailSettings`
   - `enabled`
   - `my_email`
   - `credentials_path`
   - `token_path`
   - `scopes`
   - `inbox_lookback_hours`
   - `default_fetch_limit`
2. `LLMSettings`
   - `api_key`
   - `base_url`
   - `chat_model`
   - `judge_model`
   - `judge_timeout_seconds`
3. `EmbeddingSettings`
   - `api_url`
   - `api_key`
   - `model`
   - `timeout_seconds`
   - `api_key_header`
   - `api_key_prefix`
4. `KnowledgeSettings`
   - `source_document_path`
   - `chroma_persist_directory`
   - `retriever_k`
5. `DatabaseSettings`
   - `url`
   - `host`
   - `port`
   - `name`
   - `user`
   - `password`
   - `dsn`
6. `LangSmithSettings`
   - `tracing_enabled`
   - `api_key`
   - `project`
   - `endpoint`
7. `ApiSettings`
   - `host`
   - `port`
   - `cors_allow_origins`
   - `title`
   - `version`
   - `description`
8. `AppSettings`
   - `graph_recursion_limit`
9. `Settings`
   - `project_root`
   - `gmail`
   - `llm`
   - `embedding`
   - `knowledge`
   - `database`
   - `langsmith`
   - `api`
   - `app`

### 环境变量清单

#### Gmail

1. `GMAIL_ENABLED`
2. `MY_EMAIL`
3. `GMAIL_CREDENTIALS_PATH`
4. `GMAIL_TOKEN_PATH`
5. `GMAIL_INBOX_LOOKBACK_HOURS`
6. `GMAIL_DEFAULT_FETCH_LIMIT`

#### LLM

1. `LLM_API_KEY`
2. `LLM_BASE_URL`
3. `LLM_CHAT_MODEL`
4. `LLM_JUDGE_MODEL`
5. `LLM_JUDGE_TIMEOUT_SECONDS`

#### Embedding

1. `EMBEDDING_API_URL`
2. `EMBEDDING_API_KEY`
3. `EMBEDDING_MODEL`
4. `LLM_EMBEDDING_MODEL`
5. `EMBEDDING_TIMEOUT_SECONDS`
6. `EMBEDDING_API_KEY_HEADER`
7. `EMBEDDING_API_KEY_PREFIX`

#### Knowledge

1. `KNOWLEDGE_SOURCE_PATH`
2. `KNOWLEDGE_DB_PATH`
3. `KNOWLEDGE_RETRIEVER_K`

#### Database

1. `DATABASE_URL`
2. `POSTGRES_HOST`
3. `POSTGRES_PORT`
4. `POSTGRES_DB`
5. `POSTGRES_USER`
6. `POSTGRES_PASSWORD`

#### LangSmith

1. `LANGSMITH_TRACING`
2. `LANGSMITH_API_KEY`
3. `LANGSMITH_PROJECT`
4. `LANGSMITH_ENDPOINT`

#### API

1. `API_HOST`
2. `API_PORT`
3. `CORS_ALLOW_ORIGINS`
4. `API_TITLE`
5. `API_VERSION`
6. `API_DESCRIPTION`

#### App

1. `GRAPH_RECURSION_LIMIT`

---

## 8. 导入路径改动规范

## 8.1 新代码统一使用新路径

### 示例

#### 旧写法

```python
from src.graph.workflow import Workflow
from src.core_schema import TicketRoute
from src.message_log import MessageLogService
from src.tools.service_container import get_service_container
from src.structure_outputs import TriageOutput
```

#### 新写法

```python
from src.orchestration.workflow import Workflow
from src.contracts.core import TicketRoute
from src.tickets.message_log import MessageLogService
from src.bootstrap.container import get_service_container
from src.contracts.outputs import TriageOutput
```

## 8.2 兼容导入期限

建议分三阶段：

1. 第 1 阶段：新旧路径都可导入。
2. 第 2 阶段：业务代码只使用新路径，测试允许旧路径。
3. 第 3 阶段：删除旧路径壳文件。

---

## 9. 分阶段实施计划

## 阶段 1：只做结构壳与兼容层

目标：不动业务逻辑，先搭目标目录。

执行项：

1. 新建 `src/orchestration/`、`src/tickets/`、`src/contracts/`、`src/bootstrap/`、`src/evaluation/`、`src/prompts/`。
2. 把旧模块迁入新目录。
3. 在旧路径保留 re-export 壳文件。
4. 不删任何旧字段。

验收标准：

1. `pytest` 通过。
2. 现有启动方式仍可用。

## 阶段 2：清理业务导入与拆分大文件

执行项：

1. 拆 `pipeline_agents.py`。
2. 拆 `telemetry/evaluation.py`。
3. 拆 `prompts.py`。
4. 将业务代码 import 全部切到新路径。

验收标准：

1. `rg "from src\.graph|from src\.core_schema|from src\.message_log|from src\.tools\.service_container|from src\.structure_outputs" src tests` 结果只剩兼容层文件。

## 阶段 3：清理状态兼容字段

执行项：

1. 收敛 `GraphState`。
2. 删除 B 类兼容字段。
3. 更新节点逻辑、测试和文档。

验收标准：

1. `GraphState` 只保留正式字段。
2. 测试不再引用旧字段别名。

## 阶段 4：删除旧路径壳文件

执行项：

1. 删除 `src/graph/` 兼容壳。
2. 删除 `src/core_schema.py`、`src/structure_outputs.py`、`src/message_log.py`、`src/ticket_state_machine.py` 等旧路径壳。

验收标准：

1. 仓库中不存在旧路径导入引用。

---

## 10. 测试与验证要求

## 10.1 单元测试关注点

1. `triage`：规则路由、优先级、升级判断。
2. `orchestration`：route map、node 切换、checkpoint 恢复。
3. `tickets`：状态机迁移、message log reopen 规则。
4. `telemetry`：trace event 记录、metrics 聚合。
5. `evaluation`：judge 输出校验、trajectory score。
6. `bootstrap`：容器 lazy initialization。

## 10.2 迁移期间必须重点回归的文件

1. `tests/test_checkpoint_resume.py`
2. `tests/test_nodes.py`
3. `tests/test_ticket_worker.py`
4. `tests/test_api_contract.py`
5. `tests/test_observability.py`
6. `tests/test_service_container.py`
7. `tests/test_triage_outputs.py`

## 10.3 建议命令

```bash
pytest -q
```

重构中期可加局部回归：

```bash
pytest tests/test_service_container.py -q
pytest tests/test_observability.py -q
pytest tests/test_ticket_worker.py -q
pytest tests/test_api_contract.py -q
```

---

## 11. 风险清单

1. `GraphState` 同时存在新旧字段，最容易在迁移中出现隐式兼容 bug。
2. `tests/test_nodes.py` 仍覆盖了旧教程式字段名，必须区分“兼容保留”与“正式字段”。
3. `telemetry/evaluation.py` 拆分时，`workers/runner.py` 和 `tools/service_container.py` 的导入链最容易断。
4. `src/tools/__init__.py` 当前对外暴露容器，迁移时必须保留兼容导出。
5. 文档、README、脚本命令如果不同步，会让目录重构后的学习成本上升。

---

## 12. 最终结论

本次目录重构的核心，不是为了“文件更少”或“更像某个框架模板”，而是为了让仓库本身直接表达系统设计：

1. `agents/` 放 Agent 本体。
2. `orchestration/` 放 Agent 编排。
3. `memory / tools / rag / llm` 放共享能力。
4. `telemetry/` 放 trace 与 metrics。
5. `evaluation/` 放结果评估。
6. `contracts/` 放共享契约。
7. `bootstrap/` 放装配。

只要按本文档的迁移顺序推进，就能在不破坏现有功能的前提下，把项目结构整理成更清晰、可扩展、能体现 Agent 核心的形态。
