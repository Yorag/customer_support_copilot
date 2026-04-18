import { render, screen } from "@testing-library/react";

import { App } from "@/app/App";
import { createAppRouter } from "@/app/router";

describe("Trace & Eval route shell state", () => {
  it("updates shell state for the live dossier route", async () => {
    const router = createAppRouter(["/trace"]);

    render(<App router={router} />);

    expect(
      await screen.findByRole("heading", {
        name: "Trace 与评估",
      }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("全局状态条")).toHaveTextContent("OPS-05");
    expect(screen.getByText("等待选择 Trace")).toBeInTheDocument();
    expect(screen.getByText("等待载入运行")).toBeInTheDocument();
    expect(screen.getByText("当前运行结果")).toBeInTheDocument();
  });
});
