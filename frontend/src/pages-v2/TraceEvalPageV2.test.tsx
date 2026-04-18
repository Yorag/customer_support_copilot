import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { TraceEvalPageV2 } from "@/pages-v2/TraceEvalPageV2";
import { useConsoleUiStore } from "@/state/console-ui-store";

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function renderTraceEvalPage(initialEntry = "/trace?ticketId=ticket_trace") {
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
          <Route path="/trace" element={<TraceEvalPageV2 />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("TraceEvalPageV2", () => {
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

  it("shows inline event observer details when selecting stages", async () => {
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
          ],
          page: 1,
          page_size: 12,
          total: 1,
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
            expected_route: ["triage", "draft_reply", "qa_review", "create_gmail_draft"],
            actual_route: ["triage", "draft_reply", "qa_review", "create_gmail_draft"],
            violations: [],
          },
          events: [
            {
              event_id: "evt_triage_node",
              event_type: "node",
              event_name: "triage",
              node_name: "triage",
              start_time: "2026-04-17T09:58:10Z",
              end_time: "2026-04-17T09:58:10.240Z",
              latency_ms: 240,
              status: "succeeded",
              metadata: {
                selected_rule: "deterministic_v1",
              },
            },
            {
              event_id: "evt_triage",
              event_type: "decision",
              event_name: "triage_decision",
              node_name: "triage",
              start_time: "2026-04-17T09:58:10Z",
              end_time: "2026-04-17T09:58:10.200Z",
              latency_ms: 200,
              status: "succeeded",
              metadata: {
                primary_route: "technical_issue",
                response_strategy: "troubleshooting",
                needs_clarification: false,
                needs_escalation: false,
                final_action: "create_draft",
              },
            },
            {
              event_id: "evt_checkpoint",
              event_type: "checkpoint",
              event_name: "checkpoint_restore",
              node_name: "run_ticket",
              start_time: "2026-04-17T09:58:10.500Z",
              end_time: "2026-04-17T09:58:10.620Z",
              latency_ms: 120,
              status: "succeeded",
              metadata: {
                thread_id: "thread_trace_1",
                checkpoint_ns: "ticket-workflow",
                restore_mode: "resume",
                restored: true,
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
                model: "gpt-test",
                provider: "openai-compatible",
                prompt_tokens: 11,
                completion_tokens: 5,
                total_tokens: 16,
                token_source: "provider_actual",
                request_id: "req_trace_1",
                prompt_version: "response_quality_judge_v1",
                judge_status: "succeeded",
                finish_reason: "stop",
              },
            },
            {
              event_id: "evt_draft_node",
              event_type: "node",
              event_name: "draft_reply",
              node_name: "draft_reply",
              start_time: "2026-04-17T09:58:11.300Z",
              end_time: "2026-04-17T09:58:11.620Z",
              latency_ms: 320,
              status: "succeeded",
              metadata: {
                version_index: 1,
                logic_type: "llm_role_with_fallback",
              },
            },
            {
              event_id: "evt_tool",
              event_type: "tool_call",
              event_name: "tool.message_log.get_thread_messages_for_drafting",
              node_name: "draft_reply",
              start_time: "2026-04-17T09:58:11.400Z",
              end_time: "2026-04-17T09:58:11.500Z",
              latency_ms: 100,
              status: "succeeded",
              metadata: {
                tool_name: "message_log.get_thread_messages_for_drafting",
                input_ref: "msg_input_ref_1",
                output_ref: "msg_output_ref_1",
              },
            },
            {
              event_id: "evt_worker",
              event_type: "worker",
              event_name: "worker_start_run",
              node_name: "ticket_worker",
              start_time: "2026-04-17T09:58:11.520Z",
              end_time: "2026-04-17T09:58:11.680Z",
              latency_ms: 160,
              status: "succeeded",
              metadata: {
                ticket_id: "ticket_trace",
                run_id: "run_trace_latest",
                worker_id: "worker-7",
                lease_owner: "worker-7",
                lease_expires_at: "2026-04-17T10:03:11Z",
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

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);
    useConsoleUiStore.setState({ selectedTicketId: "ticket_trace" });

    renderTraceEvalPage();

    expect(await screen.findByLabelText("Trace 执行轨迹")).toBeInTheDocument();
    expect(screen.queryByText(/当前运行拆解为/)).not.toBeInTheDocument();
    expect(screen.getByText("triage -> draft_reply -> qa_review -> create_gmail_draft")).toBeInTheDocument();
    const observer = screen.getByLabelText("Trace 节点观察");
    expect(observer).toHaveTextContent("triage");
    expect(within(observer).getByText("发生序号")).toBeInTheDocument();
    expect(within(observer).getByText("关联记录")).toBeInTheDocument();
    expect(within(observer).getByText("关联类型")).toBeInTheDocument();
    expect(within(observer).getByText("selected_rule")).toBeInTheDocument();
    expect(within(observer).getByText("deterministic_v1")).toBeInTheDocument();
    expect(within(observer).getByText("triage_decision")).toBeInTheDocument();
    expect(within(observer).queryByText("关键线索")).not.toBeInTheDocument();
    expect(screen.getAllByText("回复质量评分").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("轨迹符合度评分").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("端到端延迟").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("资源消耗").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByLabelText("回复质量评分说明").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByLabelText("轨迹符合度评分说明").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("工单焦点")).not.toBeInTheDocument();
    expect(screen.queryByText("运行焦点")).not.toBeInTheDocument();
    expect(screen.queryByText("轨迹结论")).not.toBeInTheDocument();
    expect(screen.getByText("最终动作")).toBeInTheDocument();
    expect(screen.getByText("尝试次数")).toBeInTheDocument();
    const controlPanel = screen.getByLabelText("运行选择").closest("section");
    expect(controlPanel).not.toBeNull();
    expect(within(controlPanel as HTMLElement).getAllByText("生成草稿").length).toBeGreaterThanOrEqual(1);
    expect(within(controlPanel as HTMLElement).getByText("第 2 次")).toBeInTheDocument();
    expect(within(controlPanel as HTMLElement).getByText("状态")).toBeInTheDocument();
    expect(within(controlPanel as HTMLElement).getByText("Trace 引用")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "轨迹节点 qa_handoff" }));
    const qaObserver = await screen.findByLabelText("Trace 节点观察");
    expect(within(qaObserver).getByText("response_quality_judge")).toBeInTheDocument();
    expect(within(qaObserver).getByText("关联记录")).toBeInTheDocument();
    expect(within(qaObserver).getByText("关联类型")).toBeInTheDocument();
    expect(within(qaObserver).getByText("response_quality_judge_v1")).toBeInTheDocument();
    expect(within(qaObserver).getByText("req_trace_1")).toBeInTheDocument();
    expect(within(qaObserver).getByText("gpt-test")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", {
        name: "轨迹节点 draft_reply",
      }),
    );
    const draftObserver = screen.getByLabelText("Trace 节点观察");
    expect(await within(draftObserver).findByText("msg_input_ref_1")).toBeInTheDocument();
    expect(within(draftObserver).getByText("msg_output_ref_1")).toBeInTheDocument();
    expect(within(draftObserver).getByText("version_index")).toBeInTheDocument();
    expect(within(draftObserver).getByText("1")).toBeInTheDocument();
    expect(within(draftObserver).getByText("展开该节点原始记录")).toBeInTheDocument();
    expect(within(draftObserver).queryByText("关键线索")).not.toBeInTheDocument();
    fireEvent.click(within(draftObserver).getByText("展开该节点原始记录"));
    expect(await within(draftObserver).findByText(/"event_id": "evt_tool"/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "轨迹节点 ticket_worker" }));
    const workerObserver = await screen.findByLabelText("Trace 节点观察");
    expect((await within(workerObserver).findAllByText("worker-7")).length).toBeGreaterThanOrEqual(2);
    expect(within(workerObserver).getByText("ticket_trace")).toBeInTheDocument();
  });

  it("omits response-quality score cards when trace has no response quality", async () => {
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
              final_action: "handoff_to_human",
              started_at: "2026-04-17T09:58:10Z",
              ended_at: "2026-04-17T09:58:12Z",
              attempt_index: 2,
              is_human_action: false,
              evaluation_summary_ref: {
                status: "partial",
                trace_id: "trace_latest",
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
          run_id: "run_trace_latest",
          trace_id: "trace_latest",
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
            expected_route: ["triage", "escalate_to_human"],
            actual_route: ["triage", "escalate_to_human"],
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

    renderTraceEvalPage();

    expect(await screen.findByText("端到端延迟")).toBeInTheDocument();
    expect(screen.getAllByText("轨迹符合度评分").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("回复质量评分")).not.toBeInTheDocument();
  });
});
