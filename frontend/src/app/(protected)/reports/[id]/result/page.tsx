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

export default function ReportResultPage() {
  const params = useParams<{ id: string }>();
  const report = useQuery({ queryKey: ["report", params.id], queryFn: () => api.getReport(params.id) });

  if (report.isLoading) return <div className="page"><div className="loading"><div className="spinner" /></div></div>;
  if (report.isError || !report.data) return <div className="page"><div className="notice urgent">无法读取该报告。</div></div>;

  const data = report.data;
  const highCount = data.items.filter((item) => item.status === "high").length;
  const lowCount = data.items.filter((item) => item.status === "low").length;
  const normalCount = data.items.filter((item) => item.status === "normal").length;

  return <div className="page">
    <div className="page-heading">
      <div>
        <p className="eyebrow">报告解读结果</p>
        <h1>{data.file_name}</h1>
        <p>以下内容仅用于健康科普和复核记录，不能替代医生诊断。</p>
      </div>
      <Link href="/history" className="secondary-button"><ArrowLeft size={16} />返回历史</Link>
    </div>

    <ReportSteps step={3} />

    {data.status !== "completed" && <div className="notice" style={{ marginBottom: 18 }}>
      <AlertCircle size={18} />
      <span>该报告尚未完成解读，可以返回 OCR 核对页继续处理。</span>
      <Link href={`/reports/${data.report_id}/ocr`} className="text-button">继续核对</Link>
    </div>}

    <div className="grid two">
      <section className="panel">
        <header className="panel-head">
          <div>
            <h2>解读摘要</h2>
            <p>系统根据已确认指标和个人画像关键词生成。</p>
          </div>
        </header>
        <div className="panel-pad">
          <p className="report-summary">{data.summary || "当前报告还没有生成摘要。"}</p>
          <div className="tag-row" style={{ marginTop: 16 }}>
            {data.profile_tags_used.map((tag) => <span className="tag neutral" key={tag}>{tag}</span>)}
          </div>
        </div>
      </section>

      <section className="panel">
        <header className="panel-head">
          <div>
            <h2>指标统计</h2>
            <p>共提取 {data.items.length} 项。</p>
          </div>
        </header>
        <div className="grid three panel-pad">
          <div className="profile-kv"><span>偏高</span><strong>{highCount}</strong></div>
          <div className="profile-kv"><span>偏低</span><strong>{lowCount}</strong></div>
          <div className="profile-kv"><span>范围内</span><strong>{normalCount}</strong></div>
        </div>
      </section>
    </div>

    <section className="panel" style={{ marginTop: 18 }}>
      <header className="panel-head">
        <div>
          <h2>指标明细</h2>
          <p>包含数值、单位、参考范围和状态。</p>
        </div>
      </header>
      <div className="panel-pad table-wrap">
        <table className="report-table">
          <thead>
            <tr><th>项目名称</th><th>结果</th><th>参考范围</th><th>状态</th></tr>
          </thead>
          <tbody>
            {data.items.map((item) => <tr key={item.item_id}>
              <td>{item.name}</td>
              <td>{item.value ?? "-"} {item.unit}</td>
              <td>{item.reference_low ?? "-"} - {item.reference_high ?? "-"} {item.unit}</td>
              <td><span className={`status ${item.status}`}><CheckCircle2 size={14} />{STATUS_LABEL[item.status]}</span></td>
            </tr>)}
          </tbody>
        </table>
      </div>
    </section>
  </div>;
}
