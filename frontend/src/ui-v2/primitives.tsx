import type { PropsWithChildren, ReactNode } from "react";

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

function keepHoverOnly(event: React.MouseEvent<HTMLElement>) {
  event.preventDefault();
  event.stopPropagation();
}

type InfoTipProps = PropsWithChildren<{
  label?: string;
  title?: string;
  className?: string;
}>;

export function InfoTip({
  label = "说明",
  title,
  className,
  children,
}: InfoTipProps) {
  return (
    <div className={cx("v2-info-tip", className)}>
      <button
        type="button"
        className="v2-info-tip-trigger"
        aria-label={title ?? label}
        onMouseDown={keepHoverOnly}
        onClick={keepHoverOnly}
      >
        <span aria-hidden="true">?</span>
      </button>
      <div className="v2-info-tip-popover" role="note">
        <p className="v2-info-tip-label">{label}</p>
        {title ? <strong className="v2-info-tip-title">{title}</strong> : null}
        <div className="v2-info-tip-body">{children}</div>
      </div>
    </div>
  );
}

type PanelProps = PropsWithChildren<{
  label?: string;
  title?: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
}>;

export function Panel({
  label,
  title,
  description,
  actions,
  className,
  children,
}: PanelProps) {
  return (
    <section className={cx("v2-panel", className)}>
      {label || title || description || actions ? (
        <header className="v2-panel-header">
          <div className="v2-panel-copy">
            {label ? <p className="v2-panel-label">{label}</p> : null}
            {title ? <h2 className="v2-panel-title">{title}</h2> : null}
            {description ? <p className="v2-panel-description">{description}</p> : null}
          </div>
          {actions ? <div className="v2-panel-actions">{actions}</div> : null}
        </header>
      ) : null}
      {children}
    </section>
  );
}

type MetricCardProps = {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  tone?: "default" | "accent" | "danger" | "success" | "muted";
};

export function MetricCard({ label, value, note, tone = "default" }: MetricCardProps) {
  return (
    <article className={cx("v2-metric-card", tone !== "default" && `is-${tone}`)}>
      <p className="v2-metric-label">{label}</p>
      <strong className="v2-metric-value">{value}</strong>
      {note ? <p className="v2-metric-note">{note}</p> : null}
    </article>
  );
}

type StatusTagProps = {
  children: ReactNode;
  tone?: "default" | "accent" | "danger" | "success" | "muted";
  className?: string;
};

export function StatusTag({ children, tone = "default", className }: StatusTagProps) {
  return (
    <span className={cx("v2-status-tag", tone !== "default" && `is-${tone}`, className)}>
      {children}
    </span>
  );
}

type EmptyStateProps = {
  label?: string;
  title: string;
  description?: string;
};

export function EmptyState({ label, title, description }: EmptyStateProps) {
  return (
    <section className="v2-empty-state" role="status">
      {label ? <p className="v2-panel-label">{label}</p> : null}
      <h3 className="v2-empty-title">{title}</h3>
      {description ? <p className="v2-empty-description">{description}</p> : null}
    </section>
  );
}

type InlineNoticeProps = {
  title: string;
  detail: string;
  tone?: "success" | "error" | "neutral";
};

export function InlineNotice({
  title,
  detail,
  tone = "neutral",
}: InlineNoticeProps) {
  return (
    <section
      className={cx("v2-inline-notice", tone !== "neutral" && `is-${tone}`)}
      role={tone === "error" ? "alert" : "status"}
    >
      <strong>{title}</strong>
      <p>{detail}</p>
    </section>
  );
}

type TipProps = PropsWithChildren<{
  title: string;
  summary?: string;
  className?: string;
}>;

export function Tip({
  title,
  summary = "查看说明",
  className,
  children,
}: TipProps) {
  return (
    <div className={cx("v2-tip", className)}>
      <button
        type="button"
        className="v2-tip-summary"
        aria-label={title}
        onMouseDown={keepHoverOnly}
        onClick={keepHoverOnly}
      >
        <span className="v2-tip-trigger">{summary}</span>
      </button>
      <div className="v2-tip-body" role="note">
        <p className="v2-tip-label">{summary}</p>
        <strong className="v2-tip-title">{title}</strong>
        <div className="v2-tip-content">{children}</div>
      </div>
    </div>
  );
}

type KeyValueItem = {
  key: string;
  label: string;
  value: ReactNode;
  detail?: ReactNode;
};

type KeyValueGridProps = {
  items: KeyValueItem[];
  className?: string;
};

export function KeyValueGrid({ items, className }: KeyValueGridProps) {
  return (
    <dl className={cx("v2-kv-grid", className)}>
      {items.map((item) => (
        <div key={item.key} className="v2-kv-card">
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
          {item.detail ? <p>{item.detail}</p> : null}
        </div>
      ))}
    </dl>
  );
}

type ToolbarProps = PropsWithChildren<{
  actions?: ReactNode;
  className?: string;
}>;

export function Toolbar({ actions, className, children }: ToolbarProps) {
  return (
    <section className={cx("v2-toolbar", className)}>
      <div className="v2-toolbar-fields">{children}</div>
      {actions ? <div className="v2-toolbar-actions">{actions}</div> : null}
    </section>
  );
}

type FieldProps = {
  label: string;
  children: ReactNode;
  className?: string;
  hint?: ReactNode;
};

export function Field({ label, children, className, hint }: FieldProps) {
  return (
    <label className={cx("v2-field", className)}>
      <span className="v2-field-label-row">
        <span>{label}</span>
        {hint ? (
          <InfoTip label={label} title={`${label}说明`}>
            {hint}
          </InfoTip>
        ) : null}
      </span>
      {children}
    </label>
  );
}

type DataListProps = {
  items: Array<{
    id: string;
    title: ReactNode;
    meta?: ReactNode;
    extra?: ReactNode;
    tone?: "default" | "accent" | "danger";
  }>;
  empty: {
    label: string;
    title: string;
    description: string;
  };
};

export function DataList({ items, empty }: DataListProps) {
  if (items.length === 0) {
    return (
      <EmptyState
        label={empty.label}
        title={empty.title}
        description={empty.description}
      />
    );
  }

  return (
    <div className="v2-list" role="list">
      {items.map((item) => (
        <article
          key={item.id}
          className={cx("v2-list-item", item.tone && `is-${item.tone}`)}
          role="listitem"
        >
          <div className="v2-list-main">
            <strong>{item.title}</strong>
            {item.meta ? <p>{item.meta}</p> : null}
          </div>
          {item.extra ? <div className="v2-list-extra">{item.extra}</div> : null}
        </article>
      ))}
    </div>
  );
}
