import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { GmailOpsPage } from "@/pages/GmailOpsPage";

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function renderGmailOpsPage() {
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
      <GmailOpsPage />
    </QueryClientProvider>,
  );
}

describe("GmailOpsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders runtime status, preview candidates, and scan receipt", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/ops/status")) {
        return jsonResponse({
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
            ticket_id: "ticket_err_1",
            run_id: "run_err_1",
            trace_id: "trace_err_1",
            error_code: "run_execution_failed",
            occurred_at: "2026-04-17T09:40:00Z",
          },
        });
      }

      if (url.endsWith("/ops/gmail/scan-preview")) {
        expect(init?.method).toBe("POST");
        expect(init?.body).toBe(JSON.stringify({ max_results: 20 }));

        return jsonResponse({
          gmail_enabled: true,
          requested_max_results: 20,
          summary: {
            candidate_threads: 3,
            skipped_existing_draft_threads: 1,
            skipped_self_sent_threads: 1,
          },
          items: [
            {
              source_thread_id: "thread-101",
              source_message_id: "<msg-101@gmail.com>",
              sender_email_raw: '"Alex" <alex@example.com>',
              subject: "Refund follow-up",
              skip_reason: null,
            },
            {
              source_thread_id: "thread-102",
              source_message_id: "<msg-102@gmail.com>",
              sender_email_raw: '"Jamie" <jamie@example.com>',
              subject: "Draft already exists",
              skip_reason: "existing_draft",
            },
          ],
        });
      }

      if (url.endsWith("/ops/gmail/scan")) {
        expect(init?.method).toBe("POST");
        expect(init?.body).toBe(JSON.stringify({ max_results: 20, enqueue: true }));

        return jsonResponse(
          {
            scan_id: "scan_20260417123001",
            status: "accepted",
            gmail_enabled: true,
            requested_max_results: 20,
            enqueue: true,
            summary: {
              fetched_threads: 3,
              ingested_tickets: 2,
              queued_runs: 2,
              skipped_existing_draft_threads: 1,
              skipped_self_sent_threads: 0,
              errors: 0,
            },
            items: [
              {
                source_thread_id: "thread-101",
                ticket_id: "ticket_101",
                created_ticket: true,
                queued_run_id: "run_101",
              },
              {
                source_thread_id: "thread-103",
                ticket_id: "ticket_103",
                created_ticket: false,
                queued_run_id: "run_103",
              },
            ],
          },
          202,
        );
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderGmailOpsPage();

    expect(
      screen.getByRole("heading", {
        name: "先预览候选，再执行摄入。",
      }),
    ).toBeInTheDocument();

    expect(
      await screen.findByText("当前邮箱已启用，允许操作员扫描。"),
    ).toBeInTheDocument();
    expect(screen.getByText("已连接")).toBeInTheDocument();
    expect(screen.getByText("support@example.com")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "预览扫描" }));

    expect(await screen.findByText("预览已加载")).toBeInTheDocument();
    const previewList = screen.getByLabelText("预览候选列表");
    expect(within(previewList).getByText("Refund follow-up")).toBeInTheDocument();
    expect(within(previewList).getByText("已有草稿")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "立即扫描" }));

    expect(await screen.findByText("扫描已接受")).toBeInTheDocument();
    expect(screen.getByText("scan_20260417123001")).toBeInTheDocument();
    const receiptList = screen.getByLabelText("扫描回执列表");
    expect(within(receiptList).getByText("ticket_101")).toBeInTheDocument();
    expect(within(receiptList).getByText("run_103")).toBeInTheDocument();
  });

  it("surfaces API failures for preview requests", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/ops/status")) {
        return jsonResponse({
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
        });
      }

      if (url.endsWith("/ops/gmail/scan-preview")) {
        expect(init?.method).toBe("POST");
        return jsonResponse(
          {
            error: {
              code: "invalid_state_transition",
              message: "Gmail integration is disabled.",
            },
          },
          409,
        );
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderGmailOpsPage();

    await screen.findByText("当前邮箱摄入已禁用。");
    fireEvent.click(screen.getByRole("button", { name: "预览扫描" }));

    expect(await screen.findByText("预览失败")).toBeInTheDocument();
    expect(screen.getByText("Gmail integration is disabled.")).toBeInTheDocument();
  });
});
