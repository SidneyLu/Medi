"use client";

import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Check, ShieldCheck, Sparkles } from "lucide-react";
import { api } from "@/lib/api/client";
import type { Profile } from "@/lib/api/types";

const optionalNumber = (min: number, max: number) => z.preprocess(
  (value) => value === "" || value === null ? undefined : value,
  z.coerce.number().min(min).max(max).optional(),
);

const schema = z.object({
  nickname: z.string().min(1, "请填写称呼"),
  birth_date: z.string().min(1, "请选择出生日期"),
  sex_at_birth: z.enum(["female", "male", "other", "unknown"]),
  pregnancy_status: z.enum(["not_applicable", "pregnant", "postpartum", "unknown"]),
  height_cm: optionalNumber(30, 250),
  weight_kg: optionalNumber(1, 500),
  smoking_status: z.enum(["never", "former", "current", "unknown"]),
  alcohol_use: z.enum(["none", "occasional", "frequent", "unknown"]),
  exercise_level: z.enum(["low", "moderate", "high", "unknown"]),
  sleep_quality: z.enum(["good", "fair", "poor", "unknown"]),
  diet_pattern: z.enum(["balanced", "high_salt", "high_sugar", "high_fat", "irregular", "unknown"]),
  chronic_conditions: z.string(),
  allergies: z.string(),
  current_medications: z.string(),
  family_history: z.string(),
  recent_symptoms: z.string(),
});

type FormInput = z.input<typeof schema>;
type FormValues = z.output<typeof schema>;

const split = (value: string) => value.split(/[,，;；、\n]/).map((item) => item.trim()).filter(Boolean);
const join = (value: string[] | undefined) => (value ?? []).join("，");

const DEFAULT_VALUES: FormInput = {
  nickname: "",
  birth_date: "",
  sex_at_birth: "unknown",
  pregnancy_status: "not_applicable",
  height_cm: undefined,
  weight_kg: undefined,
  smoking_status: "unknown",
  alcohol_use: "unknown",
  exercise_level: "unknown",
  sleep_quality: "unknown",
  diet_pattern: "unknown",
  chronic_conditions: "",
  allergies: "",
  current_medications: "",
  family_history: "",
  recent_symptoms: "",
};

export default function ProfilePage() {
  const queryClient = useQueryClient();
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.getProfile });
  const form = useForm<FormInput, undefined, FormValues>({ resolver: zodResolver(schema), defaultValues: DEFAULT_VALUES });

  useEffect(() => {
    const data = profile.data?.profile;
    if (!data) return;
    form.reset({
      ...data,
      height_cm: data.height_cm,
      weight_kg: data.weight_kg,
      chronic_conditions: join(data.chronic_conditions),
      allergies: join(data.allergies),
      current_medications: join(data.current_medications),
      family_history: join(data.family_history),
      recent_symptoms: join(data.recent_symptoms),
    });
  }, [form, profile.data]);

  const save = useMutation({
    mutationFn: (values: FormValues) => api.saveProfile({
      ...values,
      chronic_conditions: split(values.chronic_conditions),
      allergies: split(values.allergies),
      current_medications: split(values.current_medications),
      family_history: split(values.family_history),
      recent_symptoms: split(values.recent_symptoms),
    } as Profile),
    onSuccess: (data) => queryClient.setQueryData(["profile"], data),
  });

  return <div className="page">
    <div className="page-heading">
      <div>
        <p className="eyebrow">个人健康信息</p>
        <h1>我的健康画像</h1>
        <p>画像会被后端转成状态标签和关键词，在你开启“使用健康画像”时提供给 AI 作为上下文。</p>
      </div>
    </div>

    <div className="grid two">
      <form className="panel panel-pad" onSubmit={form.handleSubmit((values) => save.mutate(values))}>
        <div className="grid" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 14 }}>
          <div className="field"><label>称呼</label><input {...form.register("nickname")} />{form.formState.errors.nickname && <span className="field-error">{form.formState.errors.nickname.message}</span>}</div>
          <div className="field"><label>出生日期</label><input type="date" {...form.register("birth_date")} />{form.formState.errors.birth_date && <span className="field-error">{form.formState.errors.birth_date.message}</span>}</div>
          <div className="field"><label>出生性别</label><select {...form.register("sex_at_birth")}><option value="female">女性</option><option value="male">男性</option><option value="other">其他</option><option value="unknown">未说明</option></select></div>
          <div className="field"><label>妊娠状态</label><select {...form.register("pregnancy_status")}><option value="not_applicable">不适用</option><option value="pregnant">妊娠中</option><option value="postpartum">产后</option><option value="unknown">未说明</option></select></div>
          <div className="field"><label>身高 cm</label><input type="number" {...form.register("height_cm")} /></div>
          <div className="field"><label>体重 kg</label><input type="number" step="0.1" {...form.register("weight_kg")} /></div>
          <div className="field"><label>吸烟状态</label><select {...form.register("smoking_status")}><option value="unknown">未说明</option><option value="never">从不吸烟</option><option value="former">既往吸烟</option><option value="current">当前吸烟</option></select></div>
          <div className="field"><label>饮酒状态</label><select {...form.register("alcohol_use")}><option value="unknown">未说明</option><option value="none">不饮酒</option><option value="occasional">偶尔饮酒</option><option value="frequent">经常饮酒</option></select></div>
          <div className="field"><label>运动水平</label><select {...form.register("exercise_level")}><option value="unknown">未说明</option><option value="low">较少运动</option><option value="moderate">规律运动</option><option value="high">高频运动</option></select></div>
          <div className="field"><label>睡眠质量</label><select {...form.register("sleep_quality")}><option value="unknown">未说明</option><option value="good">良好</option><option value="fair">一般</option><option value="poor">较差</option></select></div>
          <div className="field" style={{ gridColumn: "1 / -1" }}><label>饮食模式</label><select {...form.register("diet_pattern")}><option value="unknown">未说明</option><option value="balanced">相对均衡</option><option value="high_salt">偏高盐</option><option value="high_sugar">偏高糖</option><option value="high_fat">偏高脂</option><option value="irregular">不规律</option></select></div>
        </div>

        <div className="field"><label>已知慢性病或长期健康情况</label><textarea placeholder="例如：高血压，过敏性鼻炎。用逗号分隔。" {...form.register("chronic_conditions")} /></div>
        <div className="field"><label>过敏史</label><textarea placeholder="例如：青霉素，花粉。用逗号分隔。" {...form.register("allergies")} /></div>
        <div className="field"><label>当前常用药</label><textarea placeholder="例如：氯雷他定，二甲双胍。用逗号分隔。" {...form.register("current_medications")} /></div>
        <div className="field"><label>家族史</label><textarea placeholder="例如：糖尿病，高血压，冠心病。用逗号分隔。" {...form.register("family_history")} /></div>
        <div className="field"><label>近期症状</label><textarea placeholder="例如：头晕，乏力，咳嗽。用逗号分隔。" {...form.register("recent_symptoms")} /></div>

        {save.isSuccess && <div className="notice"><Check size={18} /><span>已保存。后端已重新生成画像标签和关键词。</span></div>}
        <button className="primary-button" type="submit" disabled={save.isPending}>{save.isPending ? "正在保存…" : "保存健康画像"}</button>
      </form>

      <aside className="grid" style={{ alignContent: "start" }}>
        <section className="panel panel-pad">
          <ShieldCheck color="#087d77" size={23} />
          <h2 style={{ fontSize: 18, margin: "11px 0 8px" }}>数据如何参与 AI</h2>
          <p className="subcopy" style={{ margin: 0 }}>后端会先把结构化画像转换为标签，再通过关键词算法提取高优先级健康关键词；AI 只接收这些摘要上下文，不需要直接读取完整表单。</p>
        </section>
        <section className="panel panel-pad">
          <h2 style={{ fontSize: 17, marginTop: 0 }}>当前标签</h2>
          <div className="tag-row">{profile.data?.tags.length ? profile.data.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>) : <span className="tag neutral">保存后生成</span>}</div>
        </section>
        <section className="panel panel-pad">
          <h2 style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 17, marginTop: 0 }}><Sparkles size={17} />画像关键词</h2>
          <div className="tag-row">{profile.data?.keywords.length ? profile.data.keywords.map((item) => <span className="tag" title={`${item.category} · ${item.source} · ${item.score}`} key={`${item.category}-${item.keyword}`}>{item.keyword}</span>) : <span className="tag neutral">保存后提取</span>}</div>
        </section>
      </aside>
    </div>
  </div>;
}
