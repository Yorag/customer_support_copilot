type PagePlaceholderProps = {
  title: string;
  description: string;
  endpointRefs: string[];
  nextBatch: string;
};

export function PagePlaceholder({
  title,
  description,
  endpointRefs,
  nextBatch,
}: PagePlaceholderProps) {
  return (
    <article className="placeholder-page">
      <div className="placeholder-copy">
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      <div className="placeholder-grid">
        <section className="placeholder-card">
          <p className="placeholder-eyebrow">已绑定 API 合约</p>
          <ul className="placeholder-list">
            {endpointRefs.map((endpoint) => (
              <li key={endpoint}>{endpoint}</li>
            ))}
          </ul>
        </section>
        <section className="placeholder-card">
          <p className="placeholder-eyebrow">下一交付批次</p>
          <p className="placeholder-strong">{nextBatch}</p>
        </section>
        <section className="placeholder-card">
          <p className="placeholder-eyebrow">实施策略</p>
          <p className="placeholder-strong">
            先搭壳层，再按批次补页面能力，并为每批次补测试。
          </p>
        </section>
      </div>
    </article>
  );
}
