# Clean 架构图素材

这套是精简版，专门解决“图太乱”的问题。

特点：

- 纯白背景
- 不带标题和副标题
- 不带箭头注释文字
- 只保留核心节点和主方向箭头
- 字体整体比原版更小、更克制

## 文件

- `00-base.svg`
- `01-ingress.svg`
- `02-console-worker.svg`
- `03-workflow.svg`
- `04-support.svg`
- `05-observability.svg`
- `99-full.svg`

## 最推荐的用法

在同一页 PPT 中按顺序叠放：

1. `00-base.svg`
2. `01-ingress.svg`
3. `02-console-worker.svg`
4. `03-workflow.svg`
5. `04-support.svg`
6. `05-observability.svg`

然后给 `01` 到 `05` 设置“淡化出现”。

## 如果还觉得乱

继续精简的顺序建议是：

1. 先不要放 `04-support.svg`
2. 再不要放 `05-observability.svg`
3. 只保留 `01 + 02 + 03`

这样就会变成最核心的主链路图：

`Mailbox / API -> Control Plane -> Ticket -> Worker -> Workflow`

## 适合什么场景

- 架构段只有 `8-12 秒`
- 你想自己在 PPT 里加标题
- 你打算自己配字幕，而不想让图本身承担解释任务
