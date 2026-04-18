# 前端控制台与控制面实施拆解及进度计划

## 1. 文档目的

本文档用于把当前“控制台前端 + 控制面 API”工作拆成可持续推进的增量任务。

该计划用于约束后续实施方式：

1. 每次只实现一个明确功能包
2. 每叠加一个功能包，必须单独补测试并单独执行测试
3. 每次实施前后都要回看本计划表并更新状态
4. 先完成后端最小联调闭环，再推进前端页面

---

## 2. 当前现状

基于当前仓库代码与文档，现状如下：

1. 已有 V1 核心 API：`ingest-email`、`run`、`ticket snapshot`、`trace`、人工动作、`metrics summary`
2. 已有较完整的 API 合约测试基础，主入口在 [tests/test_api_contract.py](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/tests/test_api_contract.py)
3. Gmail poller 能力已下沉并沉淀为控制面 API，`scan-preview`、`scan` 与 `ops/status` 已形成可联调闭环
4. 控制台信息架构与控制面 API 草案已落成实现，核心页面均已接入真实控制面数据
5. 当前仓库已包含正式前端工程，具备路由、typed API client、React Query、Zustand、页面测试与 build smoke 能力

结论：

1. 控制面最小闭环 M1 已完成
2. 控制台最小可演示版本 M2 已完成
3. 当前计划可按里程碑验收结果统一收口，后续进入下一阶段规划而非继续执行本批次清单

---

## 3. 实施原则

### 3.1 增量原则

每次实施只选择一个最小功能包，禁止一次混入多个不相干能力。

功能包粒度建议为：

1. 一个接口
2. 一组强耦合的 schema + service + route
3. 一个页面骨架
4. 一个页面上的单一数据区块

### 3.2 测试原则

每个功能包完成后，必须立即执行独立测试。

测试顺序固定为：

1. 先补对应测试
2. 再跑该功能包的定向测试
3. 功能包所属里程碑完成后，再跑更大范围回归

### 3.3 状态更新原则

每个任务状态只能取以下值之一：

1. `Pending`
2. `In Progress`
3. `Blocked`
4. `Implemented`
5. `Tested`
6. `Done`

推荐更新规则：

1. 开始编码前：改为 `In Progress`
2. 代码完成但未测：改为 `Implemented`
3. 定向测试通过：改为 `Tested`
4. 相关联调或里程碑验收通过：改为 `Done`

### 3.4 前端设计执行约束

从 `FE-01` 开始，所有前端页面、布局、组件和视觉层实现都必须显式使用仓库内的 `frontend-design` skill。

约束如下：

1. skill 路径固定为 `.codex/skills/frontend-design/SKILL.md`
2. `FE-01` 到 `FE-14` 的实现不得脱离该 skill 自行决定视觉方向或随意发挥
3. 每次开始一个前端批次前，必须先明确该批次的 `Purpose`、`Tone`、`Constraints`、`Differentiation`
4. `frontend-design` 负责指导视觉与交互表达，但不能覆盖本仓库已有的信息架构、控制面 API 合约和实施批次约束
5. 前端实现时必须避免 generic AI 风格，包括但不限于：
   `Inter/Arial/Roboto/system` 默认字体堆栈、紫白渐变默认配色、模板化卡片布局、无明确审美立场的通用控制台样式
6. 如果后续要偏离该 skill 的设计约束，必须先在文档中补充新的明确规则，再开始实现

---

## 4. 统一实施流程

后续每次实施都按以下步骤执行：

1. 从本计划表选择一个 `Pending` 任务
2. 确认依赖任务已达到 `Done` 或至少 `Tested`
3. 只修改该任务所需最小文件集合
4. 为该任务补一组对应测试
5. 先运行该任务的定向测试
6. 测试通过后再汇报改动
7. 更新本计划表中的状态、测试命令、完成日期或备注

禁止事项：

1. 未补测试先叠加下一功能
2. 一个提交同时实现多个跨层大功能
3. 在前置依赖未完成时强行开始后续页面联调

---

## 5. 进度计划表

说明：

1. 本表基于“单人顺序推进”制定
2. `建议批次` 代表推荐执行顺序，不是强制自然日
3. 若后续引入前端工程，页面任务可在接口稳定后并行拆解

| ID | 建议批次 | 任务 | 层级 | 依赖 | 主要输出 | 单功能测试要求 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CP-00 | 第 0 批 | 固化实施计划与任务台账 | 文档 | 无 | 本计划文档 | 文档类，无强制测试 | Done |
| CP-01 | 第 1 批 | 提炼控制面分页与列表通用 schema | 后端 API | 无 | `page/page_size/items/total` 通用响应模型 | 新增 schema 单测或接口契约测试 | Done |
| CP-02 | 第 1 批 | 实现 `GET /tickets` 查询 service | 后端 API | CP-01 | ticket 列表查询、过滤、分页逻辑 | 仅跑 tickets list 相关契约测试 | Done |
| CP-03 | 第 1 批 | 暴露 `GET /tickets` 路由与响应 schema | 后端 API | CP-02 | 列表接口可供 Tickets 页使用 | 仅跑 `GET /tickets` API 测试 | Done |
| CP-04 | 第 2 批 | 实现 `GET /tickets/{ticket_id}/runs` service | 后端 API | 无 | run 历史查询与排序逻辑 | 仅跑 runs history 相关测试 | Done |
| CP-05 | 第 2 批 | 暴露 `GET /tickets/{ticket_id}/runs` 路由与 schema | 后端 API | CP-04 | Ticket Detail run history 数据源 | 仅跑 runs endpoint 测试 | Done |
| CP-06 | 第 2 批 | 实现 `GET /tickets/{ticket_id}/drafts` service | 后端 API | 无 | draft 历史查询与排序逻辑 | 仅跑 drafts history 相关测试 | Done |
| CP-07 | 第 2 批 | 暴露 `GET /tickets/{ticket_id}/drafts` 路由与 schema | 后端 API | CP-06 | Ticket Detail draft history 数据源 | 仅跑 drafts endpoint 测试 | Done |
| CP-08 | 第 3 批 | 下沉 Gmail scan 逻辑为复用 service | 后端 API | 无 | 从脚本提炼可复用 Gmail scan 服务 | 仅跑 gmail scan service 测试 | Done |
| CP-09 | 第 3 批 | 实现 `POST /ops/gmail/scan-preview` | 后端 API | CP-08 | 扫描预览接口 | 仅跑 scan preview 契约测试 | Done |
| CP-10 | 第 3 批 | 实现 `POST /ops/gmail/scan` | 后端 API | CP-08 | 手动扫描、摄入、可选入队 | 仅跑 gmail scan endpoint 测试 | Done |
| CP-11 | 第 4 批 | 实现 `GET /ops/status` service | 后端 API | 无 | Gmail、worker、queue、dependencies 摘要 | 仅跑 ops status 相关测试 | Done |
| CP-12 | 第 4 批 | 暴露 `GET /ops/status` 路由与 schema | 后端 API | CP-11 | Dashboard/System Status 数据源 | 仅跑 ops status endpoint 测试 | Done |
| CP-13 | 第 5 批 | 实现 `POST /dev/test-email` service | 后端 API | 无 | 复用 ingest + run 的测试注入入口 | 仅跑 test-email 相关测试 | Done |
| CP-14 | 第 5 批 | 暴露 `POST /dev/test-email` 路由与 schema | 后端 API | CP-13 | Test Lab 数据源 | 仅跑 test-email endpoint 测试 | Done |
| CP-15 | 第 6 批 | 实现 `POST /tickets/{ticket_id}/retry` | 后端 API | 现有 run 接口 | 语义化 retry 入口 | 仅跑 retry 相关测试 | Done |
| CP-16 | 第 6 批 | 控制面第一阶段回归与文档对齐修正 | 后端 API | CP-03, CP-05, CP-07, CP-10, CP-12, CP-14, CP-15 | 第一批控制面闭环 | 跑 `tests/test_api_contract.py` 及必要补充测试 | Done |
| FE-00 | 第 7 批 | 建立前端工程骨架与基础约定 | 前端 | CP-16 | 前端目录、路由、数据请求层、状态管理骨架 | 前端工程可启动，基础 smoke test 通过 | Done |
| FE-01 | 第 7 批 | 实现全局布局与导航框架 | 前端 | FE-00 | 左侧导航、顶部状态条、主内容布局 | 仅跑 layout 相关测试 | Done |
| FE-02 | 第 8 批 | 实现 Dashboard 页面骨架 | 前端 | FE-01, CP-12 | Dashboard 静态区块与数据占位 | 仅跑 Dashboard 页面测试 | Done |
| FE-03 | 第 8 批 | 接入 Dashboard 实时数据 | 前端 | FE-02, CP-03, CP-12 | `ops/status + metrics + tickets` 页面联动 | 仅跑 Dashboard 数据测试 | Done |
| FE-04 | 第 9 批 | 实现 Tickets 列表页骨架与筛选 UI | 前端 | FE-01, CP-03 | 列表、筛选器、分页 | 仅跑 Tickets list 页面测试 | Done |
| FE-05 | 第 9 批 | 接入 Tickets 列表真实数据与跳转 | 前端 | FE-04, CP-03 | Ticket 列表联调 | 仅跑 Tickets 数据测试 | Done |
| FE-06 | 第 10 批 | 实现 Ticket Detail 页面骨架 | 前端 | FE-01, CP-05, CP-07 | 摘要区、消息区、草稿区、run history 容器 | 仅跑 Ticket Detail 页面测试 | Done |
| FE-07 | 第 10 批 | 接入 Ticket snapshot、runs、drafts 数据 | 前端 | FE-06, CP-05, CP-07 | Ticket Detail 首次联调闭环 | 仅跑 Ticket Detail 数据测试 | Done |
| FE-08 | 第 11 批 | 接入人工动作按钮 | 前端 | FE-07, 现有人工动作 API | approve、edit、rewrite、escalate、close | 仅跑人工动作 UI 测试 | Done |
| FE-09 | 第 12 批 | 实现 Trace & Eval 页面骨架 | 前端 | FE-01 | 时间线、指标卡、事件表骨架 | 仅跑 Trace 页面测试 | Done |
| FE-10 | 第 12 批 | 接入 trace 与评估数据 | 前端 | FE-09, 现有 trace API | run 时间线与评估展示 | 仅跑 Trace 数据测试 | Done |
| FE-11 | 第 13 批 | 实现 Gmail Ops 页面 | 前端 | FE-01, CP-10, CP-12 | scan、scan-preview、status 展示 | 仅跑 Gmail Ops 页面测试 | Done |
| FE-12 | 第 14 批 | 实现 Test Lab 页面 | 前端 | FE-01, CP-14 | 测试邮件注入与结果跳转 | 仅跑 Test Lab 页面测试 | Done |
| FE-13 | 第 15 批 | 实现 System Status 页面 | 前端 | FE-01, CP-12 | worker、依赖、最近失败摘要 | 仅跑 System Status 页面测试 | Done |
| FE-14 | 第 16 批 | 前端第一阶段集成回归 | 前端 | FE-03, FE-05, FE-07, FE-10, FE-11, FE-12, FE-13 | 最小控制台可演示版本 | 跑前端集成测试和基础 smoke test | Done |

---

## 6. 里程碑定义

### 6.1 里程碑 M1：控制面最小闭环

完成条件：

1. `GET /tickets`
2. `GET /tickets/{ticket_id}/runs`
3. `GET /tickets/{ticket_id}/drafts`
4. `POST /ops/gmail/scan`
5. `POST /ops/gmail/scan-preview`
6. `GET /ops/status`
7. `POST /dev/test-email`
8. `POST /tickets/{ticket_id}/retry`

验收标准：

1. 每个接口都有独立契约测试
2. 第一阶段新增接口至少有一轮集中回归
3. 返回结构与 [13-control-plane-api.zh-CN.md](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/docs/specs/13-control-plane-api.zh-CN.md) 对齐

### 6.2 里程碑 M2：控制台最小可演示版本

完成条件：

1. Dashboard
2. Tickets
3. Ticket Detail
4. Trace & Eval
5. Gmail Ops
6. Test Lab
7. System Status

验收标准：

1. 每个页面至少有独立页面测试或组件测试
2. 核心页面能从 UI 触发主闭环演示路径
3. 页面显示字段与 [frontend-information-architecture.zh-CN.md](/C:/Users/lkw/Desktop/github/agent-project/langgraph-email-automation/docs/frontend-information-architecture.zh-CN.md) 对齐

---

## 7. 每批次推荐测试清单

### 7.1 后端控制面任务

每完成一个接口，至少执行：

1. 新增或更新对应的 API 契约测试
2. 仅运行该接口相关测试

推荐命令模式：

```bash
pytest -q tests/test_api_contract.py -k "<feature_keyword>"
```

控制面阶段每完成一个大批次，再执行：

```bash
pytest -q tests/test_api_contract.py
```

在 M1 里程碑完成时，再追加：

```bash
pytest -q
```

### 7.2 前端页面任务

每完成一个页面或页面子功能，至少执行：

1. 页面级渲染测试
2. 数据请求层测试
3. 页面关键交互测试

如果前端测试框架尚未建立，则 `FE-00` 必须先补齐最小测试脚手架，再继续页面开发。

前端页面进入 `FE-01` 及后续批次后，还必须额外满足：

1. 实现前已按 `frontend-design` skill 明确本批次设计方向
2. 页面测试之外，提交说明中需记录本批次采用的视觉方向与关键差异化点

---

## 8. 首批推荐实施顺序

如果从当前状态立即开始编码，推荐严格按以下顺序推进：

1. CP-01
2. CP-02
3. CP-03
4. CP-04
5. CP-05
6. CP-06
7. CP-07
8. CP-08
9. CP-09
10. CP-10
11. CP-11
12. CP-12
13. CP-13
14. CP-14
15. CP-15
16. CP-16
17. FE-00

原因：

1. `GET /tickets` 是列表页和 Dashboard 的基础数据源
2. `runs/drafts` 直接决定 Ticket Detail 是否能真实联调
3. `scan/status/test-email` 决定 Gmail Ops、Test Lab、Dashboard 是否可用
4. 前端工程应在控制面最小闭环稳定后再启动，避免大量 mock 返工

---

## 9. 任务台账维护模板

后续每次实施结束后，建议按以下格式补充备注：

| ID | 状态 | 实施日期 | 实际改动 | 测试命令 | 结果 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| CP-02 | Done | 2026-04-17 | `queries.py`, `schemas.py`, `routes.py`, `tests/test_api_contract.py` | `pytest -q tests/test_api_contract.py -k "tickets_list"` | Passed | 已支持分页与基础筛选，并在 M1 验收后统一收口 |
| CP-01 | Done | 2026-04-17 | `src/api/schemas.py`, `tests/test_api_contract.py` | `pytest -q tests/test_api_contract.py -k "tickets_list"` | Passed | 已提炼分页响应模型与 Tickets 列表项 schema，并在 M1 验收后统一收口 |
| CP-02 | Done | 2026-04-17 | `src/api/services/queries.py`, `tests/test_api_contract.py` | `pytest -q tests/test_api_contract.py -k "tickets_list"` | Passed | 已支持分页、状态过滤、草稿过滤、待审核过滤与关键字搜索，并在 M1 验收后统一收口 |
| CP-03 | Done | 2026-04-17 | `src/api/routes.py`, `src/api/schemas.py`, `tests/test_api_contract.py` | `pytest -q tests/test_api_contract.py -k "tickets_list"` | Passed | 已暴露 `GET /tickets` 路由并完成响应序列化与参数校验，并在 M1 验收后统一收口 |
| CP-04 | Done | 2026-04-17 | `src/api/services/queries.py`, `tests/test_api_contract.py` | `pytest -q tests/test_api_contract.py -k "runs_history or drafts_history"` | Passed | 已支持 run 历史分页、倒序排序与评估摘要引用，并在 M1 验收后统一收口 |
| CP-05 | Done | 2026-04-17 | `src/api/routes.py`, `src/api/schemas.py`, `tests/test_api_contract.py` | `pytest -q tests/test_api_contract.py -k "runs_history or drafts_history"` | Passed | 已暴露 `GET /tickets/{ticket_id}/runs` 路由与响应投影，并在 M1 验收后统一收口 |
| CP-06 | Done | 2026-04-17 | `src/api/services/queries.py`, `tests/test_api_contract.py` | `pytest -q tests/test_api_contract.py -k "runs_history or drafts_history"` | Passed | 已支持 draft 历史按版本升序返回，并在 M1 验收后统一收口 |
| CP-07 | Done | 2026-04-17 | `src/api/routes.py`, `src/api/schemas.py`, `tests/test_api_contract.py` | `pytest -q tests/test_api_contract.py -k "runs_history or drafts_history"` | Passed | 已暴露 `GET /tickets/{ticket_id}/drafts` 路由与字段序列化，并在 M1 验收后统一收口 |
| CP-08 | Done | 2026-04-17 | `src/api/services/gmail_ops.py`, `src/tools/gmail_client.py`, `src/tools/null_gmail_client.py`, `src/contracts/protocols.py`, `run_poller.py` | `pytest -q tests/test_api_contract.py -k "gmail_scan"` | Passed | 已下沉 Gmail scan 逻辑并让 poller 复用同一 service，并在 M1 验收后统一收口 |
| CP-09 | Done | 2026-04-17 | `src/api/routes.py`, `src/api/schemas.py`, `src/api/services/gmail_ops.py`, `tests/test_api_contract.py` | `pytest -q tests/test_api_contract.py -k "gmail_scan"` | Passed | 已暴露 `POST /ops/gmail/scan-preview` 并返回跳过原因预览，并在 M1 验收后统一收口 |
| CP-10 | Done | 2026-04-17 | `src/api/routes.py`, `src/api/schemas.py`, `src/api/services/gmail_ops.py`, `tests/test_api_contract.py` | `pytest -q tests/test_api_contract.py -k "gmail_scan"` | Passed | 已暴露 `POST /ops/gmail/scan` 支持摄入与可选入队，并在 M1 验收后统一收口 |
| CP-11 | Done | 2026-04-17 | `src/api/services/runtime_status.py`, `src/api/services/gmail_ops.py`, `tests/test_api_contract.py` | `pytest -q tests/test_api_contract.py -k "ops_status"` | Passed | 已汇总 Gmail 最近扫描、queue 计数、依赖摘要与最近失败 run，并在 M1 验收后统一收口 |
| CP-12 | Done | 2026-04-17 | `src/api/routes.py`, `src/api/schemas.py`, `tests/test_api_contract.py` | `pytest -q tests/test_api_contract.py -k "ops_status"` | Passed | 已暴露 `GET /ops/status` 路由并返回 Dashboard 可直接消费的摘要结构，并在 M1 验收后统一收口 |
| CP-13 | Done | 2026-04-17 | `src/api/services/dev_tools.py`, `tests/test_api_contract.py` | `pytest -q tests/test_api_contract.py -k "test_email"` | Passed | 已复用 ingest + run 流程实现测试邮件注入，并在 M1 验收后统一收口 |
| CP-14 | Done | 2026-04-17 | `src/api/routes.py`, `src/api/schemas.py`, `tests/test_api_contract.py` | `pytest -q tests/test_api_contract.py -k "test_email"` | Passed | 已暴露 `POST /dev/test-email` 路由与测试元数据响应，并在 M1 验收后统一收口 |
| CP-15 | Done | 2026-04-17 | `src/api/services/commands.py`, `src/api/routes.py`, `src/api/schemas.py`, `tests/test_api_contract.py` | `pytest -q tests/test_api_contract.py -k "retry_ticket"` | Passed | 已暴露失败工单的语义化 retry 入口并复用强制重试路径，并在 M1 验收后统一收口 |
| CP-16 | Done | 2026-04-17 | `docs/frontend-control-plane-implementation-plan.zh-CN.md`, `tests/test_api_contract.py` | `pytest -q tests/test_api_contract.py` | Passed | 控制面第一阶段新增接口回归通过，M1 已完成并统一收口 |
| FE-00 | Done | 2026-04-17 | `frontend/`, `.gitignore`, `docs/frontend-control-plane-implementation-plan.zh-CN.md` | `cd frontend && npm run test:run && npm run build` | Passed | 已建立 React + TypeScript + Vite 前端骨架，包含路由、typed API client、React Query、Zustand 与最小 smoke test，并在 M2 验收后统一收口 |
| FE-01 | Done | 2026-04-17 | `frontend/src/app/layouts/AppShell.tsx`, `frontend/src/app/routes.tsx`, `frontend/src/app/consoleShell.ts`, `frontend/src/styles/global.css`, `frontend/src/app/App.test.tsx`, `frontend/src/components/PagePlaceholder.tsx`, `docs/frontend-control-plane-implementation-plan.zh-CN.md` | `cd frontend && npm run test:run -- src/app/App.test.tsx` | Passed | 已建立全局布局、左侧导航、顶部状态条与路由上下文侧栏，采用 editorial operations room 视觉方向，并在 M2 验收后统一收口 |
| FE-02 | Done | 2026-04-17 | `frontend/src/pages/DashboardPage.tsx`, `frontend/src/pages/DashboardPage.test.tsx`, `frontend/src/styles/global.css`, `docs/frontend-control-plane-implementation-plan.zh-CN.md` | `cd frontend && npm run test:run -- src/pages/DashboardPage.test.tsx` | Passed | 已实现 Dashboard 页面骨架，包含状态卡、趋势区、最近列表与失败/扫描摘要占位，采用 shift handoff board 视觉方向，并在 M2 验收后统一收口 |
| FE-03 | Done | 2026-04-17 | `frontend/src/pages/DashboardPage.tsx`, `frontend/src/pages/DashboardPage.test.tsx`, `frontend/src/lib/query/dashboard.ts`, `frontend/src/lib/query/keys.ts`, `frontend/src/lib/api/types.ts`, `frontend/src/app/routes.tsx`, `frontend/src/styles/global.css`, `docs/frontend-control-plane-implementation-plan.zh-CN.md` | `cd frontend && npm run test:run -- src/pages/DashboardPage.test.tsx` | Passed | 已接入 `GET /ops/status`、`GET /metrics/summary` 与双路 `GET /tickets` 查询，完成 Dashboard 实时状态、质量读数、最近 ticket 与 review queue 联动，采用 live shift handoff board 视觉方向，并在 M2 验收后统一收口 |
| FE-04 | Done | 2026-04-17 | `frontend/src/pages/TicketsPage.tsx`, `frontend/src/pages/TicketsPage.test.tsx`, `frontend/src/app/layouts/AppShell.tsx`, `frontend/src/app/App.test.tsx`, `frontend/src/styles/global.css`, `docs/frontend-control-plane-implementation-plan.zh-CN.md` | `cd frontend && npm run test:run -- src/pages/TicketsPage.test.tsx src/app/App.test.tsx` | Passed | 已实现 Tickets 列表页骨架、筛选工作台、分页壳与行级动作占位，采用 shift triage ledger 视觉方向，并在 M2 验收后统一收口 |
| FE-05 | Done | 2026-04-17 | `frontend/src/pages/TicketsPage.tsx`, `frontend/src/pages/TicketsPage.test.tsx`, `frontend/src/lib/query/tickets.ts`, `frontend/src/app/routes.tsx`, `frontend/src/app/layouts/AppShell.tsx`, `frontend/src/app/App.test.tsx`, `frontend/src/styles/global.css`, `docs/frontend-control-plane-implementation-plan.zh-CN.md` | `cd frontend && npm run test:run -- src/pages/TicketsPage.test.tsx src/app/App.test.tsx`; `cd frontend && npm run build` | Passed | 已接入真实 `GET /tickets`、服务端分页与筛选参数映射，补齐加载/错误/空态，并支持从列表直接跳转 Ticket Detail，延续 shift triage ledger 视觉方向，并在 M2 验收后统一收口 |
| FE-06 | Done | 2026-04-17 | `frontend/src/pages/TicketDetailPage.tsx`, `frontend/src/pages/TicketDetailPage.test.tsx`, `frontend/src/app/TicketDetailRoute.test.tsx`, `frontend/src/app/routes.tsx`, `frontend/src/app/layouts/AppShell.tsx`, `frontend/src/styles/global.css`, `docs/frontend-control-plane-implementation-plan.zh-CN.md` | `cd frontend && npm run test:run -- src/pages/TicketDetailPage.test.tsx src/app/TicketDetailRoute.test.tsx` | Passed | 已实现 Ticket Detail 案件室骨架，包含摘要带、消息证据区、草稿工作台、运行态侧栏与底部 run history 容器，采用 editorial case room 视觉方向，以三栏证据桌面和底部运行胶片带区别于常规后台详情页，并在 M2 验收后统一收口 |
| FE-07 | Done | 2026-04-17 | `frontend/src/pages/TicketDetailPage.tsx`, `frontend/src/pages/TicketDetailPage.test.tsx`, `frontend/src/app/TicketDetailRoute.test.tsx`, `frontend/src/lib/query/tickets.ts`, `frontend/src/app/routes.tsx`, `frontend/src/app/layouts/AppShell.tsx`, `frontend/src/styles/global.css`, `docs/frontend-control-plane-implementation-plan.zh-CN.md` | `cd frontend && npm run test:run -- src/pages/TicketDetailPage.test.tsx src/app/TicketDetailRoute.test.tsx` | Passed | 已接入真实 `GET /tickets/{ticket_id}`、`GET /tickets/{ticket_id}/runs`、`GET /tickets/{ticket_id}/drafts`，补齐加载/错误/空态与 run/draft 实际展示；消息区明确标注当前 contract 未提供线程数据，延续 editorial case room 视觉方向，并在 M2 验收后统一收口 |
| FE-08 | Done | 2026-04-17 | `frontend/src/pages/TicketDetailPage.tsx`, `frontend/src/pages/TicketDetailPage.test.tsx`, `frontend/src/app/TicketDetailRoute.test.tsx`, `frontend/src/lib/query/tickets.ts`, `frontend/src/lib/api/controlPlane.ts`, `frontend/src/lib/api/types.ts`, `frontend/src/app/routes.tsx`, `frontend/src/app/layouts/AppShell.tsx`, `frontend/src/styles/global.css`, `docs/frontend-control-plane-implementation-plan.zh-CN.md` | `cd frontend && npm run test:run -- src/pages/TicketDetailPage.test.tsx src/app/TicketDetailRoute.test.tsx`; `cd frontend && npm run build` | Passed | 采用 editorial review bench 视觉方向，把审批、编辑审批、重写、升级、关闭动作收敛进 Ticket Detail 中央工作台；通过 reviewer id 输入映射真实 `X-Actor-Id` header，并在成功后刷新 snapshot/runs/drafts 与 tickets 查询，并在 M2 验收后统一收口 |
| FE-09 | Done | 2026-04-17 | `frontend/src/pages/TraceEvalPage.tsx`, `frontend/src/pages/TraceEvalPage.test.tsx`, `frontend/src/app/TraceEvalRoute.test.tsx`, `frontend/src/app/routes.tsx`, `frontend/src/app/layouts/AppShell.tsx`, `frontend/src/styles/global.css`, `docs/frontend-control-plane-implementation-plan.zh-CN.md` | `cd frontend && npm run test:run -- src/pages/TraceEvalPage.test.tsx src/app/TraceEvalRoute.test.tsx`; `cd frontend && npm run build` | Passed | 采用 signal dossier wall 视觉方向，把 Trace & Eval 从占位页提升为时间线、指标侧栏、事件台账和 JSON drawer reserve 的正式骨架，为 FE-10 的 trace 实时数据接入固定布局，并在 M2 验收后统一收口 |
| FE-10 | Done | 2026-04-17 | `frontend/src/pages/TraceEvalPage.tsx`, `frontend/src/pages/TraceEvalPage.test.tsx`, `frontend/src/app/TraceEvalRoute.test.tsx`, `frontend/src/app/routes.tsx`, `frontend/src/app/layouts/AppShell.tsx`, `frontend/src/lib/api/controlPlane.ts`, `frontend/src/lib/query/keys.ts`, `frontend/src/lib/query/trace.ts`, `frontend/src/styles/global.css`, `docs/frontend-control-plane-implementation-plan.zh-CN.md` | `cd frontend && npm run test:run -- src/pages/TraceEvalPage.test.tsx src/app/TraceEvalRoute.test.tsx` | Passed | 延续 signal dossier wall 视觉方向，已接入真实 `GET /tickets/{ticket_id}/trace`、run 选择、窗口指标对比与 raw drawer，形成 Trace & Eval 首次 live dossier 闭环，并在 M2 验收后统一收口 |
| FE-11 | Done | 2026-04-17 | `frontend/src/pages/GmailOpsPage.tsx`, `frontend/src/pages/GmailOpsPage.test.tsx`, `frontend/src/lib/query/gmailOps.ts`, `frontend/src/styles/global.css`, `docs/frontend-control-plane-implementation-plan.zh-CN.md` | `cd frontend && npm run test:run -- src/pages/GmailOpsPage.test.tsx` | Passed | 采用 intake dispatch deck 视觉方向，实现 Gmail 运行状态、scan-preview 候选池与 scan 执行回执；当前 contract 未提供扫描历史，因此页面明确展示该限制而不伪造历史数据，并在 M2 验收后统一收口 |
| FE-12 | Done | 2026-04-17 | `frontend/src/pages/TestLabPage.tsx`, `frontend/src/pages/TestLabPage.test.tsx`, `frontend/src/lib/query/testLab.ts`, `frontend/src/app/layouts/AppShell.tsx`, `frontend/src/styles/global.css`, `docs/frontend-control-plane-implementation-plan.zh-CN.md` | `cd frontend && npm run test:run -- src/pages/TestLabPage.test.tsx` | Passed | 采用 controlled experiment bench 视觉方向，把 `POST /dev/test-email` 提升为场景注入工位；通过预设场景、可编辑信封与 ticket/trace 结果跳转形成最小实验闭环，并在 M2 验收后统一收口 |
| FE-13 | Done | 2026-04-17 | `frontend/src/pages/SystemStatusPage.tsx`, `frontend/src/pages/SystemStatusPage.test.tsx`, `frontend/src/lib/query/systemStatus.ts`, `frontend/src/app/layouts/AppShell.tsx`, `frontend/src/styles/global.css`, `docs/frontend-control-plane-implementation-plan.zh-CN.md` | `cd frontend && npm run test:run -- src/pages/SystemStatusPage.test.tsx` | Passed | 采用 reliability board 视觉方向，把 `GET /ops/status` 单独提升为系统健康板；通过运行态卡片、依赖板、watch list 与失败交接卡保持可靠性信号可见，并在 M2 验收后统一收口 |
| FE-14 | Done | 2026-04-17 | `frontend/src/app/App.test.tsx`, `docs/frontend-control-plane-implementation-plan.zh-CN.md` | `cd frontend && npm run test:run`; `cd frontend && npm run build` | Passed | 已完成前端第一阶段集成回归，补齐 Gmail Ops、Test Lab、System Status 的壳层路由验证；当前控制台核心页面测试与 build smoke 全部通过，M2 已完成并统一收口 |

该台账可以直接追加在本文件末尾，也可以在后续单独拆成实施日志。

---

## 10. 当前建议

从当前仓库状态看，本计划范围内的任务已完成收口：

1. M1 控制面最小闭环已验收通过
2. M2 控制台最小可演示版本已验收通过
3. 当前计划表中满足里程碑条件的任务已统一更新为 `Done`

本计划后续不再作为“待实施清单”继续推进。

如果进入下一阶段，应该新建下一版实施计划，而不是继续在本表上追加未分批的新需求。
