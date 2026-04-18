import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { TraceEvalPage } from "@/pages/TraceEvalPage";
import { useConsoleUiStore } from "@/state/console-ui-store";

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function renderTraceEvalPage(initialEntry = "/trace") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/trace" element={<TraceEvalPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("TraceEvalPage", () => {
  beforeEach(() => {
    useConsoleUiStore.setState({
      selectedTicketId: null,
      selectedRunId: null,
      traceDrawerOpen: false,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders live trace data, run switching, and raw drawer payloads", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request) => {
      const url = String(input);

      if (url.endsWith("/tickets/ticket_trace/runs?page=1&page_size=12")) {
        return jsonResponse({
          ticket_id: "ticket_trace",
          items: [
            {
              run_id: "run_trace_latest",
              trace_id: "trace_latest",
              trigger_type: "manual_api",
              triggered_by: "operator-1",
              status: "succeeded",
              final_action: "create_draft",
              started_at: "2026-04-17T09:58:10Z",
              ended_at: "2026-04-17T09:58:12Z",
              attempt_index: 2,
              is_human_action: false,
              evaluation_summary_ref: {
                status: "complete",
                trace_id: "trace_latest",
                has_response_quality: true,
                response_quality_overall_score: 4.4,
                has_trajectory_evaluation: true,
                trajectory_score: 4.8,
                trajectory_violation_count: 0,
              },
            },
            {
              run_id: "run_trace_first",
              trace_id: "trace_first",
              trigger_type: "scheduled_retry",
              triggered_by: null,
              status: "failed",
              final_action: null,
              started_at: "2026-04-17T09:41:10Z",
              ended_at: "2026-04-17T09:41:12Z",
              attempt_index: 1,
              is_human_action: false,
              evaluation_summary_ref: {
                status: "partial",
                trace_id: "trace_first",
                has_response_quality: false,
                response_quality_overall_score: null,
                has_trajectory_evaluation: true,
                trajectory_score: 2.8,
                trajectory_violation_count: 1,
              },
            },
          ],
          page: 1,
          page_size: 12,
          total: 2,
        });
      }

      if (url.endsWith("/tickets/ticket_trace/trace")) {
        return jsonResponse({
          ticket_id: "ticket_trace",
          run_id: "run_trace_latest",
          trace_id: "trace_latest",
          latency_metrics: {
            end_to_end_ms: 2400,
            slowest_node: "draft_reply",
          },
          resource_metrics: {
            total_tokens: 240,
            llm_call_count: 2,
            tool_call_count: 1,
            token_coverage_ratio: 0.5,
          },
          response_quality: {
            overall_score: 4.4,
            reason: "Draft is strong and policy-aligned.",
          },
          trajectory_evaluation: {
            score: 4.8,
            expected_route: "technical_issue",
            actual_route: "technical_issue",
            violations: [],
          },
          events: [
            {
              event_id: "evt_triage",
              event_type: "node",
              event_name: "triage_decision",
              node_name: "triage",
              start_time: "2026-04-17T09:58:10Z",
              end_time: "2026-04-17T09:58:10.200Z",
              latency_ms: 200,
              status: "succeeded",
              metadata: {
                route: "technical_issue",
                confidence: 0.92,
              },
            },
            {
              event_id: "evt_judge",
              event_type: "llm_call",
              event_name: "response_quality_judge",
              node_name: "qa_handoff",
              start_time: "2026-04-17T09:58:11Z",
              end_time: "2026-04-17T09:58:11.250Z",
              latency_ms: 250,
              status: "succeeded",
              metadata: {
                judge_status: "succeeded",
                request_id: "req_trace_1",
              },
            },
          ],
        });
      }

      if (url.includes("/metrics/summary?")) {
        return jsonResponse({
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
            avg_estimated_token_call_count: 0.5,
            avg_unavailable_token_call_count: 0,
            avg_token_coverage_ratio: 0.75,
          },
          response_quality: {
            avg_overall_score: 4.5,
          },
          trajectory_evaluation: {
            avg_score: 4.7,
          },
        });
      }

      if (url.includes("/tickets/ticket_trace/trace?run_id=run_trace_first")) {
        return jsonResponse({
          ticket_id: "ticket_trace",
          run_id: "run_trace_first",
          trace_id: "trace_first",
          latency_metrics: {
            end_to_end_ms: 4100,
            slowest_node: "qa_handoff",
          },
          resource_metrics: {
            total_tokens: 180,
            llm_call_count: 1,
            tool_call_count: 0,
            token_coverage_ratio: 1,
          },
          response_quality: null,
          trajectory_evaluation: {
            score: 2.8,
            expected_route: "technical_issue",
            actual_route: "technical_issue",
            violations: ["missing_required_diagnostic_step"],
          },
          events: [
            {
              event_id: "evt_failed",
              event_type: "node",
              event_name: "qa_handoff",
              node_name: "qa_handoff",
              start_time: "2026-04-17T09:41:10Z",
              end_time: "2026-04-17T09:41:12Z",
              latency_ms: 2000,
              status: "failed",
              metadata: {
                issue_count: 1,
              },
            },
          ],
        });
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);
    useConsoleUiStore.setState({ selectedTicketId: "ticket_trace" });

    renderTraceEvalPage("/trace?ticketId=ticket_trace");

    expect(
      screen.getByRole("heading", {
        name: "顺着一次运行看清楚发生了什么。",
      }),
    ).toBeInTheDocument();

    expect(
      await screen.findByRole("heading", {
        name: /run_trace_latest 是当前 Trace 档案的锚点。/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("2,400 ms")).toBeInTheDocument();
    expect(screen.getByText("240 tokens")).toBeInTheDocument();
    expect(screen.getByText("Draft is strong and policy-aligned.")).toBeInTheDocument();

    const timeline = screen.getByLabelText("Trace 时间线墙");
    expect(within(timeline).getByText("分诊决策")).toBeInTheDocument();
    expect(
      within(timeline).getByText(/route: technical_issue · confidence: 0\.92/i),
    ).toBeInTheDocument();
    expect(within(timeline).getByText("回复质量评估")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "打开原始记录" }));
    expect(await screen.findByLabelText("Trace 原始记录抽屉")).toHaveTextContent(
      '"overall_score": 4.4',
    );

    fireEvent.change(screen.getByLabelText("运行浏览器"), {
      target: { value: "run_trace_first" },
    });

    expect(
      await screen.findByRole("heading", {
        name: /run_trace_first 是当前 Trace 档案的锚点。/i,
      }),
    ).toBeInTheDocument();
    expect(
      within(screen.getByLabelText("Trace 事件台账")).getAllByText("质量交接").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/missing_required_diagnostic_step/i)).toBeInTheDocument();
  });

  it("renders an empty state before a ticket dossier is selected", () => {
    vi.stubGlobal("fetch", vi.fn());

    renderTraceEvalPage();

    expect(screen.getByText("运行浏览器正在等待工单档案。")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /当前还没有载入任何实时 Trace。/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "载入档案" })).toBeDisabled();
  });

  it("surfaces a request alert when trace loading fails", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request) => {
      const url = String(input);

      if (url.endsWith("/tickets/ticket_broken/runs?page=1&page_size=12")) {
        return jsonResponse({
          ticket_id: "ticket_broken",
          items: [],
          page: 1,
          page_size: 12,
          total: 0,
        });
      }

      if (url.endsWith("/tickets/ticket_broken/trace")) {
        return jsonResponse(
          {
            error: {
              code: "not_found",
              message: "Trace not found for the selected ticket.",
            },
          },
          404,
        );
      }

      if (url.includes("/metrics/summary?")) {
        return jsonResponse({
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
        });
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);
    useConsoleUiStore.setState({ selectedTicketId: "ticket_broken" });

    renderTraceEvalPage("/trace?ticketId=ticket_broken");

    expect(
      await screen.findByRole("alert"),
    ).toHaveTextContent("Trace not found for the selected ticket.");
  });

  it("hides response-quality metrics when the selected run has no response quality", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request) => {
      const url = String(input);

      if (url.endsWith("/tickets/ticket_trace/runs?page=1&page_size=12")) {
        return jsonResponse({
          ticket_id: "ticket_trace",
          items: [
            {
              run_id: "run_trace_no_quality",
              trace_id: "trace_no_quality",
              trigger_type: "manual_api",
              triggered_by: "operator-1",
              status: "succeeded",
              final_action: "handoff_to_human",
              started_at: "2026-04-17T09:58:10Z",
              ended_at: "2026-04-17T09:58:12Z",
              attempt_index: 2,
              is_human_action: false,
              evaluation_summary_ref: {
                status: "partial",
                trace_id: "trace_no_quality",
                has_response_quality: false,
                response_quality_overall_score: null,
                has_trajectory_evaluation: true,
                trajectory_score: 4.8,
                trajectory_violation_count: 0,
              },
            },
          ],
          page: 1,
          page_size: 12,
          total: 1,
        });
      }

      if (url.endsWith("/tickets/ticket_trace/trace")) {
        return jsonResponse({
          ticket_id: "ticket_trace",
          run_id: "run_trace_no_quality",
          trace_id: "trace_no_quality",
          latency_metrics: {
            end_to_end_ms: 2400,
            slowest_node: "escalate_to_human",
          },
          resource_metrics: {
            total_tokens: 0,
            llm_call_count: 0,
            tool_call_count: 0,
            token_coverage_ratio: 0,
          },
          response_quality: null,
          trajectory_evaluation: {
            score: 4.8,
            expected_route: "commercial_policy_request_high_risk",
            actual_route: "commercial_policy_request_high_risk",
            violations: [],
          },
          events: [],
        });
      }

      if (url.includes("/metrics/summary?")) {
        return jsonResponse({
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
            avg_estimated_token_call_count: 0.5,
            avg_unavailable_token_call_count: 0,
            avg_token_coverage_ratio: 0.75,
          },
          response_quality: {
            avg_overall_score: null,
          },
          trajectory_evaluation: {
            avg_score: 4.7,
          },
        });
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);
    useConsoleUiStore.setState({ selectedTicketId: "ticket_trace" });

    renderTraceEvalPage("/trace?ticketId=ticket_trace");

    expect(await screen.findByText("2,400 ms")).toBeInTheDocument();
    expect(screen.getByText("轨迹轨")).toBeInTheDocument();
    expect(screen.queryByText("质量轨")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "打开原始记录" }));
    expect(await screen.findByLabelText("Trace 原始记录抽屉")).not.toHaveTextContent(
      "response_quality",
    );
  });
});
