"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, ArrowLeft, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api/client";
import { ReportSteps } from "@/components/report-steps";

const STATUS_LABEL = {
  low: "偏低",
  normal: "范围内",
  high: "偏高",
  unknown: "待确认",
};

/** Remove Chinese sentence periods for UI copy. */
function withoutChinesePeriods(text: string) {
  return text.replace(/。/g, "");
}

type SummaryBlock = { title?: string; body: string };

/** Split summary text on 【小节标题】 markers for readable sections. */
function splitSummaryBlocks(raw: string): SummaryBlock[] {
  const text = withoutChinesePeriods(raw).trim();
  if (!text) return [];

  const parts = text.split(/(?=【[^】]+】)/).map((part) => part.trim()).filter(Boolean);
  if (parts.length <= 1 && !/^【[^】]+】/.test(text)) {
    return [{ body: text }];
  }

  return parts.map((part) => {
    const match = part.match(/^【([^】]+)】\s*([\s\S]*)$/);
    if (!match) return { body: part };
    return { title: match[1], body: match[2].trim() };
  });
}

function formatSectionBody(body: string) {
  const lines = body
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length <= 1) {
    // Soft-wrap numbered items like "1. … 2. …" when the model returns one line.
    const numbered = body.split(/(?=(?:^|\s)\d+[\.、]\s*)/).map((item) => item.trim()).filter(Boolean);
    if (numbered.length > 1) return numbered;
    return body ? [body] : [];
  }
  return lines;
}

export default function ReportResultPage() {
  const params = useParams<{ id: string }>();
  const report = useQuery({ queryKey: ["report", params.id], queryFn: () => api.getReport(params.id) });

  if (report.isLoading) {
    return (
      <div className="page">
        <div className="loading">
          <div className="spinner" />
        </div>
      </div>
    );
  }

  if (report.isError || !report.data) {
    return (
      <div className="page">
        <div className="notice urgent">无法读取该报告</div>
      </div>
    );
  }

  const data = report.data;

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">报告解读结果</p>
          <h1>{data.file_name}</h1>
          <p>以下内容仅供健康科普和复核记录使用，不能替代医生诊断</p>
        </div>
        <Link href="/history" className="secondary-button wide-action">
          <ArrowLeft size={16} />
          返回历史
        </Link>
      </div>

      <ReportSteps step={3} reportId={params.id} />

      {data.status !== "completed" && (
        <div className="notice" style={{ marginBottom: 18 }}>
          <AlertCircle size={18} />
          <span>该报告尚未完成解读，可以返回 OCR 核对页继续处理</span>
          <Link href={`/reports/${data.report_id}/ocr`} className="text-button">
            继续核对
          </Link>
        </div>
      )}

      <div className="grid two">
        <section className="panel">
          <header className="panel-head">
            <div>
              <h2>解读摘要</h2>
              <p>系统根据已确认的报告指标生成</p>
            </div>
          </header>
          <div className="panel-pad">
            {data.summary ? (
              <div className="report-summary">
                {splitSummaryBlocks(data.summary).map((block, index) => (
                  <section className="report-summary-block" key={`${block.title ?? "intro"}-${index}`}>
                    {block.title && <h3>{block.title}</h3>}
                    {formatSectionBody(block.body).map((paragraph, paragraphIndex) => (
                      <p key={`${index}-${paragraphIndex}`}>{paragraph}</p>
                    ))}
                  </section>
                ))}
              </div>
            ) : (
              <p className="report-summary">当前报告还没有生成摘要</p>
            )}
          </div>
        </section>

        <section className="panel">
          <header className="panel-head">
            <div>
              <h2>指标统计</h2>
              <p>共提取 {data.items.length} 项</p>
            </div>
          </header>
          <div className="grid three panel-pad">
            <div className="profile-kv">
              <span>偏高</span>
              <strong>{data.items.filter((item) => item.status === "high").length}</strong>
            </div>
            <div className="profile-kv">
              <span>偏低</span>
              <strong>{data.items.filter((item) => item.status === "low").length}</strong>
            </div>
            <div className="profile-kv">
              <span>范围内</span>
              <strong>{data.items.filter((item) => item.status === "normal").length}</strong>
            </div>
          </div>
        </section>
      </div>

      <section className="panel" style={{ marginTop: 18 }}>
        <header className="panel-head">
          <div>
            <h2>指标明细</h2>
            <p>包含数值、单位、参考范围和状态</p>
          </div>
        </header>
        <div className="panel-pad table-wrap">
          <table className="report-table">
            <thead>
              <tr>
                <th>项目名称</th>
                <th>结果</th>
                <th>参考范围</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr key={item.item_id}>
                  <td>{item.name}</td>
                  <td>
                    {item.value ?? "-"} {item.unit}
                  </td>
                  <td>
                    {item.reference_low ?? "-"} - {item.reference_high ?? "-"} {item.unit}
                  </td>
                  <td>
                    <span className={`status ${item.status}`}>
                      <CheckCircle2 size={14} />
                      {STATUS_LABEL[item.status]}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {data.items.some((item) => item.explanation) && (
        <section className="panel" style={{ marginTop: 18 }}>
          <header className="panel-head">
            <div>
              <h2>说明与建议</h2>
              <p>来自已确认指标的科普信息</p>
            </div>
          </header>
          <div className="panel-pad">
            {data.items
              .filter((item) => item.explanation)
              .map((item) => (
                <div className="explanation" key={item.item_id}>
                  <h3>
                    {item.name}
                    <span className={`status ${item.status}`}>{STATUS_LABEL[item.status]}</span>
                  </h3>
                  <p>{withoutChinesePeriods(item.explanation || "")}</p>
                  {!!item.suggestions?.length && (
                    <div className="tag-row" style={{ marginTop: 10 }}>
                      {item.suggestions.map((suggestion) => (
                        <span className="tag neutral" key={suggestion}>
                          {withoutChinesePeriods(suggestion)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
          </div>
        </section>
      )}
    </div>
  );
}
