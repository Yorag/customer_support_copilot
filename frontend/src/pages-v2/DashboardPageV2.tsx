import { buildDashboardViewModel, useDashboardData } from "@/lib/query/dashboard";
import { EmptyState, MetricCard, Panel, StatusTag } from "@/ui-v2/primitives";

export function DashboardPageV2() {
  const dashboardQuery = useDashboardData();

  if (dashboardQuery.isPending) {
    return (
      <section className="v2-stack">
      <Panel
        label="总览"
        title="正在载入控制面快照"
        description="同步运行态和待处理信号。"
      >
        <div className="v2-metric-grid" aria-label="总览实时状态带">
          <MetricCard label="Gmail" value="载入中" note="等待 ops status" />
            <MetricCard label="Worker" value="载入中" note="等待心跳" />
            <MetricCard label="队列" value="载入中" note="等待快照" />
            <MetricCard label="扫描" value="载入中" note="等待最近状态" />
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
    <section className="v2-stack">
      <Panel
        label="总览"
        title="当前系统需要先看的信号"
        description="先判断健康度，再决定优先处理项。"
      >
        <div className="v2-metric-grid" aria-label="总览实时状态带">
          <MetricCard label="Gmail" value={viewModel.hero.gmailLabel} note="邮箱运行态" />
          <MetricCard label="Worker" value={viewModel.hero.workerLabel} note="执行器健康" />
          <MetricCard label="队列" value={viewModel.hero.queueLabel} note="当前积压" />
          <MetricCard label="扫描" value={viewModel.hero.scanLabel} note="最近扫描结果" />
        </div>
      </Panel>

      <div className="v2-metric-grid">
        {viewModel.metrics.map((card) => (
          <MetricCard key={card.label} label={card.label} value={card.value} note={card.note} />
        ))}
      </div>

      <div className="v2-tiles-grid">
        <Panel label="待处理" title="审核与新进工单">
          <div className="v2-stack">
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
          </div>
        </Panel>

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
      </div>

      <div className="v2-tiles-grid">
        {viewModel.incidents.map((panel) => (
          <Panel
            key={panel.title}
            label={panel.eyebrow}
            title={panel.title}
            actions={<StatusTag tone="muted">{panel.chip}</StatusTag>}
          >
            <strong>{panel.summary}</strong>
            <p className="v2-panel-description">{panel.detail}</p>
          </Panel>
        ))}
      </div>
    </section>
  );
}
