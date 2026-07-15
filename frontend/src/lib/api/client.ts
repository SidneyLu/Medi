import type { ApiEnvelope, AuthSession, ChatMessage, Conversation, ConversationDetail, Paginated, Profile, ProfileResponse, Report, ReportItem, User } from "./types";
import { ApiError } from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const API = `${BASE_URL}/api/v1`;
const TOKEN_KEY = "medi_access_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setAccessToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "network_error", "无法连接后端服务，请确认后端已启动且地址正确。");
  }
  let payload: ApiEnvelope<T> & { error?: { type: string } };
  try {
    payload = await response.json() as ApiEnvelope<T> & { error?: { type: string } };
  } catch {
    throw new ApiError(response.status, "invalid_response", `后端返回异常（HTTP ${response.status}）`);
  }
  if (!response.ok || payload.code !== 0) throw new ApiError(response.status, payload.error?.type ?? "request_failed", payload.message);
  return payload.data;
}

async function authenticate(path: "/auth/login" | "/auth/register", email: string, password: string): Promise<User> {
  const session = await request<AuthSession>(path, { method: "POST", body: JSON.stringify({ email, password }) });
  setAccessToken(session.access_token);
  return { user_id: session.user_id, email: session.email, nickname: session.nickname };
}

export const api = {
  register: (email: string, password: string) => authenticate("/auth/register", email, password),
  login: (email: string, password: string) => authenticate("/auth/login", email, password),
  logout: async () => {
    try {
      await request<null>("/auth/logout", { method: "POST" });
    } finally {
      setAccessToken(null);
    }
    return null;
  },
  getMe: () => request<User>("/auth/me"),
  getProfile: () => request<ProfileResponse>("/profile"),
  saveProfile: (profile: Profile) => request<ProfileResponse>("/profile", { method: "PUT", body: JSON.stringify(profile) }),
  listConversations: () => request<Paginated<Conversation>>("/chat/conversations"),
  createConversation: () => request<ConversationDetail>("/chat/conversations", { method: "POST" }),
  getConversation: (id: string) => request<ConversationDetail>(`/chat/conversations/${id}`),
  sendMessage: (id: string, question: string, use_profile: boolean) => request<ChatMessage>(`/chat/conversations/${id}/messages`, { method: "POST", body: JSON.stringify({ question, use_profile }) }),
  uploadReport: (file: File, reportType: Report["report_type"]) => { const body = new FormData(); body.append("file", file); body.append("report_type", reportType); return request<Report>("/reports/analyze", { method: "POST", body }); },
  listReports: () => request<Paginated<Report>>("/reports"),
  getReport: (id: string) => request<Report>(`/reports/${id}`),
  updateReportItems: (id: string, items: ReportItem[]) => request<Report>(`/reports/${id}/items`, { method: "PATCH", body: JSON.stringify({ items }) }),
  interpretReport: (id: string) => request<Report>(`/reports/${id}/interpret`, { method: "POST" }),
  deleteReport: (id: string) => request<null>(`/reports/${id}`, { method: "DELETE" }),
};
