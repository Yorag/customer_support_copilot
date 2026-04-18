import { buildDashboardViewModel, useDashboardData } from "@/lib/query/dashboard";
import { EmptyState, MetricCard, Panel, StatusTag } from "@/ui-v2/primitives";

export function DashboardPageV2() {
  const dashboardQuery = useDashboardData();

  if (dashboardQuery.isPending) {
    return (
      <section className="v2-stack">
        <Panel label="总览" title="正在载入控制面快照">
          <div className="v2-metric-grid" aria-label="总览实时状态带">
            <MetricCard label="Gmail" value="载入中" />
            <MetricCard label="Worker" value="载入中" note="等待心跳" />
            <MetricCard label="队列" value="载入中" />
            <MetricCard label="扫描" value="载入中" />
          </div>
        </Panel>
      </section>
    );
  }

  if (dashboardQuery.isError) {
    return (
      <EmptyState
        label="总览不可用"
        title="无法读取总览数据"
        description={
          dashboardQuery.error instanceof Error
            ? dashboardQuery.error.message
            : "总览查询出现未知错误。"
        }
      />
    );
  }

  const viewModel = buildDashboardViewModel(dashboardQuery.data);

  return (
    <section className="v2-stack v2-dashboard-page">
      <Panel label="总览" title="总览" className="v2-dashboard-hero">
        <div className="v2-stack">
          <div className="v2-metric-grid" aria-label="总览实时状态带">
            <MetricCard label="Gmail" value={viewModel.hero.gmailLabel} />
            <MetricCard label="Worker" value={viewModel.hero.workerLabel} />
            <MetricCard label="队列" value={viewModel.hero.queueLabel} />
            <MetricCard label="扫描" value={viewModel.hero.scanLabel} />
          </div>

          <div className="v2-metric-grid" aria-label="总览核心指标">
            {viewModel.metrics.map((card) => (
              <MetricCard key={card.label} label={card.label} value={card.value} note={card.note} />
            ))}
          </div>
        </div>
      </Panel>

      <div className="v2-split-grid v2-dashboard-band">
        <Panel label="待处理" title="审核队列">
          <section className="v2-divider-list">
            {viewModel.feeds.reviewQueue.length > 0 ? (
              viewModel.feeds.reviewQueue.map((item) => (
                <article key={item.id} className="v2-divider-row">
                  <strong>{item.title}</strong>
                  <p>{item.meta}</p>
                  <div className="v2-action-row">
                    <StatusTag tone="accent">{item.emphasis}</StatusTag>
                  </div>
                </article>
              ))
            ) : (
              <article className="v2-divider-row">
                <strong>当前没有待人工审核的工单</strong>
                <p>审核队列为空。</p>
              </article>
            )}
          </section>
        </Panel>

        <Panel label="质量" title="24 小时">
          <div className="v2-summary-grid">
            {viewModel.qualityCards.map((card) => (
              <MetricCard
                key={card.label}
                label={card.label}
                value={card.value}
                note={card.note}
                tone="accent"
              />
            ))}
          </div>
        </Panel>
      </div>

      <div className="v2-split-grid v2-dashboard-band">
        <Panel label="最近进入" title="新进入控制面的工单">
          <section className="v2-divider-list">
            {viewModel.feeds.recentTickets.length > 0 ? (
              viewModel.feeds.recentTickets.map((item) => (
                <article key={item.id} className="v2-divider-row">
                  <strong>{item.title}</strong>
                  <p>{item.meta}</p>
                  <div className="v2-action-row">
                    <StatusTag>{item.emphasis}</StatusTag>
                  </div>
                </article>
              ))
            ) : (
              <article className="v2-divider-row">
                <strong>当前没有新进入工单</strong>
                <p>最近工单列表为空。</p>
              </article>
            )}
          </section>
        </Panel>

        <Panel label="可靠性" title="系统快照">
          <div className="v2-summary-grid v2-dashboard-summary-grid" aria-label="可靠性摘要区域">
            {viewModel.reliability.summaryCards.map((card) => (
              <MetricCard
                key={card.label}
                label={card.label}
                value={card.value}
                note={card.note}
                tone={card.tone}
              />
            ))}
          </div>

          <div className="v2-dashboard-dependencies" aria-label="依赖状态标签">
            {viewModel.reliability.dependencies.map((item) => (
              <StatusTag key={item.label} tone={item.tone}>
                {`${item.label} ${item.value}`}
              </StatusTag>
            ))}
          </div>

          <div className="v2-dashboard-detail-grid">
            <article className="v2-divider-row v2-dashboard-detail-card">
              <p className="v2-panel-label">最近失败</p>
              <strong>{viewModel.reliability.failure.title}</strong>
              <p>{viewModel.reliability.failure.detail}</p>
            </article>
            <article className="v2-divider-row v2-dashboard-detail-card">
              <p className="v2-panel-label">最近扫描</p>
              <strong>{viewModel.reliability.scan.title}</strong>
              <p>{viewModel.reliability.scan.detail}</p>
            </article>
          </div>
        </Panel>
      </div>
    </section>
  );
}
