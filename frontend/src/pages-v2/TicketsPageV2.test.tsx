import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { Providers } from "@/app/providers";
import { TicketsPageV2 } from "@/pages-v2/TicketsPageV2";
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
          <Route path="/tickets" element={<TicketsPageV2 />} />
          <Route path="/tickets/:ticketId" element={<div>Ticket Detail Route</div>} />
          <Route path="/trace" element={<div>Trace Route</div>} />
        </Routes>
      </Providers>
    </MemoryRouter>,
  );
}

describe("TicketsPageV2", () => {
  beforeEach(() => {
    useConsoleUiStore.getState().resetTicketListFilters();
    useConsoleUiStore.setState({
      selectedTicketId: null,
      selectedRunId: null,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders live rows and exposes the reduced ledger structure", async () => {
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
      await screen.findByRole("heading", {
        name: "实时工单队列",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("筛选工单")).toBeInTheDocument();
    expect(screen.queryByText("当前未附加额外筛选。")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("工单队列摘要")).not.toBeInTheDocument();

    await screen.findByText("Duplicate billing charge still unresolved");
    const rows = within(screen.getByLabelText("工单实时行")).getAllByRole("row");
    expect(rows).toHaveLength(2);
    expect(screen.getByText("Duplicate billing charge still unresolved")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "详情" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Trace" })).toHaveLength(2);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/tickets?page=1&page_size=20"),
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("forwards filter state into GET /tickets and resets the toolbar state", async () => {
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
    expect(screen.getByText("2 项筛选生效")).toBeInTheDocument();
    expect(screen.getByText("搜索 refund · 仅看待审核")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "重置筛选" }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.at(-1)?.[0]).toContain("/tickets?page=1&page_size=20");
    });

    expect(screen.getByLabelText("搜索工单")).toHaveValue("");
    expect(screen.getByLabelText("待审核")).toHaveValue("all");
    expect(screen.queryByText("搜索 refund · 仅看待审核")).not.toBeInTheDocument();
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

    await screen.findByText("Duplicate billing charge still unresolved");
    expect(screen.getAllByText(/第 1 \/ 2 页/i)).toHaveLength(1);
    expect(screen.getByText(/显示 1-2 \/ 3 条记录/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("每页行数"), {
      target: { value: "2" },
    });

    await waitFor(() => {
      expect(fetchMock.mock.calls.at(-1)?.[0]).toContain("page_size=2");
    });

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));

    await screen.findByText("Agent suggested escalation after compliance request");
    expect(screen.getAllByText(/第 2 \/ 2 页/i)).toHaveLength(1);
    expect(screen.getByText("Agent suggested escalation after compliance request")).toBeInTheDocument();
    expect(fetchMock.mock.calls.at(-1)?.[0]).toContain("page=2");
    expect(fetchMock.mock.calls.at(-1)?.[0]).toContain("page_size=2");
  });

  it("navigates into detail and trace routes from row actions", async () => {
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

    fireEvent.click(screen.getAllByRole("button", { name: "Trace" })[0]);

    expect(await screen.findByText("Trace Route")).toBeInTheDocument();
    expect(useConsoleUiStore.getState().selectedTicketId).toBe("ticket_4012");
    expect(useConsoleUiStore.getState().selectedRunId).toBe("run_4012");
  });

  it("renders the empty state when the live query returns zero rows", async () => {
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
        name: "当前筛选没有命中任何工单",
      }),
    ).toBeInTheDocument();
  });
});
