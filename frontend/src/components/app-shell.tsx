"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Activity, ClipboardPlus, FileText, House, LogOut, MessageSquareText, ShieldCheck, UserRound } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";

const NAV = [
  { href: "/dashboard", label: "健康工作台", icon: House },
  { href: "/chat", label: "循证问答", icon: MessageSquareText },
  { href: "/reports", label: "报告解读", icon: FileText },
  { href: "/profile", label: "我的画像", icon: UserRound },
  { href: "/history", label: "历史记录", icon: ClipboardPlus },
];

function isActive(pathname: string, href: string) {
  return pathname === href || (href !== "/dashboard" && pathname.startsWith(`${href}/`));
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const session = useQuery({ queryKey: ["session"], queryFn: api.getMe });
  const logout = useMutation({ mutationFn: api.logout, onSuccess: () => router.push("/login") });

  if (session.isLoading) return <div className="loading"><div className="spinner" /></div>;
  if (session.isError) { router.replace("/login"); return null; }
  const user = session.data;
  const current = NAV.find((entry) => isActive(pathname, entry.href))?.label ?? "Medi-家用医疗健康助手";

  return <div className="app-shell">
    <aside className="sidebar">
      <Link href="/dashboard" className="brand"><span className="brand-mark"><Activity size={17} /></span>Medi-家用医疗健康助手</Link>
      <nav className="nav-list" aria-label="主导航">
        {NAV.map(({ href, label, icon: Icon }) => <Link key={href} href={href} className={`nav-link ${isActive(pathname, href) ? "active" : ""}`} title={label}><Icon size={18} /><span>{label}</span></Link>)}
      </nav>
      <div className="sidebar-foot"><ShieldCheck size={14} /> 本服务仅提供健康科普，不替代医生诊疗。</div>
    </aside>
    <main className="main-area">
      <header className="topbar"><span className="crumb">{current}</span><div className="account-menu"><span className="account-avatar">{user.nickname.slice(0, 1)}</span><span className="account-meta"><b>{user.nickname}</b><small>{user.email}</small></span><button className="icon-button" title="退出登录" aria-label="退出登录" onClick={() => logout.mutate()}><LogOut size={18} /></button></div></header>
      {children}
    </main>
  </div>;
}
