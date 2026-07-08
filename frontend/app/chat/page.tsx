"use client";

import { useEffect, useState } from "react";

import { ChatResponse, ProductListItem } from "../../lib/types";

export default function ChatPage() {
  const [products, setProducts] = useState<ProductListItem[]>([]);
  const [skuIds, setSkuIds] = useState<number[]>([]);
  const [question, setQuestion] = useState("Xiaomi 14 和 vivo X200 的参数差异是什么？用户口碑更偏向哪一款？");
  const [result, setResult] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch("/api/products")
      .then((response) => response.json())
      .then(setProducts);
  }, []);

  async function submitQuestion() {
    setLoading(true);
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        sku_ids: skuIds,
        comparison_sku_ids: skuIds.slice(0, 2)
      })
    });
    setResult(await response.json());
    setLoading(false);
  }

  function toggleSku(skuId: number) {
    setSkuIds((current) => (current.includes(skuId) ? current.filter((value) => value !== skuId) : [...current, skuId]));
  }

  return (
    <div className="grid two">
      <section className="card stack">
        <span className="tag">RAG 问答</span>
        <textarea rows={8} value={question} onChange={(event) => setQuestion(event.target.value)} />
        <div className="stack">
          {products.map((product) => (
            <label key={product.sku_id} style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={skuIds.includes(product.sku_id)}
                onChange={() => toggleSku(product.sku_id)}
                style={{ width: 18, height: 18 }}
              />
              <span>{product.model_name}</span>
            </label>
          ))}
        </div>
        <button onClick={submitQuestion} disabled={loading}>
          {loading ? "生成中..." : "提交问题"}
        </button>
      </section>

      <section className="card stack">
        <h2 style={{ margin: 0 }}>回答</h2>
        {result ? (
          <>
            <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{result.answer_text}</p>
            <div>
              <strong>缺失字段</strong>
              <div className="muted">{result.missing_fields.length ? result.missing_fields.join("、") : "无"}</div>
            </div>
            {result.compare_table?.columns?.length ? (
              <table className="table">
                <thead>
                  <tr>
                    {result.compare_table.columns.map((column) => (
                      <th key={column}>{column}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.compare_table.rows.map((row, index) => (
                    <tr key={index}>
                      {result.compare_table.columns.map((column) => (
                        <td key={column}>{String(row[column] ?? "-")}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
            <div className="stack">
              <strong>引用来源</strong>
              {result.citations.map((citation) => (
                <a key={`${citation.url}-${citation.title}`} href={citation.url} target="_blank">
                  <strong>{citation.title}</strong>
                  <div className="muted">{citation.snippet}</div>
                </a>
              ))}
            </div>
          </>
        ) : (
          <p className="muted">这里会显示结构化总结、引用和对比表。</p>
        )}
      </section>
    </div>
  );
}
