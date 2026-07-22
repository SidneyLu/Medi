"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { FileText, MessageSquareText, Plus } from "lucide-react";
import { api } from "@/lib/api/client";
import type { Report } from "@/lib/api/types";

const STATUS_LABEL: Record<Report["status"], string> = {
  uploaded: "已上传",
  ocr_processing: "识别中",
  needs_confirmation: "待核对",
  interpreting: "解读中",
  completed: "已完成",
  failed: "处理失败",
};

const REPORT_TYPE_LABEL: Record<Report["report_type"], string> = {
  physical_exam: "体检报告",
  blood_test: "血液检验",
  other: "其他报告",
};

function dateOnly(value: string) {
  return value ? value.slice(0, 10) : "";
}

function reportHref(report: Report) {
  return `/reports/${report.report_id}/${report.status === "completed" ? "result" : "ocr"}`;
}

export default function HistoryPage() {
  const conversations = useQuery({ queryKey: ["conversations"], queryFn: api.listConversations });
  const reports = useQuery({ queryKey: ["reports"], queryFn: api.listReports });

  return <div className="page">
    <div className="page-heading">
      <div>
        <p className="eyebrow">历史记录</p>
        <h1>问诊与报告历史</h1>
        <p>这里汇总当前账户的健康咨询和体检报告，便于继续追踪。</p>
      </div>
      <div style={{ display: "flex", gap: 10 }}>
        <Link href="/chat" className="secondary-button"><Plus size={16} />新建咨询</Link>
        <Link href="/reports" className="primary-button"><FileText size={16} />上传报告</Link>
      </div>
    </div>

    <div className="grid two">
      <section className="panel">
        <header className="panel-head">
          <div>
            <h2>咨询记录</h2>
            <p>按最近更新时间排序。</p>
          </div>
        </header>
        <div className="panel-pad history-list">
          {conversations.isLoading && <div className="loading compact"><div className="spinner" /></div>}
          {conversations.isError && <div className="notice urgent">无法读取咨询历史，请确认后端已启动。</div>}
          {conversations.data?.items.length === 0 && <div className="empty compact">暂无咨询记录。</div>}
          {conversations.data?.items.map((conversation) => <Link className="history-row" href="/chat" key={conversation.conversation_id}>
            <span className="action-icon"><MessageSquareText size={17} /></span>
            <span className="grow">
              <b>{conversation.title || "未命名咨询"}</b>
              <p>{dateOnly(conversation.updated_at)} · {conversation.preview || "暂无回复摘要"}</p>
            </span>
            <span className="tag neutral">问诊</span>
          </Link>)}
        </div>
      </section>

      <section className="panel">
        <header className="panel-head">
          <div>
            <h2>报告记录</h2>
            <p>上传、核对和解读结果都会保留。</p>
          </div>
        </header>
        <div className="panel-pad history-list">
          {reports.isLoading && <div className="loading compact"><div className="spinner" /></div>}
          {reports.isError && <div className="notice urgent">无法读取报告历史，请确认后端已启动。</div>}
          {reports.data?.items.length === 0 && <div className="empty compact">暂无报告记录。</div>}
          {reports.data?.items.map((report) => <Link className="history-row" href={reportHref(report)} key={report.report_id}>
            <span className="action-icon"><FileText size={17} /></span>
            <span className="grow">
              <b>{report.file_name}</b>
              <p>{dateOnly(report.created_at)} · {REPORT_TYPE_LABEL[report.report_type]} · {report.items.length} 项指标</p>
            </span>
            <span className={`tag ${report.status === "failed" ? "danger" : report.status === "needs_confirmation" ? "warn" : "neutral"}`}>{STATUS_LABEL[report.status]}</span>
          </Link>)}
        </div>
      </section>
    </div>
  </div>;
}
