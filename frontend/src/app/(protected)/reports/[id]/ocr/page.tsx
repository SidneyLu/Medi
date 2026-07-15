"use client";

import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Save } from "lucide-react";
import { api } from "@/lib/api/client";
import { ReportSteps } from "@/components/report-steps";
import type { ReportItem } from "@/lib/api/types";

export default function OcrPage() {
  const params = useParams<{ id: string }>(); const router = useRouter(); const queryClient = useQueryClient(); const report = useQuery({ queryKey: ["report", params.id], queryFn: () => api.getReport(params.id) });
  const save = useMutation({ mutationFn: (items: ReportItem[]) => api.updateReportItems(params.id, items), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["report", params.id] }) });
  const interpret = useMutation({ mutationFn: () => api.interpretReport(params.id), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["reports"] }); router.push(`/reports/${params.id}/result`); } });
  if (report.isLoading) return <div className="page"><div className="loading"><div className="spinner" /></div></div>; if (report.isError || !report.data) return <div className="page"><div className="notice urgent">无法读取该报告。</div></div>;
  const data = report.data; function changeItem(index: number, field: keyof ReportItem, value: string) { const items = data.items.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: field === "name" || field === "unit" ? value : value === "" ? null : Number(value) } : item); save.mutate(items); }
  if (data.status === "completed") { router.replace(`/reports/${params.id}/result`); return null; }
  return <div className="page"><div className="page-heading"><div><p className="eyebrow">OCR 结果确认</p><h1>核对识别的指标</h1><p>请以原始报告为准。错误的名称、数值、单位或参考范围会影响后续信息整理。</p></div></div><ReportSteps step={2} /><div className="notice"><AlertCircle size={18} /><span>系统不会根据未确认的 OCR 数据生成解读。请逐项核对后继续。</span></div><section className="panel" style={{ marginTop: 18 }}><header className="panel-head"><div><h2>{data.file_name}</h2><p>识别到 {data.items.length} 项检验指标</p></div></header><div className="panel-pad table-wrap"><table className="report-table"><thead><tr><th>项目名称</th><th>数值</th><th>单位</th><th>参考下限</th><th>参考上限</th><th>标记</th></tr></thead><tbody>{data.items.map((item, index) => <tr key={item.item_id}><td><input value={item.name} onChange={(event) => changeItem(index, "name", event.target.value)} /></td><td><input type="number" value={item.value ?? ""} onChange={(event) => changeItem(index, "value", event.target.value)} /></td><td><input value={item.unit} onChange={(event) => changeItem(index, "unit", event.target.value)} /></td><td><input type="number" value={item.reference_low ?? ""} onChange={(event) => changeItem(index, "reference_low", event.target.value)} /></td><td><input type="number" value={item.reference_high ?? ""} onChange={(event) => changeItem(index, "reference_high", event.target.value)} /></td><td><span className={`status ${item.status}`}>{item.status === "low" ? "偏低" : item.status === "high" ? "偏高" : item.status === "normal" ? "范围内" : "待确认"}</span></td></tr>)}</tbody></table></div><div className="panel-pad" style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}><button className="secondary-button" onClick={() => save.mutate(data.items)} disabled={save.isPending}><Save size={16} />保存核对结果</button><button className="primary-button" onClick={() => interpret.mutate()} disabled={interpret.isPending}>{interpret.isPending ? "正在生成…" : "确认并生成解读"}</button></div></section></div>;
}
