"use client";

import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Check, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api/client";
import type { Profile } from "@/lib/api/types";

const schema = z.object({
  nickname: z.string().min(1, "请填写称呼"),
  birth_date: z
    .string()
    .min(1, "请选择出生日期")
    .refine((value) => value >= "1900-01-01" && value <= "2026-12-31", "出生年份须在 1900–2026 之间"),
  sex_at_birth: z.enum(["female", "male", "other", "unknown"]),
  height_cm: z.coerce.number().min(30).max(250).optional(),
  weight_kg: z.coerce.number().min(1).max(500).optional(),
  pregnancy_status: z.enum(["not_applicable", "pregnant", "postpartum", "unknown"]),
  chronic_conditions: z.string(),
  allergies: z.string(),
  current_medications: z.string(),
});
type FormInput = z.input<typeof schema>;
const split = (value: string) => value.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean);

export default function ProfilePage() {
  const queryClient = useQueryClient(); const profile = useQuery({ queryKey: ["profile"], queryFn: api.getProfile });
  const form = useForm<FormInput, unknown, FormValues>({ resolver: zodResolver(schema), defaultValues: { nickname: "", birth_date: "", sex_at_birth: "unknown", pregnancy_status: "not_applicable", chronic_conditions: "", allergies: "", current_medications: "" } });
  useEffect(() => { const data = profile.data?.profile; if (data) form.reset({ ...data, height_cm: data.height_cm, weight_kg: data.weight_kg, chronic_conditions: data.chronic_conditions.join("，"), allergies: data.allergies.join("，"), current_medications: data.current_medications.join("，") }); }, [form, profile.data]);
  const save = useMutation({ mutationFn: (values: FormValues) => api.saveProfile({ ...values, chronic_conditions: split(values.chronic_conditions), allergies: split(values.allergies), current_medications: split(values.current_medications) } as Profile), onSuccess: (data) => { queryClient.setQueryData(["profile"], data); } });
  return <div className="page"><div className="page-heading"><div><p className="eyebrow">个人健康信息</p><h1>我的健康画像</h1><p>此信息仅在你开启“使用健康画像”时参与问答整理</p></div></div><div className="grid two"><form className="panel panel-pad" onSubmit={form.handleSubmit((values) => save.mutate(values))}><div className="grid" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 14 }}><div className="field"><label>称呼</label><input {...form.register("nickname")} />{form.formState.errors.nickname && <span className="field-error">{form.formState.errors.nickname.message}</span>}</div><div className="field"><label>出生日期</label><input type="date" min="1900-01-01" max="2026-12-31" {...form.register("birth_date")} />{form.formState.errors.birth_date && <span className="field-error">{form.formState.errors.birth_date.message}</span>}</div><div className="field"><label>出生性别</label><select {...form.register("sex_at_birth")}><option value="female">女性</option><option value="male">男性</option><option value="other">其他</option><option value="unknown">未说明</option></select></div><div className="field"><label>妊娠状态</label><select {...form.register("pregnancy_status")}><option value="not_applicable">不适用</option><option value="pregnant">妊娠中</option><option value="postpartum">产后</option><option value="unknown">未说明</option></select></div><div className="field"><label>身高（厘米，可选）</label><input type="number" {...form.register("height_cm")} /></div><div className="field"><label>体重（千克，可选）</label><input type="number" step="0.1" {...form.register("weight_kg")} /></div></div><div className="field"><label>已知慢性病或长期健康情况</label><textarea placeholder="例如：高血压，过敏性鼻炎（用逗号分隔）" {...form.register("chronic_conditions")} /></div><div className="field"><label>过敏史</label><textarea placeholder="例如：青霉素（用逗号分隔，不确定请留空）" {...form.register("allergies")} /></div><div className="field"><label>当前常用药</label><textarea placeholder="例如：氯雷他定（用逗号分隔，不确定请留空）" {...form.register("current_medications")} /></div>{save.isSuccess && <div className="notice"><Check size={18} /><span>已保存。标签由后端规则生成。</span></div>}<button className="primary-button" type="submit" disabled={save.isPending}>{save.isPending ? "正在保存…" : "保存健康画像"}</button></form><aside className="grid" style={{ alignContent: "start" }}><section className="panel panel-pad"><ShieldCheck color="#087d77" size={23} /><h2 style={{ fontSize: 18, margin: "11px 0 8px" }}>你的数据如何被使用</h2><p className="subcopy" style={{ margin: 0 }}>健康信息属于敏感个人信息。系统仅在你选择使用健康画像时，将相应标签用于整理问答上下文。</p></section><section className="panel panel-pad"><h2 style={{ fontSize: 17, marginTop: 0 }}>当前标签</h2><div className="tag-row">{profile.data?.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>) ?? <span className="tag neutral">保存后生成</span>}</div></section></aside></div></div>;
}
