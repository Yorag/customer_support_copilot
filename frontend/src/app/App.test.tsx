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
    const navigation = screen.getByRole("navigation", { name: "主导航" });

    expect(navigation).toBeInTheDocument();
    expect(screen.getByText("运营控制台")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /总览仪表盘/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /系统状态/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /工单列表/i })).toHaveClass("is-active");
    expect(within(navigation).getByText("筛选工单，进入处理详情。")).toBeInTheDocument();
    expect(screen.getByLabelText("全局状态条")).toHaveTextContent("OPS-02");
    expect(within(workspace).getByText("筛选工单")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "工单列表" }),
    ).toBeInTheDocument();
  });

  it("updates shell context for the dashboard route", async () => {
    mockOpsStatusFetch();
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockImplementation((input: string | URL | Request) => {
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

      if (url.includes("/metrics/summary")) {
        return jsonResponse({
          window: {
            from: "2026-04-16T10:00:00Z",
            to: "2026-04-17T10:00:00Z",
          },
          latency: {
            p50_ms: 1200,
            p95_ms: 4100,
          },
          resources: {
            avg_total_tokens: 3000,
            avg_llm_call_count: 3,
            avg_actual_token_call_count: 2.8,
            avg_estimated_token_call_count: 0.2,
            avg_unavailable_token_call_count: 0,
            avg_token_coverage_ratio: 0.9,
          },
          response_quality: {
            avg_overall_score: 4.5,
          },
          trajectory_evaluation: {
            avg_score: 4.3,
          },
        });
      }

      if (url.includes("/tickets")) {
        return jsonResponse({
          items: [],
          page: 1,
          page_size: 5,
          total: 0,
        });
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    const router = createAppRouter(["/"]);

    render(<App router={router} />);

    expect(
      await screen.findByRole("heading", { name: "总览" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("全局状态条")).toHaveTextContent("OPS-01");
    expect(screen.getByText("系统快照")).toBeInTheDocument();
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
      await screen.findByRole("heading", { name: "摄入与入队" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("全局状态条")).toHaveTextContent("OPS-04");
    expect(screen.getByLabelText("Gmail 运维工作区")).toHaveTextContent("摄入与入队");
    expect(screen.getByLabelText("Gmail 运维区域")).toHaveTextContent("入队方式");
    expect(screen.getByLabelText("Gmail 运维区域")).toHaveTextContent("全部摄入当前批次");
  });

  it("updates shell copy for the Test Lab route", async () => {
    const router = createAppRouter(["/test-lab"]);

    render(<App router={router} />);

    expect(
      await screen.findByRole("heading", { name: "测试实验台" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("全局状态条")).toHaveTextContent("OPS-06");
    expect(screen.getByLabelText("测试实验台工作区")).toHaveTextContent("先确认输入，再提交");
    expect(screen.queryByLabelText("测试实验台区域")).not.toBeInTheDocument();
  });

  it("keeps the legacy System Status route as a dashboard alias", async () => {
    mockOpsStatusFetch();
    const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockImplementation((input: string | URL | Request) => {
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

      if (url.includes("/metrics/summary")) {
        return jsonResponse({
          window: {
            from: "2026-04-16T10:00:00Z",
            to: "2026-04-17T10:00:00Z",
          },
          latency: {
            p50_ms: 1200,
            p95_ms: 4100,
          },
          resources: {
            avg_total_tokens: 3000,
            avg_llm_call_count: 3,
            avg_actual_token_call_count: 2.8,
            avg_estimated_token_call_count: 0.2,
            avg_unavailable_token_call_count: 0,
            avg_token_coverage_ratio: 0.9,
          },
          response_quality: {
            avg_overall_score: 4.5,
          },
          trajectory_evaluation: {
            avg_score: 4.3,
          },
        });
      }

      if (url.includes("/tickets")) {
        return jsonResponse({
          items: [],
          page: 1,
          page_size: 5,
          total: 0,
        });
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    const router = createAppRouter(["/system-status"]);

    render(<App router={router} />);

    expect(
      await screen.findByRole("heading", { name: "总览" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("全局状态条")).toHaveTextContent("OPS-01");
    expect(screen.getByLabelText("总览仪表盘工作区")).toHaveTextContent("系统快照");
  });
});
