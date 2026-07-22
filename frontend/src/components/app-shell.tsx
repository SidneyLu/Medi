"use client";

import Link from "next/link";
import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Activity, ClipboardPlus, FileText, House, MessageSquareText, ShieldCheck, UserRound } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, syncAccessTokenCookie } from "@/lib/api/client";

const NAV = [
  { href: "/dashboard", label: "健康主页", crumb: "主页", icon: House },
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
  const queryClient = useQueryClient();

  useEffect(() => {
    syncAccessTokenCookie();
  }, []);

  const session = useQuery({ queryKey: ["session"], queryFn: api.getMe });
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      queryClient.clear();
      router.replace("/login");
    },
  });

  useEffect(() => {
    if (session.isError) router.replace("/login");
  }, [router, session.isError]);

  if (session.isLoading) return <div className="loading"><div className="spinner" /></div>;
  if (session.isError || !session.data) return <div className="loading"><div className="spinner" /></div>;

  const user = session.data;
  const activeNav = NAV.find((entry) => isActive(pathname, entry.href));
  const current = activeNav?.crumb ?? activeNav?.label ?? "Medi-家用医疗健康助手";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/dashboard" className="brand">
          <span className="brand-mark"><Activity size={17} /></span>
          Medi-家用医疗健康助手
        </Link>
        <nav className="nav-list" aria-label="主导航">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href} className={`nav-link ${isActive(pathname, href) ? "active" : ""}`} title={label}>
              <Icon size={18} />
              <span>{label}</span>
            </Link>
          ))}
        </nav>
        <div className="sidebar-foot">
          <ShieldCheck size={14} /> 本服务仅提供健康科普，不替代医生诊疗
        </div>
      </aside>
      <main className="main-area">
        <header className="topbar">
          <span className="crumb">{current}</span>
          <div className="account-menu">
            <Link href="/profile" className="account-profile" title="进入我的画像" aria-label="进入我的画像">
              <span className="account-avatar">{user.nickname.slice(0, 1)}</span>
              <span className="account-meta">
                <b>{user.nickname}</b>
                <small>{user.email}</small>
              </span>
            </Link>
            <button
              className="primary-button account-logout"
              type="button"
              disabled={logout.isPending}
              onClick={() => logout.mutate()}
            >
              {logout.isPending ? "退出中…" : "退出登录"}
            </button>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}
