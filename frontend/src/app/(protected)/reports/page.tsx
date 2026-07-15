"use client";

import { ChangeEvent, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, FileText, History, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api/client";
import { ReportSteps } from "@/components/report-steps";
import type { Report } from "@/lib/api/types";

const STATUS_LABEL: Record<Report["status"], string> = { uploaded: "已上传", ocr_processing: "识别中", needs_confirmation: "待核对", interpreting: "解读中", completed: "已完成", failed: "处理失败" };

export default function ReportsPage() {
  const router = useRouter(); const queryClient = useQueryClient(); const [file, setFile] = useState<File | null>(null); const [reportType, setReportType] = useState<Report["report_type"]>("physical_exam");
  const reports = useQuery({ queryKey: ["reports"], queryFn: api.listReports });
  const upload = useMutation({ mutationFn: () => api.uploadReport(file!, reportType), onSuccess: (report) => { queryClient.invalidateQueries({ queryKey: ["reports"] }); router.push(`/reports/${report.report_id}/ocr`); } });
  function chooseFile(event: ChangeEvent<HTMLInputElement>) { const selected = event.target.files?.[0]; if (!selected) return; if (!/(image\/jpeg|image\/png|application\/pdf)/.test(selected.type) || selected.size > 15 * 1024 * 1024) { setFile(null); return; } setFile(selected); }
  return <div className="page"><div className="page-heading"><div><p className="eyebrow">体检与化验报告</p><h1>上传报告</h1><p>上传后请先核对 OCR 识别结果，再生成仅供科普参考的解读。</p></div><Link href="/history" className="secondary-button"><History size={16} />查看历史</Link></div><ReportSteps step={1} /><div className="grid two"><section className="panel panel-pad"><div className="field"><label>报告类型</label><select value={reportType} onChange={(event) => setReportType(event.target.value as Report["report_type"])}><option value="physical_exam">体检报告</option><option value="blood_test">血液检验</option><option value="other">其他检验报告</option></select></div><label className="upload-zone"><FileUp size={35} color="#087d77" /><h2>{file ? file.name : "选择或拖入报告文件"}</h2><p>支持 JPG、JPEG、PNG 或 PDF，单个文件不超过 15 MB。请避免上传与本次解读无关的个人信息。</p><span className="secondary-button"><Upload size={16} />选择文件</span><input type="file" accept="image/jpeg,image/png,application/pdf" onChange={chooseFile} /></label>{!file && <p style={{ color: "#62727e", fontSize: 13 }}>文件格式或大小不符合要求时将无法提交。</p>}{upload.isError && <div className="notice urgent">{upload.error.message}</div>}<button className="primary-button" style={{ marginTop: 18 }} onClick={() => upload.mutate()} disabled={!file || upload.isPending}>{upload.isPending ? "正在上传与识别…" : "开始识别"}<Upload size={16} /></button></section><section className="panel"><header className="panel-head"><div><h2>最近报告</h2><p>报告和图片属于敏感个人信息。</p></div></header><div className="panel-pad history-list">{reports.data?.items.slice(0, 4).map((report) => <Link className="history-row" href={`/reports/${report.report_id}/${report.status === "completed" ? "result" : "ocr"}`} key={report.report_id}><span className="action-icon"><FileText size={17} /></span><span className="grow"><b>{report.file_name}</b><p>{report.created_at.slice(0, 10)} · {report.report_type}</p></span><span className={`tag ${report.status === "failed" ? "danger" : report.status === "needs_confirmation" ? "warn" : "neutral"}`}>{STATUS_LABEL[report.status]}</span></Link>)}</div></section></div></div>;
}
