import { fetchProductDetail } from "../../../lib/server-api";

export default async function ProductDetailPage({ params }: { params: { skuId: string } }) {
  const product = await fetchProductDetail(params.skuId);
  return (
    <div className="grid">
      <section className="hero">
        <div className="card stack">
          <span className="tag">{product.brand_name}</span>
          <h1 style={{ margin: 0 }}>{product.model_name}</h1>
          <div className="muted">{product.series_name ?? "未归档系列"}</div>
          <div>当前价格：{product.current_price ? `${product.current_price} 元` : "未知"}</div>
          <div>促销：{product.promotion_text ?? "暂无"}</div>
        </div>
        <div className="card stack">
          <strong>卖点</strong>
          <div>
            {product.selling_points.map((point) => (
              <span className="pill" key={point}>
                {point}
              </span>
            ))}
          </div>
        </div>
      </section>

      <section className="card">
        <h2>核心参数</h2>
        <table className="table">
          <tbody>
            {Object.entries(product.spec_json).map(([key, value]) => (
              <tr key={key}>
                <th>{key}</th>
                <td>{String(value ?? "未知")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="grid two">
        <div className="card">
          <h2>来源证据</h2>
          <div className="stack">
            {product.citations.map((citation) => (
              <a key={`${citation.url}-${citation.title}`} href={citation.url} target="_blank">
                <strong>{citation.title}</strong>
                <div className="muted">{citation.source_type}</div>
              </a>
            ))}
          </div>
        </div>
        <div className="card">
          <h2>时间线</h2>
          <div className="stack">
            {product.timeline.map((item) => (
              <div key={`${item.field}-${item.observed_at}`}>
                <strong>{item.field}</strong>
                <div className="muted">
                  {item.old_value ?? "空"} → {item.new_value ?? "空"}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
