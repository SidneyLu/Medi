"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, FileText, Save } from "lucide-react";
import { api } from "@/lib/api/client";
import { ReportSteps } from "@/components/report-steps";
import type { ReportItem } from "@/lib/api/types";

export default function OcrPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const report = useQuery({ queryKey: ["report", params.id], queryFn: () => api.getReport(params.id) });
  const [items, setItems] = useState<ReportItem[]>([]);
  const [savedHint, setSavedHint] = useState(false);

  useEffect(() => {
    if (report.data?.items) setItems(report.data.items);
  }, [report.data?.items]);

  const save = useMutation({
    mutationFn: (next: ReportItem[]) => api.updateReportItems(params.id, next),
    onSuccess: (updated) => {
      setItems(updated.items);
      queryClient.invalidateQueries({ queryKey: ["report", params.id] });
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      setSavedHint(true);
      window.setTimeout(() => setSavedHint(false), 2500);
    },
  });

  const interpret = useMutation({
    mutationFn: async () => {
      await api.updateReportItems(params.id, items);
      return api.interpretReport(params.id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      queryClient.invalidateQueries({ queryKey: ["report", params.id] });
      router.push(`/reports/${params.id}/result`);
    },
  });

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

  if (data.status === "completed") {
    router.replace(`/reports/${params.id}/result`);
    return null;
  }

  const hasOnlyPlaceholder =
    items.length > 0 &&
    items.every((item) => !item.name.trim() || item.name.trim().toLowerCase() === "ocr pending");

  function changeItem(index: number, field: keyof ReportItem, value: string) {
    setItems((prev) =>
      prev.map((item, itemIndex) => {
        if (itemIndex !== index) return item;
        if (field === "name" || field === "unit") return { ...item, [field]: value };
        return { ...item, [field]: value === "" ? null : Number(value) };
      }),
    );
    setSavedHint(false);
  }

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">OCR 结果确认</p>
          <h1>核对识别的指标</h1>
          <p>请以原始报告为准。错误的名称、数值、单位或参考范围会影响后续信息整理</p>
        </div>
      </div>

      <ReportSteps step={2} reportId={params.id} />

      <div className="upload-file-card" style={{ marginBottom: 16 }}>
        <span className="action-icon">
          <FileText size={17} />
        </span>
        <span className="grow">
          <b>{data.file_name}</b>
          <p>已上传并完成识别 · {items.length} 项指标待核对</p>
        </span>
        <span className="tag neutral">已上传</span>
      </div>

      <div className="notice">
        <AlertCircle size={18} />
        <span>系统不会根据未确认的 OCR 数据生成解读。请逐项核对后继续。「保存核对结果」只把当前表格写入服务器，不会进入解读页</span>
      </div>

      {(data.error_message || hasOnlyPlaceholder) && (
        <div className="notice urgent" style={{ marginTop: 12 }}>
          <AlertCircle size={18} />
          <span>
            {data.error_message ||
              "自动识别未得到有效指标（常见原因：图片 OCR 依赖未安装，或 PDF 无可提取文字）。请手工填写下表后保存，或安装 paddleocr 后重新上传。"}
          </span>
        </div>
      )}

      <section className="panel" style={{ marginTop: 18 }}>
        <header className="panel-head">
          <div>
            <h2>{data.file_name}</h2>
            <p>
              {hasOnlyPlaceholder
                ? "尚未识别到有效指标，请手工填写或重新上传"
                : `识别到 ${items.length} 项检验指标`}
            </p>
          </div>
        </header>
        <div className="panel-pad table-wrap">
          <table className="report-table">
            <thead>
              <tr>
                <th>项目名称</th>
                <th>数值</th>
                <th>单位</th>
                <th>参考下限</th>
                <th>参考上限</th>
                <th>标记</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={item.item_id}>
                  <td>
                    <input value={item.name} onChange={(event) => changeItem(index, "name", event.target.value)} />
                  </td>
                  <td>
                    <input type="number" value={item.value ?? ""} onChange={(event) => changeItem(index, "value", event.target.value)} />
                  </td>
                  <td>
                    <input value={item.unit} onChange={(event) => changeItem(index, "unit", event.target.value)} />
                  </td>
                  <td>
                    <input
                      type="number"
                      value={item.reference_low ?? ""}
                      onChange={(event) => changeItem(index, "reference_low", event.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      value={item.reference_high ?? ""}
                      onChange={(event) => changeItem(index, "reference_high", event.target.value)}
                    />
                  </td>
                  <td>
                    <span className={`status ${item.status}`}>
                      {item.status === "low" ? "偏低" : item.status === "high" ? "偏高" : item.status === "normal" ? "范围内" : "待确认"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel-pad" style={{ display: "flex", gap: 10, justifyContent: "flex-end", alignItems: "center", flexWrap: "wrap" }}>
          {savedHint && (
            <span className="save-hint">
              <CheckCircle2 size={15} />
              核对结果已保存
            </span>
          )}
          {(save.isError || interpret.isError) && (
            <span className="notice urgent" style={{ margin: 0, flex: "1 1 220px" }}>
              {(save.error as Error | null)?.message || (interpret.error as Error | null)?.message || "操作失败，请确认后端已启动"}
            </span>
          )}
          <button className="secondary-button" onClick={() => save.mutate(items)} disabled={save.isPending || interpret.isPending}>
            <Save size={16} />
            {save.isPending ? "保存中…" : "保存核对结果"}
          </button>
          <button className="primary-button" onClick={() => interpret.mutate()} disabled={interpret.isPending || save.isPending}>
            {interpret.isPending ? "正在生成…" : "确认并生成解读"}
          </button>
        </div>
      </section>
    </div>
  );
}
