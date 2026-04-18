import { buildDashboardViewModel, useDashboardData } from "@/lib/query/dashboard";

function DashboardStateCard(props: {
  label: string;
  value: string;
  note: string;
}) {
  return (
    <section className="dashboard-card metric-card">
      <p className="dashboard-card-label">{props.label}</p>
      <p className="metric-card-value">{props.value}</p>
      <p className="metric-card-note">{props.note}</p>
    </section>
  );
}

function DashboardFeedCard(props: {
  eyebrow: string;
  title: string;
  chip: string;
  items: Array<{
    id: string;
    title: string;
    meta: string;
    emphasis: string;
  }>;
  emptyCopy: string;
}) {
  return (
    <section className="dashboard-card feed-card">
      <div className="dashboard-card-header">
        <div>
          <p className="dashboard-card-label">{props.eyebrow}</p>
          <h3>{props.title}</h3>
        </div>
        <span className="dashboard-card-chip">{props.chip}</span>
      </div>
      {props.items.length > 0 ? (
        <div className="dashboard-feed-list" role="list">
          {props.items.map((item) => (
            <article key={item.id} className="dashboard-feed-item" role="listitem">
              <p className="dashboard-feed-title">{item.title}</p>
              <p className="dashboard-feed-meta">{item.meta}</p>
              <p className="dashboard-feed-emphasis">{item.emphasis}</p>
            </article>
          ))}
        </div>
      ) : (
        <p className="dashboard-empty-copy">{props.emptyCopy}</p>
      )}
    </section>
  );
}

function DashboardIncidentCard(props: {
  eyebrow: string;
  title: string;
  chip: string;
  summary: string;
  detail: string;
  bars: number[];
}) {
  return (
    <section className="dashboard-card incident-card">
      <div className="dashboard-card-header">
        <div>
          <p className="dashboard-card-label">{props.eyebrow}</p>
          <h3>{props.title}</h3>
        </div>
        <span className="dashboard-card-chip">{props.chip}</span>
      </div>
      <div className="incident-placeholder" aria-hidden="true">
        {props.bars.map((height, index) => (
          <span key={`${props.title}-${index}`} style={{ height: `${height}%` }} />
        ))}
      </div>
      <p className="incident-summary">{props.summary}</p>
      <p className="dashboard-card-footnote">{props.detail}</p>
    </section>
  );
}

export function DashboardPage() {
  const dashboardQuery = useDashboardData();

  if (dashboardQuery.isPending) {
    return (
      <article className="dashboard-page">
        <section className="dashboard-hero">
          <div className="dashboard-hero-copy">
            <p className="placeholder-eyebrow">总览</p>
            <h2>正在载入系统读数。</h2>
            <p>稍后会显示运行态、队列压力和需要优先关注的工单。</p>
          </div>

          <div className="dashboard-hero-strip" aria-label="总览实时状态带">
            <div className="dashboard-strip-item">
              <span>Gmail</span>
              <strong>正在读取实时状态</strong>
            </div>
            <div className="dashboard-strip-item">
              <span>Worker</span>
              <strong>正在收集心跳</strong>
            </div>
            <div className="dashboard-strip-item">
              <span>队列</span>
              <strong>正在同步积压</strong>
            </div>
            <div className="dashboard-strip-item">
              <span>扫描</span>
              <strong>正在检查邮箱状态</strong>
            </div>
          </div>
        </section>

        <section className="dashboard-card dashboard-message-card" role="status">
          <p className="dashboard-card-label">实时查询</p>
          <h3>总览页正在等待第一份控制面快照。</h3>
          <p className="dashboard-card-footnote">
            一旦本批数据返回，这块看板就会从占位态切换为实时队列、质量和最近工单信号。
          </p>
        </section>
      </article>
    );
  }

  if (dashboardQuery.isError) {
    return (
      <article className="dashboard-page">
        <section className="dashboard-card dashboard-message-card" role="alert">
          <p className="dashboard-card-label">总览不可用</p>
          <h3>无法读取总览数据。</h3>
          <p className="dashboard-card-footnote">
            {dashboardQuery.error instanceof Error
              ? dashboardQuery.error.message
              : "总览查询出现未知错误。"}
          </p>
        </section>
      </article>
    );
  }

  const viewModel = buildDashboardViewModel(dashboardQuery.data);

  return (
    <article className="dashboard-page">
      <section className="dashboard-hero">
        <div className="dashboard-hero-copy">
          <p className="placeholder-eyebrow">总览</p>
          <h2>把运行态、积压和质量读数放在同一张台面上。</h2>
          <p>先看系统是否健康，再判断队列是否需要干预。</p>
        </div>

        <div className="dashboard-hero-strip" aria-label="总览实时状态带">
          <div className="dashboard-strip-item">
            <span>Gmail</span>
            <strong>{viewModel.hero.gmailLabel}</strong>
          </div>
          <div className="dashboard-strip-item">
            <span>Worker</span>
            <strong>{viewModel.hero.workerLabel}</strong>
          </div>
          <div className="dashboard-strip-item">
            <span>队列</span>
            <strong>{viewModel.hero.queueLabel}</strong>
          </div>
          <div className="dashboard-strip-item">
            <span>扫描</span>
            <strong>{viewModel.hero.scanLabel}</strong>
          </div>
        </div>
      </section>

      <section className="dashboard-grid dashboard-grid-metrics">
        {viewModel.metrics.map((card) => (
          <DashboardStateCard
            key={card.label}
            label={card.label}
            value={card.value}
            note={card.note}
          />
        ))}
      </section>

      <section className="dashboard-grid dashboard-grid-trends">
        {viewModel.trendCards.map((card) => (
          <section key={card.label} className="dashboard-card trend-card">
            <div className="dashboard-card-header">
              <div>
                <p className="dashboard-card-label">{card.label}</p>
                <h3>{card.title}</h3>
              </div>
              <span className="dashboard-card-chip">{card.chip}</span>
            </div>
            <div className="trend-chart" aria-hidden="true">
              {card.bars.map((height, index) => (
                <span key={`${card.label}-${index}`} style={{ height: `${height}%` }} />
              ))}
            </div>
            <p className="trend-summary">{card.summary}</p>
            <p className="dashboard-card-footnote">{card.detail}</p>
          </section>
        ))}
      </section>

      <section className="dashboard-grid dashboard-grid-handoff">
        <DashboardFeedCard
          eyebrow="GET /tickets"
          title="最近工单"
          chip="最新进入"
          items={viewModel.feeds.recentTickets}
          emptyCopy="当前还没有摄入任何工单。"
        />
        <DashboardFeedCard
          eyebrow="GET /tickets"
          title="审核队列"
          chip="等待审核"
          items={viewModel.feeds.reviewQueue}
          emptyCopy="当前没有需要人工审核的工单。"
        />
      </section>

      <section className="dashboard-grid dashboard-grid-incidents">
        {viewModel.incidents.map((panel) => (
          <DashboardIncidentCard
            key={panel.title}
            eyebrow={panel.eyebrow}
            title={panel.title}
            chip={panel.chip}
            summary={panel.summary}
            detail={panel.detail}
            bars={panel.bars}
          />
        ))}
      </section>
    </article>
  );
}
