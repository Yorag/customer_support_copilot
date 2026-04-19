import { render, screen } from "@testing-library/react";

import { App } from "@/app/App";
import { createAppRouter } from "@/app/router";

describe("Ticket detail route shell state", () => {
  it("updates shell state for the live review bench route", async () => {
    const router = createAppRouter(["/tickets/ticket_4012"]);

    render(<App router={router} />);

    expect(
      await screen.findByRole("heading", { name: "工单详情" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("全局状态条")).toHaveTextContent("OPS-03");
    expect(screen.getByLabelText("工单详情区域")).toHaveTextContent("版本");
    expect(screen.getByText("等待客户来信")).toBeInTheDocument();
    expect(screen.getByText("最新运行")).toBeInTheDocument();
  });
});
