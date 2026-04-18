import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { Providers } from "@/app/providers";
import { TicketsPage } from "@/pages/TicketsPage";
import { useConsoleUiStore } from "@/state/console-ui-store";

function buildTicketListResponse(overrides?: {
  items?: Array<Record<string, unknown>>;
  page?: number;
  page_size?: number;
  total?: number;
}) {
  return {
    items: [
      {
        ticket_id: "ticket_4012",
        customer_id: "cust_4012",
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
      {
        ticket_id: "ticket_4008",
        customer_id: "cust_4008",
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
    page_size: 20,
    total: 2,
    ...overrides,
  };
}

function renderTicketsPage() {
  return render(
    <MemoryRouter initialEntries={["/tickets"]}>
      <Providers>
        <Routes>
          <Route path="/tickets" element={<TicketsPage />} />
          <Route path="/tickets/:ticketId" element={<div>Ticket Detail Route</div>} />
        </Routes>
      </Providers>
    </MemoryRouter>,
  );
}

describe("TicketsPage", () => {
  beforeEach(() => {
    useConsoleUiStore.getState().resetTicketListFilters();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders live ticket rows from GET /tickets", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify(buildTicketListResponse()), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderTicketsPage();

    expect(
      screen.getByRole("heading", {
        name: "先整理台账，再进入单个案件。",
      }),
    ).toBeInTheDocument();

    expect(
      await screen.findByRole("heading", {
        name: "从当前分页中找到需要处理的工单。",
      }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("工单队列摘要")).toHaveTextContent("筛选结果");
    expect(
      await screen.findByLabelText("工单实时行"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("每页行数")).toHaveValue("20");
    expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
    expect(screen.getByText(/正在显示 1-2 \/ 2 条实时记录/i)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "打开详情" })).toHaveLength(2);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/tickets?page=1&page_size=20"),
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("forwards filter state into GET /tickets and resets the workbench state", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify(buildTicketListResponse({ total: 2 })), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderTicketsPage();

    await screen.findByText("Duplicate billing charge still unresolved");

    fireEvent.change(screen.getByLabelText("待审核"), {
      target: { value: "yes" },
    });
    fireEvent.change(screen.getByLabelText("搜索工单"), {
      target: { value: "refund" },
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        expect.stringContaining("awaiting_review=true"),
        expect.objectContaining({ method: "GET" }),
      );
    });
    expect(fetchMock.mock.calls.at(-1)?.[0]).toContain("query=refund");

    fireEvent.click(screen.getByRole("button", { name: "重置全部筛选" }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.at(-1)?.[0]).toContain("/tickets?page=1&page_size=20");
    });

    const ledger = screen.getByLabelText("工单实时行");
    const rows = within(ledger).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(screen.getByLabelText("搜索工单")).toHaveValue("");
    expect(screen.getByLabelText("待审核")).toHaveValue("all");
  });

  it("uses server pagination responses to advance the ledger", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() =>
        Promise.resolve(
          new Response(
            JSON.stringify(
              buildTicketListResponse({
                items: [buildTicketListResponse().items[0], buildTicketListResponse().items[1]],
                page: 1,
                page_size: 2,
                total: 3,
              }),
            ),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        ),
      )
      .mockImplementationOnce(() =>
        Promise.resolve(
          new Response(
            JSON.stringify(
              buildTicketListResponse({
                items: [
                  {
                    ticket_id: "ticket_3988",
                    customer_id: "cust_3988",
                    customer_email_raw: "mika@harbor.example",
                    subject: "Agent suggested escalation after compliance request",
                    business_status: "escalated",
                    processing_status: "error",
                    priority: "critical",
                    primary_route: "compliance_escalation",
                    multi_intent: false,
                    version: 7,
                    updated_at: "2026-04-17T09:40:00Z",
                    latest_run: {
                      run_id: "run_3988",
                      trace_id: "trace_3988",
                      status: "error",
                      final_action: null,
                      evaluation_summary_ref: {
                        status: "partial",
                        trace_id: "trace_3988",
                        has_response_quality: false,
                        has_trajectory_evaluation: true,
                        trajectory_score: 2.5,
                        trajectory_violation_count: 1,
                      },
                    },
                    latest_draft: null,
                  },
                ],
                page: 2,
                page_size: 2,
                total: 3,
              }),
            ),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          ),
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    renderTicketsPage();

    expect(await screen.findByText(/第 1 \/ 2 页/i)).toBeInTheDocument();
    expect(screen.getByText(/正在显示 1-2 \/ 3 条实时记录/i)).toBeInTheDocument();

    expect(screen.getByRole("button", { name: "下一页" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));

    expect(await screen.findByText(/第 2 \/ 2 页/i)).toBeInTheDocument();
    expect(screen.getByText(/正在显示 3-3 \/ 3 条实时记录/i)).toBeInTheDocument();
    expect(
      screen.getByText("Agent suggested escalation after compliance request"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "上一页" })).toBeEnabled();
    expect(fetchMock.mock.calls.at(-1)?.[0]).toContain("page=2");
    expect(fetchMock.mock.calls.at(-1)?.[0]).toContain("page_size=2");
  });

  it("navigates into the ticket detail route from a live row action", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify(buildTicketListResponse()), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderTicketsPage();

    await screen.findByText("Duplicate billing charge still unresolved");

    fireEvent.click(screen.getAllByRole("button", { name: "打开详情" })[0]);

    expect(await screen.findByText("Ticket Detail Route")).toBeInTheDocument();
    expect(useConsoleUiStore.getState().selectedTicketId).toBe("ticket_4012");
  });

  it("renders the empty-state shell when the live query returns zero rows", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify(
            buildTicketListResponse({
              items: [],
              total: 0,
            }),
          ),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderTicketsPage();

    expect(
      await screen.findByRole("heading", {
        name: "当前筛选没有命中任何工单。",
      }),
    ).toBeInTheDocument();
  });
});
