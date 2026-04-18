import { NavLink, Outlet, useLocation, useMatches } from "react-router-dom";

import { primaryNavItems, type ConsoleRouteHandle } from "@/app/consoleShell";
import { Tip } from "@/ui-v2/primitives";

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

export function AppShellV2() {
  const location = useLocation();
  const matches = useMatches();
  const currentHandle = matches.at(-1)?.handle as ConsoleRouteHandle | undefined;

  const title = currentHandle?.title ?? "控制台";
  const eyebrow = currentHandle?.eyebrow ?? "运营视图";
  const phase = currentHandle?.phase ?? "OPS-00";
  const contextTitle = currentHandle?.contextTitle ?? "当前页面说明";
  const contextDescription =
    currentHandle?.contextDescription ?? "当前页面用于完成控制面里的核心操作。";
  const contextItems = currentHandle?.contextItems ?? [];
  const relatedEndpoints = currentHandle?.relatedEndpoints ?? [];

  return (
    <div className="v2-shell">
      <aside className="v2-sidebar" aria-label="控制台侧边栏">
        <div className="v2-brand">
          <p>control plane</p>
          <h1>运营控制台</h1>
        </div>

        <nav className="v2-nav" aria-label="主导航">
          {primaryNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => cx("v2-nav-link", isActive && "is-active")}
            >
              <strong>{item.label}</strong>
              <span>{item.note}</span>
            </NavLink>
          ))}
        </nav>
      </aside>

      <main className="v2-main">
        <header className="v2-topbar">
          <div className="v2-topbar-copy">
            <p className="v2-topbar-label">{eyebrow}</p>
            <h2>{title}</h2>
          </div>
          <div className="v2-topbar-meta" aria-label="全局状态条">
            <span>
              <strong>{phase}</strong>
              <em>{location.pathname}</em>
            </span>
            <Tip
              title={contextTitle}
              summary="说明"
              className="v2-topbar-tip"
            >
              <p>{contextDescription}</p>
              {contextItems.length > 0 ? (
                <ul className="v2-tip-list">
                  {contextItems.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : null}
              {relatedEndpoints.length > 0 ? (
                <>
                  <p className="v2-tip-label">相关接口</p>
                  <ul className="v2-tip-list v2-tip-list-code">
                    {relatedEndpoints.map((endpoint) => (
                      <li key={endpoint}>{endpoint}</li>
                    ))}
                  </ul>
                </>
              ) : null}
            </Tip>
          </div>
        </header>

        <section className="v2-workspace" aria-label={`${title}工作区`}>
          <Outlet />
        </section>
      </main>
    </div>
  );
}
