# LangSmith 集成与接口设计

## 1. 结论

当前项目已经有 `LangSmith` 集成实现，不是空白状态。

现有代码位置：

1. [src/telemetry/exporters.py](C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/src/telemetry/exporters.py)
2. [src/telemetry/trace.py](C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/src/telemetry/trace.py)
3. [src/config.py](C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/src/config.py)

当前能力：

1. 支持通过环境变量开启或关闭 `LangSmith`
2. 每次 `TicketRun` 可以创建一个 LangSmith root run
3. 每个 `TraceEvent` 可以同步成 LangSmith child run
4. run 结束时会把汇总输出 patch 回 root run
5. LangSmith 写失败不会阻塞主业务，数据库仍然是主记录

当前缺口：

1. 之前只有实现，没有正式 exporter 接口
2. `TraceRecorder` 以前直接依赖 `LangSmithTraceClient`
3. 注入边界不在 `ServiceContainer`，后续扩展其他 trace 后端不够顺手

本次设计把它补成了“有实现，也有接口”的结构。

---

## 2. 当前实现边界

### 2.1 业务权威存储

业务权威存储始终是数据库中的：

1. `ticket_runs`
2. `trace_events`
3. `draft_artifacts`
4. `human_reviews`
5. 评估结果字段

`LangSmith` 是可选外部观测后端，不参与业务状态判断，不承担审计主记录。

### 2.2 当前配置

相关环境变量：

1. `LANGSMITH_TRACING`
2. `LANGSMITH_API_KEY`
3. `LANGSMITH_PROJECT`
4. `LANGSMITH_ENDPOINT`

配置入口在 [src/config.py](C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/src/config.py)。

启用条件：

1. `LANGSMITH_TRACING=true`
2. `LANGSMITH_API_KEY` 非空

否则自动降级为 no-op exporter。

---

## 3. 新接口设计

### 3.1 目标

目标不是把 telemetry 全部插件化，而是先把“外部 trace 导出”从 `TraceRecorder` 中拆出来。

### 3.2 核心接口

统一协议定义在 [src/contracts/protocols.py](C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/src/contracts/protocols.py)：

```python
class TraceExporterProtocol(Protocol):
    def create_root_run(...)
    def create_child_run(...)
    def finalize_run(...)
```

### 3.3 实现类

当前 exporter 实现：

1. `LangSmithTraceExporter`
2. `NoOpTraceExporter`

位置在 [src/telemetry/exporters.py](C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/src/telemetry/exporters.py)。

兼容性处理：

1. 保留 `LangSmithTraceClient = LangSmithTraceExporter` 别名
2. `TraceRecorder(..., langsmith_client=...)` 旧调用方式仍可用

### 3.4 注入位置

运行时注入入口在 [src/bootstrap/container.py](C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/src/bootstrap/container.py)：

1. `ServiceContainer.trace_exporter_factory`
2. `ServiceContainer.trace_exporter`

消费方在 [src/workers/runner.py](C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/src/workers/runner.py)：

1. `TicketRunner` 默认从 `container.trace_exporter` 获取 exporter
2. 测试场景可直接覆写 `trace_exporter`

---

## 4. 数据流设计

### 4.1 启动 run

`TicketWorker.claim_next()` 进入运行态后：

1. `TicketRunner.start_trace_for_worker_run(...)`
2. `TraceRecorder.start_run(...)`
3. `TraceExporterProtocol.create_root_run(...)`

root run 元信息至少包含：

1. `trace_id`
2. `run_id`
3. `ticket_id`
4. `trigger_type`
5. `triggered_by`
6. `worker_id`

### 4.2 记录事件

每次 `TraceRecorder.record_event(...)`：

1. 先落数据库 `trace_events`
2. 再调用 `create_child_run(...)` 同步到外部 exporter

因此系统采用：

1. 主写数据库
2. 可选双写 LangSmith

### 4.3 结束 run

run 结束后：

1. 汇总 `latency_metrics`
2. 汇总 `resource_metrics`
3. 写入 `response_quality`
4. 写入 `trajectory_evaluation`
5. 调用 `finalize_run(...)` 更新 LangSmith root run

---

## 5. 事件映射规则

### 5.1 root run

LangSmith root run：

1. `name = "ticket_run"`
2. `run_type = "chain"`
3. `id = uuid5(namespace, trace_id)`
4. `trace_id = uuid5(namespace, trace_id)`

说明：

1. 项目内部仍使用前缀 ID，例如 `trace_xxx`
2. 导出到 LangSmith 时稳定映射为 UUID，保证重复运行时映射可预测

### 5.2 child run

事件映射规则：

1. `llm_call -> llm`
2. `tool_call -> tool`
3. 其他事件类型 -> `chain`

当前支持同步的本地事件类型包括：

1. `node`
2. `llm_call`
3. `tool_call`
4. `decision`
5. `checkpoint`
6. `worker`

### 5.3 metadata 约定

child run metadata 至少包含：

1. `trace_id`
2. `run_id`
3. `ticket_id`
4. `event_type`
5. `node_name`
6. `status`

再附加本地 `event_metadata`。

---

## 6. 失败与降级策略

### 6.1 不阻塞主流程

所有 LangSmith 调用失败时：

1. 不抛出到业务主流程
2. 不影响 `ticket` 状态推进
3. 不影响 `trace_events` 落库

这符合当前系统定位：

1. `LangSmith` 是 observability 后端
2. 不是事务性依赖

### 6.2 降级顺序

降级顺序如下：

1. tracing 关闭 -> `NoOp`
2. API key 缺失 -> `NoOp`
3. 单次 `post/patch` 失败 -> 忽略该次外部写入

### 6.3 审计原则

任何需要审计、排障、重放的正式依据，都应回到数据库查询，而不是直接依赖 LangSmith 页面。

---

## 7. 为什么需要这层接口

如果没有 exporter 接口，后续会出现几个问题：

1. `TraceRecorder` 同时负责本地 trace 组装和远端写入，职责混杂
2. 想加 `NoOp`、批量 exporter、异步 exporter 时只能改核心 recorder
3. 测试只能 monkeypatch 具体类，不利于可控替换
4. 将来如果引入第二个 trace 后端，耦合会继续扩大

所以本次设计把边界定成：

1. `TraceRecorder` 负责本地事件建模与持久化
2. `TraceExporterProtocol` 负责外部同步
3. `ServiceContainer` 负责运行时装配

---

## 8. 后续建议

当前接口已经够 V1 使用，但如果继续增强，建议按下面顺序推进。

### 8.1 V1.1

1. 给 exporter 增加内部错误计数和 logger
2. 在 `run.app_metadata` 中记录 `trace_export_status`
3. 为 LangSmith 写失败增加测试覆盖

### 8.2 V1.2

1. 区分 `decision`、`checkpoint`、`worker` 在 LangSmith 中的 tag 规范
2. 为 `response_quality_judge` 输出增加固定 tag
3. 在 API 或离线评测报表中增加 LangSmith run URL 引用字段

### 8.3 V2

1. 支持异步/批量 exporter，避免高频事件逐条网络提交
2. 支持多个 exporter 并行输出，例如 `CompositeTraceExporter`
3. 把 exporter 健康状态纳入 metrics

---

## 9. 判断

如果你的问题是“当前项目的 LangSmith 是否有实现接口”，准确回答是：

1. 之前已经有实现，但更像内嵌客户端，不算完整接口层
2. 现在已经补成 exporter 协议 + 容器注入 + 文档化设计

如果你的标准是“是否已经形成清晰、可替换、可扩展的 LangSmith 接口设计”，那现在答案才算是“基本有了”。
