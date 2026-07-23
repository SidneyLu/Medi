import { createOpenAI } from "@ai-sdk/openai";
import { generateText } from "ai";
import {
  msdPage,
  msdSearch,
  type Citation,
  type KnowledgeChunk,
  type MsdSearchItem,
} from "@/lib/server/backend";

export function createQwenProvider() {
  const apiKey = process.env.DASHSCOPE_API_KEY || process.env.QWEN_API_KEY || "";
  const baseURL = (
    process.env.DASHSCOPE_BASE_URL || "https://dashscope.aliyuncs.com/compatible-mode/v1"
  ).replace(/\/$/, "");
  return createOpenAI({
    apiKey: apiKey || "missing-key",
    baseURL,
    name: "dashscope",
  });
}

export function qwenModelId() {
  return process.env.QWEN_MODEL || "qwen3.5-flash";
}

export function hasQwenKey() {
  return Boolean(process.env.DASHSCOPE_API_KEY || process.env.QWEN_API_KEY);
}

export function buildRagSystemPrompt() {
  return [
    "你是Medi健康科普助手。",
    "只能依据用户问题、会话历史（若提供）、用户健康画像（若提供）和提供的本地MSD知识块回答，",
    "不得使用资料之外的医学事实补全答案，也不得把网页正文当作答题依据。",
    "使用简体中文。不进行确诊，不开具处方，不擅自给出药物剂量，不替代医生诊断。",
    "回答时可在相关句子旁用《资料标题》标注本地资料来源（尚不必写外链）。",
    "资料不足时明确说明当前检索资料不足以支持明确结论。",
    "存在明显危险信号时，提示及时线下就医或急诊。",
    "直接输出 Markdown 正文，不要返回 JSON。",
  ].join("\n");
}

export function buildRagUserPrompt(input: {
  question: string;
  history: { role: string; content: string }[];
  profileContext: string;
  profileTags: string[];
  profileKeywords: string[];
  chunks: KnowledgeChunk[];
}) {
  const historyBlock =
    input.history.length > 0
      ? `近期会话：\n${input.history
          .map((item) => `${item.role === "user" ? "用户" : "助手"}：${item.content}`)
          .join("\n")}\n\n`
      : "";
  const profileParts: string[] = [];
  if (input.profileContext.trim()) profileParts.push(input.profileContext.trim());
  if (input.profileTags.length) profileParts.push(`画像标签：${input.profileTags.join("、")}`);
  if (input.profileKeywords.length) {
    profileParts.push(`画像关键词：${input.profileKeywords.join("、")}`);
  }
  const profileBlock = profileParts.length
    ? `用户健康画像：\n${profileParts.join("\n")}\n\n`
    : "用户健康画像：本次未启用或尚未填写。\n\n";
  const chunksBlock = input.chunks
    .map(
      (chunk, index) =>
        `[资料${index + 1}]\narticle_title: ${chunk.article_title}\nsection_title: ${chunk.section_title}\ncontent: ${chunk.content}`,
    )
    .join("\n\n");
  return `${historyBlock}用户本轮问题：${input.question}\n\n${profileBlock}请仅基于以下本地资料回答：\n\n${chunksBlock}`;
}

function titlesRelated(a: string, b: string) {
  const normalize = (value: string) => value.toLowerCase().replace(/\s+/g, "");
  const left = normalize(a);
  const right = normalize(b);
  if (!left || !right) return false;
  return left.includes(right) || right.includes(left) || left.slice(0, 4) === right.slice(0, 4);
}

export async function enrichAnswerWithMsdLinks(options: {
  token: string;
  draft: string;
  chunks: KnowledgeChunk[];
}): Promise<{ content: string; linkMap: { title: string; url: string }[] }> {
  const { token, draft, chunks } = options;
  const queries = Array.from(
    new Set(
      chunks
        .map((chunk) => chunk.article_title?.trim())
        .filter((title): title is string => Boolean(title))
        .slice(0, 4),
    ),
  );

  const candidates: MsdSearchItem[] = [];
  for (const query of queries) {
    try {
      const result = await msdSearch(token, query, 3);
      candidates.push(...(result.items ?? []));
    } catch {
      // Enrichment must not fail the answer path.
    }
  }

  const verified: { title: string; url: string }[] = [];
  const seen = new Set<string>();
  for (const hit of candidates) {
    if (!hit.url || seen.has(hit.url)) continue;
    const matchedChunk = chunks.find((chunk) => titlesRelated(chunk.article_title, hit.title));
    if (!matchedChunk && !queries.some((query) => titlesRelated(query, hit.title))) continue;
    try {
      const page = await msdPage(token, hit.url);
      if (!page.url || /\/home\/?$/.test(page.url)) continue;
      if (!titlesRelated(hit.title, page.title) && !queries.some((query) => titlesRelated(query, page.title))) {
        continue;
      }
      seen.add(page.url);
      verified.push({ title: matchedChunk?.article_title || hit.title, url: page.url });
    } catch {
      // skip invalid pages
    }
    if (verified.length >= 4) break;
  }

  if (!verified.length) {
    return { content: draft, linkMap: verified };
  }

  if (!hasQwenKey()) {
    let patched = draft;
    for (const link of verified) {
      const escaped = link.title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      patched = patched.replace(new RegExp(`《${escaped}》`, "g"), `[${link.title}](${link.url})`);
    }
    return { content: patched, linkMap: verified };
  }

  try {
    const openai = createQwenProvider();
    const { text } = await generateText({
      model: openai.chat(qwenModelId()),
      temperature: 0,
      maxOutputTokens: 1200,
      system: [
        "你只负责给已有健康科普正文添加或修正行内 Markdown 链接。",
        "严禁改写医学结论、增删事实、调整建议强度。",
        "只能使用提供的 {title,url} 映射；搜不到的标题保留纯文本《标题》或原文，不得编造 URL，不得链接到 /home。",
        "输出完整正文 Markdown，不要解释。",
      ].join("\n"),
      prompt: `原文：\n${draft}\n\n允许的链接映射 JSON：\n${JSON.stringify(verified, null, 2)}\n\n请只插入/校正行内链接后返回全文。`,
    });
    const enriched = (text || "").trim();
    return { content: enriched || draft, linkMap: verified };
  } catch {
    return { content: draft, linkMap: verified };
  }
}

export function citationsFromChunks(chunks: KnowledgeChunk[]): Citation[] {
  return chunks.map((chunk) => ({
    chunk_id: chunk.chunk_id,
    article_title: chunk.article_title,
    section_title: chunk.section_title,
    source_url: chunk.source_url,
  }));
}
