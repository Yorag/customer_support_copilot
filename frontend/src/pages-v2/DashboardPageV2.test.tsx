import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { DashboardPageV2 } from "@/pages-v2/DashboardPageV2";

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function renderDashboardPage() {
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
      <DashboardPageV2 />
    </QueryClientProvider>,
  );
}

describe("DashboardPageV2", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the merged overview with reliability summary", async () => {
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
            error_tickets: 1,
          },
          dependencies: {
            database: "ok",
            gmail: "ok",
            llm: "unknown",
            checkpointing: "ok",
          },
          recent_failure: {
            ticket_id: "ticket_4001",
            run_id: "run_4001",
            trace_id: "trace_4001",
            error_code: "run_execution_failed",
            occurred_at: "2026-04-17T10:01:00Z",
          },
        });
      }

      if (url.includes("/metrics/summary")) {
        return jsonResponse({
          window: {
            from: "2026-04-16T10:00:00Z",
            to: "2026-04-17T10:00:00Z",
          },
          latency: {
            p50_ms: 1120,
            p95_ms: 3980,
          },
          resources: {
            avg_total_tokens: 3100,
            avg_llm_call_count: 3.2,
            avg_actual_token_call_count: 3.1,
            avg_estimated_token_call_count: 0.1,
            avg_unavailable_token_call_count: 0,
            avg_token_coverage_ratio: 0.91,
          },
          response_quality: {
            avg_overall_score: 4.6,
          },
          trajectory_evaluation: {
            avg_score: 4.4,
          },
        });
      }

      if (url.includes("/tickets") && url.includes("awaiting_review=true")) {
        return jsonResponse({
          items: [
            {
              ticket_id: "ticket_4012",
              customer_email_raw: "liwei@northwind.example",
              subject: "Duplicate billing charge still unresolved",
              business_status: "awaiting_human_review",
              processing_status: "queued",
              priority: "high",
              primary_route: "billing_refund",
              multi_intent: false,
              version: 4,
              updated_at: "2026-04-17T10:32:00Z",
              latest_run: {
                run_id: "run_4012",
                trace_id: "trace_4012",
                status: "queued",
                final_action: null,
                evaluation_summary_ref: {
                  status: "not_available",
                  trace_id: "trace_4012",
                  has_response_quality: false,
                  has_trajectory_evaluation: false,
                },
              },
              latest_draft: {
                draft_id: "draft_4012",
                qa_status: "pending_review",
              },
            },
          ],
          page: 1,
          page_size: 5,
          total: 1,
        });
      }

      if (url.includes("/tickets")) {
        return jsonResponse({
          items: [
            {
              ticket_id: "ticket_4008",
              customer_email_raw: "anna@rivet.example",
              subject: "SSO login loop after identity migration",
              business_status: "triaged",
              processing_status: "running",
              priority: "medium",
              primary_route: "technical_issue",
              multi_intent: false,
              version: 2,
              updated_at: "2026-04-17T10:21:00Z",
              latest_run: {
                run_id: "run_4008",
                trace_id: "trace_4008",
                status: "running",
                final_action: null,
                evaluation_summary_ref: {
                  status: "partial",
                  trace_id: "trace_4008",
                  has_response_quality: true,
                  response_quality_overall_score: 4.4,
                  has_trajectory_evaluation: false,
                },
              },
              latest_draft: {
                draft_id: "draft_4008",
                qa_status: "drafting",
              },
            },
          ],
          page: 1,
          page_size: 5,
          total: 1,
        });
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderDashboardPage();

    expect(
      await screen.findByRole("heading", { name: "总览" }),
    ).toBeInTheDocument();
    expect(screen.getByText("系统快照")).toBeInTheDocument();
    expect(screen.getByLabelText("可靠性摘要区域")).toHaveTextContent("最近失败");

    const dependencyStrip = screen.getByLabelText("依赖状态标签");
    expect(within(dependencyStrip).getByText("Database 正常")).toBeInTheDocument();
    expect(within(dependencyStrip).getByText("LLM 未知")).toBeInTheDocument();

    expect(screen.getByText("run_4001 · 运行执行失败")).toBeInTheDocument();
    expect(screen.getByText("Duplicate billing charge still unresolved")).toBeInTheDocument();
  });
});
