# Customer Support Copilot

`Customer Support Copilot` 是一个基于 `LangGraph + FastAPI + Postgres + Gmail` 的客服工单执行系统，不再是最初的教程型“邮箱分类 + RAG + 草稿生成”示例。

当前仓库已经完成 V1 主链路：

1. Gmail 邮件入库为 `ticket`
2. 通过显式状态机管理 `business_status` 和 `processing_status`
3. 用 `LangGraph` 执行真实 ticket workflow
4. 生成草稿、澄清请求、人工升级或关闭结果
5. 持久化 message log、draft、human review、customer memory、trace 和 metrics
6. 通过业务 API 暴露 ingest/run/manual actions/trace/memory/metrics

## What This Repo Is Now

系统定位已经从“AI 邮件自动化 Demo”升级为“可追踪的客服 Copilot 后端”。

核心能力：

1. `ticket`、`ticket_run`、`draft_artifact`、`human_review`、`trace_event`、`customer_memory` 持久化
2. `knowledge_request`、`technical_issue`、`commercial_policy_request`、`feedback_intake`、`unrelated` 五类主路由
3. 人工动作接口：`approve`、`edit-and-approve`、`rewrite`、`escalate`、`close`
4. `LangSmith` 可选接入，以及本地 trace/latency/resource/response_quality/trajectory_evaluation 聚合
5. 离线评测样本与可复现报告输出

## V1 Scope

V1 已包含：

1. Gmail 工单化入口
2. Ticket 状态机、lease、失败恢复、draft 幂等
3. Graph/Agent 重构后的 ticket execution workflow
4. 长期记忆查询与收尾回写
5. 业务 API 和标准错误码
6. Trace、metrics 和离线 eval

V1 明确不包含：

1. 人工审核动作与自动流程并发写同一工单的复杂冲突控制
2. `RAG MCP` 外部知识接入
3. 多渠道接入
4. 控制台或后台页面
5. 图片附件理解

## Architecture

### Main Flow

```mermaid
flowchart TD
    A[Gmail inbox or API ingest] --> B[POST /tickets/ingest-email]
    B --> C[Message log + Ticket persistence]
    C --> D[POST /tickets/{ticket_id}/run]
    D --> E[load_ticket_context]
    E --> F[load_memory]
    F --> G[triage]

    G -->|knowledge_request| H[knowledge_lookup]
    G -->|commercial_policy_request| I[policy_check]
    G -->|feedback_intake| J[draft_reply]
    G -->|technical_issue + insufficient info| K[clarify_request]
    G -->|unrelated| L[close_ticket]

    H --> M{after knowledge}
    I --> M
    M -->|draft| N[customer_history_lookup]
    M -->|handoff| O[escalate_to_human]

    N --> P{after customer history}
    P -->|draft| J
    P -->|handoff| O

    J --> Q[qa_review]
    Q -->|pass| R[create_gmail_draft]
    Q -->|rewrite| J
    Q -->|handoff| O

    K --> S[collect_case_context]
    R --> S
    O --> S
    L --> S

    S --> T[extract_memory_updates]
    T --> U[validate_memory_updates]
```

系统流程图文本源也保存在 [docs/system-workflow.mmd](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/docs/system-workflow.mmd)。

### Key Modules

1. `src/api/`
   业务 API、DTO、错误处理、依赖注入
2. `src/graph.py`
   ticket execution workflow 定义
3. `src/nodes.py`
   各节点的业务逻辑、trace 打点和 provider 调用
4. `src/ticket_state_machine.py`
   显式业务状态迁移、lease、失败恢复、人工动作前置校验
5. `src/message_log.py`
   邮件入库、reopen 判定、上下文读取
6. `src/customer_memory.py`
   记忆读取与收尾回写
7. `src/observability.py`
   trace、metrics、response quality 和 trajectory evaluation
8. `src/tools/`
   Gmail、knowledge、policy、ticket store provider 抽象

## Repository Layout

```text
langgraph-email-automation/
├── src/
│   ├── api/
│   ├── db/
│   ├── agents.py
│   ├── customer_memory.py
│   ├── graph.py
│   ├── message_log.py
│   ├── nodes.py
│   ├── observability.py
│   ├── state.py
│   ├── ticket_state_machine.py
│   └── tools/
├── docs/
├── tests/
├── scripts/
├── alembic/
├── main.py
├── deploy_api.py
└── create_index.py
```

## Requirements

建议环境：

1. Python `3.10+`
2. Postgres `14+`
3. Gmail OAuth 凭据
4. OpenAI-compatible chat 接口
5. 独立 embedding 接口

安装依赖：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

复制 `.env.example` 并按本地环境填写。

最小运行配置：

```env
GMAIL_ENABLED=true
MY_EMAIL=your_email@gmail.com
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_CHAT_MODEL=gpt-4o-mini
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/customer_support_copilot
EMBEDDING_API_URL=https://your-embedding-endpoint/v1/embeddings
EMBEDDING_API_KEY=your_embedding_api_key
EMBEDDING_MODEL=bge-large-zh-v1.5
```

其余关键变量：

1. `GMAIL_CREDENTIALS_PATH`
2. `GMAIL_TOKEN_PATH`
3. `KNOWLEDGE_SOURCE_PATH`
4. `KNOWLEDGE_DB_PATH`
5. `EMBEDDING_TIMEOUT_SECONDS`
6. `EMBEDDING_API_KEY_HEADER`
7. `EMBEDDING_API_KEY_PREFIX`
8. `LANGSMITH_TRACING`
9. `LANGSMITH_API_KEY`
10. `LANGSMITH_ENDPOINT`
11. `API_HOST`
12. `API_PORT`

如果当前环境还没有 Gmail OAuth，可以先设置 `GMAIL_ENABLED=false`。
这样 `POST /tickets/ingest-email -> POST /tickets/{ticket_id}/run` 这条 API 主链路仍可运行，但 `python main.py` 的 Gmail 轮询入口不可用。

## Setup

### 1. Initialize Database

```bash
python scripts/init_db.py
```

### 2. Build the Local Knowledge Index

默认知识源是 [data/agency.txt](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/data/agency.txt)。

```bash
python create_index.py
```

### 3. Prepare Gmail OAuth

需要本地准备：

1. `credentials.json`
2. `token.json`

Gmail 认证和草稿写入逻辑位于 [src/tools/gmail_client.py](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/src/tools/gmail_client.py) 和 [src/tools/GmailTools.py](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/src/tools/GmailTools.py)。

## Running

### API Server

```bash
python deploy_api.py
```

默认监听 `http://localhost:8000`，OpenAPI 文档位于 `/docs`。

### Poller Batch

```bash
python main.py
```

它会：

1. 从 Gmail 拉取未处理线程
2. 调用 `ingest_email`
3. 立即执行 `run_ticket`

这不是常驻 worker，而是一次批处理入口。

### Offline Eval

```bash
python scripts/run_offline_eval.py
```

默认样本为 [tests/samples/eval/customer_support_eval.jsonl](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/tests/samples/eval/customer_support_eval.jsonl)，报告输出到 [tests/samples/eval/customer_support_eval_report.json](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/tests/samples/eval/customer_support_eval_report.json)。

### Real Eval

如果你要用真实环境配置来跑自建测试集，而不是 fake provider，可以使用：

```bash
python scripts/run_real_eval.py --rebuild-index
```

常见用法：

```bash
python scripts/run_real_eval.py ^
  --samples-path tests/samples/eval/customer_support_eval.jsonl ^
  --report-path evals/customer_support_real_eval_report.json ^
  --knowledge-source-path data/agency.txt ^
  --knowledge-db-path db ^
  --rebuild-index
```

如果 API 已经独立运行，也可以直接打到现有服务：

```bash
python scripts/run_real_eval.py ^
  --api-base-url http://127.0.0.1:8000 ^
  --samples-path path/to/your_eval.jsonl ^
  --report-path evals/your_real_eval_report.json
```

这个脚本会：

1. 可选地按当前 embedding 配置重建知识索引
2. 默认关闭 Gmail 轮询入口，仅验证非 Gmail 主流程
3. 通过真实 HTTP 调用 `ingest-email -> run -> trace`
4. 复用系统内建的 `response_quality`、`trajectory_evaluation`、`latency_metrics`、`resource_metrics`
5. 输出与离线评测一致结构的 JSON 报告

自建测试集格式与 [tests/samples/eval/customer_support_eval.jsonl](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/tests/samples/eval/customer_support_eval.jsonl) 一致。建议至少覆盖这些类型：

1. `knowledge_request`，包含已知答案和知识缺口两类
2. `technical_issue`，区分信息充分与需要澄清
3. `commercial_policy_request`，包含退款、补偿、合同边界
4. `feedback_intake`，包含纯反馈与功能建议
5. `unrelated`
6. `multi_intent`
7. 高风险升级场景
8. 容易误分类的边界场景

## API Surface

写接口：

1. `POST /tickets/ingest-email`
2. `POST /tickets/{ticket_id}/run`
3. `POST /tickets/{ticket_id}/approve`
4. `POST /tickets/{ticket_id}/edit-and-approve`
5. `POST /tickets/{ticket_id}/rewrite`
6. `POST /tickets/{ticket_id}/escalate`
7. `POST /tickets/{ticket_id}/close`

查接口：

1. `GET /tickets/{ticket_id}`
2. `GET /tickets/{ticket_id}/trace`
3. `GET /customers/{customer_id}/memory`
4. `GET /metrics/summary`

请求头约定：

1. `X-Actor-Id`
2. `X-Request-Id`
3. `Idempotency-Key`

人工动作接口要求显式提供 `X-Actor-Id`。

## Quick Demo

### Demo 1: Happy Path API Run

适合演示“知识问答 -> 草稿生成 -> trace 查询”。

1. 启动 API：`python deploy_api.py`
2. 调用 `POST /tickets/ingest-email`
3. 调用 `POST /tickets/{ticket_id}/run`
4. 查看 `GET /tickets/{ticket_id}`
5. 查看 `GET /tickets/{ticket_id}/trace`

可直接参考 [tests/test_api_contract.py](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/tests/test_api_contract.py) 中的 `test_run_ticket_creates_run_trace_and_draft_created_status`。

### Demo 2: High-Risk Policy Handoff

适合演示“高风险商业/退款请求不会自动答复，而是升级人工”。

可直接参考 [tests/test_api_contract.py](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/tests/test_api_contract.py) 中的 `test_run_ticket_routes_high_risk_case_to_human_review`。

### Demo 3: Manual Review Lifecycle

适合演示 `approve`、`close`、memory 回写和 metrics 查询。

可直接参考 [tests/test_api_contract.py](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/tests/test_api_contract.py) 中的 `test_approve_and_close_update_memory_and_metrics_queries`。

完整演示说明见 [docs/demo-cases.zh-CN.md](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/docs/demo-cases.zh-CN.md)。

## Testing

运行测试：

```bash
pytest -q
```

关键测试覆盖：

1. API 契约
2. 状态机与 lease
3. 消息日志与 reopen
4. triage 输出和路由决策
5. graph 节点与人工升级分支
6. trace、metrics、offline eval

## Known Gaps

当前仓库已经可演示，但还存在明确缺口：

1. 离线评测报告不是全绿，说明路由与轨迹规则仍有偏差
2. 目前没有前端控制台
3. 多渠道接入和 `RAG MCP` 仍属于后续版本
4. 人工动作与自动 worker 的复杂并发控制未进入 V1

这类边界和失败样例已经整理在 [docs/demo-cases.zh-CN.md](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/docs/demo-cases.zh-CN.md)。

## V2 Direction

V2 预计聚焦：

1. 更强的人工审核并发控制
2. 外部知识接入与 `RAG MCP`
3. 多渠道入口
4. 运维/审核控制台
5. 更完整的评测闭环和回归门禁
