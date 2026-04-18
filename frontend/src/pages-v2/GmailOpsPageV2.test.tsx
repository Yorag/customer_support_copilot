import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { GmailOpsPageV2 } from "@/pages-v2/GmailOpsPageV2";

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
      <GmailOpsPageV2 />
    </QueryClientProvider>,
  );
}

describe("GmailOpsPageV2", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the compact action row, candidate waterfall, and batch notice", async () => {
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
          recent_failure: null,
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
      await screen.findByRole("heading", {
        name: "摄入与入队",
      }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/邮箱可扫描 .* 本次摄入后自动入队/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Gmail 运维区域")).toHaveTextContent("入队方式");
    expect(screen.getByLabelText("Gmail 运维区域")).toHaveTextContent("扫描上限");
    expect(screen.getByRole("button", { name: "全部摄入当前批次" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "预览候选" })).toBeInTheDocument();
    expect(screen.getByText("当前还没有待处理新邮件")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "预览候选" }));

    expect(await screen.findByText("预览已加载")).toBeInTheDocument();
    expect(screen.getByText("3 个待摄入候选 · 1 个已有草稿 · 1 个自发邮件")).toBeInTheDocument();
    const previewList = screen.getByLabelText("预览候选列表");
    expect(within(previewList).getByText("Refund follow-up")).toBeInTheDocument();
    expect(within(previewList).getByText("已有草稿")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "全部摄入当前批次" }));

    expect(await screen.findByText("批次已提交")).toBeInTheDocument();
    expect(
      screen.getByText("已摄入 2 个工单，并入队 2 次运行。"),
    ).toBeInTheDocument();
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

    await screen.findByText(/邮箱未启用 .* 本次摄入后自动入队/);
    fireEvent.click(screen.getByRole("button", { name: "预览候选" }));

    expect(await screen.findByText("预览失败")).toBeInTheDocument();
    expect(screen.getByText("Gmail integration is disabled.")).toBeInTheDocument();
    expect(screen.getByText(/邮箱未启用 .* 尚无扫描记录/)).toBeInTheDocument();
  });
});
