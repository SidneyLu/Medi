export type ApiEnvelope<T> = { code: number; message: string; data: T; request_id: string };
export type Citation = { chunk_id: string; article_title: string; section_title: string; source_url: string };
export type PdfBoundingBox = { page: number; bbox: number[] };
export type CitationDetail = { chunk_id: string; document_id: string; document_title: string; section_title: string; heading_path: string[]; page_start: number; page_end: number; page_count: number; source_excerpt: string; document_version: string; source_bboxes: PdfBoundingBox[]; preview_url: string };
export type RiskLevel = "low" | "medium" | "high" | "unknown";
export type User = { user_id: string; email: string; nickname: string };
export type AuthSession = User & { access_token: string; token_type: "bearer"; expires_in: number };
export type Profile = { nickname: string; birth_date: string; sex_at_birth: "female" | "male" | "other" | "unknown"; height_cm?: number; weight_kg?: number; pregnancy_status: "not_applicable" | "pregnant" | "postpartum" | "unknown"; chronic_conditions: string[]; allergies: string[]; current_medications: string[] };
export type ProfileResponse = { profile: Profile | null; tags: string[] };
export type Conversation = { conversation_id: string; title: string; updated_at: string; preview: string };
export type ChatMessage = { message_id: string; role: "user" | "assistant"; content: string; created_at: string; risk_level?: RiskLevel; suggestions?: string[]; profile_tags_used?: string[]; citations?: Citation[]; evidence_available?: boolean };
export type ConversationDetail = Conversation & { messages: ChatMessage[] };
export type ReportStatus = "uploaded" | "ocr_processing" | "needs_confirmation" | "interpreting" | "completed" | "failed";
export type ReportItem = { item_id: string; name: string; value: number | null; unit: string; reference_low: number | null; reference_high: number | null; status: "low" | "normal" | "high" | "unknown"; explanation?: string; suggestions?: string[]; citations?: Citation[] };
export type Report = { report_id: string; file_name: string; report_type: "physical_exam" | "blood_test" | "other"; status: ReportStatus; created_at: string; summary?: string; profile_tags_used: string[]; items: ReportItem[]; error_message?: string };
export type Paginated<T> = { items: T[]; next_cursor: string | null };
export class ApiError extends Error { constructor(public status: number, public type: string, message: string) { super(message); } }
