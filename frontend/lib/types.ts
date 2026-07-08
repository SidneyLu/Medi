export type ProductListItem = {
  sku_id: number;
  model_name: string;
  normalized_model_name: string;
  brand_name: string;
  category: string;
  launch_date?: string | null;
  current_price?: number | null;
  chipset?: string | null;
};

export type Citation = {
  title: string;
  url: string;
  source_type: string;
  crawled_at?: string | null;
  snippet: string;
};

export type ProductDetail = {
  sku_id: number;
  model_name: string;
  normalized_model_name: string;
  brand_name: string;
  series_name?: string | null;
  category: string;
  competitor_group?: string | null;
  launch_date?: string | null;
  official_url?: string | null;
  current_price?: number | null;
  original_price?: number | null;
  promotion_text?: string | null;
  observed_at?: string | null;
  spec_json: Record<string, string | number | null>;
  selling_points: string[];
  citations: Citation[];
  timeline: Array<{ field: string; old_value?: string | null; new_value?: string | null; observed_at: string }>;
};

export type CompareTable = {
  columns: string[];
  rows: Array<Record<string, string | number | null>>;
};

export type ChatResponse = {
  answer_text: string;
  citations: Citation[];
  compare_table: CompareTable;
  timeline_events: Array<{ field: string; old_value?: string | null; new_value?: string | null; observed_at: string }>;
  related_skus: Array<{ sku_id: number; model_name: string; brand_name: string }>;
  missing_fields: string[];
  generated_at: string;
};
