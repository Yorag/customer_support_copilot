# 客服 Copilot 评估系统

## 1. 概述

本评估系统用于端到端验证客服邮件自动化流程的真实表现。评测在真实 LLM、真实知识库、真实路由逻辑下运行，不使用 mock provider，确保结果直接反映生产行为。

核心评估维度：

| 维度 | 衡量目标 | 数据来源 |
|---|---|---|
| 路由准确率 | triage 是否将邮件分类到正确意图 | `primary_route` vs `expected_primary_route` |
| 升级准确率 | 系统是否在且仅在需要时升级到人工 | `needs_escalation` vs `expected_escalation` |
| 回复质量 | 草稿是否正确、相关、清晰、意图对齐 | LLM Judge 四维评分 |
| 轨迹评分 | 工作流节点执行路径是否符合预期 | 路径模板匹配 + 违规扣分 |
| 延迟指标 | 端到端和各节点耗时 | trace event 时间戳 |
| 资源指标 | token 消耗和调用次数 | LLM/tool call 元数据 |

## 2. 样本集

### 2.1 样本文件

`evals/samples/customer_support_eval_zh.jsonl`（21 条中文样本）

### 2.2 场景覆盖

| 场景类型 | 样本数 | 样本 ID | 预期行为 |
|---|---|---|---|
| `knowledge_supported` | 3 | `zh_knowledge_001`~`003` | 知识库有答案 → 草稿回复 |
| `knowledge_gap` | 3 | `zh_kb_gap_001`~`003` | 知识库无答案 → 保守草稿，不虚构 |
| `technical_issue_clarification` | 3 | `zh_tech_clarify_001`~`003` | 信息不充分 → 索要诊断信息 |
| `technical_issue_detailed` | 3 | `zh_tech_detail_001`~`003` | 信息充分 → 直接排查建议 |
| `commercial_policy_high_risk` | 2 | `zh_policy_001`~`002` | 退款/SLA → 必须升级人工 |
| `commercial_policy_standard` | 1 | `zh_policy_003` | 常规取消订阅 → 可自动草稿 |
| `feedback_intake` | 2 | `zh_feedback_001`~`002` | 功能建议/不满 → 确认收到 |
| `unrelated` | 2 | `zh_unrelated_001`~`002` | SEO/赞助 → 识别并关闭 |
| `multi_intent` | 2 | `zh_multi_001`~`002` | 混合意图 → 优先高风险路由 |

### 2.3 样本字段规范

每条样本为一行 JSON，包含以下字段：

```json
{
  "sample_id": "zh_knowledge_001",
  "scenario_type": "knowledge_supported",
  "email_subject": "如何开启单点登录",
  "email_body": "我们正在做企业接入，请问专业版如何开启 SSO ...",
  "expected_primary_route": "knowledge_request",
  "expected_escalation": false,
  "expected_route_template": "knowledge_request",
  "reference_answer_or_constraints": [
    "应说明专业版及以上支持基于 SAML 2.0 的单点登录",
    "不能虚构不在知识库中的能力"
  ]
}
```

- `expected_primary_route`：预期的一级路由分类
- `expected_escalation`：预期是否需要人工升级
- `expected_route_template`：轨迹评估所使用的路径模板 key
- `reference_answer_or_constraints`：人工标注的回复质量约束（供人工审查，不参与自动评分）

## 3. 评分计算规则

### 3.1 路由准确率（Route Accuracy）

```
route_accuracy = count(primary_route == expected_primary_route) / total_samples
```

精确匹配，不区分子路由。取值范围 `[0.0, 1.0]`。

### 3.2 升级准确率（Escalation Accuracy）

```
escalation_accuracy = count(needs_escalation == expected_escalation) / total_samples
```

布尔精确匹配。过度升级（false positive）和漏升级（false negative）同等计入失败。

### 3.3 回复质量评分（Response Quality）

#### LLM Judge（主评分器）

由独立的 LLM 作为 Judge，对系统生成的草稿进行四维评分：

| 子维度 | 含义 | 分值范围 |
|---|---|---|
| `relevance` | 草稿是否回应了客户的核心问题 | 1~5 |
| `correctness` | 内容是否事实正确、不虚构 | 1~5 |
| `intent_alignment` | 回复策略是否匹配意图（如 knowledge 走知识回答，feedback 走确认收到） | 1~5 |
| `clarity` | 表述是否清晰、结构合理 | 1~5 |

综合分 = 四维均值：

```
overall_score = (relevance + correctness + intent_alignment + clarity) / 4
```

Judge 通过 `with_structured_output` 调用 LLM，要求返回严格 JSON。最多重试 3 次，全部失败则标记为 `unavailable`。

Judge prompt 位于 `src/prompts/response_quality_judge.txt`，输入包括原始邮件、草稿文本、知识证据摘要、策略说明、路由类型和最终动作。

#### 规则基线（Rule-Based Baseline）

`RuleBasedResponseQualityBaseline` 提供一个不依赖 LLM 的确定性评分，用于：
- 当 Judge LLM 不可用时作为 fallback
- 与 LLM Judge 评分做对比，检测 Judge 偏差

基线评分规则：

| 条件 | 分值影响 |
|---|---|
| 无草稿文本 | 四维全部 = 1 |
| 有草稿文本（默认） | relevance=5, correctness=4, intent_alignment=4, clarity=4 |
| `commercial_policy_request` 路由 + 草稿或策略中含 "policy" | correctness 提升到 5 |
| `technical_issue` + 澄清动作 + 覆盖 ≥3 个诊断关键词 | correctness 和 intent_alignment = 5 |
| `unrelated` 路由 + 草稿 < 240 字符 | clarity = 5 |
| 有知识证据 + knowledge/technical 路由 | correctness +1（上限 5） |
| 草稿 < 40 字符 | clarity ≤ 3 |

#### Judge 状态跟踪

每条样本记录 Judge 的执行状态：

- `succeeded`：LLM Judge 成功返回结构化评分
- `failed`：3 次重试全部失败
- `unavailable`：trace 中无 Judge 事件

报告聚合统计三类状态的计数，用于监控 Judge 的可用性。

### 3.4 轨迹评分（Trajectory Evaluation）

#### 路径模板

系统为每种路由定义了期望的节点执行路径：

| 模板 Key | 期望路径 |
|---|---|
| `knowledge_request` | triage → knowledge_lookup → draft_reply → qa_review → create_gmail_draft |
| `technical_issue` | triage → knowledge_lookup → draft_reply → qa_review → create_gmail_draft |
| `technical_issue_clarify` | triage → clarify_request → create_gmail_draft → awaiting_customer_input |
| `commercial_policy_request` | triage → policy_check → customer_history_lookup → draft_reply → qa_review → create_gmail_draft |
| `commercial_policy_request_high_risk` | triage → policy_check → customer_history_lookup → escalate_to_human |
| `feedback_intake` | triage → draft_reply → qa_review → create_gmail_draft |
| `unrelated` | triage → close_ticket |

模板选择逻辑（`_select_expected_template_key`）：
- `technical_issue` + (`needs_clarification` 或 `final_action == request_clarification`) → `technical_issue_clarify`
- `commercial_policy_request` + (`needs_escalation` 或 `final_action == handoff_to_human`) → `commercial_policy_request_high_risk`
- 其余使用 `primary_route` 作为 key

#### 违规检测与扣分

从满分 5.0 开始，逐项扣分（下限 0.0）：

| 违规类型 | 扣分 | 触发条件 |
|---|---|---|
| `missing_required_node` | -1.5 | 期望路径中的节点未出现在实际执行路径中 |
| `wrong_order` | -1.0 | 节点出现但执行顺序与期望不符 |
| `missed_escalation` | -2.0 | ticket 标记了 `needs_escalation` 但未执行 `escalate_to_human` |
| `missed_clarification` | -2.0 | ticket 标记了 `needs_clarification` 但未执行 `clarify_request` |
| `unexpected_auto_draft` | -1.5 | 高风险商业政策 ticket 走了 `create_gmail_draft` 而非升级 |

违规可叠加。例如缺少 2 个必需节点 = -3.0，最终得分 2.0。

### 3.5 延迟指标（Latency Metrics）

从 trace event 的时间戳计算：

| 指标 | 含义 |
|---|---|
| `end_to_end_ms` | 单次 run 的端到端延迟 |
| `slowest_node` | 耗时最长的图节点名 |
| `slowest_call` | 耗时最长的单次事件（含 event_name 和 latency_ms） |
| `node_latencies` | 各节点平均延迟（同名节点多次执行取均值） |
| `llm_call_latencies` | 各 LLM 调用延迟 |
| `tool_call_latencies` | 各 tool 调用延迟 |

### 3.6 资源指标（Resource Metrics）

| 指标 | 含义 |
|---|---|
| `prompt_tokens_total` | 所有 LLM 调用的 prompt token 总计 |
| `completion_tokens_total` | 所有 LLM 调用的 completion token 总计 |
| `total_tokens` | prompt + completion |
| `llm_call_count` | LLM 调用次数 |
| `tool_call_count` | tool 调用次数 |
| `token_coverage_ratio` | 有真实 token 统计的调用比例（区分 provider_actual / estimated / unavailable） |

## 4. 报告结构

评测报告输出到 `--report-path` 指定的 JSON 文件，顶层结构：

```json
{
  "mode": { ... },
  "records": [ ... ],
  "summary": { ... }
}
```

### 4.1 `mode`：运行环境配置

记录本次评测的完整环境快照：LLM 模型、embedding 模型、知识源路径、是否重建索引、Gmail 状态等。用于结果可复现性保证。

### 4.2 `records`：逐条样本结果

每条记录包含：

| 字段 | 说明 |
|---|---|
| `sample_id` | 样本唯一标识 |
| `scenario_type` | 场景类型 |
| `trace_id` | trace 链路 ID |
| `primary_route` / `expected_primary_route` | 实际 vs 预期路由 |
| `needs_escalation` / `expected_escalation` | 实际 vs 预期升级 |
| `final_action` | 运行最终动作（create_draft / handoff_to_human / request_clarification / skip_unrelated） |
| `http_status` | API 响应状态码（202 = 成功入队） |
| `response_quality` | LLM Judge 评分结果 |
| `response_quality_status` | Judge 执行状态 |
| `response_quality_baseline` | 规则基线评分 |
| `trajectory_evaluation` | 轨迹评分、期望路径、实际路径、违规列表 |
| `latency_metrics` | 延迟指标 |
| `resource_metrics` | 资源指标 |

### 4.3 `summary`：聚合统计

```json
{
  "total_samples": 21,
  "route_accuracy": 1.0,
  "escalation_accuracy": 0.81,
  "avg_response_quality_score": 4.447,
  "avg_trajectory_score": 4.048,
  "response_quality_judge": {
    "succeeded_count": 19,
    "failed_count": 0,
    "unavailable_count": 2
  },
  "failed_samples": [ ... ]
}
```

`failed_samples` 包含任何以下条件为真的样本：
- 路由不匹配
- 升级不匹配
- 轨迹评分 < 5.0
- HTTP 状态码不在 {202, 502}
- Judge 状态不为 `succeeded`

## 5. 运行方式

### 5.1 标准运行

```bash
python scripts/run_real_eval.py ^
  --samples-path evals/samples/customer_support_eval_zh.jsonl ^
  --report-path .artifacts/evals/customer_support_eval_zh_report.json ^
  --rebuild-index
```

### 5.2 参数说明

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--samples-path` | `evals/samples/customer_support_eval_zh.jsonl` | 样本集路径 |
| `--report-path` | `.artifacts/evals/real_eval_report.json` | 报告输出路径 |
| `--api-base-url` | 无（自动启动本地服务） | 使用已运行的 API 服务 |
| `--host` | `127.0.0.1` | 本地服务 host |
| `--port` | `8000` | 本地服务端口 |
| `--request-timeout-seconds` | `180` | 单次 HTTP 请求超时 |
| `--knowledge-source-path` | 无（使用配置默认值） | 覆盖知识源文档路径 |
| `--knowledge-db-path` | 无（使用配置默认值） | 覆盖向量库路径 |
| `--rebuild-index` | 否 | 备份现有索引并重建 |
| `--keep-gmail-enabled` | 否 | 保持 Gmail 启用（默认关闭） |

### 5.3 运行流程

1. **环境准备**：关闭 Gmail、清除评测用户的历史 customer memory、重建知识索引（如指定）
2. **启动服务**：自动启动本地 API server + ticket worker（或连接已有服务）
3. **逐条执行**：对每个样本执行 ingest-email → run → 等待完成 → 采集 snapshot + trace
4. **评分计算**：从 trace 中提取路由、升级、轨迹、质量、延迟、资源指标
5. **增量写入**：每完成一条样本立即更新报告文件（`in_progress: true`），支持中途查看进度
6. **最终输出**：全部完成后写入最终报告（`in_progress: false`）

## 6. 优化实践

### 6.1 已实施的优化：Hard/Soft 升级合并策略

#### 问题

triage 阶段采用规则引擎 + LLM 双路判断，合并时使用 OR 逻辑：

```python
needs_escalation = llm_output.needs_escalation or rule_output.needs_escalation
needs_clarification = llm_output.needs_clarification or rule_output.needs_clarification
```

规则引擎的关键词匹配对中文覆盖度低，产生大量 false positive：
- 多个场景仅匹配到 1 个信号分，confidence 降为 0.55，低于 0.60 阈值触发升级
- `_collect_clarification_reasons` 使用"缺失关键词 = 信息缺失"的反向逻辑，无法覆盖开放集的中文表达
- OR 合并使规则误判无法被 LLM 纠正

#### 方案

将升级原因拆分为 **hard**（硬性护栏）和 **soft**（启发式信号）两类：

**Hard（非协商，始终升级）**：
- 退款标签命中
- 争议扣费关键词
- SLA/补偿/安全/法律/合同关键词
- QA 失败次数 ≥ 2
- 客户需要人工审批

**Soft（LLM 可覆盖）**：
- 路由置信度 < 0.60
- 知识证据不充分

**Clarification（完全信任 LLM）**：
- "邮件是否已提供充分的诊断信息" 是语义判断任务
- LLM 远优于关键词匹配，直接以 LLM 判断为准

合并逻辑：

```python
# 升级：hard 强制，soft 让 LLM 决定
if has_hard_escalation:
    needs_escalation = True
else:
    needs_escalation = llm_output.needs_escalation

# 澄清：完全信任 LLM
needs_clarification = llm_output.needs_clarification
```

#### 涉及文件

| 文件 | 改动 |
|---|---|
| `src/triage/rules.py` | `_collect_escalation_reasons` 返回 `(hard, soft)` 二元组 |
| `src/triage/models.py` | `TriageDecision` 增加 `hard_escalation_reasons`、`soft_escalation_reasons` 字段 |
| `src/triage/service.py` | 解包 hard/soft 并传入 `TriageDecision` |
| `src/agents/triage_agent.py` | `_merge_triage_outputs` 按 hard/soft 分别处理 |

### 6.2 优化效果

#### 基线（优化前）

| 指标 | 值 |
|---|---|
| 路由准确率 | 100% |
| 升级准确率 | 66.7% |
| 平均回复质量 | 4.095 |
| 平均轨迹评分 | 3.548 |

#### 优化后

| 指标 | 值 | 变化 |
|---|---|---|
| 路由准确率 | 100% | — |
| 升级准确率 | **81.0%** | **+14.3pp** |
| 平均回复质量 | **4.447** | **+0.352** |
| 平均轨迹评分 | **4.048** | **+0.500** |

#### 逐条改善明细

| 样本 | 优化前 | 优化后 | 变化原因 |
|---|---|---|---|
| `zh_kb_gap_002` | 过度升级, traj=0.5 | 正确草稿, traj=5.0 | rule 低 confidence 不再强制升级 |
| `zh_kb_gap_003` | 过度升级, traj=0.5 | 正确草稿, traj=5.0 | 同上 |
| `zh_tech_clarify_002` | 过度升级, traj=1.5 | 正确澄清, traj=3.5 | 同上 |
| `zh_policy_003` | 过度升级 | 正确草稿, traj=5.0 | soft 升级被 LLM 覆盖 |
| `zh_unrelated_002` | 过度升级, traj=3.5 | 正确关闭, traj=5.0 | 同上 |
| `zh_tech_detail_002` | clarify, traj=3.5 | 知识草稿, traj=5.0 | LLM 判断信息充分 |

### 6.3 待优化方向

#### QA Agent 过度升级

`zh_feedback_001/002` 在 QA review 后被 LLM 判定 `escalate=True`。`zh_tech_detail_001/003` 在 3 次 QA 重写后因 retry limit 升级。这些不在 triage 合并策略范围内，需要从 QA prompt 或 `_merge_qa_handoff_outputs` 逻辑侧优化。

#### 轨迹模板适配 Gmail-disabled 模式

当前轨迹模板中的 `create_gmail_draft` 在 Gmail 关闭时不会执行，导致 clarify/feedback 路径被扣 1.5 分。可通过在评测模式下提供 Gmail-disabled 专用模板来消除此系统性偏差。

#### 回复质量 baseline 的中文覆盖

`RuleBasedResponseQualityBaseline` 中的关键词检查（如 "error"、"steps"、"environment"、"expected"）为英文硬编码，对中文样本不生效。
