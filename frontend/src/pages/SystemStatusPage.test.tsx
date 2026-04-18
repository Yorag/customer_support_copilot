import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { SystemStatusPage } from "@/pages/SystemStatusPage";

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function renderSystemStatusPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <SystemStatusPage />
    </QueryClientProvider>,
  );
}

describe("SystemStatusPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders runtime posture, dependency board, watch list, and failure handoff", async () => {
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
            healthy: false,
            worker_count: 2,
            last_heartbeat_at: "2026-04-17T10:07:00Z",
          },
          queue: {
            queued_runs: 6,
            running_runs: 2,
            waiting_external_tickets: 3,
            error_tickets: 1,
          },
          dependencies: {
            database: "ok",
            gmail: "ok",
            llm: "unknown",
            checkpointing: "degraded",
          },
          recent_failure: {
            ticket_id: "ticket_fail_3001",
            run_id: "run_fail_3001",
            trace_id: "trace_fail_3001",
            error_code: "worker_timeout",
            occurred_at: "2026-04-17T10:04:00Z",
          },
        });
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderSystemStatusPage();

    expect(
      await screen.findByRole("heading", {
        name: "把 Worker、依赖和故障信号放在一处。",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Worker 健康状态需要关注。")).toBeInTheDocument();
    const runtimeCards = screen.getByLabelText("系统运行态卡片");
    expect(within(runtimeCards).getByText("已启用")).toBeInTheDocument();
    expect(within(runtimeCards).getByText("降级")).toBeInTheDocument();

    const dependencyBoard = screen.getByLabelText("依赖面板");
    expect(within(dependencyBoard).getByText("Checkpointing")).toBeInTheDocument();
    expect(within(dependencyBoard).getByText("未知")).toBeInTheDocument();

    expect(
      screen.getByText("当前 Worker 健康状态未被报告为健康。"),
    ).toBeInTheDocument();
    expect(screen.getByText("run_fail_3001")).toBeInTheDocument();

    const queueBoard = screen.getByLabelText("队列记账");
    expect(within(queueBoard).getByText("6")).toBeInTheDocument();
    expect(within(queueBoard).getByText("3")).toBeInTheDocument();
  });

  it("surfaces API failures when system status cannot be loaded", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request) => {
      const url = String(input);

      if (url.endsWith("/ops/status")) {
        return jsonResponse(
          {
            error: {
              code: "dependency_unavailable",
              message: "Ops status is temporarily unavailable.",
            },
          },
          503,
        );
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderSystemStatusPage();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("无法加载可靠性信号。")).toBeInTheDocument();
    expect(screen.getByText("Ops status is temporarily unavailable.")).toBeInTheDocument();
  });
});
