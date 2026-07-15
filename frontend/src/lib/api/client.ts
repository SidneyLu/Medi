import type { ApiEnvelope, ChatMessage, Conversation, ConversationDetail, Paginated, Profile, ProfileResponse, Report, ReportItem, User } from "./types";
import { ApiError } from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const API = `${BASE_URL}/api/v1`;

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${API}${path}`, { ...init, headers, credentials: "include" });
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

export const api = {
  register: (email: string, password: string) => request<User>("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }),
  login: (email: string, password: string) => request<User>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request<null>("/auth/logout", { method: "POST" }),
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
