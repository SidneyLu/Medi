import {
  createUIMessageStream,
  createUIMessageStreamResponse,
  streamText,
  type UIMessage,
} from "ai";
import {
  fixedOrRefusal,
  getServerAccessToken,
  persistChat,
  prepareChat,
} from "@/lib/server/backend";
import {
  buildRagSystemPrompt,
  buildRagUserPrompt,
  citationsFromChunks,
  createQwenProvider,
  enrichAnswerWithMsdLinks,
  hasQwenKey,
  qwenModelId,
} from "@/lib/server/chat-ai";

export const runtime = "nodejs";
export const maxDuration = 60;

function lastUserText(messages: UIMessage[]): string {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== "user") continue;
    const text = (message.parts ?? [])
      .filter((part): part is { type: "text"; text: string } => part.type === "text")
      .map((part) => part.text)
      .join("")
      .trim();
    if (text) return text;
  }
  return "";
}

function localFallbackAnswer(question: string, chunkTitles: string[]) {
  const titleHint = chunkTitles.length ? `已命中本地资料：${chunkTitles.join("、")}。` : "";
  return [
    "【本地联调自检】未配置 DASHSCOPE_API_KEY，以下为非模型回答。",
    titleHint,
    `本轮问题：${question}`,
    "请在 frontend/.env.local 配置 DASHSCOPE_API_KEY 与 QWEN_MODEL=qwen3.5-flash 后重试。",
  ]
    .filter(Boolean)
    .join("\n");
}

export async function POST(request: Request) {
  let body: {
    messages?: UIMessage[];
    conversationId?: string;
    useProfile?: boolean;
    useMemory?: boolean;
  };
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const conversationId = body.conversationId?.trim();
  const messages = body.messages ?? [];
  const useProfile = body.useProfile !== false;
  const useMemory = body.useMemory !== false;
  const question = lastUserText(messages);

  if (!conversationId) {
    return Response.json({ error: "conversationId is required" }, { status: 400 });
  }
  if (question.length < 2) {
    return Response.json({ error: "question is required" }, { status: 400 });
  }

  const token = await getServerAccessToken(request);
  if (!token) {
    return Response.json({ error: "Not authenticated" }, { status: 401 });
  }

  let prepared;
  try {
    prepared = await prepareChat(token, conversationId, question, useProfile, useMemory);
  } catch (error) {
    const message = error instanceof Error ? error.message : "prepare failed";
    return Response.json({ error: message }, { status: 502 });
  }

  const citations = citationsFromChunks(prepared.chunks);
  const refusalText = fixedOrRefusal(prepared);

  const stream = createUIMessageStream({
    execute: async ({ writer }) => {
      let finalContent = "";
      let riskLevel = prepared.risk_level;
      let suggestions = prepared.suggestions ?? [];
      let evidenceAvailable = prepared.evidence_available;

      if (refusalText) {
        finalContent = refusalText;
        writer.write({ type: "text-start", id: "refusal" });
        writer.write({ type: "text-delta", id: "refusal", delta: finalContent });
        writer.write({ type: "text-end", id: "refusal" });
      } else if (!hasQwenKey()) {
        finalContent = localFallbackAnswer(
          question,
          prepared.chunks.map((chunk) => chunk.article_title),
        );
        writer.write({ type: "text-start", id: "fallback" });
        writer.write({ type: "text-delta", id: "fallback", delta: finalContent });
        writer.write({ type: "text-end", id: "fallback" });
        evidenceAvailable = true;
        riskLevel = "low";
        suggestions = ["配置 DASHSCOPE_API_KEY 后即可验证完整流式回答。"];
      } else {
        const openai = createQwenProvider();
        const result = streamText({
          model: openai.chat(qwenModelId()),
          temperature: 0.2,
          maxOutputTokens: 900,
          system: buildRagSystemPrompt(),
          prompt: buildRagUserPrompt({
            question,
            history: prepared.history,
            profileContext: prepared.profile_context,
            profileTags: prepared.profile_tags,
            profileKeywords: prepared.profile_keywords,
            chunks: prepared.chunks,
          }),
        });
        writer.merge(result.toUIMessageStream({ sendFinish: false }));
        finalContent = (await result.text).trim();
        evidenceAvailable = true;
        if (!riskLevel || riskLevel === "unknown") riskLevel = "low";
      }

      // Citation enrichment after RAG draft — patch only, never blocks answer.
      if (finalContent && prepared.chunks.length > 0 && !refusalText && riskLevel !== "high") {
        try {
          const enriched = await enrichAnswerWithMsdLinks({
            token,
            draft: finalContent,
            chunks: prepared.chunks,
          });
          if (enriched.content && enriched.content !== finalContent) {
            finalContent = enriched.content;
            writer.write({
              type: "data-citation-patch",
              data: { content: finalContent },
              transient: true,
            });
          }
        } catch {
          // keep draft
        }
      }

      try {
        await persistChat(token, conversationId, {
          question,
          content: finalContent,
          risk_level: riskLevel,
          suggestions,
          evidence_available: evidenceAvailable,
          profile_tags_used: prepared.profile_tags_used,
          citations: refusalText && riskLevel !== "high" ? [] : citations,
        });
      } catch {
        // Streaming already delivered.
      }

      writer.write({
        type: "message-metadata",
        messageMetadata: {
          riskLevel,
          suggestions,
          evidenceAvailable,
          profileTagsUsed: prepared.profile_tags_used ?? undefined,
          enrichedContent: finalContent,
        },
      });
    },
  });

  return createUIMessageStreamResponse({ stream });
}
