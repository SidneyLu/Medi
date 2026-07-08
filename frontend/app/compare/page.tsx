"use client";

import { useEffect, useState } from "react";

import { CompareTable, ProductListItem } from "../../lib/types";

export default function ComparePage() {
  const [products, setProducts] = useState<ProductListItem[]>([]);
  const [selected, setSelected] = useState<number[]>([]);
  const [result, setResult] = useState<CompareTable | null>(null);

  useEffect(() => {
    fetch("/api/products")
      .then((response) => response.json())
      .then(setProducts);
  }, []);

  async function submitCompare() {
    const response = await fetch("/api/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sku_ids: selected })
    });
    setResult(await response.json());
  }

  function toggleSku(skuId: number) {
    setSelected((current) =>
      current.includes(skuId) ? current.filter((value) => value !== skuId) : [...current, skuId].slice(-4)
    );
  }

  return (
    <div className="grid two">
      <section className="card stack">
        <span className="tag">结构化对比</span>
        <h1 style={{ margin: 0 }}>选择 2 到 4 个手机 SKU</h1>
        {products.map((product) => (
          <label key={product.sku_id} style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={selected.includes(product.sku_id)}
              onChange={() => toggleSku(product.sku_id)}
              style={{ width: 18, height: 18 }}
            />
            <span>
              {product.model_name} · {product.brand_name}
            </span>
          </label>
        ))}
        <button onClick={submitCompare} disabled={selected.length < 2}>
          生成对比表
        </button>
      </section>

      <section className="card">
        <h2>对比结果</h2>
        {result ? (
          <table className="table">
            <thead>
              <tr>
                {result.columns.map((column) => (
                  <th key={column}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row, index) => (
                <tr key={index}>
                  {result.columns.map((column) => (
                    <td key={column}>{String(row[column] ?? "-")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">生成后会在这里显示参数和价格对比。</p>
        )}
      </section>
    </div>
  );
}
