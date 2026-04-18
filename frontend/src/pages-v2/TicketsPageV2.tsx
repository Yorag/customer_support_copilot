import { useDeferredValue, useEffect } from "react";
import { useNavigate } from "react-router-dom";

import type { TicketListItem } from "@/lib/api/types";
import { formatRelativeTimeZh, formatTimestampZh, labelForCode } from "@/lib/presentation";
import { useTicketsList } from "@/lib/query/tickets";
import { useConsoleUiStore, type TicketListFilters } from "@/state/console-ui-store";
import {
  EmptyState,
  Field,
  Panel,
  StatusTag,
  Toolbar,
} from "@/ui-v2/primitives";

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

function getBusinessStatusTone(status: string) {
  if (status === "awaiting_human_review") {
    return "accent";
  }

  if (status === "escalated") {
    return "danger";
  }

  if (status === "closed") {
    return "muted";
  }

  return "default";
}

function getProcessingStatusTone(status: string) {
  if (status === "error") {
    return "danger";
  }

  if (status === "completed") {
    return "success";
  }

  if (status === "running" || status === "queued") {
    return "accent";
  }

  return "muted";
}

function getPriorityTone(priority: string) {
  if (priority === "critical" || priority === "high") {
    return "danger";
  }

  if (priority === "medium") {
    return "accent";
  }

  return "muted";
}

function getRowTone(ticket: TicketListItem) {
  if (ticket.processing_status === "error" || ticket.business_status === "escalated") {
    return "danger";
  }

  if (ticket.business_status === "awaiting_human_review" || ticket.processing_status === "running") {
    return "accent";
  }

  return "default";
}

function getRunStatusLabel(ticket: TicketListItem) {
  return ticket.latest_run?.status ? labelForCode(ticket.latest_run.status) : "暂无运行";
}

function getProcessingNote(ticket: TicketListItem) {
  if (ticket.processing_status === "completed") {
    return null;
  }

  return labelForCode(ticket.processing_status);
}

function buildFilterSummary(filters: TicketListFilters) {
  const segments: string[] = [];

  if (filters.query.trim()) {
    segments.push(`搜索 ${filters.query.trim()}`);
  }
  if (filters.businessStatus) {
    segments.push(`业务 ${labelForCode(filters.businessStatus)}`);
  }
  if (filters.processingStatus) {
    segments.push(`处理 ${labelForCode(filters.processingStatus)}`);
  }
  if (filters.primaryRoute) {
    segments.push(`路由 ${labelForCode(filters.primaryRoute)}`);
  }
  if (filters.hasDraft !== null) {
    segments.push(filters.hasDraft ? "仅看已有草稿" : "仅看无草稿");
  }
  if (filters.awaitingReview !== null) {
    segments.push(filters.awaitingReview ? "仅看待审核" : "排除待审核");
  }

  return segments.length > 0 ? segments.join(" · ") : undefined;
}

function countActiveFilters(filters: TicketListFilters) {
  return [
    filters.query.trim().length > 0,
    Boolean(filters.businessStatus),
    Boolean(filters.processingStatus),
    Boolean(filters.primaryRoute),
    filters.hasDraft !== null,
    filters.awaitingReview !== null,
  ].filter(Boolean).length;
}

function extractCustomerEmail(raw: string) {
  const matched = raw.match(/<([^>]+)>/);
  if (matched?.[1]) {
    return matched[1].trim();
  }

  return raw.replace(/^"+|"+$/g, "").trim();
}

export function TicketsPageV2() {
  const navigate = useNavigate();
  const filters = useConsoleUiStore((state) => state.ticketListFilters);
  const setTicketListFilters = useConsoleUiStore((state) => state.setTicketListFilters);
  const resetTicketListFilters = useConsoleUiStore((state) => state.resetTicketListFilters);
  const setSelectedTicketId = useConsoleUiStore((state) => state.setSelectedTicketId);
  const setSelectedRunId = useConsoleUiStore((state) => state.setSelectedRunId);
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
  const activeFilterCount = countActiveFilters(filters);
  const filterSummary = buildFilterSummary(filters);

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

  function openTrace(ticketId: string, runId?: string | null) {
    if (!runId) {
      return;
    }

    setSelectedTicketId(ticketId);
    setSelectedRunId(runId);
    navigate(`/trace?ticketId=${encodeURIComponent(ticketId)}&runId=${encodeURIComponent(runId)}`);
  }

  return (
    <section className="v2-stack v2-ticket-list-page">
      <Panel
        label="工单检索"
        title="筛选工单"
        description={filterSummary}
        actions={
          <div className="v2-action-row">
            {activeFilterCount > 0 ? (
              <StatusTag tone="muted">{`${activeFilterCount} 项筛选生效`}</StatusTag>
            ) : null}
            <button className="v2-button" type="button" onClick={() => resetTicketListFilters()}>
              重置筛选
            </button>
          </div>
        }
      >
        <Toolbar className="v2-ticket-filter-toolbar">
          <Field label="搜索" className="v2-ticket-search-field">
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
          </Field>

          <Field label="业务状态">
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
          </Field>

          <Field label="处理状态">
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
          </Field>

          <Field label="主路由">
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
          </Field>

          <Field label="草稿">
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
              <option value="all">全部</option>
              <option value="yes">已有草稿</option>
              <option value="no">没有草稿</option>
            </select>
          </Field>

          <Field label="待审核">
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
              <option value="all">全部</option>
              <option value="yes">需要人工审核</option>
              <option value="no">不处于审核挂起</option>
            </select>
          </Field>
        </Toolbar>
      </Panel>

      <Panel
        label="工单台账"
        title="实时工单队列"
        description={`显示 ${visibleRangeLabel} / ${totalItems} 条记录`}
        actions={
          isFetching ? <StatusTag tone="accent">正在刷新</StatusTag> : undefined
        }
      >
        {isLoading && !data ? (
          <EmptyState
            label="正在加载实时队列"
            title="列表正在等待第一页数据"
            description="当前筛选会在数据返回后立即生效。"
          />
        ) : null}

        {!isLoading && isError && !data ? (
          <EmptyState
            label="实时查询失败"
            title="当前无法读取工单列表"
            description={
              error instanceof Error ? error.message : "请刷新页面，或放宽当前筛选条件。"
            }
          />
        ) : null}

        {!isLoading && !isError && liveRows.length === 0 ? (
          <EmptyState
            label="没有匹配行"
            title="当前筛选没有命中任何工单"
            description="重置筛选，或放宽其中一个条件后再试。"
          />
        ) : null}

        {!isLoading && liveRows.length > 0 ? (
          <>
            <div className="v2-table-wrap">
              <table className="v2-table v2-ticket-table">
                <thead>
                  <tr>
                    <th>工单</th>
                    <th>客户</th>
                    <th>状态</th>
                    <th>最新运行</th>
                    <th>更新时间</th>
                    <th>动作</th>
                  </tr>
                </thead>
                <tbody aria-label="工单实时行">
                  {liveRows.map((record) => (
                    <tr
                      key={record.ticket_id}
                      className={`v2-ticket-row is-${getRowTone(record)}`}
                      data-ticket-id={record.ticket_id}
                    >
                      <td>
                        <div className="v2-table-cell-main">
                          <div className="v2-ticket-row-head">
                            <strong className="v2-code">{record.ticket_id}</strong>
                            <StatusTag tone={getPriorityTone(record.priority)}>
                              {labelForCode(record.priority)}
                            </StatusTag>
                            <StatusTag tone="muted">
                              {record.primary_route ? labelForCode(record.primary_route) : "路由待定"}
                            </StatusTag>
                            {record.multi_intent ? (
                              <StatusTag tone="accent">多意图</StatusTag>
                            ) : null}
                          </div>
                          <button
                            className="v2-table-link v2-ticket-subject"
                            type="button"
                            onClick={() => openTicketDetail(record.ticket_id)}
                          >
                            {record.subject}
                          </button>
                        </div>
                      </td>
                      <td>
                        <div className="v2-table-cell-main">
                          <span className="v2-ticket-customer" title={record.customer_email_raw}>
                            {extractCustomerEmail(record.customer_email_raw)}
                          </span>
                        </div>
                      </td>
                      <td>
                        <div className="v2-table-cell-main">
                          <StatusTag tone={getBusinessStatusTone(record.business_status)}>
                            {labelForCode(record.business_status)}
                          </StatusTag>
                          {getProcessingNote(record) ? (
                            <span className="v2-table-meta">{getProcessingNote(record)}</span>
                          ) : null}
                        </div>
                      </td>
                      <td>
                        <div className="v2-table-cell-main">
                          <strong>{getRunStatusLabel(record)}</strong>
                        </div>
                      </td>
                      <td>
                        <div className="v2-table-cell-main">
                          <strong>{formatRelativeTimeZh(record.updated_at)}</strong>
                          <span className="v2-table-meta">{formatTimestampZh(record.updated_at)}</span>
                        </div>
                      </td>
                      <td>
                        <div className="v2-action-row v2-ticket-actions">
                          <button
                            className="v2-button is-primary"
                            type="button"
                            onClick={() => openTicketDetail(record.ticket_id)}
                          >
                            详情
                          </button>
                          <button
                            className="v2-button"
                            type="button"
                            onClick={() => openTrace(record.ticket_id, record.latest_run?.run_id)}
                            disabled={!record.latest_run?.run_id}
                          >
                            Trace
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="v2-toolbar v2-toolbar-inline v2-ticket-table-footer">
              <div className="v2-panel-description">
                第 {currentPage} / {totalPages} 页，当前显示 {visibleRangeLabel} / {totalItems}。
              </div>
              <div className="v2-toolbar-actions">
                <Field label="每页行数">
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
                </Field>
                <div className="v2-action-row">
                  <button
                    className="v2-button"
                    type="button"
                    onClick={() => setTicketListFilters({ page: Math.max(1, currentPage - 1) })}
                    disabled={currentPage <= 1}
                  >
                    上一页
                  </button>
                  <button
                    className="v2-button is-primary"
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
            </div>
          </>
        ) : null}
      </Panel>
    </section>
  );
}
