"use client";

import Link from "next/link";
import { MouseEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, MessageSquareText, X } from "lucide-react";
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

/** Keep start/end of long names; replace the middle with an ellipsis. */
function middleEllipsis(value: string, max = 34) {
  const text = value.trim();
  if (text.length <= max) return text;
  const keep = Math.max(6, Math.floor((max - 1) / 2));
  return `${text.slice(0, keep)}…${text.slice(-keep)}`;
}

export default function HistoryPage() {
  const queryClient = useQueryClient();
  const conversations = useQuery({ queryKey: ["conversations"], queryFn: api.listConversations });
  const reports = useQuery({ queryKey: ["reports"], queryFn: api.listReports });

  const deleteConversation = useMutation({
    mutationFn: (id: string) => api.deleteConversation(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  const deleteReport = useMutation({
    mutationFn: (id: string) => api.deleteReport(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reports"] });
    },
  });

  function onDeleteConversation(event: MouseEvent, id: string, title: string) {
    event.preventDefault();
    event.stopPropagation();
    if (!window.confirm(`确定删除咨询「${middleEllipsis(title || "未命名咨询", 24)}」吗？`)) return;
    deleteConversation.mutate(id);
  }

  function onDeleteReport(event: MouseEvent, id: string, fileName: string) {
    event.preventDefault();
    event.stopPropagation();
    if (!window.confirm(`确定删除报告「${middleEllipsis(fileName, 24)}」吗？`)) return;
    deleteReport.mutate(id);
  }

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">历史记录</p>
          <h1>问诊与报告历史</h1>
          <p>汇总当前账户的健康咨询和体检报告记录（数据来自 PostgreSQL）</p>
        </div>
      </div>

      <div className="grid two">
        <section className="panel">
          <header className="panel-head">
            <div>
              <h2>咨询记录</h2>
              <p>按最近更新时间排序</p>
            </div>
          </header>
          <div className="panel-pad history-list">
            {conversations.isLoading && (
              <div className="loading compact">
                <div className="spinner" />
              </div>
            )}
            {conversations.isError && <div className="notice urgent">无法读取咨询历史</div>}
            {conversations.data?.items.length === 0 && <div className="empty compact">暂无咨询记录</div>}
            {conversations.data?.items.map((conversation) => (
              <div className="history-row" key={conversation.conversation_id}>
                <Link className="history-row-main" href="/chat">
                  <span className="action-icon">
                    <MessageSquareText size={17} />
                  </span>
                  <span className="grow">
                    <b title={conversation.title || "未命名咨询"}>{middleEllipsis(conversation.title || "未命名咨询")}</b>
                    <p title={conversation.preview || "暂无回复摘要"}>{dateOnly(conversation.updated_at)} · {middleEllipsis(conversation.preview || "暂无回复摘要", 40)}</p>
                  </span>
                  <span className="tag neutral">问诊</span>
                </Link>
                <button
                  type="button"
                  className="history-delete"
                  aria-label="删除咨询记录"
                  title="删除"
                  disabled={deleteConversation.isPending}
                  onClick={(event) => onDeleteConversation(event, conversation.conversation_id, conversation.title || "未命名咨询")}
                >
                  <X size={15} />
                </button>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <header className="panel-head">
            <div>
              <h2>报告记录</h2>
              <p>上传、核对和解读结果都会保留</p>
            </div>
          </header>
          <div className="panel-pad history-list">
            {reports.isLoading && (
              <div className="loading compact">
                <div className="spinner" />
              </div>
            )}
            {reports.isError && <div className="notice urgent">无法读取报告历史</div>}
            {reports.data?.items.length === 0 && <div className="empty compact">暂无报告记录</div>}
            {reports.data?.items.map((report) => (
              <div className="history-row" key={report.report_id}>
                <Link className="history-row-main" href={reportHref(report)}>
                  <span className="action-icon">
                    <FileText size={17} />
                  </span>
                  <span className="grow">
                    <b title={report.file_name}>{middleEllipsis(report.file_name)}</b>
                    <p>
                      {dateOnly(report.created_at)} · {REPORT_TYPE_LABEL[report.report_type]} · {report.items.length} 项指标
                    </p>
                  </span>
                  <span className={`tag ${report.status === "failed" ? "danger" : report.status === "needs_confirmation" ? "warn" : "neutral"}`}>
                    {STATUS_LABEL[report.status]}
                  </span>
                </Link>
                <button
                  type="button"
                  className="history-delete"
                  aria-label="删除报告记录"
                  title="删除"
                  disabled={deleteReport.isPending}
                  onClick={(event) => onDeleteReport(event, report.report_id, report.file_name)}
                >
                  <X size={15} />
                </button>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
