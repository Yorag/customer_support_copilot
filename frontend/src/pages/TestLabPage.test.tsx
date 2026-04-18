import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { TestLabPage } from "@/pages/TestLabPage";
import { useConsoleUiStore } from "@/state/console-ui-store";

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function renderTestLabPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <TestLabPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("TestLabPage", () => {
  beforeEach(() => {
    useConsoleUiStore.setState({
      testEmailDraft: {
        senderEmailRaw: '"Test User" <test.user@example.com>',
        subject: "",
        bodyText: "",
        autoEnqueue: true,
        scenarioLabel: "",
      },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads a preset, injects a test email, and exposes ticket and trace handoff links", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/dev/test-email")) {
        expect(init?.method).toBe("POST");
        expect(init?.body).toBe(
          JSON.stringify({
            sender_email_raw: '"Mina Park" <mina.park@example.com>',
            subject: "关于年度套餐重复扣费的退款跟进",
            body_text:
              "你好，客服团队：\n\n我昨天升级后，年度套餐被扣了两次费用。请确认其中一笔是否会退款，以及大概何时能退回到我的卡上。\n\n谢谢，\nMina",
            references:
              "客户反馈 4 月 16 日升级后发生年度套餐重复扣费。",
            auto_enqueue: true,
            scenario_label: "billing_refund_follow_up",
          }),
        );

        return jsonResponse(
          {
            ticket: {
              ticket_id: "ticket_lab_2001",
              created: true,
              business_status: "triaged",
              processing_status: "queued",
              version: 1,
            },
            run: {
              run_id: "run_lab_2001",
              trace_id: "trace_lab_2001",
              processing_status: "queued",
            },
            test_metadata: {
              scenario_label: "billing_refund_follow_up",
              auto_enqueue: true,
              source_channel: "dev_test_email",
            },
          },
          202,
        );
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderTestLabPage();

    expect(
      screen.getByRole("heading", {
        name: "用受控邮件场景验证整条流程。",
      }),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /账单退款|关于年度套餐重复扣费的退款跟进/i }),
    );

    expect(await screen.findByText("场景已装载")).toBeInTheDocument();
    expect(screen.getByDisplayValue('"Mina Park" <mina.park@example.com>')).toBeInTheDocument();
    expect(
      screen.getByDisplayValue("关于年度套餐重复扣费的退款跟进"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "注入测试邮件" }));

    expect(await screen.findByText("注入已接受")).toBeInTheDocument();
    const receiptSummary = screen.getByLabelText("注入回执摘要");
    expect(within(receiptSummary).getByText("ticket_lab_2001")).toBeInTheDocument();
    expect(within(receiptSummary).getByText("run_lab_2001")).toBeInTheDocument();

    const linkRow = screen.getByLabelText("注入结果链接");
    expect(within(linkRow).getByRole("link", { name: "打开工单" })).toHaveAttribute(
      "href",
      "/tickets/ticket_lab_2001",
    );
    expect(within(linkRow).getByRole("link", { name: "打开 Trace" })).toHaveAttribute(
      "href",
      "/trace?ticketId=ticket_lab_2001&runId=run_lab_2001",
    );
  });

  it("surfaces API failures from the injection endpoint", async () => {
    const fetchMock = vi.fn().mockImplementation((input: string | URL | Request) => {
      const url = String(input);

      if (url.endsWith("/dev/test-email")) {
        return jsonResponse(
          {
            error: {
              code: "invalid_state_transition",
              message: "The test email endpoint is disabled in this environment.",
            },
          },
          409,
        );
      }

      throw new Error(`Unhandled request in test: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    renderTestLabPage();

    fireEvent.click(
      screen.getByRole("button", { name: /技术故障|凭据轮换后 api 返回 502/i }),
    );
    fireEvent.click(screen.getByRole("button", { name: "注入测试邮件" }));

    expect(await screen.findByText("注入失败")).toBeInTheDocument();
    expect(
      screen.getByText("The test email endpoint is disabled in this environment."),
    ).toBeInTheDocument();
  });
});
