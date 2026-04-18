import { render, screen } from "@testing-library/react";

import { App } from "@/app/App";
import { createAppRouter } from "@/app/router";

describe("Trace & Eval route shell state", () => {
  it("updates shell state for the live dossier route", async () => {
    const router = createAppRouter(["/trace"]);

    render(<App router={router} />);

    expect(
      await screen.findByRole("heading", {
        name: "围绕单次运行查看轨迹、事件、评分和原始记录",
      }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("全局状态条")).toHaveTextContent("OPS-05");
    expect(screen.getByLabelText("Trace 页面区域")).toHaveTextContent("运行浏览器");
    expect(screen.getByText("运行浏览器正在等待工单档案")).toBeInTheDocument();
    expect(screen.getByText("等待选择 Trace")).toBeInTheDocument();
    expect(screen.getByText("等待选择阶段")).toBeInTheDocument();
    expect(screen.getByText("对比当前运行和近期窗口")).toBeInTheDocument();
  });
});
