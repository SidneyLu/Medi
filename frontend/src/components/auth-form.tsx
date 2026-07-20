"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Activity, ArrowRight } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { api } from "@/lib/api/client";

const schema = z.object({
  email: z.string().email("请输入有效的邮箱地址"),
  password: z
    .string()
    .min(8, "密码至少包含 8 个字符")
    .refine((value) => /[A-Za-z]/.test(value) && /\d/.test(value), "密码需同时包含字母和数字"),
});
type FormValues = z.infer<typeof schema>;

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });
  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      mode === "login" ? api.login(values.email, values.password) : api.register(values.email, values.password),
    onSuccess: (user) => {
      queryClient.setQueryData(["session"], user);
      router.push("/dashboard");
    },
  });
  const title = mode === "login" ? "欢迎回来" : "创建健康账户";

  return <main className="auth-page">
    <section className="auth-intro">
      <div className="brand"><span className="brand-mark"><Activity size={17} /></span>Medi-家用医疗健康助手</div>
      <div className="intro-copy">
        <p className="eyebrow">基于MSD 循证医学知识库——</p>
        <h1>让健康信息有据可循</h1>
        <p>管理个人健康信息，理解检验报告，并在每一次健康咨询中查看可核验的医学来源</p>
      </div>
      <div className="intro-points">
        <div className="intro-point">知识内容标注来源</div>
        <div className="intro-point">健康数据按敏感信息保护</div>
        <div className="intro-point">不替代线下诊疗</div>
      </div>
    </section>
    <section className="auth-panel"><form className="auth-form" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
      <p className="eyebrow">Medi-家用医疗健康助手</p>
      <h2>{title}</h2>
      <p className="subcopy">{mode === "login" ? "登录后继续查看你的健康档案和咨询记录" : "注册后请先完善健康画像，以获得更贴合的信息整理，密码至少 8 位，且需同时包含字母和数字"}</p>
      <div className="field">
        <label htmlFor="email">邮箱</label>
        <input id="email" autoComplete="email" placeholder="Email" {...form.register("email")} />
        {form.formState.errors.email && <span className="field-error">{form.formState.errors.email.message}</span>}
      </div>
      <div className="field">
        <label htmlFor="password">密码</label>
        <input id="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} placeholder="Password" {...form.register("password")} />
        {form.formState.errors.password && <span className="field-error">{form.formState.errors.password.message}</span>}
      </div>
      {mutation.isError && <div className="notice urgent">{mutation.error.message}</div>}
      <button className="primary-button" style={{ width: "100%", marginTop: 8 }} disabled={mutation.isPending}>{mutation.isPending ? "正在处理…" : mode === "login" ? "登录" : "创建账户"}<ArrowRight size={17} /></button>
      <p className="auth-footer">{mode === "login" ? "还没有账户？" : "已经有账户？"} <Link href={mode === "login" ? "/register" : "/login"}>{mode === "login" ? "注册" : "登录"}</Link></p>
    </form></section>
  </main>;
}
