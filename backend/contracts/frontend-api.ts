export type ApiEnvelope<T> = {
  code: number;
  message: string;
  data: T;
  request_id: string;
  error?: { type: "not_found" | "validation_error" | "request_failed" };
};

export type User = {
  user_id: string;
  email: string;
  nickname: string;
};

export type Profile = {
  nickname: string;
  birth_date: string;
  sex_at_birth: "female" | "male" | "other" | "unknown";
  height_cm?: number;
  weight_kg?: number;
  pregnancy_status: "not_applicable" | "pregnant" | "postpartum" | "unknown";
  chronic_conditions: string[];
  allergies: string[];
  current_medications: string[];
};

export type ProfileResponse = {
  profile: Profile | null;
  tags: string[];
};

export type Citation = {
  chunk_id: string;
  article_title: string;
  section_title: string;
  source_url: string;
};

export type RiskLevel = "low" | "medium" | "high" | "unknown";

export type Conversation = {
  conversation_id: string;
  title: string;
  updated_at: string;
  preview: string;
};

export type ChatMessage = {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  risk_level?: RiskLevel;
  suggestions?: string[];
  profile_tags_used?: string[];
  citations?: Citation[];
  evidence_available?: boolean;
};

export type ConversationDetail = Conversation & {
  messages: ChatMessage[];
};

export type ChatQueryRequest = {
  question: string;
  use_profile?: boolean;
  use_memory?: boolean;
};

export type ChatHistoryTurn = {
  role: "user" | "assistant";
  content: string;
};

export type KnowledgeChunk = {
  chunk_id: string;
  article_title: string;
  section_title: string;
  source_url: string;
  category: string;
  content: string;
  score: number;
  tags: string[];
  version_label?: string | null;
  revised_at?: string | null;
};

/** POST /api/v1/chat/conversations/{id}/messages/prepare */
export type ChatPrepareData = {
  question: string;
  retrieval_query: string;
  chunks: KnowledgeChunk[];
  profile_context: string;
  profile_tags: string[];
  profile_keywords: string[];
  history: ChatHistoryTurn[];
  risk_level: RiskLevel;
  evidence_available: boolean;
  refusal_content?: string | null;
  suggestions?: string[] | null;
  profile_tags_used?: string[] | null;
};

/** POST /api/v1/chat/conversations/{id}/messages/persist */
export type ChatPersistRequest = {
  question: string;
  content: string;
  risk_level?: RiskLevel | null;
  suggestions?: string[] | null;
  evidence_available?: boolean | null;
  profile_tags_used?: string[] | null;
  citations?: Citation[] | null;
};

export type MsdSearchHit = {
  title: string;
  url: string;
  snippet: string;
};

/** GET /api/v1/knowledge/msd/search?q=&limit= */
export type MsdSearchData = {
  query: string;
  items: MsdSearchHit[];
};

/** GET /api/v1/knowledge/msd/page?url= */
export type MsdPageData = {
  title: string;
  url: string;
  summary: string;
};

export type ReportStatus =
  | "uploaded"
  | "ocr_processing"
  | "needs_confirmation"
  | "interpreting"
  | "completed"
  | "failed";

export type ReportItem = {
  item_id: string;
  name: string;
  value: number | null;
  unit: string;
  reference_low: number | null;
  reference_high: number | null;
  status: "low" | "normal" | "high" | "unknown";
  explanation?: string;
  suggestions?: string[];
  citations?: Citation[];
};

export type Report = {
  report_id: string;
  file_name: string;
  report_type: "physical_exam" | "blood_test" | "other";
  status: ReportStatus;
  created_at: string;
  summary?: string;
  profile_tags_used: string[];
  items: ReportItem[];
  error_message?: string;
};

export type Paginated<T> = {
  items: T[];
  next_cursor: string | null;
};
