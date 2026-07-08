import Link from "next/link";

import { fetchProducts } from "../../lib/server-api";

export default async function ProductsPage({
  searchParams
}: {
  searchParams: { search?: string; brand?: string; category?: string };
}) {
  const products = await fetchProducts(searchParams);
  return (
    <div className="grid">
      <section className="hero">
        <div className="card stack">
          <span className="tag">手机竞品主档</span>
          <h1 style={{ margin: 0 }}>SKU 列表与结构化真值</h1>
          <p className="muted" style={{ margin: 0 }}>
            当前原型展示从种子 CSV 和样本文档导入的手机竞品数据，可直接进入详情、对比和问答页验证全链路。
          </p>
        </div>
        <div className="card stack">
          <strong>当前覆盖</strong>
          <div className="muted">品类：手机</div>
          <div className="muted">SKU 数量：{products.length}</div>
          <div className="muted">结构化来源：seed 快照</div>
        </div>
      </section>

      <section className="grid two">
        <div className="card">
          <form className="grid" method="GET">
            <input name="search" placeholder="搜索型号" defaultValue={searchParams.search ?? ""} />
            <input name="brand" placeholder="品牌筛选，如 Xiaomi" defaultValue={searchParams.brand ?? ""} />
            <input name="category" placeholder="品类筛选，如 phone" defaultValue={searchParams.category ?? ""} />
            <button type="submit">筛选</button>
          </form>
        </div>
        {products.map((product) => (
          <Link key={product.sku_id} href={`/products/${product.sku_id}`} className="card stack">
            <div className="tag">{product.brand_name}</div>
            <h2 style={{ margin: 0 }}>{product.model_name}</h2>
            <div className="muted">{product.chipset ?? "暂无芯片信息"}</div>
            <div>现价：{product.current_price ? `${product.current_price} 元` : "未知"}</div>
            <div className="muted">标准名：{product.normalized_model_name}</div>
          </Link>
        ))}
      </section>
    </div>
  );
}
