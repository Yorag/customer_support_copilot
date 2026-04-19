import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { TestLabPageV2 } from "@/pages-v2/TestLabPageV2";
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
        <TestLabPageV2 />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("TestLabPageV2", () => {
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
            subject: "昨天升级后被扣了两笔年费，想确认退款时间",
            body_text:
              "我昨天把工作区升级到年度套餐，银行卡这边连续入账了两笔相同金额。\n\n后台现在只看到一个有效订阅，所以看起来像是重复扣费。想确认一下另一笔是不是会原路退回，大概需要多久能到账。\n\n如果你们需要，我可以把账单截图和卡片尾号后四位补过来。",
            references:
              "客户反馈 4 月 16 日升级到年度套餐后出现重复扣费，当前系统仅显示一个有效订阅。",
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

    expect(screen.queryByRole("heading", { name: "用受控邮件场景验证整条流程" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "先确认输入，再提交" })).toBeInTheDocument();
    expect(screen.queryByLabelText("测试实验台区域")).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /账单退款|昨天升级后被扣了两笔年费，想确认退款时间/i }),
    );

    expect(await screen.findByText("场景已装载")).toBeInTheDocument();
    expect(screen.getByDisplayValue('"Mina Park" <mina.park@example.com>')).toBeInTheDocument();
    expect(
      screen.getByDisplayValue("昨天升级后被扣了两笔年费，想确认退款时间"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "注入测试邮件" }));

    expect(await screen.findByText("注入已接受")).toBeInTheDocument();
    const receiptSummary = screen.getByLabelText("注入回执摘要");
    expect(within(receiptSummary).getByText("ticket_lab_2001")).toBeInTheDocument();
    expect(within(receiptSummary).getByText("运行: run_lab_2001")).toBeInTheDocument();

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
      screen.getByRole("button", { name: /技术故障|生产环境从今天早上开始一直返回 502/i }),
    );
    fireEvent.click(screen.getByRole("button", { name: "注入测试邮件" }));

    expect(await screen.findByText("注入失败")).toBeInTheDocument();
    expect(
      screen.getByText("The test email endpoint is disabled in this environment."),
    ).toBeInTheDocument();
  });
});
