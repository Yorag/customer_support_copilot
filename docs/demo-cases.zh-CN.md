# Demo Cases

本文档用于支持 `X2.3` 交付目标：把当前仓库中“可以稳定演示什么”和“当前失败边界在哪里”说明清楚。

## 1. 演示原则

当前 demo 分成两类：

1. 成功主路径 demo
   基于现有 API 集成测试，演示当前系统已经稳定实现的链路。
2. 失败边界 demo
   基于离线评测报告，展示当前系统仍然存在的路由或轨迹偏差。

这样做的原因是：

1. API 主路径已经有稳定测试覆盖。
2. 离线评测报告当前并非全绿，不适合包装成“全部成功”的演示。

## 2. Demo 环境

准备步骤：

1. 安装依赖：`pip install -r requirements.txt`
2. 初始化数据库：`python scripts/init_db.py`
3. 构建本地知识索引：`python create_index.py`
4. 配置 `.env`
5. 启动 API：`python deploy_api.py`

如果只做本地可重复演示，也可以直接运行测试：

```bash
pytest -q tests/test_api_contract.py
```

## 3. 成功主路径 Demo

### 3.1 知识问答到草稿生成

目标：

1. 演示 ticket 被成功 ingest
2. 演示 `run` 进入真实 graph
3. 演示最终进入 `draft_created`
4. 演示 trace 和 resource metrics 可查

推荐依据：

1. [tests/test_api_contract.py](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/tests/test_api_contract.py) 中的 `test_run_ticket_creates_run_trace_and_draft_created_status`

演示步骤：

1. `POST /tickets/ingest-email`
2. `POST /tickets/{ticket_id}/run`
3. `GET /tickets/{ticket_id}`
4. `GET /tickets/{ticket_id}/trace`

预期结果：

1. `processing_status = completed`
2. `business_status = draft_created`
3. `latest_draft.qa_status = passed`
4. trace 中存在事件列表、`resource_metrics` 和 `latency_metrics`

推荐请求体：

```json
{
  "source_channel": "gmail",
  "source_thread_id": "demo-thread-001",
  "source_message_id": "<demo-msg-001@gmail.com>",
  "sender_email_raw": "\"Li Wei\" <liwei@example.com>",
  "subject": "How do I configure SSO?",
  "body_text": "How do I configure SSO for my workspace?",
  "message_timestamp": "2026-04-02T10:00:00+08:00",
  "attachments": []
}
```

### 3.2 高风险商业请求升级人工

目标：

1. 演示系统不会对高风险退款/商业政策请求直接自动答复
2. 演示系统会收口到人工审核队列

推荐依据：

1. [tests/test_api_contract.py](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/tests/test_api_contract.py) 中的 `test_run_ticket_routes_high_risk_case_to_human_review`

演示步骤：

1. `POST /tickets/ingest-email`
2. `POST /tickets/{ticket_id}/run`
3. `GET /tickets/{ticket_id}`

推荐请求体：

```json
{
  "source_channel": "gmail",
  "source_thread_id": "demo-thread-risk-001",
  "source_message_id": "<demo-risk-001@gmail.com>",
  "sender_email_raw": "\"Li Wei\" <liwei@example.com>",
  "subject": "Need refund for duplicate charge",
  "body_text": "I need a refund because I was charged twice.",
  "message_timestamp": "2026-04-02T10:05:00+08:00",
  "attachments": []
}
```

预期结果：

1. `business_status = awaiting_human_review`
2. `latest_draft = null`
3. run 最终不是自动发起客户答复，而是转人工

### 3.3 人工审核与记忆回写

目标：

1. 演示 `approve`
2. 演示 `close`
3. 演示长期记忆和 metrics 汇总可查询

推荐依据：

1. [tests/test_api_contract.py](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/tests/test_api_contract.py) 中的 `test_approve_and_close_update_memory_and_metrics_queries`

建议展示接口：

1. `POST /tickets/{ticket_id}/approve`
2. `POST /tickets/{ticket_id}/close`
3. `GET /customers/{customer_id}/memory`
4. `GET /metrics/summary`

重点观察：

1. 手工动作要求 `X-Actor-Id`
2. `close` 后会留下 `human_action` run
3. `memory` 返回固定结构
4. `metrics` 能按时间窗口和路由过滤

## 4. 失败边界 Demo

当前最适合展示的失败案例来源是：

1. [tests/samples/eval/customer_support_eval_report.json](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/tests/samples/eval/customer_support_eval_report.json)

运行方式：

```bash
python scripts/run_offline_eval.py
```

当前报告摘要：

1. `total_samples = 24`
2. `route_accuracy = 0.667`
3. `escalation_accuracy = 0.5`
4. `avg_response_quality_score = 3.375`
5. `avg_trajectory_score = 2.708`

这说明：

1. 系统已具备离线可评测能力
2. 但当前路由和轨迹还没有达到可作为自动门禁的水平

### 4.1 失败案例：知识缺口被误判为 unrelated

样本：

1. `eval_kb_gap_003`

现象：

1. `expected_primary_route = knowledge_request`
2. `primary_route = unrelated`
3. `final_action = skip_unrelated`

为什么适合展示：

1. 它能说明“系统并没有把所有未知问题都处理正确”
2. 也能说明离线评测不是摆设，而是真的能暴露路由问题

### 4.2 失败案例：产品咨询被误判为 commercial_policy_request

样本：

1. `eval_prod_001`
2. `eval_prod_002`
3. `eval_prod_003`

现象：

1. 预期是 `knowledge_request`
2. 实际都落到 `commercial_policy_request`

为什么适合展示：

1. 它说明 triage 规则与样本边界还需要继续收紧
2. 它是路线偏差，不是系统崩溃，便于解释下一步优化方向

### 4.3 失败案例：澄清场景轨迹不完整

样本：

1. `eval_tech_001`
2. `eval_tech_002`
3. `eval_tech_003`

现象：

1. 主路由判对了
2. 但 `trajectory_evaluation` 报告缺少 `create_gmail_draft`

为什么适合展示：

1. 它能说明“最终语义接近正确”不等于“执行路径已经完全对”
2. 也能证明轨迹评估的必要性

## 5. 推荐演示顺序

如果只有 10 分钟，建议顺序如下：

1. 先演示知识问答主路径
2. 再演示高风险退款自动升级人工
3. 再展示 `trace`、`memory`、`metrics`
4. 最后展示一条离线失败案例，说明当前边界和后续改进空间

## 6. 演示话术重点

建议强调这几个点：

1. 当前系统不是把 LangGraph runnable 直接暴露出去，而是有业务 API 契约
2. 当前系统不是单次邮件脚本，而是 ticket run 状态机
3. 当前系统支持人工审核动作、长期记忆和 trace 查询
4. 当前系统已经有离线评测，但报告不是全绿，因此演示中会明确展示边界而不是掩盖它
