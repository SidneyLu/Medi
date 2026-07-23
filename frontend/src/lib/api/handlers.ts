import { http, HttpResponse } from "msw";
import type { ChatMessage, ConversationDetail, Profile, Report, ReportItem } from "./types";

const now = "2026-07-15T08:30:00+08:00";
let profile: Profile = { nickname: "陈安", birth_date: "1991-06-12", sex_at_birth: "female", height_cm: 165, weight_kg: 54, pregnancy_status: "not_applicable", chronic_conditions: ["过敏性鼻炎"], allergies: ["青霉素"], current_medications: ["氯雷他定"], family_history: [], recent_symptoms: [], smoking_status: "unknown", alcohol_use: "unknown", exercise_level: "unknown", sleep_quality: "unknown", diet_pattern: "unknown" };
const demoKeywords = [{ keyword: "成人", category: "derived", score: 1, source: "profile_tags" }, { keyword: "青霉素", category: "allergy", score: 1.6, source: "allergies" }, { keyword: "过敏性鼻炎", category: "condition", score: 2.2, source: "chronic_conditions" }];
let reports: Report[] = [{ report_id: "report-demo", file_name: "年度体检报告.jpg", report_type: "physical_exam", status: "completed", created_at: now, profile_tags_used: ["age_adult", "sex_female", "allergy_penicillin"], summary: "报告中血红蛋白低于该报告所列参考范围。单项结果不能用于诊断，建议结合月经、饮食、既往检查和医生意见综合判断。", items: [{ item_id: "hb", name: "血红蛋白", value: 108, unit: "g/L", reference_low: 115, reference_high: 150, status: "low", explanation: "血红蛋白参与氧气运输。不同实验室、年龄和生理状态的参考范围可能不同；报告中的偏低结果需由医疗专业人员结合完整情况判断。", suggestions: ["保留原始报告并记录近期症状", "就医时告知既往检查与用药情况"], citations: [{ chunk_id: "msd-anemia-1", article_title: "贫血概述", section_title: "诊断", source_url: "https://www.msdmanuals.cn/home/blood-disorders/anemia/overview-of-anemia" }] }, { item_id: "glucose", name: "葡萄糖", value: 4.9, unit: "mmol/L", reference_low: 3.9, reference_high: 6.1, status: "normal", explanation: "该数值位于报告列出的参考范围内，仍应结合采样状态和医疗专业人员判断。", citations: [{ chunk_id: "msd-glucose-1", article_title: "糖尿病", section_title: "诊断", source_url: "https://www.msdmanuals.cn/home/hormonal-and-metabolic-disorders/diabetes-mellitus-dm-and-disorders-of-blood-sugar-metabolism/diabetes-mellitus-dm" }] }] }];
let conversations: ConversationDetail[] = [{ conversation_id: "chat-demo", title: "最近经常头晕", preview: "记录症状发生时间和伴随不适…", updated_at: now, messages: [{ message_id: "m1", role: "user", content: "最近经常头晕，可能是什么原因？", created_at: now }, { message_id: "m2", role: "assistant", content: "头晕可能与多种情况有关，单凭这句话无法判断原因。请记录发生时间、持续时长、体位变化、是否伴有视物旋转、胸痛、呼吸困难、晕厥或神经系统异常等信息。\n\n若出现突发剧烈头痛、言语困难、一侧无力、意识改变、胸痛或呼吸困难，请立即寻求急救帮助。", created_at: now, risk_level: "medium", suggestions: ["记录症状持续时长和诱因", "就医时携带既往检查结果"], profile_tags_used: ["age_adult", "sex_female"], evidence_available: true, citations: [{ chunk_id: "msd-dizziness-1", article_title: "头晕和眩晕", section_title: "常见原因", source_url: "https://www.msdmanuals.cn/home/brain-spinal-cord-and-nerve-disorders/symptoms-of-brain-spinal-cord-and-nerve-disorders/dizziness-or-vertigo" }] }] }];

function envelope<T>(data: T, status = 200) { return HttpResponse.json({ code: 0, message: "success", data, request_id: crypto.randomUUID() }, { status }); }
function failure(status: number, message: string, type: string) { return HttpResponse.json({ code: status, message, data: null, request_id: crypto.randomUUID(), error: { type } }, { status }); }
function reportById(id: string) { return reports.find((report) => report.report_id === id); }

export const handlers = [
  http.get("*/api/v1/auth/me", () => envelope({ user_id: "user-demo", email: "chen.an@example.com", nickname: profile.nickname })),
  http.post("*/api/v1/auth/login", async ({ request }) => { const body = await request.json() as { email: string }; return envelope({ user_id: "user-demo", email: body.email, nickname: profile.nickname }); }),
  http.post("*/api/v1/auth/register", async ({ request }) => { const body = await request.json() as { email: string }; return envelope({ user_id: "user-demo", email: body.email, nickname: profile.nickname }, 201); }),
  http.post("*/api/v1/auth/logout", () => envelope(null)),
  http.get("*/api/v1/profile", () => envelope({ profile, tags: ["age_adult", "sex_female", "allergy_penicillin"], keywords: demoKeywords })),
  http.put("*/api/v1/profile", async ({ request }) => { profile = await request.json() as Profile; return envelope({ profile, tags: ["age_adult", `sex_${profile.sex_at_birth}`, ...profile.allergies.map((allergy) => `allergy_${allergy}`)], keywords: demoKeywords }); }),
  http.get("*/api/v1/chat/conversations", () => envelope({ items: conversations.map((conversation) => ({ conversation_id: conversation.conversation_id, title: conversation.title, preview: conversation.preview, updated_at: conversation.updated_at })), next_cursor: null })),
  http.post("*/api/v1/chat/conversations", () => { const id = crypto.randomUUID(); const conversation: ConversationDetail = { conversation_id: id, title: "新的健康咨询", preview: "", updated_at: now, messages: [] }; conversations = [conversation, ...conversations]; return envelope(conversation, 201); }),
  http.get("*/api/v1/chat/conversations/:id", ({ params }) => { const conversation = conversations.find((item) => item.conversation_id === params.id); return conversation ? envelope(conversation) : failure(404, "会话不存在", "not_found"); }),
  http.delete("*/api/v1/chat/conversations/:id", ({ params }) => { conversations = conversations.filter((item) => item.conversation_id !== params.id); return envelope(null); }),
  http.post("*/api/v1/chat/conversations/:id/messages", async ({ params, request }) => { const conversation = conversations.find((item) => item.conversation_id === params.id); if (!conversation) return failure(404, "会话不存在", "not_found"); const body = await request.json() as { question: string; use_profile: boolean }; const userMessage: ChatMessage = { message_id: crypto.randomUUID(), role: "user", content: body.question, created_at: now }; const highRisk = /胸痛|呼吸困难|意识不清|昏迷|大出血/.test(body.question); const answer: ChatMessage = { message_id: crypto.randomUUID(), role: "assistant", content: highRisk ? "你描述的内容可能涉及紧急情况。请不要等待线上回复或自行处理，应立即联系当地急救服务或前往急诊。" : "我只能根据已检索到的默沙东医学知识提供健康科普，不能据此诊断。请关注症状的持续时间、诱因及伴随表现；若症状加重或出现警示信号，请及时线下就医。详见 [头晕和眩晕](https://www.msdmanuals.cn/home/brain-spinal-cord-and-nerve-disorders/symptoms-of-brain-spinal-cord-and-nerve-disorders/dizziness-or-vertigo)。", created_at: now, risk_level: highRisk ? "high" : "low", suggestions: highRisk ? ["立即联系急救服务", "如可行，请让身边的人陪同"] : ["记录症状发生时间和持续时长", "准备既往检查和用药信息以便就医时说明"], profile_tags_used: body.use_profile ? ["age_adult", "sex_female"] : [], evidence_available: true, citations: [{ chunk_id: "msd-dizziness-1", article_title: highRisk ? "何时应寻求医疗帮助" : "头晕和眩晕", section_title: "何时就医", source_url: "https://www.msdmanuals.cn/home/brain-spinal-cord-and-nerve-disorders/symptoms-of-brain-spinal-cord-and-nerve-disorders/dizziness-or-vertigo" }] }; conversation.messages.push(userMessage, answer); conversation.title = body.question.slice(0, 20); conversation.preview = answer.content.slice(0, 32); return envelope(answer); }),
  http.post("*/api/v1/chat/conversations/:id/messages/prepare", async ({ params, request }) => {
    const conversation = conversations.find((item) => item.conversation_id === params.id);
    if (!conversation) return failure(404, "会话不存在", "not_found");
    const body = await request.json() as { question: string; use_profile: boolean; use_memory?: boolean };
    const highRisk = /胸痛|呼吸困难|意识不清|昏迷|大出血/.test(body.question);
    const noEvidence = /编造|无关|火星|量子纠缠/.test(body.question);
    const history = body.use_memory === false
      ? []
      : conversation.messages.slice(-6).map((message) => ({ role: message.role, content: message.content }));
    const chunks = noEvidence || highRisk
      ? []
      : [{
          chunk_id: "msd-dizziness-1",
          article_title: "头晕和眩晕",
          section_title: "常见原因",
          source_url: "https://www.msdmanuals.cn/home/brain-spinal-cord-and-nerve-disorders/symptoms-of-brain-spinal-cord-and-nerve-disorders/dizziness-or-vertigo",
          category: "symptoms",
          content: "头晕可能表现为头昏、失去平衡感或周围环境旋转。体位变化相关头晕常见于直立性低血压等情形；伴随警示症状时需要及时寻求医疗帮助。",
          score: 0.92,
          tags: ["source:msd"],
        }];
    let refusal_content: string | null = null;
    let suggestions: string[] | null = null;
    let risk_level: "high" | "low" | "medium" | "unknown" = "unknown";
    let evidence_available = chunks.length > 0;
    if (highRisk) {
      risk_level = "high";
      refusal_content = "你描述的内容可能涉及紧急情况。请不要等待线上回复或自行处理，应立即联系当地急救服务或前往急诊。";
      suggestions = ["立即联系急救服务", "如可行，请让身边的人陪同"];
      evidence_available = false;
    } else if (noEvidence) {
      refusal_content = "未检索到足够相关的授权 MSD 知识块，因此不会编造医学解释。请补充症状细节或线下咨询合格医生。";
      suggestions = ["补充症状出现时间、持续时长和伴随症状。"];
      evidence_available = false;
    }
    return envelope({
      question: body.question,
      retrieval_query: body.question,
      chunks,
      profile_context: body.use_profile ? "成人女性，青霉素过敏，过敏性鼻炎" : "",
      profile_tags: body.use_profile ? ["age_adult", "sex_female", "allergy_penicillin"] : [],
      profile_keywords: body.use_profile ? demoKeywords.map((item) => item.keyword) : [],
      history,
      risk_level,
      evidence_available,
      refusal_content,
      fixed_content: refusal_content,
      suggestions,
      profile_tags_used: body.use_profile ? ["age_adult", "sex_female"] : [],
    });
  }),
  http.post("*/api/v1/chat/conversations/:id/messages/persist", async ({ params, request }) => {
    const conversation = conversations.find((item) => item.conversation_id === params.id);
    if (!conversation) return failure(404, "会话不存在", "not_found");
    const body = await request.json() as {
      question: string;
      content: string;
      risk_level?: ChatMessage["risk_level"];
      suggestions?: string[];
      evidence_available?: boolean;
      profile_tags_used?: string[];
      citations?: ChatMessage["citations"];
    };
    const userMessage: ChatMessage = { message_id: crypto.randomUUID(), role: "user", content: body.question, created_at: now };
    const answer: ChatMessage = {
      message_id: crypto.randomUUID(),
      role: "assistant",
      content: body.content,
      created_at: now,
      risk_level: body.risk_level,
      suggestions: body.suggestions,
      profile_tags_used: body.profile_tags_used,
      evidence_available: body.evidence_available,
      citations: body.citations,
    };
    conversation.messages.push(userMessage, answer);
    conversation.title = body.question.slice(0, 20);
    conversation.preview = answer.content.slice(0, 32);
    conversation.updated_at = now;
    return envelope(answer);
  }),
  http.get("*/api/v1/knowledge/msd/search", ({ request }) => {
    const url = new URL(request.url);
    const q = url.searchParams.get("q") || "";
    return envelope({
      query: q,
      items: [{
        title: "头晕和眩晕",
        url: "https://www.msdmanuals.cn/home/brain-spinal-cord-and-nerve-disorders/symptoms-of-brain-spinal-cord-and-nerve-disorders/dizziness-or-vertigo",
        snippet: "头晕可能表现为头昏、失去平衡感或周围环境旋转。",
      }],
    });
  }),
  http.get("*/api/v1/knowledge/msd/page", ({ request }) => {
    const url = new URL(request.url);
    const pageUrl = url.searchParams.get("url") || "";
    if (!pageUrl || pageUrl.replace(/\/+$/, "") === "https://www.msdmanuals.cn/home") {
      return failure(400, "URL must be an msdmanuals.cn /home topic path (not bare /home)", "validation_error");
    }
    return envelope({
      title: "头晕和眩晕",
      url: pageUrl,
      summary: "头晕可能表现为头昏、失去平衡感或周围环境旋转。",
      summary_or_sections: "头晕可能表现为头昏、失去平衡感或周围环境旋转。",
    });
  }),
  http.get("*/api/v1/content/citations/:id", ({ params }) => envelope({ chunk_id: String(params.id), document_id: "manual-demo", document_title: "默克家庭医学手册", section_title: "头晕和眩晕", heading_path: ["默克家庭医学手册", "症状", "头晕和眩晕"], page_start: 417, page_end: 418, page_count: 1582, source_excerpt: "头晕可能表现为头昏、失去平衡感或周围环境旋转。持续或伴随警示症状时需要及时寻求医疗帮助。", document_version: "30b2c00c2235", source_bboxes: [{ page: 417, bbox: [12, 28, 88, 51] }], preview_url: "/api/v1/content/documents/manual-demo/pages/417/preview" })),
  http.get("*/api/v1/content/documents/:id/pages/:page/preview", () => new HttpResponse(`<svg xmlns="http://www.w3.org/2000/svg" width="900" height="1260"><rect width="100%" height="100%" fill="#fffdf8"/><text x="80" y="105" font-family="Arial" font-size="25" fill="#142e35">默克家庭医学手册</text><line x1="80" y1="135" x2="820" y2="135" stroke="#9aaeb2"/><text x="80" y="205" font-family="Arial" font-size="32" font-weight="bold" fill="#172d34">头晕和眩晕</text><text x="80" y="270" font-family="Arial" font-size="19" fill="#344e56">头晕可能表现为头昏、失去平衡感，或感到</text><text x="80" y="304" font-family="Arial" font-size="19" fill="#344e56">周围环境旋转。症状持续或伴随警示症状时，</text><text x="80" y="338" font-family="Arial" font-size="19" fill="#344e56">应及时寻求医疗帮助。</text><line x1="80" y1="1110" x2="820" y2="1110" stroke="#d5dedf"/><text x="440" y="1160" font-family="Arial" font-size="16" fill="#667b80">417</text></svg>`, { headers: { "Content-Type": "image/svg+xml" } })),
  http.get("*/api/v1/reports", () => envelope({ items: reports, next_cursor: null })),
  http.post("*/api/v1/reports/analyze", async ({ request }) => { const form = await request.formData(); const file = form.get("file") as File | null; const reportType = form.get("report_type") as Report["report_type"] | null; if (!file) return failure(422, "请上传报告文件", "validation_error"); const report: Report = { report_id: crypto.randomUUID(), file_name: file.name, report_type: reportType ?? "other", status: "needs_confirmation", created_at: now, profile_tags_used: ["age_adult", "sex_female"], items: [{ item_id: crypto.randomUUID(), name: "血红蛋白", value: 108, unit: "g/L", reference_low: 115, reference_high: 150, status: "low" }, { item_id: crypto.randomUUID(), name: "白细胞计数", value: 6.2, unit: "×10⁹/L", reference_low: 3.5, reference_high: 9.5, status: "normal" }] }; reports = [report, ...reports]; return envelope(report, 202); }),
  http.get("*/api/v1/reports/:id", ({ params }) => { const report = reportById(String(params.id)); return report ? envelope(report) : failure(404, "报告不存在", "not_found"); }),
  http.patch("*/api/v1/reports/:id/items", async ({ params, request }) => { const report = reportById(String(params.id)); if (!report) return failure(404, "报告不存在", "not_found"); const body = await request.json() as { items: ReportItem[] }; report.items = body.items; report.status = "needs_confirmation"; return envelope(report); }),
  http.post("*/api/v1/reports/:id/interpret", ({ params }) => { const report = reportById(String(params.id)); if (!report) return failure(404, "报告不存在", "not_found"); report.status = "completed"; report.summary = "OCR 结果中包含超出该报告参考范围的项目。此结果仅供科普参考，不能替代医生结合症状、体检和其他检查进行的判断。"; report.items = report.items.map((item) => ({ ...item, explanation: item.status === "low" ? "该项目低于报告列出的参考范围。参考区间会因实验室、年龄、性别与生理状态而异，应由医疗专业人员结合完整情况判断。" : "该项目位于报告列出的参考范围内。单项数值不能替代完整健康评估。", suggestions: ["保留报告原件", "若有不适或疑问，请咨询医疗专业人员"], citations: [{ chunk_id: "msd-lab-1", article_title: "医学检查概述", section_title: "实验室检查", source_url: "https://www.msdmanuals.cn/home" }] })); return envelope(report); }),
  http.delete("*/api/v1/reports/:id", ({ params }) => { reports = reports.filter((report) => report.report_id !== params.id); return envelope(null); }),
];
