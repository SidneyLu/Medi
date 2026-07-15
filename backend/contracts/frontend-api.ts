export type ApiResponse<T> = {
  code: number;
  message: string;
  data: T | null;
};

export type AuthRequest = {
  email: string;
  password: string;
};

export type AuthData = {
  user_id: string;
  email?: string;
  access_token: string;
  token_type: "bearer";
  expires_in?: number;
};

export type ProfilePayload = {
  nickname?: string;
  birth_date?: string;
  sex_at_birth?: "female" | "male" | "intersex" | "unknown";
  height_cm?: number;
  weight_kg?: number;
  pregnancy_status?: "not_applicable" | "not_pregnant" | "pregnant" | "postpartum" | "unknown";
  chronic_conditions?: string[];
  allergies?: string[];
  current_medications?: string[];
};

export type ProfileData = {
  profile: ProfilePayload | null;
  tags: string[];
};

export type Citation = {
  chunk_id?: string;
  article_title: string;
  section_title: string;
  source_url: string;
};

export type ChatQueryRequest = {
  question: string;
  use_profile: boolean;
};

export type ChatQueryData = {
  question: string;
  answer: string;
  risk_level: "low" | "medium" | "high" | "unknown";
  suggestions: string[];
  profile_tags_used: string[];
  citations: Citation[];
};

export type ReportType = "physical_exam" | "blood_test" | "other";

export type ReportItem = {
  item_id: string;
  name: string;
  value?: number | string | null;
  unit?: string | null;
  reference_low?: number | null;
  reference_high?: number | null;
  status: "low" | "normal" | "high" | "unknown";
  explanation: string;
  suggestions: string[];
  citations: Citation[];
};

export type ReportAnalyzeData = {
  report_id: string;
  file_name: string;
  report_type: ReportType;
  status: "processing" | "completed" | "failed";
  summary: string;
  profile_tags_used: string[];
  items: ReportItem[];
};
