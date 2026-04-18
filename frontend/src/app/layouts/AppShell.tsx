import { NavLink, Outlet, useLocation, useMatches } from "react-router-dom";

import {
  primaryNavItems,
  type ConsoleRouteHandle,
} from "@/app/consoleShell";
import { getApiBaseUrl } from "@/env";

export function AppShell() {
  const location = useLocation();
  const matches = useMatches();
  const currentHandle = matches.at(-1)?.handle as ConsoleRouteHandle | undefined;

  const headerEyebrow = currentHandle?.eyebrow ?? "控制台";
  const headerTitle = currentHandle?.title ?? "智能客服工单控制台";
  const headerSummary =
    currentHandle?.summary ??
    "统一操作摄入、审核、执行路径，并保持异步系统状态可读。";
  const contextTitle = currentHandle?.contextTitle ?? "路由上下文";
  const contextDescription =
    currentHandle?.contextDescription ??
    "壳层右侧保留给当前路由的上下文信息和关联链接。";
  const contextItems = currentHandle?.contextItems ?? [];
  const relatedEndpoints = currentHandle?.relatedEndpoints ?? [];
  const phase = currentHandle?.phase ?? "OPS-01";

  return (
    <div className="app-shell">
      <div className="shell-chassis">
        <aside className="shell-sidebar" aria-label="控制台侧边栏">
          <div className="shell-brand">
            <p className="shell-kicker">控制面</p>
            <h1>运营控制台</h1>
            <p className="shell-brand-note">
              统一处理摄入、审核、执行与观测。
            </p>
          </div>

          <nav className="shell-nav" aria-label="主导航">
            {primaryNavItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `shell-nav-link${isActive ? " is-active" : ""}`
                }
              >
                <span className="shell-nav-label">{item.label}</span>
                <span className="shell-nav-note">{item.note}</span>
              </NavLink>
            ))}
          </nav>

          <section className="shell-sidebar-panel" aria-label="工作区说明">
            <p className="shell-panel-label">当前视图</p>
            <h3>{headerTitle}</h3>
            <p className="shell-panel-copy">{contextDescription}</p>
          </section>
        </aside>

        <main className="shell-main">
          <header className="shell-topbar">
            <div className="shell-topbar-copy">
              <p className="route-label">{headerEyebrow}</p>
              <h2>{headerTitle}</h2>
              <p className="route-summary">{headerSummary}</p>
            </div>
            <div className="shell-topbar-status" aria-label="全局状态条">
              <span className="shell-status-pill">
                <strong>阶段</strong>
                {phase}
              </span>
              <span className="shell-status-pill">
                <strong>路径</strong>
                {location.pathname}
              </span>
              <span className="shell-status-pill">
                <strong>模式</strong>
                控制面
              </span>
              <span className="shell-status-pill shell-status-pill-accent">
                <strong>API</strong>
                {getApiBaseUrl()}
              </span>
            </div>
          </header>

          <div className="shell-content-grid">
            <section className="route-frame">
              <div className="route-frame-header">
                <div>
                  <p className="route-phase">工作区</p>
                  <p className="route-note">
                    当前视图 <span>{headerTitle}</span>
                  </p>
                </div>
              </div>
              <Outlet />
            </section>

            <aside className="context-rail" aria-label="页面上下文">
              <section className="context-card">
                <p className="context-card-label">路由摘要</p>
                <h3>{contextTitle}</h3>
                <p>{contextDescription}</p>
              </section>

              <section className="context-card">
                <p className="context-card-label">当前页面职责</p>
                <ul className="context-list">
                  {contextItems.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>

              <section className="context-card">
                <p className="context-card-label">已绑定接口</p>
                {relatedEndpoints.length > 0 ? (
                  <ul className="context-list context-list-mono">
                    {relatedEndpoints.map((endpoint) => (
                      <li key={endpoint}>{endpoint}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="context-empty">
                    当前回退视图没有绑定任何后端合约。
                  </p>
                )}
              </section>
            </aside>
          </div>
        </main>
      </div>
    </div>
  );
}
