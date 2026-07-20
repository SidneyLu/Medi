"use client";

import { ChangeEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, FileText, History, Upload, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api/client";
import { ReportSteps } from "@/components/report-steps";
import type { Report } from "@/lib/api/types";

const STATUS_LABEL: Record<Report["status"], string> = {
  uploaded: "已上传",
  ocr_processing: "识别中",
  needs_confirmation: "待核对",
  interpreting: "解读中",
  completed: "已完成",
  failed: "处理失败",
};

function formatBytes(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ReportsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [reportType, setReportType] = useState<Report["report_type"]>("physical_exam");
  const reports = useQuery({ queryKey: ["reports"], queryFn: api.listReports });
  const upload = useMutation({
    mutationFn: () => api.uploadReport(file!, reportType),
    onSuccess: (report) => {
      queryClient.invalidateQueries({ queryKey: ["reports"] });
      router.push(`/reports/${report.report_id}/ocr`);
    },
  });

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0];
    event.target.value = "";
    if (!selected) return;
    if (!/(image\/jpeg|image\/png|application\/pdf)/.test(selected.type) || selected.size > 15 * 1024 * 1024) {
      setFile(null);
      setFileError("文件格式或大小不符合要求（仅 JPG / PNG / PDF，且不超过 15 MB）");
      return;
    }
    setFileError("");
    setFile(selected);
  }

  function clearFile() {
    setFile(null);
    setFileError("");
  }

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <h1>请上传您的体检与化验报告</h1>
          <p>上传后请先核对 OCR 识别结果，再查看报告解读</p>
        </div>
        <Link href="/history" className="secondary-button wide-action">
          <History size={16} />
          查看历史
        </Link>
      </div>
      <ReportSteps step={1} />
      <div className="grid two">
        <section className="panel panel-pad">
          <div className="field">
            <label>报告类型</label>
            <select value={reportType} onChange={(event) => setReportType(event.target.value as Report["report_type"])}>
              <option value="physical_exam">体检报告</option>
              <option value="blood_test">血液检验</option>
              <option value="other">其他检验报告</option>
            </select>
          </div>
          <label className={`upload-zone ${file ? "has-file" : ""}`}>
            <FileUp size={35} color="#087d77" />
            <h2>{file ? "已选择报告文件" : "选择或拖入报告文件"}</h2>
            <p>支持 JPG、JPEG、PNG 或 PDF，单个文件不超过 15 MB。请避免上传与本次解读无关的个人信息</p>
            <span className="secondary-button wide-action">
              <Upload size={16} />
              {file ? "重新选择" : "选择文件"}
            </span>
            <input type="file" accept="image/jpeg,image/png,application/pdf" onChange={chooseFile} />
          </label>

          {file && (
            <div className="upload-file-card">
              <span className="action-icon">
                <FileText size={17} />
              </span>
              <span className="grow">
                <b>{file.name}</b>
                <p>
                  {file.type.includes("pdf") ? "PDF 报告" : "图片报告"} · {formatBytes(file.size)} · 待上传识别
                </p>
                {previewUrl && file.type.includes("pdf") && (
                  <a className="text-button" href={previewUrl} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>
                    预览 PDF
                  </a>
                )}
              </span>
              <button type="button" className="icon-clear" onClick={clearFile} aria-label="移除文件">
                <X size={16} />
              </button>
            </div>
          )}

          {fileError && <div className="notice urgent">{fileError}</div>}
          {!file && !fileError && <p style={{ color: "#62727e", fontSize: 13 }}>选择文件后会在上方显示文件卡片，确认无误再点「开始识别」</p>}
          {upload.isError && <div className="notice urgent">{upload.error.message}</div>}
          <button
            className="primary-button"
            style={{ marginTop: 18 }}
            onClick={() => upload.mutate()}
            disabled={!file || upload.isPending}
          >
            {upload.isPending ? "正在上传与识别…" : "开始识别"}
            <Upload size={16} />
          </button>
        </section>
        <section className="panel">
          <header className="panel-head">
            <div>
              <h2>最近报告</h2>
              <p>报告和图片属于敏感个人信息</p>
            </div>
          </header>
          <div className="panel-pad history-list">
            {reports.data?.items.slice(0, 4).map((report) => (
              <Link
                className="history-row"
                href={`/reports/${report.report_id}/${report.status === "completed" ? "result" : "ocr"}`}
                key={report.report_id}
              >
                <span className="action-icon"><FileText size={17} /></span>
                <span className="grow">
                  <b>{report.file_name}</b>
                  <p>{report.created_at.slice(0, 10)} · {report.report_type}</p>
                </span>
                <span className={`tag ${report.status === "failed" ? "danger" : report.status === "needs_confirmation" ? "warn" : "neutral"}`}>
                  {STATUS_LABEL[report.status]}
                </span>
              </Link>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
