# PPT 架构图素材

这套素材用于 `3 分钟项目介绍视频` 的架构说明段，按 `PPT 分层动画` 设计。

## 文件说明

- `00-base.svg`
  - 底图。包含背景、标题、副标题。
- `01-layer-ingress.svg`
  - 渠道接入、控制面 API、Ticket 入队。
- `02-layer-console-worker.svg`
  - 前端控制台、Worker 异步领取。
- `03-layer-workflow.svg`
  - LangGraph workflow 主流程。
- `04-layer-support.svg`
  - RAG / Policy、Memory / Checkpoint、Human Review / Draft。
- `05-layer-observability.svg`
  - Trace & Eval / LangSmith。
- `99-full-architecture.svg`
  - 完整预览图。适合用在总结页，或单独替代分层动画。

## 推荐做法

### 方案 A：同一页叠层动画

1. 在 PPT 新建 `16:9` 页面。
2. 依次插入以下文件，并全部对齐到页面中心：
   - `00-base.svg`
   - `01-layer-ingress.svg`
   - `02-layer-console-worker.svg`
   - `03-layer-workflow.svg`
   - `04-layer-support.svg`
   - `05-layer-observability.svg`
3. 保持它们尺寸一致，铺满页面。
4. 给 `01` 到 `05` 依次设置 `淡化出现`。

推荐节奏：

- `01` 停留 `0.8s`
- `02` 停留 `0.8s`
- `03` 停留 `1.0s`
- `04` 停留 `1.0s`
- `05` 停留 `0.8s`

适配字幕：

- `邮件或 API 请求先进入控制面，先沉淀成 Ticket。`
- `前端负责查询和人工动作，Worker 负责异步执行。`
- `真正的处理逻辑由 LangGraph workflow 编排。`
- `知识、记忆和人工动作，都是围绕主流程服务的。`
- `每次运行都会留下 trace、评估和轨迹信息。`

### 方案 B：多页平滑切换

如果你不想做逐层动画，也可以：

1. 第一页只放 `00-base.svg + 01-layer-ingress.svg`
2. 第二页在此基础上加 `02-layer-console-worker.svg`
3. 第三页再加 `03-layer-workflow.svg`
4. 第四页再加 `04-layer-support.svg`
5. 第五页加 `05-layer-observability.svg`
6. 页面切换效果使用 `平滑` 或 `淡化`

这种方式更稳，也更适合没有剪辑经验的人。

## 录屏建议

- 架构图这一段建议控制在 `12-18 秒`。
- 不要在这张图上讲模块目录。
- 只讲主路径：
  - `入口`
  - `Ticket`
  - `Worker`
  - `Workflow`
  - `Trace`

## 使用提示

- PPT 中插入 SVG 后，可以直接缩放，清晰度不会掉。
- 如果字体显示和你本机不一致，优先在 PPT 中改成 `微软雅黑` 或 `思源黑体`。
- 如果你想把元素拆成 PPT 原生形状，可以在 PowerPoint 中右键 SVG 后尝试“转换为形状”。
