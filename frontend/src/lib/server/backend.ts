/**
 * Server-side FastAPI helpers used by Next.js /api/chat.
 */

export type KnowledgeChunk = {
  chunk_id: string;
  article_title: string;
  section_title: string;
  source_url: string;
  category: string;
  content: string;
  score?: number;
  tags?: string[];
};

export type Citation = {
  chunk_id: string;
  article_title: string;
  section_title: string;
  source_url: string;
};

export type ChatHistoryTurn = { role: "user" | "assistant"; content: string };

export type ChatPrepareData = {
  question: string;
  retrieval_query: string;
  chunks: KnowledgeChunk[];
  profile_context: string;
  profile_tags: string[];
  profile_keywords: string[];
  history: ChatHistoryTurn[];
  risk_level: "low" | "medium" | "high" | "unknown";
  evidence_available: boolean;
  /** Backend schema field for fixed refusal / emergency text */
  refusal_content?: string | null;
  /** Alternate name used by some backend revisions / plan docs */
  fixed_content?: string | null;
  suggestions: string[] | null;
  profile_tags_used: string[] | null;
};

export function fixedOrRefusal(prepare: ChatPrepareData): string | null {
  return prepare.refusal_content ?? prepare.fixed_content ?? null;
}

export type ChatPersistBody = {
  question: string;
  content: string;
  risk_level?: string | null;
  suggestions?: string[] | null;
  evidence_available?: boolean | null;
  profile_tags_used?: string[] | null;
  citations?: Citation[] | null;
};

export type ChatMessage = {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type MsdSearchItem = { title: string; url: string; snippet?: string };
export type MsdPageData = { title: string; url: string; summary_or_sections?: string; summary?: string };

type ApiEnvelope<T> = { code: number; message: string; data: T };

function apiBaseUrl(): string {
  return (
    process.env.API_BASE_URL?.replace(/\/$/, "") ||
    process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
    "http://127.0.0.1:8000"
  );
}

export function extractBearerToken(request: Request): string | null {
  const header = request.headers.get("authorization") || request.headers.get("Authorization");
  if (header) {
    const match = header.match(/^Bearer\s+(.+)$/i);
    if (match?.[1]?.trim()) return match[1].trim();
  }
  const cookie = request.headers.get("cookie") ?? "";
  const match = cookie.match(/(?:^|;\s*)medi_access_token=([^;]*)/);
  if (!match?.[1]) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

export async function getServerAccessToken(request: Request): Promise<string | null> {
  return extractBearerToken(request);
}

async function fastapiJson<T>(
  path: string,
  options: {
    method?: string;
    token?: string | null;
    body?: unknown;
    searchParams?: Record<string, string | number | undefined>;
  } = {},
): Promise<T> {
  const url = new URL(`${apiBaseUrl()}/api/v1${path}`);
  if (options.searchParams) {
    for (const [key, value] of Object.entries(options.searchParams)) {
      if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
    }
  }

  const headers = new Headers();
  headers.set("Accept", "application/json");
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  if (options.token) headers.set("Authorization", `Bearer ${options.token}`);

  const response = await fetch(url, {
    method: options.method ?? (options.body !== undefined ? "POST" : "GET"),
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    cache: "no-store",
  });

  let payload: ApiEnvelope<T>;
  try {
    payload = (await response.json()) as ApiEnvelope<T>;
  } catch {
    throw new Error(`FastAPI returned non-JSON (HTTP ${response.status})`);
  }
  if (!response.ok || payload.code !== 0) {
    throw new Error(payload.message || `FastAPI error (HTTP ${response.status})`);
  }
  return payload.data;
}

export async function prepareChat(
  token: string,
  conversationId: string,
  question: string,
  useProfile: boolean,
  useMemory: boolean,
): Promise<ChatPrepareData> {
  return fastapiJson<ChatPrepareData>(`/chat/conversations/${conversationId}/messages/prepare`, {
    token,
    method: "POST",
    body: { question, use_profile: useProfile, use_memory: useMemory },
  });
}

export async function persistChat(
  token: string,
  conversationId: string,
  body: ChatPersistBody,
): Promise<ChatMessage> {
  return fastapiJson<ChatMessage>(`/chat/conversations/${conversationId}/messages/persist`, {
    token,
    method: "POST",
    body,
  });
}

export async function msdSearch(
  token: string,
  q: string,
  limit = 3,
): Promise<{ query: string; items: MsdSearchItem[] }> {
  return fastapiJson("/knowledge/msd/search", {
    token,
    searchParams: { q, limit },
  });
}

export async function msdPage(token: string, url: string): Promise<MsdPageData> {
  return fastapiJson("/knowledge/msd/page", {
    token,
    searchParams: { url },
  });
}

export { fastapiJson };
