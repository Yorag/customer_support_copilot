# Customer Support Copilot Routing Decision Table 规格

## 1. 目的

本文档把 triage 规则收敛为可实现、可测试、可复现的决策表。

Triage 输出必须包含：

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

---

## 2. 一级路由

允许值：

1. `knowledge_request`
2. `technical_issue`
3. `commercial_policy_request`
4. `feedback_intake`
5. `unrelated`

约束：

1. 每封邮件只能有一个 `primary_route`
2. `secondary_routes` 最多 2 个
3. `tags` 最多 5 个

---

## 3. 主决策表

| 规则编号 | 条件 | `primary_route` | `response_strategy` |
|---|---|---|---|
| `R1` | 用户主要在问功能、能力边界、使用方式、配置说明 | `knowledge_request` | `answer` |
| `R2` | 用户已尝试操作且描述报错、失败、异常、不可用 | `technical_issue` | `troubleshooting` |
| `R3` | 用户涉及计费、账单、退款、取消、补偿、SLA、承诺边界 | `commercial_policy_request` | `policy_constrained` |
| `R4` | 用户主要在表达意见、抱怨、体验评价、功能建议 | `feedback_intake` | `acknowledgement` |
| `R5` | 与产品支持无关的垃圾、推销、招聘、合作邀约 | `unrelated` | `acknowledgement` |

### 3.1 冲突优先级

多类条件同时满足时，按以下顺序选择主路由：

1. `commercial_policy_request`
2. `technical_issue`
3. `knowledge_request`
4. `feedback_intake`
5. `unrelated`

说明：

1. 商业政策请求优先，因为受约束最强
2. 技术故障优先于知识咨询，因为已发生实际问题
3. `feedback_intake` 只在核心目标不是求解答、排障或政策动作时成立

---

## 4. 标签规则

标签枚举：

1. `feature_request`
2. `complaint`
3. `general_feedback`
4. `billing_question`
5. `refund_request`
6. `multi_intent`
7. `needs_clarification`
8. `needs_escalation`

打标规则：

| 条件 | 标签 |
|---|---|
| 要求新增功能、改进能力 | `feature_request` |
| 对体验或服务表示不满 | `complaint` |
| 一般性意见反馈 | `general_feedback` |
| 账单解释、收费构成 | `billing_question` |
| 明确要求退款、退费、撤销扣款 | `refund_request` |
| 两个及以上明确业务诉求 | `multi_intent` |
| 技术故障信息不足 | `needs_clarification` |
| 高风险或需人工介入 | `needs_escalation` |

---

## 5. `intent_confidence`

分值范围：

1. `0.000` 到 `1.000`

阈值：

1. `>= 0.85`：高置信
2. `0.60 - 0.849`：中置信
3. `< 0.60`：低置信

规则：

1. `intent_confidence < 0.60` 时，`needs_escalation = true`
2. 低置信不自动改变主路由，只提高风险

---

## 6. `priority`

基础优先级：

| 条件 | `priority` |
|---|---|
| 无关内容 | `low` |
| 一般知识咨询、一般反馈 | `medium` |
| 技术故障、账单问题、投诉 | `high` |
| 安全事故、数据丢失、法律合同、SLA、退款金额争议 | `critical` |

升级规则：

以下任一命中，优先级提升一级，最高 `critical`：

1. 明确提到生产不可用
2. 明确提到数据丢失
3. 高价值客户标记为真
4. 72 小时内重复来信 2 次以上

---

## 7. `needs_clarification`

### 7.1 只对 `technical_issue` 生效

非 `technical_issue` 默认：

1. `needs_clarification = false`

### 7.2 触发条件

以下任一命中即为真：

1. 没有复现步骤
2. 没有实际报错或异常现象
3. 没有说明预期结果和实际结果差异
4. 没有环境、账号、租户、项目等定位信息

### 7.3 结果

1. 保持 `primary_route = technical_issue`
2. 打 `needs_clarification` 标签
3. 进入 `awaiting_customer_input`
4. 生成 `clarification_request` 草稿

---

## 8. `needs_escalation`

满足以下任一项即为真：

1. 涉及退款金额
2. 涉及补偿或 SLA 承诺
3. 涉及安全事故或数据丢失
4. 涉及法律、合同或政策解释
5. `intent_confidence < 0.60`
6. 知识证据不足且仍需结论性回复
7. QA 连续失败 2 次
8. 客户历史标记 `requires_manual_approval = true`

结果：

1. 打 `needs_escalation` 标签
2. 如未生成草稿，可直接人工升级
3. 如已生成草稿，进入 `awaiting_human_review`

---

## 9. `secondary_routes`

规则：

1. 只有 `multi_intent = true` 时允许非空
2. 主诉求对应 `primary_route`
3. 次诉求最多保留两个 `secondary_routes`
4. 只保留真实影响执行路径的次路由

### 9.1 持久化同步规则

1. `multi_intent` 布尔值是权威字段。
2. `multi_intent = true` 时，`tags` 中必须包含 `multi_intent`。
3. `multi_intent = false` 时，`tags` 中不得包含 `multi_intent`。
4. `secondary_routes` 非空时，`multi_intent` 必须为 `true`。

示例：

邮件：

“本月为什么被多扣费？另外我按文档配置 SSO 也一直失败。”

输出：

1. `primary_route = commercial_policy_request`
2. `secondary_routes = ['technical_issue']`
3. `tags = ['billing_question', 'multi_intent', 'needs_escalation']`

---

## 10. 边界样例

### 10.1 知识咨询 vs 技术故障

输入：

“专业版支持 SSO 吗？”

输出：

1. `primary_route = knowledge_request`
2. `needs_clarification = false`

输入：

“我按文档配置了 SSO，但一直登录失败。”

输出：

1. `primary_route = technical_issue`

### 10.2 商业政策请求 vs 技术故障

输入：

“为什么本月账单比上月高？”

输出：

1. `primary_route = commercial_policy_request`
2. `tags = ['billing_question']`

输入：

“升级套餐时页面一直报错，导致我被重复扣费。”

输出：

1. `primary_route = commercial_policy_request`
2. `secondary_routes = ['technical_issue']`
3. `tags = ['billing_question', 'multi_intent', 'needs_escalation']`

### 10.3 反馈受理 vs 无关内容

输入：

“新版报表不好用，建议增加地区筛选。”

输出：

1. `primary_route = feedback_intake`
2. `tags = ['feature_request', 'complaint']`

输入：

“我们做海外 SEO 服务，想和贵司商务合作。”

输出：

1. `primary_route = unrelated`

---

## 11. Triage 输出 JSON 模板

```json
{
  "primary_route": "commercial_policy_request",
  "secondary_routes": [],
  "tags": ["billing_question", "refund_request", "needs_escalation"],
  "response_strategy": "policy_constrained",
  "multi_intent": false,
  "intent_confidence": 0.93,
  "priority": "high",
  "needs_clarification": false,
  "needs_escalation": true,
  "routing_reason": "The customer requests a refund for a billing issue, which requires policy-constrained handling."
}
```

---

## 12. 与当前实现的关系

当前 [structure_outputs.py](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/src/structure_outputs.py#L12) 的分类输出只有单个 `category`。

V1 必须新增：

1. 结构化 triage 输出模型
2. 路由冲突处理
3. 优先级和升级规则
4. 可离线验证的边界样本集
