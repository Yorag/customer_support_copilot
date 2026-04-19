import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { TicketDetailPageV2 } from "@/pages-v2/TicketDetailPageV2";
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
          <Route path="/tickets/:ticketId" element={<TicketDetailPageV2 />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("TicketDetailPageV2", () => {
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

  it("renders a condensed object-first detail layout", async () => {
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
          messages: [
            {
              ticket_message_id: "msg_internal_1",
              source_message_id: "msg_internal_source_1",
              direction: "outbound",
              message_type: "internal_note",
              sender_email: "ops@example.com",
              recipient_emails: [],
              subject: "Internal note",
              body_text: "Need human review",
              reply_to_source_message_id: null,
              customer_visible: false,
              message_timestamp: "2026-04-17T09:45:00Z",
              metadata: {},
            },
            {
              ticket_message_id: "msg_customer_1",
              source_message_id: "msg_customer_source_1",
              direction: "inbound",
              message_type: "customer_email",
              sender_email: "customer@example.com",
              recipient_emails: ["support@example.com"],
              subject: "Need policy exception approval",
              body_text: "Can you approve a special commercial exception for this order?",
              reply_to_source_message_id: null,
              customer_visible: true,
              message_timestamp: "2026-04-17T10:14:00Z",
              metadata: {
                sender_email_raw: "\"Customer\" <customer@example.com>",
                gmail_thread_id: "thread_4012",
              },
            },
          ],
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
      await screen.findByRole("heading", { name: "原始邮件" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "当前状态" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "草稿与动作" })).toBeInTheDocument();
    expect(await screen.findByDisplayValue("Approved draft body for the customer.")).toBeInTheDocument();
    expect(screen.getAllByText("Approved draft body for the customer.").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("人工动作状态")).toHaveTextContent("草稿 draft_4012_v2");
    expect(
      screen.getByRole("heading", { name: "Need policy exception approval" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("\"Customer\" <customer@example.com>").length).toBeGreaterThan(0);
    expect(screen.getByText("support@example.com")).toBeInTheDocument();
    expect(screen.getByText("msg_customer_source_1")).toBeInTheDocument();
    expect(screen.getByLabelText("原始邮件正文")).toHaveTextContent(
      "Can you approve a special commercial exception for this order?",
    );
    expect(screen.getByText("最新运行")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "打开 Trace" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "批准当前草稿" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "重新生成草稿" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "保存草稿" })).toBeDisabled();

    fireEvent.click(screen.getByText("运行历史 2 次"));
    const runHistory = await screen.findByLabelText("运行历史卷带");
    expect(within(runHistory).getByText("run_4012_failed")).toBeInTheDocument();
    expect(within(runHistory).getByText(/轨迹 2\.5 · 1 条违规/i)).toBeInTheDocument();

    fireEvent.click(screen.getByText("草稿历史 2 个版本"));
    const draftHistory = await screen.findByLabelText("草稿版本阶梯");
    expect(within(draftHistory).getByText("draft_4012_v1")).toBeInTheDocument();
    expect(within(draftHistory).getByText(/版本 2 · 已通过/i)).toBeInTheDocument();

    fireEvent.click(screen.getByText("邮件线程 2 条消息"));
    fireEvent.click(screen.getByRole("button", { name: /Internal note/i }));
    expect(await screen.findByDisplayValue("Approved draft body for the customer.")).toBeInTheDocument();
    expect(screen.getAllByText("Need human review").length).toBeGreaterThan(0);
    expect(screen.getAllByText("ops@example.com").length).toBeGreaterThan(0);
  });

  it("keeps action buttons honest when no draft or run exists", async () => {
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
          messages: [],
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
      await screen.findByRole("heading", { name: "草稿与动作" }),
    ).toBeInTheDocument();
    expect(screen.getByText("该工单当前没有任何草稿版本")).toBeInTheDocument();
    expect(screen.getByText("暂无可查看的运行。")).toBeInTheDocument();
    expect(await screen.findByDisplayValue("reviewer-console")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建草稿" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "批准当前草稿" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "保存草稿" })).toBeDisabled();
    fireEvent.click(screen.getByText("更多操作"));
    expect(screen.getByRole("button", { name: "按原因重写" })).toBeDisabled();
  });

  it("renders long run and trace ids inside the handoff cards", async () => {
    const longRunId = "run_01KP7YNRVF5FNBYS3CB17Z6V7M01KP7YNRVF5FNBYS3CB17Z6V7M";
    const longTraceId = "trace_01KP7YNRVGDX21JH96J2TRACE01KP7YNRVGDX21JH96J2TRACE";
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request) => {
      const url = String(input);

      if (url.endsWith("/tickets/ticket_long")) {
        return jsonResponse({
          ticket: {
            ticket_id: "ticket_long",
            business_status: "awaiting_human_review",
            processing_status: "waiting_external",
            claimed_by: null,
            claimed_at: null,
            lease_until: null,
            priority: "high",
            primary_route: "commercial_policy_request",
            multi_intent: false,
            tags: [],
            version: 6,
          },
          latest_run: {
            run_id: longRunId,
            trace_id: longTraceId,
            status: "succeeded",
            final_action: "handoff_to_human",
            evaluation_summary_ref: {
              status: "complete",
              trace_id: longTraceId,
              has_response_quality: true,
              response_quality_overall_score: 3,
              has_trajectory_evaluation: true,
              trajectory_score: 5,
              trajectory_violation_count: 0,
            },
          },
          latest_draft: null,
          messages: [],
        });
      }

      if (url.endsWith("/tickets/ticket_long/runs?page=1&page_size=20")) {
        return jsonResponse({
          ticket_id: "ticket_long",
          items: [
            {
              run_id: longRunId,
              trace_id: longTraceId,
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
                trace_id: longTraceId,
                has_response_quality: true,
                response_quality_overall_score: 3,
                has_trajectory_evaluation: true,
                trajectory_score: 5,
                trajectory_violation_count: 0,
              },
            },
          ],
          page: 1,
          page_size: 20,
          total: 1,
        });
      }

      if (url.endsWith("/tickets/ticket_long/drafts")) {
        return jsonResponse({
          ticket_id: "ticket_long",
          items: [],
        });
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderTicketDetailPage("/tickets/ticket_long");

    expect(await screen.findByRole("button", { name: "打开 Trace" })).toBeInTheDocument();
    const codeNodes = Array.from(document.querySelectorAll(".v2-code")).map((node) =>
      node.textContent?.trim(),
    );
    expect(codeNodes).toContain(longRunId);
    expect(codeNodes).toContain(longTraceId);
  });

  it("saves an edited draft and keeps approval blocked until the new version loads", async () => {
    let snapshotRequestCount = 0;
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/tickets/ticket_reply")) {
        snapshotRequestCount += 1;

        return jsonResponse({
          ticket: {
            ticket_id: "ticket_reply",
            business_status: "awaiting_human_review",
            processing_status: "waiting_external",
            claimed_by: null,
            claimed_at: null,
            lease_until: null,
            priority: "high",
            primary_route: "technical_issue",
            multi_intent: false,
            tags: [],
            version: snapshotRequestCount === 1 ? 4 : 5,
          },
          latest_run: {
            run_id: snapshotRequestCount === 1 ? "run_reply_1" : "run_reply_2",
            trace_id: snapshotRequestCount === 1 ? "trace_reply_1" : "trace_reply_2",
            status: "succeeded",
            final_action: "handoff_to_human",
            evaluation_summary_ref: {
              status: "complete",
              trace_id: snapshotRequestCount === 1 ? "trace_reply_1" : "trace_reply_2",
              has_response_quality: true,
              response_quality_overall_score: 4.2,
              has_trajectory_evaluation: true,
              trajectory_score: 4.3,
              trajectory_violation_count: 0,
            },
          },
          latest_draft: {
            draft_id: snapshotRequestCount === 1 ? "draft_reply_v1" : "draft_reply_v2",
            qa_status: snapshotRequestCount === 1 ? "passed" : "pending",
          },
          messages: [
            {
              ticket_message_id: "msg_reply_customer",
              source_message_id: "msg_reply_source",
              direction: "inbound",
              message_type: "customer_email",
              sender_email: "customer@example.com",
              recipient_emails: ["support@example.com"],
              subject: "Need timeline",
              body_text: "Please give me a concrete ETA.",
              reply_to_source_message_id: null,
              customer_visible: true,
              message_timestamp: "2026-04-17T10:14:00Z",
              metadata: {
                sender_email_raw: "\"Customer\" <customer@example.com>",
              },
            },
          ],
        });
      }

      if (url.endsWith("/tickets/ticket_reply/runs?page=1&page_size=20")) {
        return jsonResponse({
          ticket_id: "ticket_reply",
          items: [
            {
              run_id: snapshotRequestCount === 1 ? "run_reply_1" : "run_reply_2",
              trace_id: snapshotRequestCount === 1 ? "trace_reply_1" : "trace_reply_2",
              trigger_type: "human_action",
              triggered_by: "reviewer-console",
              status: "succeeded",
              final_action: snapshotRequestCount === 1 ? "handoff_to_human" : "no_op",
              started_at: "2026-04-17T10:20:00Z",
              ended_at: "2026-04-17T10:20:10Z",
              attempt_index: 2,
              is_human_action: true,
              evaluation_summary_ref: {
                status: "complete",
                trace_id: snapshotRequestCount === 1 ? "trace_reply_1" : "trace_reply_2",
                has_response_quality: true,
                response_quality_overall_score: 4.6,
                has_trajectory_evaluation: true,
                trajectory_score: 4.6,
                trajectory_violation_count: 0,
              },
            },
          ],
          page: 1,
          page_size: 20,
          total: 1,
        });
      }

      if (url.endsWith("/tickets/ticket_reply/drafts")) {
        return jsonResponse({
          ticket_id: "ticket_reply",
          items:
            snapshotRequestCount <= 1
              ? [
                  {
                    draft_id: "draft_reply_v1",
                    run_id: "run_reply_1",
                    version_index: 1,
                    draft_type: "reply",
                    qa_status: "passed",
                    content_text: "Initial agent draft",
                    source_evidence_summary: null,
                    gmail_draft_id: "gmail-draft-reply-1",
                    created_at: "2026-04-17T10:15:05Z",
                  },
                ]
              : [
                  {
                    draft_id: "draft_reply_v1",
                    run_id: "run_reply_1",
                    version_index: 1,
                    draft_type: "reply",
                    qa_status: "passed",
                    content_text: "Initial agent draft",
                    source_evidence_summary: null,
                    gmail_draft_id: "gmail-draft-reply-1",
                    created_at: "2026-04-17T10:15:05Z",
                  },
                  {
                    draft_id: "draft_reply_v2",
                    run_id: "run_reply_2",
                    version_index: 2,
                    draft_type: "reply",
                    qa_status: "pending",
                    content_text: "Human revised reply with concrete ETA.",
                    source_evidence_summary: null,
                    gmail_draft_id: null,
                    created_at: "2026-04-17T10:20:05Z",
                  },
                ],
        });
      }

      if (url.endsWith("/tickets/ticket_reply/drafts/save")) {
        expect(init?.method).toBe("POST");
        expect(init?.headers).toMatchObject({
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Actor-Id": "reviewer-console",
        });
        expect(init?.body).toBe(
          JSON.stringify({
            ticket_version: 4,
            draft_id: "draft_reply_v1",
            comment: null,
            edited_content_text: "Human revised reply with concrete ETA.",
          }),
        );

        return jsonResponse({
          ticket_id: "ticket_reply",
          review_id: "review_reply_save_1",
          business_status: "awaiting_human_review",
          processing_status: "waiting_external",
          version: 5,
        });
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderTicketDetailPage("/tickets/ticket_reply");

    expect(await screen.findByDisplayValue("Initial agent draft")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("人工回复正文"), {
      target: { value: "Human revised reply with concrete ETA." },
    });
    expect(screen.getByText("编辑区有未保存改动")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "批准当前草稿" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));

    expect(await screen.findByText("草稿已保存")).toBeInTheDocument();
    expect(screen.getByText(/待人工审核 · 等待外部处理 · 工单版本 5/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByDisplayValue("Human revised reply with concrete ETA.")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "批准当前草稿" })).toBeEnabled();
  });

  it("submits a human reply edit and then closes the ticket", async () => {
    let snapshotRequestCount = 0;
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/tickets/ticket_reply")) {
        snapshotRequestCount += 1;

        if (snapshotRequestCount === 1) {
          return jsonResponse({
            ticket: {
              ticket_id: "ticket_reply",
              business_status: "awaiting_human_review",
              processing_status: "waiting_external",
              claimed_by: null,
              claimed_at: null,
              lease_until: null,
              priority: "high",
              primary_route: "technical_issue",
              multi_intent: false,
              tags: [],
              version: 4,
            },
            latest_run: {
              run_id: "run_reply_1",
              trace_id: "trace_reply_1",
              status: "succeeded",
              final_action: "handoff_to_human",
              evaluation_summary_ref: {
                status: "complete",
                trace_id: "trace_reply_1",
                has_response_quality: true,
                response_quality_overall_score: 4.2,
                has_trajectory_evaluation: true,
                trajectory_score: 4.3,
                trajectory_violation_count: 0,
              },
            },
            latest_draft: {
              draft_id: "draft_reply_v1",
              qa_status: "passed",
            },
            messages: [
              {
                ticket_message_id: "msg_reply_customer",
                source_message_id: "msg_reply_source",
                direction: "inbound",
                message_type: "customer_email",
                sender_email: "customer@example.com",
                recipient_emails: ["support@example.com"],
                subject: "Need timeline",
                body_text: "Please give me a concrete ETA.",
                reply_to_source_message_id: null,
                customer_visible: true,
                message_timestamp: "2026-04-17T10:14:00Z",
                metadata: {
                  sender_email_raw: "\"Customer\" <customer@example.com>",
                },
              },
            ],
          });
        }

        return jsonResponse({
          ticket: {
            ticket_id: "ticket_reply",
            business_status: "closed",
            processing_status: "completed",
            claimed_by: null,
            claimed_at: null,
            lease_until: null,
            priority: "high",
            primary_route: "technical_issue",
            multi_intent: false,
            tags: [],
            version: 6,
          },
          latest_run: {
            run_id: "run_reply_2",
            trace_id: "trace_reply_2",
            status: "succeeded",
            final_action: "close_ticket",
            evaluation_summary_ref: {
              status: "complete",
              trace_id: "trace_reply_2",
              has_response_quality: true,
              response_quality_overall_score: 4.6,
              has_trajectory_evaluation: true,
              trajectory_score: 4.6,
              trajectory_violation_count: 0,
            },
          },
          latest_draft: {
            draft_id: "draft_reply_v2",
            qa_status: "passed",
          },
          messages: [
            {
              ticket_message_id: "msg_reply_customer",
              source_message_id: "msg_reply_source",
              direction: "inbound",
              message_type: "customer_email",
              sender_email: "customer@example.com",
              recipient_emails: ["support@example.com"],
              subject: "Need timeline",
              body_text: "Please give me a concrete ETA.",
              reply_to_source_message_id: null,
              customer_visible: true,
              message_timestamp: "2026-04-17T10:14:00Z",
              metadata: {
                sender_email_raw: "\"Customer\" <customer@example.com>",
              },
            },
          ],
        });
      }

      if (url.endsWith("/tickets/ticket_reply/runs?page=1&page_size=20")) {
        return jsonResponse({
          ticket_id: "ticket_reply",
          items: [
            {
              run_id: "run_reply_2",
              trace_id: "trace_reply_2",
              trigger_type: "human_action",
              triggered_by: "reviewer-console",
              status: "succeeded",
              final_action: "close_ticket",
              started_at: "2026-04-17T10:20:00Z",
              ended_at: "2026-04-17T10:20:10Z",
              attempt_index: 2,
              is_human_action: true,
              evaluation_summary_ref: {
                status: "complete",
                trace_id: "trace_reply_2",
                has_response_quality: true,
                response_quality_overall_score: 4.6,
                has_trajectory_evaluation: true,
                trajectory_score: 4.6,
                trajectory_violation_count: 0,
              },
            },
          ],
          page: 1,
          page_size: 20,
          total: 1,
        });
      }

      if (url.endsWith("/tickets/ticket_reply/drafts")) {
        return jsonResponse({
          ticket_id: "ticket_reply",
          items:
            snapshotRequestCount <= 1
              ? [
                  {
                    draft_id: "draft_reply_v1",
                    run_id: "run_reply_1",
                    version_index: 1,
                    draft_type: "reply",
                    qa_status: "passed",
                    content_text: "Initial agent draft",
                    source_evidence_summary: null,
                    gmail_draft_id: "gmail-draft-reply-1",
                    created_at: "2026-04-17T10:15:05Z",
                  },
                ]
              : [
                  {
                    draft_id: "draft_reply_v1",
                    run_id: "run_reply_1",
                    version_index: 1,
                    draft_type: "reply",
                    qa_status: "passed",
                    content_text: "Initial agent draft",
                    source_evidence_summary: null,
                    gmail_draft_id: "gmail-draft-reply-1",
                    created_at: "2026-04-17T10:15:05Z",
                  },
                  {
                    draft_id: "draft_reply_v2",
                    run_id: "run_reply_2",
                    version_index: 2,
                    draft_type: "reply",
                    qa_status: "passed",
                    content_text: "Human revised reply with concrete ETA.",
                    source_evidence_summary: null,
                    gmail_draft_id: "gmail-draft-reply-2",
                    created_at: "2026-04-17T10:20:05Z",
                  },
                ],
        });
      }

      if (url.endsWith("/tickets/ticket_reply/edit-and-approve")) {
        expect(init?.method).toBe("POST");
        expect(init?.headers).toMatchObject({
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Actor-Id": "reviewer-console",
        });
        expect(init?.body).toBe(
          JSON.stringify({
            ticket_version: 4,
            draft_id: "draft_reply_v1",
            comment: null,
            edited_content_text: "Human revised reply with concrete ETA.",
          }),
        );

        return jsonResponse({
          ticket_id: "ticket_reply",
          review_id: "review_reply_1",
          business_status: "approved",
          processing_status: "completed",
          version: 5,
        });
      }

      if (url.endsWith("/tickets/ticket_reply/close")) {
        expect(init?.method).toBe("POST");
        expect(init?.headers).toMatchObject({
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Actor-Id": "reviewer-console",
        });
        expect(init?.body).toBe(
          JSON.stringify({
            ticket_version: 5,
            reason: "resolved_manually",
          }),
        );

        return jsonResponse({
          ticket_id: "ticket_reply",
          business_status: "closed",
          processing_status: "completed",
          version: 6,
        });
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderTicketDetailPage("/tickets/ticket_reply");

    expect(await screen.findByDisplayValue("Initial agent draft")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("人工回复正文"), {
      target: { value: "Human revised reply with concrete ETA." },
    });
    fireEvent.click(screen.getByText("更多操作"));
    fireEvent.click(screen.getByRole("button", { name: "保存并批准后关闭" }));

    expect(await screen.findByText("人工回复已保存并关闭工单")).toBeInTheDocument();
    expect(
      screen.getByText(/已关闭 · 已完成 · 工单版本 6。/i),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByDisplayValue("Human revised reply with concrete ETA.")).toBeInTheDocument();
    });
  });

  it("queues draft generation directly from the detail page when no draft exists", async () => {
    let snapshotRequestCount = 0;
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/tickets/ticket_generate")) {
        snapshotRequestCount += 1;

        return jsonResponse(
          snapshotRequestCount === 1
            ? {
                ticket: {
                  ticket_id: "ticket_generate",
                  business_status: "awaiting_human_review",
                  processing_status: "waiting_external",
                  claimed_by: null,
                  claimed_at: null,
                  lease_until: null,
                  priority: "high",
                  primary_route: "commercial_policy_request",
                  multi_intent: false,
                  tags: ["needs_escalation"],
                  version: 5,
                },
                latest_run: null,
                latest_draft: null,
                messages: [],
              }
            : {
                ticket: {
                  ticket_id: "ticket_generate",
                  business_status: "triaged",
                  processing_status: "queued",
                  claimed_by: null,
                  claimed_at: null,
                  lease_until: null,
                  priority: "high",
                  primary_route: "commercial_policy_request",
                  multi_intent: false,
                  tags: ["needs_escalation"],
                  version: 6,
                },
                latest_run: {
                  run_id: "run_generate_1",
                  trace_id: "trace_generate_1",
                  status: "queued",
                  final_action: null,
                  evaluation_summary_ref: {
                    status: "not_available",
                    trace_id: "trace_generate_1",
                    has_response_quality: false,
                    response_quality_overall_score: null,
                    has_trajectory_evaluation: false,
                    trajectory_score: null,
                    trajectory_violation_count: null,
                  },
                },
                latest_draft: null,
                messages: [],
              },
        );
      }

      if (url.endsWith("/tickets/ticket_generate/runs?page=1&page_size=20")) {
        return jsonResponse({
          ticket_id: "ticket_generate",
          items:
            snapshotRequestCount === 1
              ? []
              : [
                  {
                    run_id: "run_generate_1",
                    trace_id: "trace_generate_1",
                    trigger_type: "manual_api",
                    triggered_by: "reviewer-console",
                    status: "queued",
                    final_action: null,
                    started_at: null,
                    ended_at: null,
                    attempt_index: 1,
                    is_human_action: false,
                    evaluation_summary_ref: {
                      status: "not_available",
                      trace_id: "trace_generate_1",
                      has_response_quality: false,
                      response_quality_overall_score: null,
                      has_trajectory_evaluation: false,
                      trajectory_score: null,
                      trajectory_violation_count: null,
                    },
                  },
                ],
          page: 1,
          page_size: 20,
          total: snapshotRequestCount === 1 ? 0 : 1,
        });
      }

      if (url.endsWith("/tickets/ticket_generate/drafts")) {
        return jsonResponse({
          ticket_id: "ticket_generate",
          items: [],
        });
      }

      if (url.endsWith("/tickets/ticket_generate/drafts/generate")) {
        expect(init?.method).toBe("POST");
        expect(init?.headers).toMatchObject({
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Actor-Id": "reviewer-console",
        });
        expect(init?.body).toBe(
          JSON.stringify({
            ticket_version: 5,
            mode: "create",
            source_draft_id: null,
            comment: null,
          }),
        );
        return jsonResponse({
          ticket_id: "ticket_generate",
          run_id: "run_generate_1",
          trace_id: "trace_generate_1",
          processing_status: "queued",
        }, 202);
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderTicketDetailPage("/tickets/ticket_generate");

    expect(await screen.findByDisplayValue("reviewer-console")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "创建草稿" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "创建草稿" }));

    expect(await screen.findByText("已提交创建草稿")).toBeInTheDocument();
    expect(screen.getByText(/运行 run_generate_1 已入队/i)).toBeInTheDocument();
  });

  it("sends rewrite guidance through draft generation instead of the legacy rewrite endpoint", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/tickets/ticket_guided")) {
        return jsonResponse({
          ticket: {
            ticket_id: "ticket_guided",
            business_status: "awaiting_human_review",
            processing_status: "waiting_external",
            claimed_by: null,
            claimed_at: null,
            lease_until: null,
            priority: "high",
            primary_route: "commercial_policy_request",
            multi_intent: false,
            tags: ["needs_escalation"],
            version: 9,
          },
          latest_run: null,
          latest_draft: {
            draft_id: "draft_guided_v1",
            qa_status: "passed",
          },
          messages: [],
        });
      }

      if (url.endsWith("/tickets/ticket_guided/runs?page=1&page_size=20")) {
        return jsonResponse({
          ticket_id: "ticket_guided",
          items: [],
          page: 1,
          page_size: 20,
          total: 0,
        });
      }

      if (url.endsWith("/tickets/ticket_guided/drafts")) {
        return jsonResponse({
          ticket_id: "ticket_guided",
          items: [
            {
              draft_id: "draft_guided_v1",
              run_id: "run_guided_0",
              version_index: 1,
              draft_type: "reply",
              qa_status: "passed",
              content_text: "Initial guided draft",
              source_evidence_summary: null,
              gmail_draft_id: "gmail-guided-1",
              created_at: "2026-04-17T10:15:05Z",
            },
          ],
        });
      }

      if (url.endsWith("/tickets/ticket_guided/drafts/generate")) {
        expect(init?.method).toBe("POST");
        expect(init?.body).toBe(
          JSON.stringify({
            ticket_version: 9,
            mode: "regenerate",
            source_draft_id: "draft_guided_v1",
            comment: null,
            rewrite_guidance: [
              "Keep the tone calm.",
              "Avoid commitment wording.",
            ],
          }),
        );
        return jsonResponse({
          ticket_id: "ticket_guided",
          run_id: "run_guided_1",
          trace_id: "trace_guided_1",
          processing_status: "queued",
        }, 202);
      }

      if (url.endsWith("/tickets/ticket_guided/rewrite")) {
        throw new Error("Legacy rewrite endpoint should not be called.");
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderTicketDetailPage("/tickets/ticket_guided");

    expect(await screen.findByDisplayValue("reviewer-console")).toBeInTheDocument();
    fireEvent.click(screen.getByText("更多操作"));
    fireEvent.change(screen.getByLabelText("重写原因"), {
      target: { value: "Keep the tone calm.\nAvoid commitment wording." },
    });
    fireEvent.click(screen.getByRole("button", { name: "按原因重写" }));

    expect(await screen.findByText("已提交带指导的草稿重生成")).toBeInTheDocument();
    expect(screen.getByText(/运行 run_guided_1 已入队/i)).toBeInTheDocument();
  });

  it("shows trajectory-only evaluation copy when latest run has no response quality", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request) => {
      const url = String(input);

      if (url.endsWith("/tickets/ticket_partial")) {
        return jsonResponse({
          ticket: {
            ticket_id: "ticket_partial",
            business_status: "awaiting_human_review",
            processing_status: "waiting_external",
            claimed_by: null,
            claimed_at: null,
            lease_until: null,
            priority: "high",
            primary_route: "commercial_policy_request",
            multi_intent: false,
            tags: ["needs_escalation"],
            version: 3,
          },
          latest_run: {
            run_id: "run_partial",
            trace_id: "trace_partial",
            status: "succeeded",
            final_action: "handoff_to_human",
            evaluation_summary_ref: {
              status: "partial",
              trace_id: "trace_partial",
              has_response_quality: false,
              response_quality_overall_score: null,
              has_trajectory_evaluation: true,
              trajectory_score: 4.8,
              trajectory_violation_count: 0,
            },
          },
          latest_draft: null,
          messages: [],
        });
      }

      if (url.endsWith("/tickets/ticket_partial/runs?page=1&page_size=20")) {
        return jsonResponse({
          ticket_id: "ticket_partial",
          items: [
            {
              run_id: "run_partial",
              trace_id: "trace_partial",
              trigger_type: "manual_api",
              triggered_by: "operator-1",
              status: "succeeded",
              final_action: "handoff_to_human",
              started_at: "2026-04-17T10:15:00Z",
              ended_at: "2026-04-17T10:15:09Z",
              attempt_index: 1,
              is_human_action: false,
              evaluation_summary_ref: {
                status: "partial",
                trace_id: "trace_partial",
                has_response_quality: false,
                response_quality_overall_score: null,
                has_trajectory_evaluation: true,
                trajectory_score: 4.8,
                trajectory_violation_count: 0,
              },
            },
          ],
          page: 1,
          page_size: 20,
          total: 1,
        });
      }

      if (url.endsWith("/tickets/ticket_partial/drafts")) {
        return jsonResponse({
          ticket_id: "ticket_partial",
          items: [],
        });
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderTicketDetailPage("/tickets/ticket_partial");

    expect((await screen.findAllByText(/轨迹 4\.8 · 0 条违规/i)).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("当前运行没有回复质量评分，只展示常规运行与轨迹信息。")).toBeInTheDocument();
    expect(screen.queryByText("质量 4.8")).not.toBeInTheDocument();
  });
});
