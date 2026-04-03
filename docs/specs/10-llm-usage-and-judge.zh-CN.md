# Customer Support Copilot LLM Usage And Judge 规格

## 1. 目的

本文档把“真实 provider usage 采集 + 正式 LLM judge 协议”收敛为 V1.1 可执行规范。

本规格要解决两个问题：

1. 资源指标不能长期依赖词数估算而不标注来源
2. `response_quality` 不能继续由规则硬编码冒充正式 judge

如与以下文档局部冲突，本规格优先：

1. `docs/specs/05-trace-and-eval.zh-CN.md`
2. `docs/customer-support-copilot-technical-design.zh-CN.md`

---

## 2. 固定原则

### 2.1 资源指标原则

1. 能拿真实 token usage 时，必须使用真实值
2. 拿不到真实 token usage 时，允许降级估算
3. 只要发生降级，必须显式标记 `token_source`
4. 不允许把估算值伪装成真实 provider usage

### 2.2 Judge 原则

1. `response_quality` 的正式实现固定为 `LLM-as-a-judge`
2. `trajectory_evaluation` 仍固定为规则脚本主导
3. judge 失败不得阻塞 Ticket 主流程
4. 但 judge 失败必须留下可观测痕迹

---

## 3. 目录与实现边界约束

为避免后续实现分散、重复、不可追踪，目录落点固定如下：

1. 新增 `src/llm_runtime.py`：统一封装 LLM 调用与 usage 提取
2. `src/agents.py`：只能通过 `llm_runtime` 发起模型调用
3. `src/observability.py`：只负责汇总，不直接猜 provider usage 来源
4. `src/api/services.py`：只负责调用 judge，不直接拼 judge JSON

明确禁止：

1. 在 `nodes.py` 或 `agents.py` 内各自实现一套 token 提取逻辑
2. 一部分调用走 wrapper，一部分直接 `.invoke()`
3. 用 regex 从自由文本里猜 judge 分数

---

## 4. LLM 调用统一封装合同

### 4.1 正式入口

所有面向业务的 LLM 调用必须统一通过 `src/llm_runtime.py` 完成。

正式 wrapper 输出结构固定为：

```json
{
  "parsed_output": {},
  "raw_text": "...",
  "model": "gpt-4o-mini",
  "provider": "openai-compatible",
  "usage": {
    "prompt_tokens": 123,
    "completion_tokens": 45,
    "total_tokens": 168,
    "token_source": "provider_actual"
  },
  "request_id": "req_...",
  "finish_reason": "stop"
}
```

### 4.2 `token_source` 枚举

固定取值：

1. `provider_actual`
2. `provider_mapped`
3. `estimated`
4. `unavailable`

语义固定如下：

#### `provider_actual`

直接从 provider 原始 usage 字段获得。

#### `provider_mapped`

从 OpenAI-compatible 响应的兼容字段映射获得。

#### `estimated`

无法拿到真实 usage，退化为估算。

#### `unavailable`

既无真实值，也未做估算。

---

## 5. Usage 提取优先级

### 5.1 固定优先级

usage 提取顺序固定为：

1. provider SDK 或响应对象上的原生 usage 字段
2. `response_metadata` 中兼容的 usage 字段
3. wrapper 层显式映射的兼容 usage 字段
4. `estimate_token_usage()`
5. 标记为 `unavailable`

### 5.2 明确禁止

1. 跳过真实 usage 直接走估算
2. 拿到部分 usage 时随意补零而不标记来源
3. 不标记 `token_source` 就把值写进 trace

---

## 6. `llm_call` 事件 metadata 合同

每个 `llm_call` 事件的 `metadata` 必须包含：

1. `model`
2. `provider`
3. `prompt_tokens`
4. `completion_tokens`
5. `total_tokens`
6. `token_source`

允许附加：

1. `request_id`
2. `finish_reason`
3. `prompt_version`
4. `judge_name`

### 6.1 字段规则

#### `prompt_tokens` / `completion_tokens` / `total_tokens`

1. 当 `token_source in ('provider_actual', 'provider_mapped', 'estimated')` 时必须为整数
2. 当 `token_source = 'unavailable'` 时必须为 `null`

#### `total_tokens`

固定规则：

1. 若前两者存在，则 `total_tokens = prompt_tokens + completion_tokens`
2. 不允许单独写一个互相对不上的 `total_tokens`

---

## 7. 资源汇总指标修订

### 7.1 保留字段

原有字段继续保留：

1. `prompt_tokens_total`
2. `completion_tokens_total`
3. `total_tokens`
4. `llm_call_count`
5. `tool_call_count`

### 7.2 必须新增字段

资源汇总必须新增：

1. `actual_token_call_count`
2. `estimated_token_call_count`
3. `unavailable_token_call_count`
4. `token_coverage_ratio`

### 7.3 计算规则

1. `actual_token_call_count = provider_actual + provider_mapped`
2. `estimated_token_call_count = token_source == estimated` 的调用数
3. `unavailable_token_call_count = token_source == unavailable` 的调用数
4. `token_coverage_ratio = actual_token_call_count / llm_call_count`，保留 3 位小数

### 7.4 输出约束

如果某次 run 全部是估算：

1. 仍可输出 `prompt_tokens_total` / `completion_tokens_total` / `total_tokens`
2. 但 `token_coverage_ratio` 必须为 `0`

---

## 8. `ResponseQualityJudge` 正式合同

### 8.1 固定实现

`response_quality` 的正式实现固定为：

1. OpenAI-compatible chat model
2. `temperature = 0`
3. 结构化 JSON 输出
4. 最多重试 `2` 次 JSON 纠正

### 8.2 Judge 输入

必须固定包含以下输入：

1. 原始邮件主题
2. 原始邮件正文
3. 最终草稿正文
4. 证据摘要
5. 策略约束摘要
6. 主路由

### 8.3 Judge 输出 schema

Judge 必须输出严格 JSON：

```json
{
  "relevance": 5,
  "correctness": 4,
  "intent_alignment": 4,
  "clarity": 4,
  "reason": "The draft addresses the request directly and stays within policy boundaries."
}
```

固定规则：

1. 不允许额外键
2. 不允许 markdown code fence
3. 不允许自由文本混排

### 8.4 评分约束

1. 每个维度必须是 `1` 到 `5` 的整数
2. `overall_score` 仍由系统按平均值计算
3. 不允许让 judge 直接输出 `overall_score`

原因：

1. 避免 judge 和系统各算一套总分

---

## 9. Judge 失败策略

### 9.1 在线主流程

如果在线 run 的 judge 调用失败、超时、结构化校验失败，则：

1. 不得让 Ticket 主流程失败
2. `run.response_quality = null`
3. 必须记录一条失败的 `llm_call` 或 `decision` 事件
4. 必须在 run 级 metadata 中记录 `response_quality_status = failed`

### 9.2 离线评测

离线评测场景下：

1. judge 失败必须显式记入报告
2. 该样本不得伪造一个规则分数补位

### 9.3 明确禁止

1. 在线失败时悄悄回退到旧规则 judge 但不标记
2. 离线评测时静默跳过 judge 失败样本
3. 用硬编码规则长期替代正式 judge 实现

---

## 10. 旧规则评测的边界

现有规则式 `ResponseQualityJudge` 允许保留的唯一用途：

1. 作为开发期对照基线
2. 作为单元测试中的 deterministic fixture

明确禁止：

1. 继续作为线上 `response_quality` 正式来源

如果代码中仍保留旧规则实现，命名必须明确体现：

1. `RuleBasedResponseQualityBaseline`

禁止继续命名为：

1. `ResponseQualityJudge`

---

## 11. 配置合同

### 11.1 Judge 模型配置

新增配置键固定为：

1. `LLM_JUDGE_MODEL`
2. `LLM_JUDGE_TIMEOUT_SECONDS`

规则：

1. 若未设置 `LLM_JUDGE_MODEL`，默认回退到 `LLM_CHAT_MODEL`
2. 但 judge 与业务主模型的调用仍必须通过独立 wrapper 路径记录

### 11.2 Prompt 版本

judge 调用必须记录：

1. `prompt_version`

V1.1 固定首个版本名：

1. `response_quality_judge_v1`

---

## 12. 测试要求

### 12.1 单元测试

至少覆盖：

1. usage 提取优先级
2. `token_source` 四种取值
3. `total_tokens` 计算一致性
4. judge JSON schema 校验

### 12.2 集成测试

至少覆盖：

1. provider 返回真实 usage 时正确落 trace
2. provider 无 usage 时落为 `estimated`
3. judge 超时不阻塞 Ticket run
4. judge 成功时 `response_quality` 结构与 spec 一致

### 12.3 回归测试

至少覆盖：

1. `GET /tickets/{id}/trace` 可看到新的 token 来源信息
2. `GET /metrics/summary` 聚合出 coverage 指标
3. 离线 eval 报表能区分 judge 成功与失败

---

## 13. 验收标准

满足以下条件时，本规格视为落地完成：

1. 所有业务 LLM 调用已统一通过 `llm_runtime` 封装
2. `llm_call.metadata` 已固定包含 `token_source`
3. 资源指标能区分真实 usage、估算 usage、不可用 usage
4. 线上 `response_quality` 已由正式 LLM judge 产生
5. judge 失败不会阻塞主流程，但可被 trace / report 观测到

