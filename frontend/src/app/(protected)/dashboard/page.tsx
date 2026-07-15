"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FileText, MessageSquareText, ShieldAlert, Stethoscope, UserRound } from "lucide-react";
import { api } from "@/lib/api/client";

export default function DashboardPage() {
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.getProfile });
  const reports = useQuery({ queryKey: ["reports"], queryFn: api.listReports });
  const conversations = useQuery({ queryKey: ["conversations"], queryFn: api.listConversations });
  const userProfile = profile.data?.profile;
  return <div className="page">
    <div className="page-heading"><div><p className="eyebrow">家庭健康工作台</p><h1>早上好，{userProfile?.nickname ?? ""}</h1><p>从健康档案、检验报告和循证知识中整理下一步信息。</p></div><Link className="primary-button" href="/chat"><MessageSquareText size={17} />发起健康咨询</Link></div>
    <div className="notice"><ShieldAlert size={18} /><span><strong>健康提示：</strong>本服务只提供健康科普，不替代医生诊断、处方或紧急医疗服务。出现胸痛、呼吸困难、意识改变等紧急情况，请立即寻求急救帮助。</span></div>
    <div className="grid three" style={{ marginTop: 18 }}><section className="panel metric"><span className="metric-label">健康画像</span><strong className="metric-value">{userProfile ? "已完善" : "待填写"}</strong><span className="metric-note">{profile.data?.tags.length ?? 0} 个标签已生成</span></section><section className="panel metric"><span className="metric-label">已存报告</span><strong className="metric-value">{reports.data?.items.length ?? 0}</strong><span className="metric-note">可查看 OCR 与解读记录</span></section><section className="panel metric"><span className="metric-label">咨询记录</span><strong className="metric-value">{conversations.data?.items.length ?? 0}</strong><span className="metric-note">全部回答附来源链接</span></section></div>
    <div className="grid two" style={{ marginTop: 18 }}><section className="panel"><header className="panel-head"><div><h2>快速开始</h2><p>完成以下操作，建立你的健康信息视图。</p></div></header><div className="panel-pad action-list"><Link className="action-row" href="/profile"><span className="action-icon"><UserRound size={18} /></span><span className="grow"><b>完善个人健康画像</b><p>记录基本信息、慢病、过敏史和常用药。</p></span><ArrowRight size={17} /></Link><Link className="action-row" href="/reports"><span className="action-icon"><FileText size={18} /></span><span className="grow"><b>上传体检或化验报告</b><p>核对 OCR 结果后查看带来源的科普解读。</p></span><ArrowRight size={17} /></Link><Link className="action-row" href="/chat"><span className="action-icon"><Stethoscope size={18} /></span><span className="grow"><b>查看循证健康信息</b><p>描述问题，查看默沙东原文引用。</p></span><ArrowRight size={17} /></Link></div></section>
    <section className="panel"><header className="panel-head"><div><h2>当前画像</h2><p>后端生成的标签将用于你主动选择的问答上下文。</p></div><Link className="text-button" href="/profile">编辑</Link></header><div className="panel-pad">{userProfile ? <><div className="profile-summary"><div className="profile-kv"><span>出生日期</span><strong>{userProfile.birth_date}</strong></div><div className="profile-kv"><span>性别</span><strong>{userProfile.sex_at_birth === "female" ? "女性" : userProfile.sex_at_birth === "male" ? "男性" : "未说明"}</strong></div><div className="profile-kv"><span>过敏史</span><strong>{userProfile.allergies.join("、") || "未记录"}</strong></div><div className="profile-kv"><span>常用药</span><strong>{userProfile.current_medications.join("、") || "未记录"}</strong></div></div><div className="tag-row" style={{ marginTop: 15 }}>{profile.data?.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}</div></> : <div className="empty">尚未填写健康画像</div>}</div></section></div>
  </div>;
}
