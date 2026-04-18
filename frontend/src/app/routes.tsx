import type { RouteObject } from "react-router-dom";

import { AppShellV2 } from "@/app/layouts/AppShellV2";
import type { ConsoleRouteHandle } from "@/app/consoleShell";
import { DashboardPageV2 } from "@/pages-v2/DashboardPageV2";
import { GmailOpsPageV2 } from "@/pages-v2/GmailOpsPageV2";
import { SystemStatusPageV2 } from "@/pages-v2/SystemStatusPageV2";
import { TestLabPageV2 } from "@/pages-v2/TestLabPageV2";
import { TicketDetailPageV2 } from "@/pages-v2/TicketDetailPageV2";
import { TicketsPageV2 } from "@/pages-v2/TicketsPageV2";
import { TraceEvalPageV2 } from "@/pages-v2/TraceEvalPageV2";
import { NotFoundPage } from "@/pages/NotFoundPage";

const dashboardHandle: ConsoleRouteHandle = {
  title: "总览仪表盘",
  eyebrow: "全局态势",
  summary: "把运行态、积压压力和最近变化收进同一张值班看板。",
  phase: "OPS-01",
  contextTitle: "全局读数",
  contextDescription: "面向值班视角的总览页，强调当前健康度、吞吐和需要优先处理的事项。",
  contextItems: [
    "快速读取系统健康度与队列压力。",
    "查看最近工单和待审核事项。",
    "识别失败、延迟和质量偏移。",
  ],
  relatedEndpoints: ["GET /ops/status", "GET /metrics/summary", "GET /tickets"],
};

const ticketsHandle: ConsoleRouteHandle = {
  title: "工单列表",
  eyebrow: "主收件台",
  summary: "在实时台账里筛选工单，再进入单个案件处理。",
  phase: "OPS-02",
  contextTitle: "列表职责",
  contextDescription: "工单列表承担检索、筛选和分流职责，是进入详情页前的主工作面。",
  contextItems: [
    "按工单号、客户和主题搜索。",
    "按状态、路由和审核需求过滤。",
    "从台账直接进入工单详情。",
  ],
  relatedEndpoints: ["GET /tickets", "POST /tickets/{ticket_id}/retry"],
};

const ticketDetailHandle: ConsoleRouteHandle = {
  title: "工单详情",
  eyebrow: "案件室",
  summary: "围绕单个工单查看快照、草稿、动作和运行历史。",
  phase: "OPS-03",
  contextTitle: "审核工作台",
  contextDescription: "详情页用于集中处理单个案件，把状态阅读和人工动作放在同一空间。",
  contextItems: [
    "读取工单快照和最新运行状态。",
    "检查草稿与评估结果。",
    "执行批准、重写、升级和关闭。",
  ],
  relatedEndpoints: [
    "GET /tickets/{ticket_id}",
    "GET /tickets/{ticket_id}/runs",
    "GET /tickets/{ticket_id}/drafts",
    "POST /tickets/{ticket_id}/approve",
    "POST /tickets/{ticket_id}/edit-and-approve",
    "POST /tickets/{ticket_id}/rewrite",
    "POST /tickets/{ticket_id}/escalate",
    "POST /tickets/{ticket_id}/close",
    "POST /tickets/{ticket_id}/retry",
  ],
};

const gmailOpsHandle: ConsoleRouteHandle = {
  title: "Gmail 运维",
  eyebrow: "摄入控制",
  summary: "把邮箱摄入作为显式操作来管理，而不是后台黑盒。",
  phase: "OPS-04",
  contextTitle: "邮箱控制",
  contextDescription: "这里负责邮箱扫描、预览和批次回执，适合调度与排障。",
  contextItems: [
    "预览候选线程。",
    "执行扫描并查看回执。",
    "确认邮箱运行状态与失败信号。",
  ],
  relatedEndpoints: [
    "GET /ops/status",
    "POST /ops/gmail/scan-preview",
    "POST /ops/gmail/scan",
  ],
};

const traceHandle: ConsoleRouteHandle = {
  title: "Trace 与评估",
  eyebrow: "执行剖面",
  summary: "围绕单次运行查看轨迹、事件、评分和原始记录。",
  phase: "OPS-05",
  contextTitle: "执行档案墙",
  contextDescription: "Trace 页面面向调查和复盘，重点是顺着一次运行看清楚发生了什么。",
  contextItems: [
    "切换工单和运行。",
    "阅读事件时间线与事件台账。",
    "对比当前运行与近期指标窗口。",
  ],
  relatedEndpoints: ["GET /tickets/{ticket_id}/trace", "GET /metrics/summary"],
};

const testLabHandle: ConsoleRouteHandle = {
  title: "测试实验台",
  eyebrow: "场景注入",
  summary: "注入受控邮件场景，用于演示、验证和回归测试。",
  phase: "OPS-06",
  contextTitle: "实验台面",
  contextDescription: "测试台用于快速制造真实风格的工单输入，并直接跳转到结果页面。",
  contextItems: [
    "加载常见业务场景预设。",
    "编辑邮件信封和正文。",
    "跳转到生成的工单或 Trace。",
  ],
  relatedEndpoints: ["POST /dev/test-email"],
};

const systemStatusHandle: ConsoleRouteHandle = {
  title: "系统状态",
  eyebrow: "可靠性看板",
  summary: "围绕 Worker、依赖和失败信号查看系统健康度。",
  phase: "OPS-07",
  contextTitle: "可靠性信号",
  contextDescription: "系统状态页用于持续观察健康度，而不是只在问题出现后临时排障。",
  contextItems: [
    "跟踪 Worker 心跳与队列压力。",
    "查看依赖是否正常或降级。",
    "确认最近失败与待关注事项。",
  ],
  relatedEndpoints: ["GET /ops/status"],
};

const notFoundHandle: ConsoleRouteHandle = {
  title: "未找到",
  eyebrow: "路由缺失",
  summary: "控制台非法路径的回退路由。",
  phase: "OPS-00",
  contextTitle: "恢复路径",
  contextDescription: "壳层保持完整，操作员无需丢失上下文即可返回到有效页面。",
  contextItems: ["提供清晰的返回路径，回到当前可用的控制台页面。"],
  relatedEndpoints: [],
};

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppShellV2 />,
    children: [
      {
        index: true,
        element: <DashboardPageV2 />,
        handle: dashboardHandle,
      },
      {
        path: "tickets",
        element: <TicketsPageV2 />,
        handle: ticketsHandle,
      },
      {
        path: "tickets/:ticketId",
        element: <TicketDetailPageV2 />,
        handle: ticketDetailHandle,
      },
      {
        path: "gmail-ops",
        element: <GmailOpsPageV2 />,
        handle: gmailOpsHandle,
      },
      {
        path: "trace",
        element: <TraceEvalPageV2 />,
        handle: traceHandle,
      },
      {
        path: "test-lab",
        element: <TestLabPageV2 />,
        handle: testLabHandle,
      },
      {
        path: "system-status",
        element: <SystemStatusPageV2 />,
        handle: systemStatusHandle,
      },
      {
        path: "*",
        element: <NotFoundPage />,
        handle: notFoundHandle,
      },
    ],
  },
];
