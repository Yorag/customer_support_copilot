import { render, screen, within } from "@testing-library/react";

import { DashboardPage } from "@/pages/DashboardPage";
import { Providers } from "@/app/providers";

function renderDashboardPage() {
  return render(
    <Providers>
      <DashboardPage />
    </Providers>,
  );
}

describe("DashboardPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders live dashboard signals from ops, metrics, and ticket feeds", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            gmail: {
              enabled: true,
              account_email: "support@example.com",
              last_scan_at: "2026-04-17T09:42:01Z",
              last_scan_status: "succeeded",
            },
            worker: {
              healthy: true,
              worker_count: 2,
              last_heartbeat_at: "2026-04-17T09:48:00Z",
            },
            queue: {
              queued_runs: 4,
              running_runs: 2,
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
              ticket_id: "ticket_error",
              run_id: "run_error",
              trace_id: "trace_error",
              error_code: "run_execution_failed",
              occurred_at: "2026-04-17T09:40:00Z",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            window: {
              from: "2026-04-16T10:00:00Z",
              to: "2026-04-17T10:00:00Z",
            },
            latency: {
              p50_ms: 1000,
              p95_ms: 2400,
            },
            resources: {
              avg_total_tokens: 120,
              avg_llm_call_count: 1.5,
              avg_actual_token_call_count: 1,
              avg_estimated_token_call_count: 0,
              avg_unavailable_token_call_count: 0,
              avg_token_coverage_ratio: 1,
            },
            response_quality: {
              avg_overall_score: 4.7,
            },
            trajectory_evaluation: {
              avg_score: 4.8,
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [
              {
                ticket_id: "ticket_001",
                customer_id: "cust_001",
                customer_email_raw: "alex@example.com",
                subject: "Refund still pending",
                business_status: "awaiting_human_review",
                processing_status: "queued",
                priority: "high",
                primary_route: "commercial_policy_request",
                multi_intent: false,
                version: 3,
                updated_at: "2026-04-17T09:30:00Z",
                latest_run: {
                  run_id: "run_001",
                  trace_id: "trace_001",
                  status: "queued",
                  final_action: null,
                  evaluation_summary_ref: {
                    status: "not_available",
                    trace_id: "trace_001",
                    has_response_quality: false,
                    has_trajectory_evaluation: false,
                  },
                },
                latest_draft: {
                  draft_id: "draft_001",
                  qa_status: "pending_review",
                },
              },
              {
                ticket_id: "ticket_002",
                customer_id: "cust_002",
                customer_email_raw: "jamie@example.com",
                subject: "SSO login loop",
                business_status: "triaged",
                processing_status: "running",
                priority: "medium",
                primary_route: "technical_issue",
                multi_intent: false,
                version: 2,
                updated_at: "2026-04-17T09:20:00Z",
                latest_run: {
                  run_id: "run_002",
                  trace_id: "trace_002",
                  status: "running",
                  final_action: null,
                  evaluation_summary_ref: {
                    status: "partial",
                    trace_id: "trace_002",
                    has_response_quality: true,
                    response_quality_overall_score: 4.6,
                    has_trajectory_evaluation: false,
                  },
                },
                latest_draft: null,
              },
            ],
            page: 1,
            page_size: 5,
            total: 12,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [
              {
                ticket_id: "ticket_001",
                customer_id: "cust_001",
                customer_email_raw: "alex@example.com",
                subject: "Refund still pending",
                business_status: "awaiting_human_review",
                processing_status: "queued",
                priority: "high",
                primary_route: "commercial_policy_request",
                multi_intent: false,
                version: 3,
                updated_at: "2026-04-17T09:30:00Z",
                latest_run: {
                  run_id: "run_001",
                  trace_id: "trace_001",
                  status: "queued",
                  final_action: null,
                  evaluation_summary_ref: {
                    status: "not_available",
                    trace_id: "trace_001",
                    has_response_quality: false,
                    has_trajectory_evaluation: false,
                  },
                },
                latest_draft: {
                  draft_id: "draft_001",
                  qa_status: "pending_review",
                },
              },
            ],
            page: 1,
            page_size: 5,
            total: 3,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );

    vi.stubGlobal("fetch", fetchMock);

    renderDashboardPage();

    expect(
      screen.getByRole("heading", {
        name: "正在载入系统读数。",
      }),
    ).toBeInTheDocument();

    expect(
      await screen.findByRole("heading", {
        name: "把运行态、积压和质量读数放在同一张台面上。",
      }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("总览实时状态带")).toHaveTextContent("已连接");
    expect(screen.getByText("工单总量")).toBeInTheDocument();
    expect(screen.getByText("待审核")).toBeInTheDocument();
    expect(screen.getByText("队列流动与任务吞吐")).toBeInTheDocument();
    expect(
      screen.getByText("质量 4.7，轨迹 4.8，P50 延迟 1,000 ms。"),
    ).toBeInTheDocument();

    const recentTicketsCard = screen
      .getByRole("heading", { name: "最近工单" })
      .closest("section");
    expect(recentTicketsCard).not.toBeNull();
    expect(
      within(recentTicketsCard!).getByText("Refund still pending"),
    ).toBeInTheDocument();
    expect(
      within(recentTicketsCard!).getByText("运行：已入队 · 已入队"),
    ).toBeInTheDocument();

    const reviewQueueCard = screen
      .getByRole("heading", { name: "审核队列" })
      .closest("section");
    expect(reviewQueueCard).not.toBeNull();
    expect(within(reviewQueueCard!).getByText("Refund still pending")).toBeInTheDocument();
    expect(
      within(reviewQueueCard!).getByText("审核：待人工审核 · 草稿：待审核"),
    ).toBeInTheDocument();

    const failuresCard = screen
      .getByRole("heading", { name: "最近失败" })
      .closest("section");
    expect(failuresCard).not.toBeNull();
    expect(within(failuresCard!).getByText("ticket_error 上的 run_error")).toBeInTheDocument();
    expect(
      within(failuresCard!).getByText(/运行执行失败/i),
    ).toBeInTheDocument();

    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("renders empty review state when no tickets need human approval", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            gmail: {
              enabled: false,
              account_email: null,
              last_scan_at: null,
              last_scan_status: null,
            },
            worker: {
              healthy: null,
              worker_count: null,
              last_heartbeat_at: null,
            },
            queue: {
              queued_runs: 0,
              running_runs: 0,
              waiting_external_tickets: 0,
              error_tickets: 0,
            },
            dependencies: {
              database: "ok",
              gmail: "disabled",
              llm: "unknown",
              checkpointing: "ok",
            },
            recent_failure: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            window: {
              from: "2026-04-16T10:00:00Z",
              to: "2026-04-17T10:00:00Z",
            },
            latency: {
              p50_ms: null,
              p95_ms: null,
            },
            resources: {
              avg_total_tokens: null,
              avg_llm_call_count: null,
              avg_actual_token_call_count: null,
              avg_estimated_token_call_count: null,
              avg_unavailable_token_call_count: null,
              avg_token_coverage_ratio: null,
            },
            response_quality: {
              avg_overall_score: null,
            },
            trajectory_evaluation: {
              avg_score: null,
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [],
            page: 1,
            page_size: 5,
            total: 0,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [],
            page: 1,
            page_size: 5,
            total: 0,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );

    vi.stubGlobal("fetch", fetchMock);

    renderDashboardPage();

    expect(
      await screen.findByText("当前没有需要人工审核的工单。"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("当前运行时已禁用邮箱摄入。"),
    ).toBeInTheDocument();
  });
});
