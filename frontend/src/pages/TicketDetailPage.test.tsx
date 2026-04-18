import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { TicketDetailPage } from "@/pages/TicketDetailPage";
import { useConsoleUiStore } from "@/state/console-ui-store";

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function renderTicketDetailPage(initialEntry = "/tickets/ticket_4012") {
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
          <Route path="/tickets/:ticketId" element={<TicketDetailPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("TicketDetailPage", () => {
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

  it("renders live snapshot, draft history, and run history data", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request) => {
      const url = String(input);

      if (url.endsWith("/tickets/ticket_4012")) {
        return jsonResponse({
            ticket: {
              ticket_id: "ticket_4012",
              business_status: "awaiting_human_review",
              processing_status: "waiting_external",
              claimed_by: "worker-9",
              claimed_at: "2026-04-17T10:15:00Z",
              lease_until: "2026-04-17T10:20:00Z",
              priority: "high",
              primary_route: "commercial_policy_request",
              multi_intent: false,
              tags: ["needs_escalation"],
              version: 7,
            },
            latest_run: {
              run_id: "run_4012_latest",
              trace_id: "trace_4012_latest",
              status: "succeeded",
              final_action: "handoff_to_human",
              evaluation_summary_ref: {
                status: "complete",
                trace_id: "trace_4012_latest",
                has_response_quality: true,
                response_quality_overall_score: 4.6,
                has_trajectory_evaluation: true,
                trajectory_score: 4.8,
                trajectory_violation_count: 0,
              },
            },
            latest_draft: {
              draft_id: "draft_4012_v2",
              qa_status: "passed",
            },
          });
      }

      if (url.endsWith("/tickets/ticket_4012/runs?page=1&page_size=20")) {
        return jsonResponse({
            ticket_id: "ticket_4012",
            items: [
              {
                run_id: "run_4012_latest",
                trace_id: "trace_4012_latest",
                trigger_type: "human_action",
                triggered_by: "reviewer-77",
                status: "succeeded",
                final_action: "handoff_to_human",
                started_at: "2026-04-17T10:15:00Z",
                ended_at: "2026-04-17T10:15:09Z",
                attempt_index: 3,
                is_human_action: true,
                evaluation_summary_ref: {
                  status: "complete",
                  trace_id: "trace_4012_latest",
                  has_response_quality: true,
                  response_quality_overall_score: 4.6,
                  has_trajectory_evaluation: true,
                  trajectory_score: 4.8,
                  trajectory_violation_count: 0,
                },
              },
              {
                run_id: "run_4012_failed",
                trace_id: "trace_4012_failed",
                trigger_type: "scheduled_retry",
                triggered_by: null,
                status: "failed",
                final_action: null,
                started_at: "2026-04-17T09:52:00Z",
                ended_at: "2026-04-17T09:52:11Z",
                attempt_index: 2,
                is_human_action: false,
                evaluation_summary_ref: {
                  status: "partial",
                  trace_id: "trace_4012_failed",
                  has_response_quality: false,
                  response_quality_overall_score: null,
                  has_trajectory_evaluation: true,
                  trajectory_score: 2.5,
                  trajectory_violation_count: 1,
                },
              },
            ],
            page: 1,
            page_size: 20,
            total: 2,
          });
      }

      if (url.endsWith("/tickets/ticket_4012/drafts")) {
        return jsonResponse({
            ticket_id: "ticket_4012",
            items: [
              {
                draft_id: "draft_4012_v1",
                run_id: "run_4012_first",
                version_index: 1,
                draft_type: "reply",
                qa_status: "pending",
                content_text: "Initial draft body",
                source_evidence_summary: null,
                gmail_draft_id: null,
                created_at: "2026-04-17T09:40:00Z",
              },
              {
                draft_id: "draft_4012_v2",
                run_id: "run_4012_latest",
                version_index: 2,
                draft_type: "reply",
                qa_status: "passed",
                content_text: "Approved draft body for the customer.",
                source_evidence_summary: "policy summary",
                gmail_draft_id: "gmail-draft-2",
                created_at: "2026-04-17T10:15:05Z",
              },
            ],
          });
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderTicketDetailPage();

    expect(
      screen.getByRole("heading", {
        name: "在一个空间里读状态、看草稿、做人工决策。",
      }),
    ).toBeInTheDocument();

    expect(
      await screen.findByText("待人工审核"),
    ).toBeInTheDocument();
    expect(screen.getByText(/worker-9，租约至/i)).toBeInTheDocument();
    expect(screen.getByText("run_4012_latest 是当前主运行。")).toBeInTheDocument();
    expect(screen.getByText("Approved draft body for the customer.")).toBeInTheDocument();
    expect(screen.getAllByText("draft_4012_v2").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText(/质量 4\.6 · 轨迹 4\.8/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("ticket_4012")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "批准" }),
    ).toBeEnabled();
    expect(
      screen.getByLabelText("人工动作状态"),
    ).toHaveTextContent("草稿 draft_4012_v2");

    const history = screen.getByLabelText("运行历史卷带");
    expect(within(history).getByText("run_4012_failed")).toBeInTheDocument();
    expect(within(history).getByText(/轨迹 2\.5 · 1 条违规/i)).toBeInTheDocument();

    const draftLadder = screen.getByLabelText("草稿版本阶梯");
    expect(within(draftLadder).getByText("版本 2 · 已通过")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("renders honest empty states when the ticket has no runs or drafts", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request) => {
      const url = String(input);

      if (url.endsWith("/tickets/ticket_empty")) {
        return jsonResponse({
            ticket: {
              ticket_id: "ticket_empty",
              business_status: "triaged",
              processing_status: "queued",
              claimed_by: null,
              claimed_at: null,
              lease_until: null,
              priority: "medium",
              primary_route: "technical_issue",
              multi_intent: false,
              tags: [],
              version: 2,
            },
            latest_run: null,
            latest_draft: null,
          });
      }

      if (url.endsWith("/tickets/ticket_empty/runs?page=1&page_size=20")) {
        return jsonResponse({
            ticket_id: "ticket_empty",
            items: [],
            page: 1,
            page_size: 20,
            total: 0,
          });
      }

      if (url.endsWith("/tickets/ticket_empty/drafts")) {
        return jsonResponse({
            ticket_id: "ticket_empty",
            items: [],
          });
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderTicketDetailPage("/tickets/ticket_empty");

    expect(
      await screen.findByText(/当前还没有来自 GET \/tickets\/ticket_empty\/drafts。/i),
    ).toBeInTheDocument();
    expect(await screen.findByText("已分诊")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "这个工单还没有任何已记录尝试。",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/当前没有执行器持有租约。/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "批准" })).toBeDisabled();
    expect(screen.getByText(/在存在草稿产物之前，批准、编辑和重写按钮会保持禁用。/i)).toBeInTheDocument();
  });

  it("surfaces an alert when one of the detail requests fails", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request) => {
      const url = String(input);

      if (url.endsWith("/tickets/ticket_missing")) {
        return jsonResponse({
            error: {
              code: "not_found",
              message: "Ticket snapshot missing.",
            },
          }, 404);
      }

      if (url.endsWith("/tickets/ticket_missing/runs?page=1&page_size=20")) {
        return jsonResponse({
            ticket_id: "ticket_missing",
            items: [],
            page: 1,
            page_size: 20,
            total: 0,
          });
      }

      if (url.endsWith("/tickets/ticket_missing/drafts")) {
        return jsonResponse({
            ticket_id: "ticket_missing",
            items: [],
          });
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderTicketDetailPage("/tickets/ticket_missing");

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(screen.getByText(/部分详情数据没有成功返回。/i)).toBeInTheDocument();
    expect(screen.getByText("Ticket snapshot missing.")).toBeInTheDocument();
  });

  it("syncs the selected ticket id from the route parameter", () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request) => {
      const url = String(input);

      if (url.endsWith("/tickets/ticket_9981")) {
        return jsonResponse({
            ticket: {
              ticket_id: "ticket_9981",
              business_status: "triaged",
              processing_status: "queued",
              claimed_by: null,
              claimed_at: null,
              lease_until: null,
              priority: "medium",
              primary_route: "technical_issue",
              multi_intent: false,
              tags: [],
              version: 2,
            },
            latest_run: null,
            latest_draft: null,
          });
      }

      if (url.endsWith("/tickets/ticket_9981/runs?page=1&page_size=20")) {
        return jsonResponse({
          ticket_id: "ticket_9981",
          items: [],
          page: 1,
          page_size: 20,
          total: 0,
        });
      }

      if (url.endsWith("/tickets/ticket_9981/drafts")) {
        return jsonResponse({
          ticket_id: "ticket_9981",
          items: [],
        });
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderTicketDetailPage("/tickets/ticket_9981");

    expect(useConsoleUiStore.getState().selectedTicketId).toBe("ticket_9981");
  });

  it("submits approve action with actor header and refreshes detail queries", async () => {
    let snapshotRequestCount = 0;
    let runsRequestCount = 0;
    let draftsRequestCount = 0;

    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/tickets/ticket_approve")) {
        snapshotRequestCount += 1;

        return jsonResponse({
          ticket: {
            ticket_id: "ticket_approve",
            business_status: snapshotRequestCount === 1 ? "awaiting_human_review" : "approved",
            processing_status: "completed",
            claimed_by: null,
            claimed_at: null,
            lease_until: null,
            priority: "high",
            primary_route: "commercial_policy_request",
            multi_intent: false,
            tags: [],
            version: snapshotRequestCount === 1 ? 7 : 8,
          },
          latest_run: {
            run_id: "run_approve_latest",
            trace_id: "trace_approve_latest",
            status: "succeeded",
            final_action: "handoff_to_human",
            evaluation_summary_ref: {
              status: "complete",
              trace_id: "trace_approve_latest",
              has_response_quality: true,
              response_quality_overall_score: 4.8,
              has_trajectory_evaluation: true,
              trajectory_score: 4.9,
              trajectory_violation_count: 0,
            },
          },
          latest_draft: {
            draft_id: "draft_approve_v1",
            qa_status: "passed",
          },
        });
      }

      if (url.endsWith("/tickets/ticket_approve/runs?page=1&page_size=20")) {
        runsRequestCount += 1;

        return jsonResponse({
          ticket_id: "ticket_approve",
          items: [
            {
              run_id: "run_approve_latest",
              trace_id: "trace_approve_latest",
              trigger_type: "human_action",
              triggered_by: "reviewer-console",
              status: "succeeded",
              final_action: "handoff_to_human",
              started_at: "2026-04-17T10:15:00Z",
              ended_at: "2026-04-17T10:15:09Z",
              attempt_index: 1,
              is_human_action: true,
              evaluation_summary_ref: {
                status: "complete",
                trace_id: "trace_approve_latest",
                has_response_quality: true,
                response_quality_overall_score: 4.8,
                has_trajectory_evaluation: true,
                trajectory_score: 4.9,
                trajectory_violation_count: 0,
              },
            },
          ],
          page: 1,
          page_size: 20,
          total: 1,
        });
      }

      if (url.endsWith("/tickets/ticket_approve/drafts")) {
        draftsRequestCount += 1;

        return jsonResponse({
          ticket_id: "ticket_approve",
          items: [
            {
              draft_id: "draft_approve_v1",
              run_id: "run_approve_latest",
              version_index: 1,
              draft_type: "reply",
              qa_status: "passed",
              content_text: "Ready for approval.",
              source_evidence_summary: "policy summary",
              gmail_draft_id: "gmail-draft-approve",
              created_at: "2026-04-17T10:15:05Z",
            },
          ],
        });
      }

      if (url.endsWith("/tickets/ticket_approve/approve")) {
        expect(init?.method).toBe("POST");
        expect(init?.headers).toMatchObject({
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Actor-Id": "reviewer-console",
        });
        expect(init?.body).toBe(
          JSON.stringify({
            ticket_version: 7,
            draft_id: "draft_approve_v1",
            comment: "Looks good to send.",
          }),
        );

        return jsonResponse({
          ticket_id: "ticket_approve",
          review_id: "review_approve_1",
          business_status: "approved",
          processing_status: "completed",
          version: 8,
        });
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderTicketDetailPage("/tickets/ticket_approve");

    await screen.findByText("Ready for approval.");

    fireEvent.change(screen.getByLabelText("操作备注"), {
      target: { value: "Looks good to send." },
    });
    fireEvent.click(screen.getByRole("button", { name: "批准" }));

    expect(
      await screen.findByText("已记录批准动作"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/已批准 · 已完成 · 工单版本 8 · 审核 review_approve_1。/i),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("已批准")).toBeInTheDocument();
    });
    expect(snapshotRequestCount).toBeGreaterThanOrEqual(2);
    expect(runsRequestCount).toBeGreaterThanOrEqual(2);
    expect(draftsRequestCount).toBeGreaterThanOrEqual(2);
  });

  it("surfaces API failure when a manual action is rejected", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/tickets/ticket_error")) {
        return jsonResponse({
          ticket: {
            ticket_id: "ticket_error",
            business_status: "awaiting_human_review",
            processing_status: "waiting_external",
            claimed_by: null,
            claimed_at: null,
            lease_until: null,
            priority: "high",
            primary_route: "commercial_policy_request",
            multi_intent: false,
            tags: [],
            version: 5,
          },
          latest_run: {
            run_id: "run_error_latest",
            trace_id: "trace_error_latest",
            status: "succeeded",
            final_action: "handoff_to_human",
            evaluation_summary_ref: {
              status: "complete",
              trace_id: "trace_error_latest",
              has_response_quality: true,
              response_quality_overall_score: 4.5,
              has_trajectory_evaluation: true,
              trajectory_score: 4.4,
              trajectory_violation_count: 0,
            },
          },
          latest_draft: {
            draft_id: "draft_error_v1",
            qa_status: "pending",
          },
        });
      }

      if (url.endsWith("/tickets/ticket_error/runs?page=1&page_size=20")) {
        return jsonResponse({
          ticket_id: "ticket_error",
          items: [],
          page: 1,
          page_size: 20,
          total: 0,
        });
      }

      if (url.endsWith("/tickets/ticket_error/drafts")) {
        return jsonResponse({
          ticket_id: "ticket_error",
          items: [
            {
              draft_id: "draft_error_v1",
              run_id: "run_error_latest",
              version_index: 1,
              draft_type: "reply",
              qa_status: "pending",
              content_text: "Escalate me.",
              source_evidence_summary: null,
              gmail_draft_id: null,
              created_at: "2026-04-17T10:15:05Z",
            },
          ],
        });
      }

      if (url.endsWith("/tickets/ticket_error/approve")) {
        expect(init?.headers).toMatchObject({
          "X-Actor-Id": "reviewer-console",
        });

        return jsonResponse(
          {
            error: {
              code: "invalid_state_transition",
              message: "Ticket cannot be approved in its current state.",
            },
          },
          409,
        );
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderTicketDetailPage("/tickets/ticket_error");

    await screen.findByText("Escalate me.");
    fireEvent.click(screen.getByRole("button", { name: "批准" }));

    expect(
      await screen.findByText("批准失败"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Ticket cannot be approved in its current state."),
    ).toBeInTheDocument();
  });
});
