# 前后端分离生产部署清单

## 1. 文档目的

本文档用于给当前仓库提供一份“前端静态站点 + 后端 API + Worker 独立进程”的生产部署清单。

这不是一套现成的 `Docker Compose`、`systemd` 或 Kubernetes 模板，而是一份面向当前代码结构的落地检查表。目标是帮助你确认：

1. 哪些组件必须一起部署
2. 哪些环境变量必须提前准备
3. 哪些安全与运维前提不能省略
4. 上线后最小 smoke check 应该怎么做

---

## 2. 推荐部署拓扑

推荐至少拆成以下逻辑组件：

1. `console.example.com`
   前端静态站点，托管 `frontend/dist/`
2. `api.example.com`
   FastAPI 控制面 API
3. `worker`
   独立 Worker 进程，消费队列并执行 workflow
4. `postgres`
   Ticket、run、draft、trace、memory、metadata 等持久化存储
5. `knowledge_db`
   本地知识库索引目录，默认位于 `.artifacts/knowledge_db`
6. 可选 `poller`
   Gmail 自动摄入进程

部署原则：

1. API 与 Worker 必须运行同一应用版本
2. API 与 Worker 必须连接同一个 `Postgres`
3. 执行 workflow 的节点必须拥有可用的知识库索引
4. 前端只与 API 交互，不直接访问数据库或 Worker

---

## 3. 上线前硬性前提

### 3.1 基础设施

- 一套可用的 `Postgres`
- 至少一台承载 API 的主机或容器
- 至少一台承载 Worker 的主机或容器
- 一个静态文件托管位置或 Web 服务器用于前端构建产物
- HTTPS 终止点或反向代理

### 3.2 必备配置

至少准备以下后端环境变量：

- `DATABASE_URL`
- `MY_EMAIL`
- `LLM_API_KEY`
- `EMBEDDING_API_URL`
- `EMBEDDING_MODEL`
- `CORS_ALLOW_ORIGINS`

常见可选项：

- `GMAIL_ENABLED`
- `GMAIL_CREDENTIALS_PATH`
- `GMAIL_TOKEN_PATH`
- `LANGSMITH_TRACING`
- `LANGSMITH_API_KEY`

前端至少需要：

- `VITE_API_BASE_URL`

### 3.3 安全前提

当前仓库没有内建正式认证体系，因此以下项不能省略：

1. API 必须置于反向代理、网关、VPN 或 SSO 之后
2. 前端不要直接指向无鉴权的公网 API
3. 不要继续使用 `CORS_ALLOW_ORIGINS=*`
4. 不要把 `credentials.json`、`token.json`、`.env` 等敏感文件打进公开制品

说明：

- `X-Actor-Id` 只用于记录人工动作发起人，不构成认证或授权边界
- 如果没有额外访问控制，不建议把控制台直接公开到互联网

---

## 4. 后端部署清单

### 4.1 部署制品

建议 API 与 Worker 均从同一 git revision 或同一打包产物部署，避免：

- 数据库 schema 与运行代码不匹配
- API 写入结构和 Worker 读取逻辑不匹配
- 前端调用的控制面 contract 与 API 版本漂移

### 4.2 初始化步骤

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
Copy-Item .env.example .env
python scripts/init_db.py
python scripts/build_index.py
```

注意：

- `python scripts/init_db.py` 负责执行 Alembic migration
- `python scripts/build_index.py` 负责生成本地知识库索引
- 任何执行 workflow 的节点都应具备可访问的知识库索引目录

### 4.3 API 进程

最小启动命令：

```powershell
python serve_api.py
```

生产要求：

1. 通过反向代理暴露，而不是直接裸露应用端口
2. `CORS_ALLOW_ORIGINS` 精确设置为前端域名
3. API 进程应具备自动拉起、日志采集和重启策略

### 4.4 Worker 进程

最小启动命令：

```powershell
python run_worker.py
```

生产要求：

1. Worker 必须与 API 一起部署，否则 `run` 类操作只能入队不能执行
2. Worker 需要和 API 指向同一数据库
3. Worker 应作为独立守护进程管理，而不是手工开终端常驻

### 4.5 可选 Gmail poller

只有在需要 live Gmail 自动摄入时才启用：

```powershell
python run_poller.py
```

如果只是演示、联调或内网试运行，可以直接设置：

```env
GMAIL_ENABLED=false
```

并改用控制台 `Test Lab` 页面或 API `POST /dev/test-email` 做注入验证。

---

## 5. 前端部署清单

### 5.1 构建步骤

```powershell
cd frontend
npm install
Copy-Item .env.example .env
```

将 `frontend/.env` 中的 API 地址改为真实后端域名，例如：

```bash
VITE_API_BASE_URL=https://api.example.com
```

然后执行：

```powershell
npm run build
```

产物位于：

```text
frontend/dist/
```

### 5.2 托管要求

前端是纯静态站点，可部署到：

- Nginx
- CDN / Object Storage 静态托管
- 任何支持静态文件发布的平台

生产要求：

1. 前端域名应通过 HTTPS 暴露
2. 前端只应访问 API 域名，不要写死内网地址
3. 构建时的 `VITE_API_BASE_URL` 必须与后端 CORS 设置一致

---

## 6. 反向代理与访问控制清单

如果采用前后端分离部署，建议至少具备以下边界：

1. `console.example.com` 与 `api.example.com` 均启用 HTTPS
2. API 通过网关、反向代理或 VPN 控制访问来源
3. 前端域名与 API 域名都有明确日志、限流和错误页
4. 上传的 Gmail OAuth 凭据文件和 token 文件不通过静态目录暴露

建议额外补齐：

1. SSO 或统一登录
2. API Gateway 或反向代理鉴权
3. 审计日志与请求关联 ID
4. 进程保活与异常告警

---

## 7. 上线后最小 Smoke Check

建议按以下顺序执行：

1. 打开控制台首页，确认 Dashboard 能正常加载
2. 调用或页面读取 `GET /ops/status`，确认 API 与数据库可用
3. 打开 `Tickets`，确认 `GET /tickets` 返回正常
4. 在 `Test Lab` 注入一封测试邮件
5. 确认 Worker 消费该 run，并能在 `Ticket Detail` 中看到 snapshot / runs / drafts
6. 打开 `Trace & Eval`，确认 trace、事件和指标可见
7. 如开启 Gmail，进入 `Gmail Ops` 验证 `scan-preview` 与 `scan`

如果第 4 步成功但状态不推进，优先检查：

1. Worker 是否运行
2. Worker 与 API 是否指向同一数据库
3. 知识库索引是否已构建
4. LLM 与 embedding 配置是否可用

---

## 8. 运行时注意事项

### 8.1 这不是“只起 API 就能用”的系统

`POST /tickets/{ticket_id}/run` 与 `POST /tickets/{ticket_id}/retry` 都是入队语义。没有 Worker 时：

- 请求可能成功返回
- 但后续 run 不会真正执行

### 8.2 索引目录属于运行依赖

`.artifacts/knowledge_db` 不是构建缓存，而是 workflow 运行时依赖的一部分。任何需要执行知识检索的环境，都应保证：

1. 索引已构建
2. 路径与配置一致
3. 进程对该目录有读权限

### 8.3 前端与 API 版本应成对发布

当前控制台依赖一组明确的控制面 contract。建议前端与后端一起发布，避免：

- 页面读取不存在字段
- 新接口未部署但前端已切换
- 后端 contract 变化导致页面错误态增多

---

## 9. 当前已知空白

以下项不影响“受控环境可部署”，但影响“公网生产成熟度”：

1. 仓库当前没有现成的 `Dockerfile`、`docker-compose`、`systemd` 或 Kubernetes 编排模板
2. 没有内建登录、鉴权与权限模型
3. Ticket Detail 还没有真实 message thread / message-log 前端数据源
4. Gmail Ops 目前没有扫描历史接口，只有当前状态与当前批次回执

如果要进入下一阶段生产化，建议新开独立实施计划，单独推进：

1. 认证鉴权
2. 部署编排
3. 进程托管与可观测
4. 运行手册与故障处置
