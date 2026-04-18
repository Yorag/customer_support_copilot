import { render, screen, within } from "@testing-library/react";

import { App } from "@/app/App";
import { createAppRouter } from "@/app/router";

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function mockOpsStatusFetch() {
  const fetchMock = vi.fn().mockImplementation((input: string | URL | Request) => {
    const url = String(input);

    if (url.endsWith("/ops/status")) {
      return jsonResponse({
        gmail: {
          enabled: true,
          account_email: "support@example.com",
          last_scan_at: "2026-04-17T10:05:00Z",
          last_scan_status: "succeeded",
        },
        worker: {
          healthy: true,
          worker_count: 2,
          last_heartbeat_at: "2026-04-17T10:07:00Z",
        },
        queue: {
          queued_runs: 4,
          running_runs: 1,
          waiting_external_tickets: 1,
          error_tickets: 0,
        },
        dependencies: {
          database: "ok",
          gmail: "ok",
          llm: "unknown",
          checkpointing: "ok",
        },
        recent_failure: null,
      });
    }

    throw new Error(`Unhandled request in test: ${url}`);
  });

  vi.stubGlobal("fetch", fetchMock);
}

describe("App", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the tickets route inside the shared shell", async () => {
    const router = createAppRouter(["/tickets"]);

    render(<App router={router} />);

    const workspace = await screen.findByLabelText("工单列表工作区");

    expect(screen.getByRole("navigation", { name: "主导航" })).toBeInTheDocument();
    expect(screen.getByText("运营控制台")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /总览仪表盘/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /工单列表/i })).toHaveClass("is-active");
    expect(screen.getByLabelText("全局状态条")).toHaveTextContent("OPS-02");
    expect(within(workspace).getByText("筛选工单")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "工单列表" }),
    ).toBeInTheDocument();
  });

  it("updates shell context for the dashboard route", async () => {
    const router = createAppRouter(["/"]);

    render(<App router={router} />);

    expect(
      await screen.findByText("正在载入控制面快照"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("全局状态条")).toHaveTextContent("OPS-01");
  });

  it("updates shell context for the tickets route", async () => {
    const router = createAppRouter(["/tickets"]);

    render(<App router={router} />);

    expect(await screen.findByText("筛选工单")).toBeInTheDocument();
    expect(screen.getByLabelText("全局状态条")).toHaveTextContent("OPS-02");
  });

  it("updates shell copy for the Gmail Ops route", async () => {
    mockOpsStatusFetch();
    const router = createAppRouter(["/gmail-ops"]);

    render(<App router={router} />);

    expect(
      await screen.findByRole("heading", { name: "手动控制邮箱摄入批次" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("全局状态条")).toHaveTextContent("OPS-04");
    expect(screen.getByLabelText("Gmail 运维工作区")).toHaveTextContent("手动控制邮箱摄入批次");
    expect(screen.getByLabelText("Gmail 运维区域")).toHaveTextContent("邮箱");
  });

  it("updates shell copy for the Test Lab route", async () => {
    const router = createAppRouter(["/test-lab"]);

    render(<App router={router} />);

    expect(
      await screen.findByRole("heading", { name: "用受控邮件场景验证整条流程" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("全局状态条")).toHaveTextContent("OPS-06");
    expect(screen.getByLabelText("测试实验台工作区")).toHaveTextContent("用受控邮件场景验证整条流程");
    expect(screen.getByLabelText("测试实验台区域")).toHaveTextContent("场景预设");
  });

  it("updates shell copy for the System Status route", async () => {
    mockOpsStatusFetch();
    const router = createAppRouter(["/system-status"]);

    render(<App router={router} />);

    expect(
      await screen.findByRole("heading", { name: "当前系统健康度" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("全局状态条")).toHaveTextContent("OPS-07");
    expect(screen.getByLabelText("系统状态工作区")).toHaveTextContent("当前系统健康度");
    expect(screen.getByLabelText("系统状态区域")).toHaveTextContent("Worker");
  });
});
