# Postmortem：QA Agent 三轮重写死循环

## 1. 现象

在 21 条中文样本的端到端评测中，`zh_tech_detail_001/002/003`（技术问题详细诊断场景）全部走入了 `draft → QA → draft → QA → draft → QA → escalate_to_human` 的三轮重写死循环，最终因 `rewrite_count >= 3` 被强制升级到人工。

预期行为：这三条样本的邮件已提供充分的诊断信息（错误信息、环境、复现步骤），应直接草稿回复并通过 QA，不需要升级。

评测指标影响：升级准确率从 81.0% 降至 76.2%，三条样本的 trajectory 评分均为 3.5/5.0。

---

## 2. 调查过程

### 2.1 第一层：查看 Trace Events

从数据库中提取 `zh_tech_detail_001` 的 trace events，发现：

- 三轮 QA review 的 metadata 均为 `{"approved": false, "escalate": false, "logic_type": "deterministic_fallback"}`
- **没有任何 QA 相关的 `llm_call` 类型事件**被记录

`deterministic_fallback` 意味着 LLM 调用失败，系统回退到了确定性规则路径。`llm_call` 事件缺失是因为 `qa_handoff_agent_detailed` 捕获异常后返回 `llm_invocation=None`，导致 `_record_llm_invocation` 的 `if agent_result.llm_invocation is not None` 条件不满足。

**关键推论**：问题不是"LLM 判断错误"，而是"LLM 调用根本没成功"。

### 2.2 第二层：直接调用 QA LLM

单独调用 `invoke_qa_handoff_agent`，5 次中 3-5 次抛出 `ValidationError`：

```
3 validation errors for QaHandoffOutput
rewrite_guidance
  Input should be a valid array [type=list_type, input_value='', input_type=str]
escalate
  Field required [type=missing, ...]
needs_escalation
  Extra inputs are not permitted [type=extra_forbidden, input_value=False, input_type=bool]
```

LLM（qwen3-max / qwen3-235b-a22b-instruct）返回的 JSON 有三个系统性偏差：

| 期望字段 | LLM 实际返回 | 原因 |
|---|---|---|
| `"escalate": bool` | `"needs_escalation": bool` | prompt 输入变量名是 `needs_escalation`，LLM 把它"回显"成了输出字段名 |
| `"rewrite_guidance": []` | `"rewrite_guidance": ""` | LLM 将空数组压缩为空字符串 |
| — | `"escalate"` 字段缺失 | 被 `needs_escalation` 替代了 |

`QaHandoffOutput` 配置了 `extra="forbid"`，Pydantic 直接拒绝了 `needs_escalation` 这个未知字段。

### 2.3 第三层：为什么确定性 fallback 没有放行？

如果 LLM 失败，系统回退到 `_build_deterministic_qa_handoff_output`。对于 `rewrite_count=1` 且草稿质量正常，确定性规则应返回 `approved=True`。但 trace 显示三轮都是 `approved=false`。

继续追踪发现第二个叠加问题——**`knowledge_confidence` 被 merge 策略拉低到 0.0**：

```
knowledge_lookup 的 _merge_knowledge_policy_outputs：
  knowledge_confidence = min(llm_output.knowledge_confidence, deterministic_output.knowledge_confidence)
```

- 确定性规则对 `technical_issue` + 无 RAG 结果给出 `0.65`
- LLM 看到空的 `knowledge_answers` 返回 `0.0`
- merge 取 `min(0.0, 0.65) = 0.0`

同时 `retrieval_hit = False`（确定性判断：RAG 没有返回实质性答案）。

QA 确定性规则中的分支逻辑：

```python
# Line 162: 有检索命中但置信度低 → 升级
if knowledge_confidence < 0.6 and retrieval_hit and ...:
    return escalate=True

# Line 176: 无检索命中且置信度低 → 重写（不升级）
if knowledge_confidence < 0.6 and not retrieval_hit and ...:
    return approved=False, escalate=False, rewrite_guidance=[...]
```

`knowledge_confidence=0.0 + retrieval_hit=False` 命中了第 176 行：返回 `approved=False, escalate=False`，附带保守重写指导。但重写不会改变 `knowledge_confidence`（它是 `knowledge_lookup` 节点的输出，不会被 `draft_reply` 更新），所以每轮 QA 都命中同一个分支，形成死循环。

### 2.4 完整因果链

```
knowledge_lookup:
  RAG 未检索到相关内容 → knowledge_answers=[]
  确定性: knowledge_confidence=0.65, retrieval_hit=False
  LLM: knowledge_confidence=0.0
  merge: min(0.0, 0.65)=0.0, retrieval_hit=False

draft_reply (Round 1):
  生成高质量技术排查草稿 → rewrite_count=1

qa_review (Round 1):
  LLM 调用 → ValidationError（字段名冲突）→ 异常被捕获
  fallback 确定性规则：
    knowledge_confidence=0.0 < 0.6 AND not retrieval_hit
    → approved=False, escalate=False, rewrite_guidance=["保守回复..."]
  route_after_qa: not approved, not escalate, rewrite_count=1 < 3 → draft_reply

draft_reply (Round 2): → rewrite_count=2
qa_review (Round 2): 同上 → draft_reply

draft_reply (Round 3): → rewrite_count=3
qa_review (Round 3): 同上 → approved=False, escalate=False
  route_after_qa: rewrite_count=3 >= 3 → escalate_to_human
```

两个独立问题叠加导致了三轮死循环：

1. **QA LLM 输出格式不稳定**（直接原因）：schema 解析失败，回退到确定性路径
2. **knowledge_confidence min-merge 过于保守**（根本原因）：确定性路径中 `knowledge_retrieval_miss` 分支永远返回"需要重写"

任一问题被修复都能打破循环——如果 LLM 调用成功，它会判断草稿质量合格直接 approve；如果 confidence 不被拉到 0.0，确定性路径也会 approve。

---

## 3. 根因分析

### 3.1 Prompt 输入变量名与 Schema 输出字段名冲突

**prompt（qa_handoff_agent.txt）** 中的输入变量：

```
needs_escalation={needs_escalation}
```

**QaHandoffOutput schema** 中的输出字段：

```python
escalate: bool = Field(...)  # 不是 needs_escalation
```

qwen3 系列模型在生成 structured output 时，会将 prompt 中出现的变量名"泄漏"到输出 JSON 的字段名中。当输入用 `needs_escalation`，模型就倾向于输出 `"needs_escalation"` 而非 schema 定义的 `"escalate"`。

这是一种典型的 **prompt-schema naming collision**：模型在两个冲突的信号源（prompt 文本 vs JSON schema 定义）之间做了错误的优先级选择。

### 3.2 Pydantic strict validation 没有容错

`QaHandoffOutput` 使用了 `ConfigDict(extra="forbid")`，这在类型安全上是正确的，但对 LLM 输出来说过于严格。LLM 不是 API client，它的输出天然有格式偏差的可能。对于 LLM 输出的 Pydantic model，需要在 strict validation 之前加一层"输入规范化"。

### 3.3 knowledge_confidence 的 min-merge 策略不合理

`_merge_knowledge_policy_outputs` 对 `knowledge_confidence` 使用 `min()` 合并，意图是"保守取低值"。但当 LLM 对"无检索结果"场景系统性地返回极低 confidence（0.0~0.5）时，`min()` 会无条件压低确定性规则给出的合理默认值（0.65），导致下游 QA 确定性路径的 `knowledge_retrieval_miss` 分支被错误触发。

---

## 4. 修复方案

### 4.1 消除 prompt-schema 命名冲突

**文件**：`src/prompts/qa_handoff_agent.txt`、`src/agents/qa_handoff_agent.py`

将 prompt 输入变量从 `needs_escalation` 重命名为 `triage_escalation_flag`，彻底消除与输出字段 `escalate` 的语义重叠。同时在 prompt 中新增 `IMPORTANT — output field names` 段落，明确约束输出字段名和类型：

```
IMPORTANT — output field names:
- Use `escalate` (not `needs_escalation`) for the boolean escalation decision.
- Use `rewrite_guidance` as a JSON array of strings (use `[]` when empty, never `""`).
```

### 4.2 添加 Pydantic model_validator 防御层

**文件**：`src/contracts/outputs.py`

在 `QaHandoffOutput` 上添加 `model_validator(mode="before")`，在 Pydantic 严格校验之前做字段修正：

```python
@model_validator(mode="before")
@classmethod
def _normalize_llm_field_names(cls, data):
    if not isinstance(data, dict):
        return data
    # 字段名映射：needs_escalation → escalate
    if "needs_escalation" in data and "escalate" not in data:
        data["escalate"] = data.pop("needs_escalation")
    elif "needs_escalation" in data and "escalate" in data:
        data.pop("needs_escalation")
    # 空字符串 → 空数组
    for list_field in ("issues", "rewrite_guidance"):
        value = data.get(list_field)
        if isinstance(value, str):
            data[list_field] = [value] if value.strip() else []
    return data
```

### 4.3 修复效果

| 指标 | 修复前 | 修复后 |
|---|---|---|
| QA LLM 调用成功率 | 0~20%（格式不稳定） | 100%（5/5 + 6/6） |
| fallback_used | 每次 True | 每次 False |
| 死循环场景 | 3 条样本全部触发 | 不再触发 |

---

## 5. 经验教训

### 5.1 LLM 输出不是 API 调用——不能假设格式稳定

即使使用了 `with_structured_output` + JSON schema，LLM 的输出仍然可能偏离 schema。常见偏差模式：

| 偏差类型 | 示例 | 应对 |
|---|---|---|
| **字段名回显** | prompt 输入叫 `needs_escalation`，输出也用这个名字替代 schema 定义的 `escalate` | 避免输入变量名与输出字段名语义重叠 |
| **类型坍缩** | 空数组 `[]` 被压缩为空字符串 `""` | 在 model_validator(mode="before") 中做类型修正 |
| **字段遗漏** | required 字段被同义词替代后缺失 | 在 model_validator 中做别名映射 |
| **额外字段** | 输出包含 schema 未定义的字段 | 视情况选择 `extra="ignore"` 或在 before validator 中清理 |

**设计原则**：对 LLM 输出的 Pydantic model，永远需要一层 `mode="before"` 的规范化。`extra="forbid"` 可以保留（确保下游不会用到未定义字段），但必须在 forbid 之前先修正已知的偏差模式。

### 5.2 Prompt 变量命名是 Schema 设计的一部分

prompt 中的输入变量名不仅是"给 LLM 看的标签"，它会直接影响 LLM 对输出字段名的选择。当 prompt 同时包含输入变量和输出 schema 时：

- **输入变量名不应与输出字段名语义重叠**：`needs_escalation`（输入） vs `escalate`（输出）就是典型的冲突
- **如果必须传递语义相近的信息，使用明确区分的前缀**：如 `triage_escalation_flag`

这个问题在使用 OpenAI 原生 function calling 的模型上可能不明显（因为 schema 约束更强），但在通过 OpenAI-compatible API 接入的模型上（如 qwen3），prompt 文本对输出格式的影响更大。

### 5.3 Fallback 路径需要"终止条件"审计

当系统有 LLM + 确定性规则的双路判断时，需要审计 fallback 路径是否会产生死循环：

1. **列出所有可能让 LLM 失败的场景**（网络错误、格式偏差、超时……）
2. **对每个 fallback 路径，验证它是否有确定性的终止条件**
3. **特别关注"非 approve 非 escalate"的中间态**——它会触发 retry，但如果触发条件不会随 retry 改变，就是死循环

在本案例中，`knowledge_retrieval_miss` 分支返回"需要重写"，但 `knowledge_confidence` 不会被 `draft_reply` 更新。这个 retry 本质上是无效的——它期望 drafting agent 能在没有新知识的情况下写出更好的回复，但 QA 的判断依据（confidence）不会改变。

### 5.4 min() 合并策略在 LLM 系统中需要特别谨慎

`min(llm_confidence, rule_confidence)` 的意图是保守安全，但在 LLM 系统中有一个隐含假设：**LLM 的低置信度输出是有信息量的**。

实际上，当 RAG 没有检索到结果时，LLM 看到空的 `knowledge_answers=[]` 就机械地返回 `confidence=0.0`，这不代表"LLM 认为答案不可靠"，而是"LLM 没有足够信息来给出置信度"。用 `min()` 把这个无信息的 0.0 传递到下游，等于把噪声放大为信号。

更合理的策略：

```python
# 只在 LLM 有实质性判断时采纳其 confidence
if llm_has_substantive_knowledge:
    confidence = min(llm_conf, det_conf)
else:
    confidence = det_conf  # 信任确定性规则的默认值
```

### 5.5 Eval 报告中的"全部失败"是最强的调查信号

当 eval 中某一类场景（如 `technical_issue_detailed`）的所有样本都以相同方式失败时，通常意味着：

- **不是 LLM 判断质量问题**（那样会有概率性分布）
- **是系统性的工程问题**（格式解析、数据流、状态传递……）

这种模式应该优先调查"为什么 100% 失败"而非"为什么判断不准确"。

---

## 6. 关联设计文档

| 文档 | 相关内容 |
|---|---|
| `evals/README.zh-CN.md` §6.3 | QA Agent 过度升级的已知问题描述 |
| `docs/project-flow-diagrams.zh-CN.md` §5 | LangGraph 节点工作流中的 `qa_review → draft_reply` 循环 |
| `docs/customer-support-copilot-interview-qa.zh-CN.md` | 面试问答中关于 LLM + 规则双路判断的设计取舍 |

## 7. 涉及文件

| 文件 | 修改内容 |
|---|---|
| `src/prompts/qa_handoff_agent.txt` | 输入变量 `needs_escalation` → `triage_escalation_flag`；新增输出字段名约束段 |
| `src/agents/qa_handoff_agent.py` | `invoke_qa_handoff_agent` 的 `input_variables` 和 `inputs` 同步改名 |
| `src/contracts/outputs.py` | `QaHandoffOutput` 添加 `model_validator(mode="before")` 做字段修正 |
