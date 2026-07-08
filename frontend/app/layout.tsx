import "./globals.css";
import Link from "next/link";
import { ReactNode } from "react";

export const metadata = {
  title: "EDBuy RAG Prototype",
  description: "Digital product competitor benchmarking prototype"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <div className="shell">
          <nav className="nav">
            <strong>{process.env.NEXT_PUBLIC_APP_NAME ?? "EDBuy RAG Prototype"}</strong>
            <Link href="/products">产品列表</Link>
            <Link href="/compare">竞品对比</Link>
            <Link href="/chat">RAG 问答</Link>
          </nav>
          {children}
        </div>
      </body>
    </html>
  );
}
