export type ConsoleRouteHandle = {
  title: string;
  eyebrow: string;
  summary: string;
  phase: string;
  contextTitle: string;
  contextDescription: string;
  contextItems: string[];
  relatedEndpoints: string[];
};

export type ConsoleNavItem = {
  to: string;
  label: string;
  note: string;
  end?: boolean;
};

export const primaryNavItems: ConsoleNavItem[] = [
  {
    to: "/",
    label: "总览仪表盘",
    note: "查看运行态、积压和关键异常。",
    end: true,
  },
  {
    to: "/tickets",
    label: "工单列表",
    note: "筛选工单，进入处理详情。",
  },
  {
    to: "/gmail-ops",
    label: "Gmail 运维",
    note: "执行扫描并检查摄入结果。",
  },
  {
    to: "/trace",
    label: "Trace 与评估",
    note: "查看执行轨迹和质量读数。",
  },
  {
    to: "/test-lab",
    label: "测试实验台",
    note: "注入受控场景，验证流程。",
  },
  {
    to: "/system-status",
    label: "系统状态",
    note: "监控依赖、Worker 和故障信号。",
  },
];
