# 前端控制台信息架构与页面线框说明

## 1. 文档目标

本文档用于把控制台前端的页面结构、数据视图、交互路径和核心组件明确下来，便于在当前后端基础上直接开始设计与实现。

本文档覆盖：

1. 信息架构
2. 页面层级
3. 关键页面线框说明
4. 核心组件建议
5. 前端状态管理边界
6. 演示路径建议

本文档不覆盖：

1. 具体前端技术选型
2. 最终视觉品牌设计
3. 具体 CSS 细节
4. 详细后端实现

补充约束：

1. 虽然本文档不直接规定最终视觉品牌细节，但后续所有前端视觉实现必须遵循仓库内的 `frontend-design` skill，而不是由实现者临时自由发挥
2. 该 skill 文件路径为 `.codex/skills/frontend-design/SKILL.md`
3. 页面实现必须先定义清晰的 `Purpose`、`Tone`、`Constraints`、`Differentiation`，再进入编码
4. 视觉实现必须与本文档规定的信息架构、页面目标和数据结构保持一致，不能为了“好看”而改写页面职责

---

## 2. 设计目标

该前端不是营销页，也不是 Gmail 客户端替代品，而是本项目的统一控制台。

它需要同时服务三类目标：

1. 操作目标：扫描、注入、入队、人工审核、重试
2. 观测目标：看 ticket、run、draft、trace、评估、状态
3. 展示目标：把“Ticket 化 + Worker 异步执行 + Agent workflow + 可观测性”清晰表达出来

一句话概括：

> 前端要让用户能看懂系统在做什么，也能操作系统继续做事。

### 2.1 视觉实现方法约束

后续页面设计与编码时，默认方法不是“先画一个常见后台模板”，而是使用 `frontend-design` skill 进行有约束的视觉设计。

执行要求：

1. 必须先选定明确的审美方向，允许极简、工业、编辑感、复古未来、粗野、精致等不同路线，但不能没有立场
2. 必须让页面具有可记忆的差异化特征，而不是标准化 SaaS 控制台外观
3. 字体、色彩、背景、空间编排、动效都应服务于该方向
4. 不能使用 skill 明确禁止的通用 AI 审美套路
5. 若项目后续形成统一品牌语言，则应在保留 skill 核心设计方法的前提下收敛为同一套风格系统

---

## 3. 一级信息架构

推荐一级导航如下：

1. `Dashboard`
2. `Tickets`
3. `Gmail Ops`
4. `Trace & Eval`
5. `Test Lab`
6. `System Status`

推荐布局：

1. 左侧固定导航
2. 顶部全局状态条
3. 中间主内容区
4. 右侧详情抽屉或次级上下文栏

### 3.1 全局状态条

建议固定显示：

1. Gmail 状态
2. Worker 状态
3. 队列中 run 数量
4. 最近扫描时间
5. 最近错误提示

它的作用是让用户在任何页面都知道系统是不是活着。

---

## 4. 页面地图

```text
Frontend Console
├─ Dashboard
├─ Tickets
│  ├─ Ticket List
│  └─ Ticket Detail
│     ├─ Summary
│     ├─ Messages
│     ├─ Drafts
│     ├─ Runs
│     ├─ Trace Summary
│     └─ Manual Actions
├─ Gmail Ops
│  ├─ Scan Controls
│  ├─ Scan History
│  └─ Gmail Runtime Status
├─ Trace & Eval
│  ├─ Run Explorer
│  ├─ Trace Timeline
│  ├─ Response Quality
│  └─ Trajectory Evaluation
├─ Test Lab
│  ├─ Inject Test Email
│  ├─ Scenario Presets
│  └─ Run Result Preview
└─ System Status
   ├─ Runtime Health
   ├─ Worker Heartbeat
   ├─ Dependency Status
   └─ Recent Failures
```

---

## 5. 页面详细设计

## 5.1 Dashboard

### 5.1.1 页面目标

Dashboard 用于回答：

1. 系统是否可用
2. 最近发生了什么
3. 质量和轨迹表现如何

### 5.1.2 推荐模块

1. 运行状态卡片区
2. 队列与运行趋势区
3. 质量与轨迹指标区
4. 最近 ticket / 最近异常 run / 待人工审核列表

### 5.1.3 推荐线框

```text
+--------------------------------------------------------------+
| Gmail: ON | Worker: Healthy | Queued: 12 | Last Scan: 10:42 |
+--------------------------------------------------------------+
| Total Tickets | Running Runs | Awaiting Review | Error Runs  |
|      248      |      3       |        7        |      2      |
+--------------------------------------------------------------+
| Queue Trend                    | Quality / Trajectory Trend  |
| [line chart]                   | [dual line chart]           |
+--------------------------------------------------------------+
| Recent Tickets                 | Review Queue                |
| [table/list]                   | [table/list]                |
+--------------------------------------------------------------+
| Recent Failures                | Recent Scan Result          |
| [compact table]                | [summary card]              |
+--------------------------------------------------------------+
```

### 5.1.4 核心交互

1. 点击状态卡进入相关列表
2. 点击 review queue 项进入 ticket 详情
3. 点击异常 run 直接进入 trace 页

---

## 5.2 Tickets 列表页

### 5.2.1 页面目标

该页面是主操作入口，用于快速定位 ticket 并进入处理。

### 5.2.2 筛选器

建议支持：

1. `business_status`
2. `processing_status`
3. `primary_route`
4. `has_draft`
5. `awaiting_human_review`
6. `updated_at` 时间范围
7. 关键词搜索

### 5.2.3 列表字段

建议每行展示：

1. `ticket_id`
2. 客户
3. 主题
4. `primary_route`
5. `business_status`
6. `processing_status`
7. 最新 run 状态
8. 最新 draft 状态
9. 更新时间

### 5.2.4 推荐线框

```text
+--------------------------------------------------------------+
| Search [....................]  Filters [status][route][...]  |
+--------------------------------------------------------------+
| Ticket ID | Customer | Subject | Route | Status | Run | Time |
| t_01...   | liwei... | Refund  | bill  | review | ok  | 10:31|
| t_02...   | anna...  | SSO     | tech  | queued | run | 10:33|
| ...                                                        ...|
+--------------------------------------------------------------+
| Pagination / Infinite List                                   |
+--------------------------------------------------------------+
```

### 5.2.5 核心交互

1. 点击整行进入 ticket 详情
2. 悬停显示最新评估摘要
3. 支持快捷动作：
   1. `Run`
   2. `Retry`
   3. `Open Trace`

---

## 5.3 Ticket 详情页

## 5.3.1 页面目标

Ticket 详情页是最重要的页面，必须完整串起：

1. 这封邮件是什么
2. 系统怎么理解它
3. 目前走到哪一步
4. 草稿是什么
5. 是否需要人工动作
6. 这次 run 的评估和轨迹如何

## 5.3.2 推荐分区

1. 顶部摘要栏
2. 左栏消息线程
3. 中栏草稿与人工动作
4. 右栏运行摘要与评估
5. 底部 run 历史和 trace 快捷入口

### 5.3.3 推荐线框

```text
+--------------------------------------------------------------+
| Ticket t_01... | route: billing | status: awaiting_review    |
| priority: high | processing: waiting_external | run: run_... |
+--------------------------------------------------------------+
| Messages                    | Drafts / Actions | Eval / Trace |
|----------------------------|------------------|--------------|
| Customer email thread      | Latest draft     | latest run   |
| prior messages             | draft history    | quality      |
| source metadata            | approve          | trajectory   |
|                            | edit+approve     | latency      |
|                            | rewrite          | tokens       |
|                            | escalate         | trace link   |
|                            | close            |              |
+--------------------------------------------------------------+
| Run History                                                     |
| run_01... | succeeded | create_draft | trace_01...             |
| run_02... | failed    | null         | trace_02...             |
+--------------------------------------------------------------+
```

### 5.3.4 必须出现的信息

1. 当前 `ticket.business_status`
2. 当前 `ticket.processing_status`
3. 当前 `claim` 信息
4. `latest_run`
5. `latest_draft`
6. 草稿版本历史
7. 最近一次评估摘要

### 5.3.5 人工动作入口

按钮建议：

1. `Approve`
2. `Edit & Approve`
3. `Rewrite`
4. `Escalate`
5. `Close`
6. `Retry`

这里直接体现本项目“自动生成 + 人工协同”的亮点。

---

## 5.4 Trace & Eval 页

### 5.4.1 页面目标

该页面用于回答：

1. 这次 run 实际走了什么路径
2. 为什么慢
3. 为什么得这个质量分
4. 是否违反预期轨迹

### 5.4.2 页面结构

1. 顶部 run 摘要区
2. 中间 trace 时间线
3. 右侧指标卡
4. 底部事件表格

### 5.4.3 推荐线框

```text
+--------------------------------------------------------------+
| run_01... | trace_01... | final_action=create_draft          |
+--------------------------------------------------------------+
| Timeline                             | Metrics               |
| triage -> knowledge -> drafting ... | latency p50/p95      |
| checkpoint / resume / lease events  | tokens / llm calls   |
| node durations                      | quality / trajectory |
+--------------------------------------------------------------+
| Response Quality                                               |
| score | subscores | reason                                     |
+--------------------------------------------------------------+
| Trajectory Evaluation                                          |
| expected route | actual route | violations                     |
+--------------------------------------------------------------+
| Event Table                                                    |
| event_name | node | status | start | end | metadata           |
+--------------------------------------------------------------+
```

### 5.4.4 设计重点

1. 不要只展示原始 JSON
2. 时间线要可扫描
3. 重要异常事件高亮
4. `checkpoint_resume_decision`、`checkpoint_restore`、`worker_renew_lease` 这类事件应可一眼看见

---

## 5.5 Gmail Ops 页

### 5.5.1 页面目标

用于展示 Gmail 接入不是“黑箱脚本”，而是可控的系统能力。

### 5.5.2 页面模块

1. Gmail 连接状态卡
2. 手动扫描操作区
3. 最近扫描历史
4. 最近扫描结果明细
5. 跳过原因摘要

### 5.5.3 推荐线框

```text
+--------------------------------------------------------------+
| Gmail Enabled: true | Account: xxx@gmail.com | Last Scan ... |
+--------------------------------------------------------------+
| [Scan Now] [Preview Scan] [Refresh Status]                   |
+--------------------------------------------------------------+
| Scan Summary                                                  |
| found: 8 | ingested: 3 | skipped_existing_draft: 4 | error:1 |
+--------------------------------------------------------------+
| Recent Scan History                                           |
| time | found | ingested | skipped | status                   |
+--------------------------------------------------------------+
```

---

## 5.6 Test Lab 页

### 5.6.1 页面目标

该页面负责降低演示门槛，让项目可以脱离真实 Gmail 也能完整走通。

### 5.6.2 页面能力

1. 输入测试邮件主题和正文
2. 选择发送人
3. 选择是否立即入队
4. 选择场景模板
5. 结果展示与一键跳转

### 5.6.3 推荐线框

```text
+--------------------------------------------------------------+
| Scenario Preset [Billing Refund v]                           |
+--------------------------------------------------------------+
| From: [liwei@example.com]                                    |
| Subject: [Need refund for duplicate charge...............]   |
| Body:                                                        |
| [textarea.................................................]  |
|                                                              |
| [x] Auto enqueue after ingest                               |
| [Inject Test Email]                                          |
+--------------------------------------------------------------+
| Result                                                        |
| ticket_id | run_id | route | business_status | open detail   |
+--------------------------------------------------------------+
```

### 5.6.4 价值

它适合：

1. 本地验证
2. 面试演示
3. 快速对比不同场景的路由与草稿结果

---

## 5.7 System Status 页

### 5.7.1 页面目标

该页面用于展示系统的工程可靠性侧，而不是业务内容。

### 5.7.2 建议展示

1. worker 心跳
2. Gmail 开关状态
3. 数据库连接状态
4. 最近错误 run
5. 最近恢复 run
6. 依赖配置摘要

这个页面对于展示“不是简单 demo，而是工程化系统”很有帮助。

---

## 6. 核心组件建议

建议提前抽象以下组件：

1. `StatusBadge`
2. `MetricCard`
3. `TicketRow`
4. `DraftVersionCard`
5. `TraceTimeline`
6. `RunHistoryTable`
7. `EventTable`
8. `JsonDrawer`
9. `ManualActionPanel`
10. `ScanSummaryCard`

这些组件会在多个页面复用，能明显减少页面层重复逻辑。

---

## 7. 前端数据模型建议

前端至少应维护以下实体模型：

1. `TicketSummaryViewModel`
2. `TicketDetailViewModel`
3. `TicketRunViewModel`
4. `DraftArtifactViewModel`
5. `TraceEventViewModel`
6. `MetricsSummaryViewModel`
7. `SystemStatusViewModel`
8. `GmailScanResultViewModel`

前端不应直接依赖数据库概念做页面拼接，而应做一层 ViewModel 归一化。

---

## 8. 状态管理边界

建议前端状态分为三类：

1. 服务器状态
2. 页面 UI 状态
3. 短暂编辑状态

### 8.1 服务器状态

包括：

1. ticket 列表
2. ticket 详情
3. run 历史
4. trace 数据
5. metrics 摘要
6. Gmail 状态

这些状态应通过统一数据请求层获取并缓存。

### 8.2 UI 状态

包括：

1. 筛选器
2. 分页
3. 选中的 run
4. 侧栏开关
5. 表格排序

### 8.3 短暂编辑状态

包括：

1. 编辑草稿文本
2. rewrite 原因输入
3. escalate 目标队列输入
4. 测试邮件输入

---

## 9. 推荐演示路径

控制台做好之后，推荐按以下顺序演示：

1. 打开 `Dashboard` 展示系统状态
2. 到 `Gmail Ops` 或 `Test Lab` 触发一条新 ticket
3. 跳到 `Tickets` 列表，看到新 ticket 进入队列
4. 打开 `Ticket Detail` 查看草稿、状态流转和人工动作
5. 进入 `Trace & Eval` 展示节点时间线、质量分和轨迹分
6. 回到 `Dashboard` 看整体指标变化

这条演示路径能完整体现系统闭环。

---

## 10. 结论

只要后端控制面接口补齐，当前项目已经足够开始前端设计。

最优先的页面不是首页，而是：

1. `Ticket Detail`
2. `Trace & Eval`
3. `Dashboard`

原因是：

1. `Ticket Detail` 承接业务闭环
2. `Trace & Eval` 承接项目区分度
3. `Dashboard` 承接系统感知

如果这三页先做出来，本项目的主要亮点就已经能被较完整地表达出来。
