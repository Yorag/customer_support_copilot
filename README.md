# Customer Support Copilot

`Customer Support Copilot` 是一个基于 `LangGraph + FastAPI + Postgres + Gmail` 的客服工单后端。系统会把邮件或 API 输入转成 `ticket`，通过显式状态机和 worker 执行 LangGraph 工作流，最终产出客服草稿、澄清请求、人工升级结果、trace、metrics 与 customer memory。

当前仓库已经不是最早的“邮箱分类 + RAG + 草稿生成”示例，而是一个可运行、可追踪、可评测的工单执行系统。

## 当前能力

- 将 Gmail 邮件或业务 API 输入持久化为 `ticket`
- 通过 `ticket` / `ticket_run` / `message_log` / `draft_artifact` / `human_review` / `trace_event` / `customer_memory` 管理完整生命周期
- 使用显式业务状态与处理状态管理 `queued`、`running`、`awaiting_human_review`、`closed` 等阶段
- 用 LangGraph 执行 `triage -> knowledge/policy -> drafting -> QA -> draft/handoff/close -> memory update`
- 提供人工动作接口：`approve`、`edit-and-approve`、`rewrite`、`escalate`、`close`
- 输出 trace、latency/resource metrics、response quality judge、trajectory evaluation
- 提供离线评测与真实环境评测脚本

## 系统流程

要点：`POST /tickets/{ticket_id}/run` 只负责入队；真正执行由 worker 完成。

```mermaid
flowchart TD
    A[Gmail poller or API ingest] --> B[POST /tickets/ingest-email]
    B --> C[Ticket + message log persistence]
    C --> D[POST /tickets/{ticket_id}/run]
    D --> E[Queued ticket run]
    E --> F[Worker loop]
    F --> G[load_ticket_context]
    G --> H[load_memory]
    H --> I[triage]

    I -->|knowledge_request| J[knowledge_lookup]
    I -->|commercial_policy_request| K[policy_check]
    I -->|feedback_intake| L[draft_reply]
    I -->|technical_issue + missing info| M[clarify_request]
    I -->|needs escalation| N[escalate_to_human]
    I -->|unrelated| O[close_ticket]

    J --> P[customer_history_lookup or draft_reply]
    K --> P
    P --> L
    L --> Q[qa_review]
    Q -->|pass| R[create_gmail_draft]
    Q -->|rewrite| L
    Q -->|handoff| N

    M --> S[collect_case_context]
    N --> S
    O --> S
    R --> S
    S --> T[extract_memory_updates]
    T --> U[validate_memory_updates]
```

工作流文本源见 `docs/system-workflow.mmd`，补充设计说明见 `docs/customer-support-copilot-technical-design.zh-CN.md`。

## 仓库结构

```text
langgraph-email-automation/
├── scripts/
│   ├── init_db.py               # 初始化 / 升级数据库
│   ├── build_index.py           # 构建本地 Chroma 知识索引
│   ├── run_offline_eval.py      # 本地隔离评测
│   └── run_real_eval.py         # 真实环境 HTTP 评测
├── serve_api.py                 # 启动 FastAPI
├── run_worker.py                # 启动 worker loop
├── run_poller.py                # Gmail 轮询并入队 ticket run
├── src/
│   ├── agents/                  # triage / drafting / QA / knowledge-policy agent 组合
│   ├── api/                     # FastAPI app、路由、schema、service
│   ├── bootstrap/               # ServiceContainer 装配
│   ├── contracts/               # 核心枚举、ID、输出契约、协议
│   ├── db/                      # SQLAlchemy model、repository、session
│   ├── evaluation/              # response quality / trajectory evaluation
│   ├── llm/                     # LLM runtime、model、judge 封装
│   ├── memory/                  # customer memory 读写
│   ├── orchestration/           # workflow、nodes、routes、checkpointing
│   ├── prompts/                 # Prompt 模板与 loader
│   ├── rag/                     # knowledge provider 适配
│   ├── telemetry/               # trace 与 metrics
│   ├── tickets/                 # state machine、message log
│   ├── tools/                   # Gmail、policy provider、ticket store
│   ├── triage/                  # triage 规则、模型与策略
│   └── workers/                 # worker loop 与 run 执行
├── tests/                       # pytest 测试套件
├── docs/                        # 设计文档、规格、演示说明
├── evals/                       # 评测说明、样本与基线资产
├── data/                        # 知识源文档
└── .artifacts/                  # 本地知识索引、评测报告等运行产物
```

## 运行入口

当前仓库的入口按职责分为 3 类：

- 核心服务
  - `python serve_api.py`：启动业务 API
  - `python run_worker.py`：启动 worker，持续消费 queued run 并执行 workflow
- 可选输入任务
  - `python run_poller.py`：从 Gmail 拉取新邮件，执行 `ingest + enqueue`
- 维护任务
  - `python scripts/build_index.py`：构建或重建本地知识索引

需要明确的是：

- `serve_api.py` 和 `run_worker.py` 是核心运行面；没有 worker，run 只会停留在队列里
- `run_poller.py` 不是执行器，它只是 Gmail 输入适配器
- 如果你不接 Gmail，只运行 API + worker 即可
- `build_index.py` 不是常驻服务，只在知识库需要重建时运行

## 技术模块映射

- `src/api/`：业务 API、DTO、错误处理、依赖注入、服务层
- `src/orchestration/workflow.py`：LangGraph workflow 组装
- `src/orchestration/nodes_ticket.py`：ticket workflow 节点实现
- `src/tickets/state_machine.py`：显式状态迁移、lease、失败恢复、人工动作前置校验
- `src/tickets/message_log.py`：邮件入库、thread 关联、reopen 判定、上下文提取
- `src/bootstrap/container.py`：Gmail、RAG、policy、judge、store 等依赖装配
- `src/workers/ticket_worker.py`：claim / renew lease / resume / execute run
- `src/contracts/core.py`：路由、状态、动作、ID 等共享契约
- `src/evaluation/` 与 `src/telemetry/`：评测与可观测性

## 环境要求

- Python `3.10+`
- 运行 API / worker 时需要可用的 Postgres
- 运行真实 Gmail 入口时需要 Gmail OAuth 凭证
- 运行主流程时需要兼容 OpenAI API 的聊天模型
- 仅在构建本地知识索引时需要 embedding 服务

## 配置

先基于 `.env.example` 创建 `.env`。

Windows:

```powershell
Copy-Item .env.example .env
```

关键配置分组如下：

- 运行主流程必需：`MY_EMAIL`、`LLM_API_KEY`
- Gmail：`GMAIL_ENABLED`、`GMAIL_CREDENTIALS_PATH`、`GMAIL_TOKEN_PATH`
- 数据库：`DATABASE_URL` 或 `POSTGRES_HOST`、`POSTGRES_PORT`、`POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD`
- 构建知识索引时必需：`EMBEDDING_API_URL`、`EMBEDDING_MODEL`，以及按需配置 `EMBEDDING_API_KEY`
- 可选观测：`LANGSMITH_TRACING`、`LANGSMITH_API_KEY`、`LANGSMITH_PROJECT`
- API：`API_HOST`、`API_PORT`、`CORS_ALLOW_ORIGINS`

默认运行知识源是 `data/customer_support_knowledge_zh.txt`。

如果你只想本地调试 API / worker 而不接真实 Gmail，可以将 `GMAIL_ENABLED=false`；但 worker 和 poller 运行时仍需要 `MY_EMAIL` 与 `LLM_API_KEY`。

## 安装与初始化

### 1. 创建虚拟环境并安装依赖

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 初始化数据库

```powershell
python scripts/init_db.py
```

这个脚本会执行 Alembic migration 到 `head`。

### 3. 构建本地知识索引

```powershell
python scripts/build_index.py
```

默认会从 `data/customer_support_knowledge_zh.txt` 构建本地知识索引。

### 4. 准备 Gmail OAuth（可选）

- 将 Gmail OAuth 客户端凭证放到 `credentials.json`
- 首次真实调用 Gmail 时会在 `GMAIL_TOKEN_PATH` 位置生成 `token.json`
- 不接 Gmail 时可直接设置 `GMAIL_ENABLED=false`

## 启动方式

推荐启动顺序：

1. 首次部署或知识源变更后，运行 `python scripts/build_index.py`
2. 启动 API：`python serve_api.py`
3. 启动 worker：`python run_worker.py`
4. 如果需要 Gmail 自动摄入，再运行 `python run_poller.py` 或把它配置成定时任务

### API 服务

```powershell
python serve_api.py
```

- 默认地址：`http://localhost:8000`
- OpenAPI 文档：`http://localhost:8000/docs`

### Worker

持续轮询队列：

```powershell
python run_worker.py
```

只处理一个任务后退出：

```powershell
python run_worker.py --once
```

worker 是唯一正式执行 ticket workflow 的进程。

### Gmail Poller 批处理

```powershell
python run_poller.py
```

`run_poller.py` 会从 Gmail 拉取未回复邮件，并为每封邮件创建 / 复用 ticket，然后入队一个 worker run。
它不负责 claim run、续租 lease 或执行 workflow。

## API 概览

写接口：

- `POST /tickets/ingest-email`
- `POST /tickets/{ticket_id}/run`
- `POST /tickets/{ticket_id}/approve`
- `POST /tickets/{ticket_id}/edit-and-approve`
- `POST /tickets/{ticket_id}/rewrite`
- `POST /tickets/{ticket_id}/escalate`
- `POST /tickets/{ticket_id}/close`

查接口：

- `GET /tickets/{ticket_id}`
- `GET /tickets/{ticket_id}/trace`
- `GET /customers/{customer_id}/memory`
- `GET /metrics/summary`

请求头约定：

- `X-Actor-Id`
- `X-Request-Id`
- `Idempotency-Key`

说明：

- 手工动作接口必须显式提供 `X-Actor-Id`
- `run` 接口返回的是“已入队”，真正执行需要 worker 消费
- `trace` 接口可以查看 run 的节点、决策、LLM、tool、worker 事件

## 本地演示建议

最小 happy path：

1. 启动 API：`python serve_api.py`
2. 启动 worker：`python run_worker.py`
3. 调用 `POST /tickets/ingest-email`
4. 调用 `POST /tickets/{ticket_id}/run`
5. 查看 `GET /tickets/{ticket_id}`
6. 查看 `GET /tickets/{ticket_id}/trace`

可参考的测试文件：

- `tests/test_api_contract.py`
- `tests/test_ticket_worker.py`
- `tests/test_triage_service.py`

更完整的演示说明见 `docs/demo-cases.zh-CN.md`。

## 评测

### 离线评测

```powershell
python scripts/run_offline_eval.py ^
  --samples-path evals/samples/customer_support_eval_zh.jsonl ^
  --report-path .artifacts/evals/offline_eval_report.json
```

特点：

- 使用本地 TestClient 调 API
- 默认隔离 Gmail、知识 provider、policy provider 与数据库依赖
- 适合验证路由、升级、轨迹与输出结构

### 真实环境评测

```powershell
python scripts/run_real_eval.py ^
  --samples-path evals/samples/customer_support_eval_zh.jsonl ^
  --report-path .artifacts/evals/real_eval_report.json ^
  --rebuild-index
```

可选参数：

- `--api-base-url`：对接已运行 API，而不是临时启动本地服务
- `--rebuild-index`：评测前备份并重建知识索引
- `--knowledge-source-path` / `--knowledge-db-path`：覆盖评测使用的知识源或索引目录
- `--keep-gmail-enabled`：评测时保留 Gmail 开关，不强制关闭

默认评测样本位于 `evals/samples/customer_support_eval_zh.jsonl`。真实评测默认复用运行时知识源配置，也就是 `KNOWLEDGE_SOURCE_PATH` / `KNOWLEDGE_DB_PATH` 指向的真实知识库；只有在需要对比实验时才显式覆盖。

## 测试

运行全部测试：

```powershell
pytest -q
```

推荐优先运行的定向测试：

```powershell
pytest tests/test_api_contract.py -q
pytest tests/test_ticket_worker.py -q
pytest tests/test_triage_service.py tests/test_triage_outputs.py -q
pytest tests/test_offline_eval.py tests/test_real_eval.py -q
```

测试套件大量使用 fake provider 与临时 SQLite，不依赖真实 Gmail 或生产数据库。

## 当前范围与已知边界

当前 V1 重点覆盖：

- Gmail / API 入站 ticket 化
- ticket 状态机、lease、worker 恢复
- triage、knowledge/policy、drafting、QA、人工升级
- customer memory、trace、metrics、evaluation

当前明确不覆盖：

- 多渠道接入
- 管理后台或前端控制台
- 图片附件理解
- 复杂的人审与自动流程并发冲突控制
- 外部 `RAG MCP` 知识接入

## 相关文档

- `docs/customer-support-copilot-requirements.zh-CN.md`
- `docs/customer-support-copilot-technical-design.zh-CN.md`
- `docs/customer-support-copilot-implementation-tracker.zh-CN.md`
- `docs/demo-cases.zh-CN.md`
- `docs/specs/`
- `evals/README.zh-CN.md`

## 安全说明

- 不要提交 `.env`、`credentials.json`、`token.json`、数据库凭证或真实客户数据
- `.artifacts/knowledge_db/` 是本地 Chroma 索引目录，不是关系型数据库 schema 目录
- `.artifacts/evals/` 是默认评测输出目录；`evals/` 存放评测样本、评测知识源和基线报告
- 如果改动知识源或 embedding 配置，请明确说明是否需要重建本地索引
