# Customer Support Copilot Directory Migration 规格

## 1. 目的

本文档把“按技术说明书建议目录进行全量一次性重构”收敛为 V1.1 可执行协议。

本规格不是“代码整理建议”，而是后续目录迁移与模块重构的强约束执行说明书。

本规格要同时满足两个目标：

1. 一次性完成目标目录结构重构，不保留长期双轨结构
2. 重构过程中每完成一段就完成该段验证，确保最终结果和中间结果都正确

如与以下文档局部冲突，本规格优先：

1. `docs/customer-support-copilot-technical-design.zh-CN.md`
2. `docs/specs/07-short-term-memory-checkpoint.zh-CN.md`
3. `docs/specs/08-worker-runtime-contract.zh-CN.md`
4. `docs/specs/09-ticket-snapshot-eval-summary.zh-CN.md`
5. `docs/specs/10-llm-usage-and-judge.zh-CN.md`

---

## 2. 适用范围

### 2.1 本规格覆盖

1. 目标目录结构
2. 模块迁移顺序
3. 每阶段允许和禁止的改动方式
4. 每阶段必须执行的测试
5. 迁移完成的验收标准

### 2.2 本规格不覆盖

1. 新业务功能需求本身
2. 非迁移引起的独立 bug 修复
3. 新前端或后台页面
4. V2 范围能力

说明：

1. 本规格解决的是“结构重构”。
2. 不是借目录迁移顺手做功能扩展。

---

## 3. 总原则

### 3.1 一次性目标态原则

本次迁移的目标是一次性交付到“新目录结构的目标态”，而不是长期保留旧结构与新结构并存。

### 3.2 分段验证原则

虽然目标态是一次性完成，但执行过程必须分段。

固定规则：

1. 每完成一个迁移阶段，必须立即运行该阶段规定的测试集
2. 该阶段测试未通过，不得进入下一阶段
3. 不允许累计多个阶段后再一次性跑全量测试

### 3.3 结构迁移优先原则

目录迁移阶段只允许为实现新结构所必需的最小代码调整。

明确禁止：

1. 借迁移顺手重写业务策略
2. 借迁移顺手更换主算法
3. 借迁移顺手做无关命名清洗
4. 借迁移顺手改 API 契约

### 3.4 行为保持原则

除本批已新增 spec 明确要求改变的行为外，迁移前后系统行为必须保持等价。

这里的“行为”至少包括：

1. 路由判断结果
2. 状态迁移语义
3. API 输入输出契约
4. trace / metrics 基本输出
5. Gmail draft 副作用幂等语义

---

## 4. 目标目录结构

### 4.1 根目标

迁移完成后，`src/` 下的目标结构固定为：

```text
src/
├── agents/
│   ├── __init__.py
│   ├── triage_agent.py
│   ├── knowledge_policy_agent.py
│   ├── drafting_agent.py
│   └── qa_handoff_agent.py
├── api/
├── db/
├── graph/
│   ├── __init__.py
│   ├── routes.py
│   ├── state.py
│   ├── workflow.py
│   └── checkpointing.py
├── llm/
│   ├── __init__.py
│   ├── models.py
│   ├── runtime.py
│   └── judge.py
├── memory/
│   ├── __init__.py
│   ├── long_term.py
│   └── short_term.py
├── rag/
│   ├── __init__.py
│   ├── provider.py
│   ├── local_provider.py
│   └── mcp_adapter.py
├── telemetry/
│   ├── __init__.py
│   ├── trace.py
│   ├── metrics.py
│   └── evaluation.py
├── tools/
└── workers/
    ├── __init__.py
    └── ticket_worker.py
```

### 4.2 本次迁移必须拆分的旧文件

以下旧文件不得继续作为最终主实现入口：

1. `src/agents.py`
2. `src/graph.py`
3. `src/state.py`
4. `src/customer_memory.py`
5. `src/observability.py`
6. `src/llm.py`

### 4.3 可暂不迁移的目录

以下目录本次允许保持原位：

1. `src/api/`
2. `src/db/`
3. `src/tools/`

但允许在内部 import 路径上调整为依赖新目录结构。

---

## 5. 旧路径兼容策略

### 5.1 迁移过程中的兼容层

在迁移尚未完成前，允许旧文件存在，但只允许作为“薄兼容层”。

所谓“薄兼容层”固定含义：

1. 只做 import re-export
2. 不再包含真实业务逻辑

### 5.2 迁移完成时的最终规则

当本规格全部落地完成时：

1. 旧平铺文件允许存在
2. 但必须只保留薄兼容层职责
3. 不允许旧平铺文件和新目录各自维护一份逻辑

### 5.3 明确禁止

1. 在 `src/agents.py` 保留真实 Agent 实现，同时在 `src/agents/*.py` 再保留一份
2. 在 `src/graph.py` 保留真实 workflow，同时在 `src/graph/workflow.py` 再保留一份
3. 以“兼容”为名长期双写双维护

---

## 6. 固定迁移顺序

本次迁移必须严格按以下顺序执行。

不允许跳步，不允许并行跨阶段推进。

### 阶段 A：新目录骨架与 import 基础

目标：

1. 建立目标目录骨架
2. 建立空 `__init__.py`
3. 调整 import 路径使后续迁移具备落点

本阶段只允许：

1. 新建目录
2. 新建空模块
3. 修改少量 import

本阶段禁止：

1. 搬迁真实业务逻辑
2. 改业务行为

### 阶段 B：`graph` 与 `state` 迁移

目标：

1. 把 `src/graph.py` 拆到 `src/graph/workflow.py`
2. 把 `src/state.py` 拆到 `src/graph/state.py`
3. 新增 `src/graph/routes.py`
4. 新增 `src/graph/checkpointing.py`

本阶段必须同时对齐：

1. `07-short-term-memory-checkpoint`

### 阶段 C：`agents` 与 `llm` 迁移

目标：

1. 把 `src/agents.py` 拆到 `src/agents/`
2. 把 `src/llm.py` 拆到 `src/llm/models.py`
3. 新增 `src/llm/runtime.py`
4. 新增 `src/llm/judge.py`

本阶段必须同时对齐：

1. `10-llm-usage-and-judge`

### 阶段 D：`memory` 与 `rag` 迁移

目标：

1. 把 `src/customer_memory.py` 拆到 `src/memory/long_term.py`
2. 新增 `src/memory/short_term.py`
3. 把知识 provider 拆到 `src/rag/`

本阶段必须同时对齐：

1. `07-short-term-memory-checkpoint`
2. `08-worker-runtime-contract`

### 阶段 E：`telemetry` 迁移

目标：

1. 把 `src/observability.py` 拆到 `src/telemetry/trace.py`
2. 把指标逻辑拆到 `src/telemetry/metrics.py`
3. 把评估逻辑拆到 `src/telemetry/evaluation.py`

本阶段必须同时对齐：

1. `09-ticket-snapshot-eval-summary`
2. `10-llm-usage-and-judge`

### 阶段 F：`workers` 落地与 API 集成切换

目标：

1. 新增 `src/workers/ticket_worker.py`
2. API 从“直接执行 graph”切到“enqueue + worker 消费”
3. `main.py` 切到 poller 角色

本阶段必须同时对齐：

1. `08-worker-runtime-contract`

### 阶段 G：薄兼容层收尾与文档回填

目标：

1. 旧平铺文件改成薄兼容层
2. README、实现跟踪表、引用文档全部回填
3. 路径说明切换到新目录

---

## 7. 每阶段必跑测试合同

### 7.1 总规则

每阶段迁移完成后，必须按本规格执行“阶段测试 + 全量回归”的双层验证。

固定规则：

1. 先跑该阶段规定的最小测试集
2. 最小测试集通过后，再跑 `pytest -q`
3. `pytest -q` 未通过，不得进入下一阶段

### 7.2 阶段 A 测试

必须通过：

1. `tests/test_config.py`
2. `tests/test_service_container.py`
3. `pytest -q`

### 7.3 阶段 B 测试

必须通过：

1. `tests/test_state.py`
2. `tests/test_nodes.py`
3. `tests/test_ticket_state_machine.py`
4. `pytest -q`

### 7.4 阶段 C 测试

必须通过：

1. `tests/test_agents.py`
2. `tests/test_triage_service.py`
3. `tests/test_triage_outputs.py`
4. `tests/test_llm.py`
5. `pytest -q`

### 7.5 阶段 D 测试

必须通过：

1. `tests/test_customer_memory.py`
2. `tests/test_message_log_service.py`
3. `tests/test_ticket_messages.py`
4. `pytest -q`

### 7.6 阶段 E 测试

必须通过：

1. `tests/test_observability.py`
2. `tests/test_offline_eval.py`
3. `tests/test_api_contract.py`
4. `pytest -q`

### 7.7 阶段 F 测试

必须通过：

1. `tests/test_api_contract.py`
2. `tests/test_nodes.py`
3. `tests/test_ticket_state_machine.py`
4. `pytest -q`

### 7.8 阶段 G 测试

必须通过：

1. `pytest -q`

说明：

1. “每重构一部分，就测试一部分”在本规格中不是建议，而是强制门禁。

---

## 8. 阶段门禁规则

### 8.1 进入下一阶段的前置条件

只有当以下条件全部满足时，才允许进入下一阶段：

1. 当前阶段代码已提交到工作区稳定状态
2. 当前阶段规定的最小测试集全部通过
3. `pytest -q` 全量通过
4. 当前阶段涉及的 import 路径已统一
5. 当前阶段不存在“新旧双逻辑并存”

### 8.2 阶段失败时的处理

如果当前阶段任一测试失败，必须：

1. 停止进入下一阶段
2. 只修当前阶段引入的问题
3. 不得通过跳到下一阶段“顺手一起修”

---

## 9. import 路径重构规则

### 9.1 同阶段内必须统一

凡是进入某个新包后的模块，该阶段结束时必须统一完成 import 切换。

例如：

1. 一旦进入阶段 B，则 `graph/state` 相关 import 在阶段 B 结束时必须全部切换完成
2. 不允许部分文件还引用旧路径、部分文件引用新路径

### 9.2 测试 monkeypatch 路径

对于测试中硬编码的 monkeypatch 路径：

1. 必须在对应阶段同步更新
2. 不允许依赖旧 shim 路径继续偷偷工作

原因：

1. 否则测试会掩盖真实迁移完成度

---

## 10. 禁止事项

本次迁移明确禁止以下行为：

1. 先全量搬文件，最后统一修 import
2. 先重构完所有目录，最后再统一跑测试
3. 为图省事保留旧逻辑实现不删，只是把新路径 import 指过去
4. 在未通过当前阶段测试的情况下继续迁移下一阶段
5. 借目录迁移顺手改业务 API 契约
6. 借目录迁移顺手重写测试语义
7. 因为某个旧测试难改，就让 shim 长期承担真实逻辑

---

## 11. 旧文件最终状态要求

迁移完成后，以下旧文件允许保留，但只能是薄兼容层：

1. `src/agents.py`
2. `src/graph.py`
3. `src/state.py`
4. `src/customer_memory.py`
5. `src/observability.py`
6. `src/llm.py`

每个薄兼容层必须满足：

1. 文件行数原则上不超过 `30` 行
2. 只包含 import re-export 或明确弃用说明
3. 不包含业务逻辑、状态计算、外部调用

---

## 12. 文档回填要求

阶段 G 必须同步更新以下文档：

1. `README.md`
2. `docs/customer-support-copilot-technical-design.zh-CN.md`
3. `docs/customer-support-copilot-implementation-tracker.zh-CN.md`
4. 相关 demo / eval / 启动说明中引用的路径

固定规则：

1. 文档中的模块路径必须与最终代码一致
2. 不允许 README 还在讲旧平铺文件结构

---

## 13. 验收标准

满足以下条件时，本规格视为落地完成：

1. `src/` 已达到本规格定义的目标目录结构
2. 被拆分的旧平铺文件不再承载真实业务逻辑
3. 每个迁移阶段均按规定测试通过后再进入下一阶段
4. 最终 `pytest -q` 全量通过
5. README 与技术文档中的目录说明已同步更新
6. 新增 `07` 至 `10` 相关 spec 的目录落点都已在新结构中有明确实现位置

---

## 14. 实施备注

本规格明确支持“全量一次性重构目标态”，但不允许“无门禁的大爆炸提交”。

也就是说：

1. 目标态必须一次到位
2. 过程必须阶段化
3. 每阶段必须测试
4. 不通过不得继续

这四条同时成立，缺一不可。

