import { useDeferredValue, useEffect } from "react";
import { useNavigate } from "react-router-dom";

import type { TicketListItem } from "@/lib/api/types";
import {
  formatNumberZh,
  formatRelativeTimeZh,
  formatTimestampZh,
  labelForCode,
} from "@/lib/presentation";
import { useTicketsList } from "@/lib/query/tickets";
import { useConsoleUiStore } from "@/state/console-ui-store";

const businessStatusOptions = [
  { value: "", label: "全部业务状态" },
  { value: "awaiting_human_review", label: "待人工审核" },
  { value: "waiting_external", label: "等待外部处理" },
  { value: "triaged", label: "已分诊" },
  { value: "drafted", label: "已起草" },
  { value: "escalated", label: "已升级" },
];

const processingStatusOptions = [
  { value: "", label: "全部处理状态" },
  { value: "queued", label: "已入队" },
  { value: "running", label: "运行中" },
  { value: "waiting_external", label: "等待外部处理" },
  { value: "completed", label: "已完成" },
  { value: "error", label: "错误" },
];

const routeOptions = [
  { value: "", label: "全部路由" },
  { value: "billing_refund", label: "账单退款" },
  { value: "order_support", label: "订单支持" },
  { value: "technical_issue", label: "技术问题" },
  { value: "commercial_policy_request", label: "商业政策请求" },
  { value: "compliance_escalation", label: "合规升级" },
];

const pageSizeOptions = [2, 3, 4, 6, 12, 20];

function formatBooleanFilter(value: boolean | null) {
  if (value === null) {
    return "all";
  }

  return value ? "yes" : "no";
}

function parseBooleanFilter(value: string) {
  if (value === "yes") {
    return true;
  }

  if (value === "no") {
    return false;
  }

  return null;
}

function formatMetricValue(value: number | undefined, fallback = "--") {
  if (value === undefined) {
    return fallback;
  }

  return formatNumberZh(value);
}

function formatRelativeTimestamp(dateString: string) {
  return formatRelativeTimeZh(dateString);
}

function formatExactTimestamp(dateString: string) {
  return formatTimestampZh(dateString);
}

function isAwaitingReview(ticket: TicketListItem) {
  return ticket.business_status === "awaiting_human_review";
}

function getRunStatusLabel(ticket: TicketListItem) {
  return ticket.latest_run?.status ? labelForCode(ticket.latest_run.status) : "暂无运行";
}

function getDraftStatusLabel(ticket: TicketListItem) {
  return ticket.latest_draft?.qa_status ? labelForCode(ticket.latest_draft.qa_status) : "暂无草稿";
}

export function TicketsPage() {
  const navigate = useNavigate();
  const filters = useConsoleUiStore((state) => state.ticketListFilters);
  const setTicketListFilters = useConsoleUiStore((state) => state.setTicketListFilters);
  const resetTicketListFilters = useConsoleUiStore((state) => state.resetTicketListFilters);
  const setSelectedTicketId = useConsoleUiStore((state) => state.setSelectedTicketId);
  const deferredQuery = useDeferredValue(filters.query.trim());
  const ticketQuery = {
    page: filters.page,
    page_size: filters.pageSize,
    business_status: filters.businessStatus ?? undefined,
    processing_status: filters.processingStatus ?? undefined,
    primary_route: filters.primaryRoute ?? undefined,
    has_draft: filters.hasDraft ?? undefined,
    awaiting_review: filters.awaitingReview ?? undefined,
    query: deferredQuery || undefined,
  };
  const { data, error, isError, isFetching, isLoading } = useTicketsList(ticketQuery);
  const liveRows = data?.items ?? [];
  const totalItems = data?.total ?? 0;
  const currentPage = data?.page ?? filters.page;
  const currentPageSize = data?.page_size ?? filters.pageSize;
  const totalPages = Math.max(1, Math.ceil(totalItems / currentPageSize));
  const visibleRangeLabel =
    totalItems === 0 || liveRows.length === 0
      ? "0-0"
      : `${(currentPage - 1) * currentPageSize + 1}-${(currentPage - 1) * currentPageSize + liveRows.length}`;
  const reviewCount = liveRows.filter((ticket) => isAwaitingReview(ticket)).length;
  const draftCount = liveRows.filter((ticket) => Boolean(ticket.latest_draft)).length;
  const errorCount = liveRows.filter(
    (ticket) => ticket.processing_status === "error",
  ).length;

  useEffect(() => {
    if (!data) {
      return;
    }

    const nextPage = Math.max(1, Math.ceil(data.total / data.page_size));
    if (filters.page > nextPage) {
      setTicketListFilters({ page: nextPage });
    }
  }, [data, filters.page, setTicketListFilters]);

  function openTicketDetail(ticketId: string) {
    setSelectedTicketId(ticketId);
    navigate(`/tickets/${ticketId}`);
  }

  return (
    <article className="tickets-page">
      <section className="tickets-hero">
        <div className="tickets-hero-copy">
          <p className="placeholder-eyebrow">工单队列</p>
          <h2>先整理台账，再进入单个案件。</h2>
          <p>这里负责筛选、定位和排序优先级，不负责长篇说明。</p>
        </div>

        <div className="tickets-hero-strip" aria-label="工单队列摘要">
          <div className="tickets-strip-item">
            <span>筛选结果</span>
            <strong>{formatMetricValue(data?.total, isLoading ? "--" : "0")}</strong>
            <p>当前控制面筛选条件返回的实时行数。</p>
          </div>
          <div className="tickets-strip-item">
            <span>本页待审</span>
            <strong>{formatMetricValue(data ? reviewCount : undefined, isLoading ? "--" : "0")}</strong>
            <p>本页可见行中仍需要人工检查的数量。</p>
          </div>
          <div className="tickets-strip-item">
            <span>本页草稿</span>
            <strong>{formatMetricValue(data ? draftCount : undefined, isLoading ? "--" : "0")}</strong>
            <p>本页可见行中已至少带有一份草稿的数量。</p>
          </div>
          <div className="tickets-strip-item tickets-strip-item-alert">
            <span>本页错误</span>
            <strong>{formatMetricValue(data ? errorCount : undefined, isLoading ? "--" : "0")}</strong>
            <p>在进入重试和 Trace 处理前暴露失败压力的行数。</p>
          </div>
        </div>
      </section>

      <section className="tickets-workbench">
        <section className="tickets-filter-card">
          <div className="tickets-card-header">
            <div>
              <p className="dashboard-card-label">筛选工作台</p>
              <h3>按状态、路由和草稿情况缩小范围。</h3>
            </div>
            <button
              className="tickets-reset-button"
              type="button"
              onClick={() => resetTicketListFilters()}
            >
              重置全部筛选
            </button>
          </div>

          <div className="tickets-filter-grid">
            <label className="tickets-field">
              <span>搜索</span>
              <input
                aria-label="搜索工单"
                type="search"
                placeholder="工单号、客户或主题"
                value={filters.query}
                onChange={(event) =>
                  setTicketListFilters({
                    query: event.target.value,
                    page: 1,
                  })
                }
              />
            </label>

            <label className="tickets-field">
              <span>业务状态</span>
              <select
                aria-label="业务状态"
                value={filters.businessStatus ?? ""}
                onChange={(event) =>
                  setTicketListFilters({
                    businessStatus: event.target.value || null,
                    page: 1,
                  })
                }
              >
                {businessStatusOptions.map((option) => (
                  <option key={option.value || "all"} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="tickets-field">
              <span>处理状态</span>
              <select
                aria-label="处理状态"
                value={filters.processingStatus ?? ""}
                onChange={(event) =>
                  setTicketListFilters({
                    processingStatus: event.target.value || null,
                    page: 1,
                  })
                }
              >
                {processingStatusOptions.map((option) => (
                  <option key={option.value || "all"} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="tickets-field">
              <span>主路由</span>
              <select
                aria-label="主路由"
                value={filters.primaryRoute ?? ""}
                onChange={(event) =>
                  setTicketListFilters({
                    primaryRoute: event.target.value || null,
                    page: 1,
                  })
                }
              >
                {routeOptions.map((option) => (
                  <option key={option.value || "all"} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="tickets-field">
              <span>是否有草稿</span>
              <select
                aria-label="是否有草稿"
                value={formatBooleanFilter(filters.hasDraft)}
                onChange={(event) =>
                  setTicketListFilters({
                    hasDraft: parseBooleanFilter(event.target.value),
                    page: 1,
                  })
                }
              >
                <option value="all">全部行</option>
                <option value="yes">已有草稿</option>
                <option value="no">没有草稿</option>
              </select>
            </label>

            <label className="tickets-field">
              <span>待审核</span>
              <select
                aria-label="待审核"
                value={formatBooleanFilter(filters.awaitingReview)}
                onChange={(event) =>
                  setTicketListFilters({
                    awaitingReview: parseBooleanFilter(event.target.value),
                    page: 1,
                  })
                }
              >
                <option value="all">全部行</option>
                <option value="yes">需要人工审核</option>
                <option value="no">不处于审核挂起</option>
              </select>
            </label>
          </div>
        </section>

        <section className="tickets-brief-card">
          <p className="dashboard-card-label">处理提示</p>
          <h3>先看待审核和错误工单。</h3>
          <p>列表页适合做分流，真正的处理动作留到详情页完成。</p>
          <div className="tickets-chip-row" aria-label="工单批次边界">
            <span className="tickets-brief-chip">实时列表</span>
            <span className="tickets-brief-chip">服务端分页</span>
            <span className="tickets-brief-chip">直达详情</span>
          </div>
        </section>
      </section>

      <section className="tickets-ledger-card">
        <div className="tickets-card-header">
          <div>
            <p className="dashboard-card-label">队列台账</p>
            <h3>从当前分页中找到需要处理的工单。</h3>
          </div>
          <div className="tickets-ledger-status">
            <p className="tickets-ledger-footnote">
              正在显示 {visibleRangeLabel} / {totalItems} 条实时记录
            </p>
            {isFetching ? (
              <span className="tickets-ledger-chip">正在刷新实时查询</span>
            ) : null}
          </div>
        </div>

        <div className="tickets-ledger-head" aria-hidden="true">
          <span>工单</span>
          <span>客户</span>
          <span>路由</span>
          <span>状态</span>
          <span>运行 + 草稿</span>
          <span>更新时间</span>
          <span>动作区</span>
        </div>

        {isLoading && !data ? (
          <section className="tickets-empty-state tickets-empty-state-muted" role="status">
            <p className="dashboard-card-label">正在加载实时队列</p>
            <h3>列表正在等待第一页数据。</h3>
            <p>当前筛选会在数据返回后立即生效。</p>
          </section>
        ) : null}

        {!isLoading && isError && !data ? (
          <section className="tickets-empty-state tickets-empty-state-alert" role="alert">
            <p className="dashboard-card-label">实时查询失败</p>
            <h3>当前无法读取工单列表。</h3>
            <p>
              {error instanceof Error
                ? error.message
                : "请刷新页面，或放宽当前筛选条件。"}
            </p>
          </section>
        ) : null}

        {!isLoading && liveRows.length > 0 ? (
          <div className="tickets-ledger-list" role="list" aria-label="工单实时行">
            {liveRows.map((record) => (
              <article
                key={record.ticket_id}
                className="tickets-row"
                role="listitem"
                data-ticket-id={record.ticket_id}
              >
                <div className="tickets-row-cell">
                  <p className="tickets-row-ticket">{record.ticket_id}</p>
                  <button
                    className="tickets-row-link"
                    type="button"
                    onClick={() => openTicketDetail(record.ticket_id)}
                  >
                    {record.subject}
                  </button>
                  <p className="tickets-row-meta">
                    优先级 {labelForCode(record.priority)} · v{record.version}
                  </p>
                </div>

                <div className="tickets-row-cell">
                  <p className="tickets-row-customer">{record.customer_email_raw}</p>
                  <p className="tickets-row-meta">
                    {isAwaitingReview(record)
                      ? "当前处于人工检查队列"
                      : "仍处于自动处理路径"}
                  </p>
                </div>

                <div className="tickets-row-cell">
                  <span className="tickets-inline-chip">
                    {record.primary_route
                      ? labelForCode(record.primary_route)
                      : "路由待定"}
                  </span>
                  <p className="tickets-row-meta">
                    {record.multi_intent
                      ? "多意图工单"
                      : "单意图工单"}
                  </p>
                </div>

                <div className="tickets-row-cell">
                  <div className="tickets-status-stack">
                    <span className="tickets-status-badge">
                      {labelForCode(record.business_status)}
                    </span>
                    <span className="tickets-status-badge tickets-status-badge-muted">
                      {labelForCode(record.processing_status)}
                    </span>
                  </div>
                </div>

                <div className="tickets-row-cell">
                  <p className="tickets-row-meta">
                    运行 {getRunStatusLabel(record)}
                  </p>
                  <p className="tickets-row-meta">
                    草稿 {getDraftStatusLabel(record)}
                  </p>
                </div>

                <div className="tickets-row-cell">
                  <p className="tickets-row-updated">{formatRelativeTimestamp(record.updated_at)}</p>
                  <p className="tickets-row-meta">{formatExactTimestamp(record.updated_at)}</p>
                </div>

                <div className="tickets-row-cell tickets-row-actions">
                  <button
                    className="tickets-action-chip tickets-action-chip-primary"
                    type="button"
                    onClick={() => openTicketDetail(record.ticket_id)}
                  >
                    打开详情
                  </button>
                  <button className="tickets-action-chip" type="button" disabled>
                    重试
                  </button>
                  <button className="tickets-action-chip" type="button" disabled>
                    打开 Trace
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : null}

        {!isLoading && !isError && liveRows.length === 0 ? (
          <section className="tickets-empty-state" role="status">
            <p className="dashboard-card-label">没有匹配行</p>
            <h3>当前筛选没有命中任何工单。</h3>
            <p>重置筛选，或放宽其中一个条件后再试。</p>
          </section>
        ) : null}
      </section>

      <section className="tickets-pagination-card">
        <div>
          <p className="dashboard-card-label">分页</p>
          <h3>列表范围由服务端分页决定。</h3>
          <p className="tickets-pagination-copy">
            第 {currentPage} / {totalPages} 页，当前显示 {visibleRangeLabel} / {totalItems}。
          </p>
        </div>

        <div className="tickets-pagination-controls">
          <label className="tickets-field tickets-field-compact">
            <span>每页行数</span>
            <select
              aria-label="每页行数"
              value={String(filters.pageSize)}
              onChange={(event) =>
                setTicketListFilters({
                  pageSize: Number(event.target.value),
                  page: 1,
                })
              }
            >
              {pageSizeOptions.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>

          <div className="tickets-pagination-buttons">
            <button
              className="tickets-page-button"
              type="button"
              onClick={() => setTicketListFilters({ page: Math.max(1, currentPage - 1) })}
              disabled={currentPage <= 1}
            >
              上一页
            </button>
            <button
              className="tickets-page-button tickets-page-button-accent"
              type="button"
              onClick={() =>
                setTicketListFilters({ page: Math.min(totalPages, currentPage + 1) })
              }
              disabled={currentPage >= totalPages}
            >
              下一页
            </button>
          </div>
        </div>
      </section>
    </article>
  );
}
