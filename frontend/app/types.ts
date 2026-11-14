export interface MemoryEntry {
  id: string;
  statement: string;
  slot: string;
  lang: string;
  source: string;
  sensitivity: string;
  confidence: number;
  salience: number;
  category_id?: string;
  category_slug?: string;
  category_label_en?: string;
  subcategory_id: string | null;
  subcategory_slug: string;
  subcategory_label?: string;
  subcategory_label_en: string;
  subcategory_label_sw: string;
  layer?: number;
  surface: string;
  product_area: string;
  conversation_id: string;
  created_by: string;
  valid_from: string | null;
  recorded_at: string | null;
  last_updated_display?: string;
  last_updated_short?: string;
}

export interface SubcategoryItem {
  id: string;
  slug: string;
  label_en: string;
  label_sw: string;
  parent_id?: string;
  parent_slug?: string;
  parent_label_en?: string;
  layer?: number;
  summary?: string;
  last_updated?: string;
  last_updated_short?: string;
  memory_count?: number;
  memories?: MemoryEntry[];
}

export interface CategoryCardData {
  id: string;
  slug: string;
  label_en: string;
  label_sw: string;
  section?: "you" | "topics";
  layer?: number;
  description?: string;
  summary: string;
  last_updated: string;
  last_updated_short?: string;
  sensitivity?: string;
  status?: string;
  is_protected?: boolean;
  is_life_area?: boolean;
  created_by?: string;
  frozen_until: string | null;
  subcategories: SubcategoryItem[];
  memories: MemoryEntry[];
  memory_count: number;
}

export interface MemorySectionGroup {
  id: "you" | "topics" | string;
  slug: string;
  label_en: string;
  label_sw: string;
  layer: number;
  description: string;
  categories: CategoryCardData[];
}

export interface PendingConsentItem {
  consent_id: string;
  memory_id: string;
  statement: string;
  prompt_text: string;
  slot: string;
  category_slug: string;
  category_label: string;
  subcategory_label: string;
  channel: string;
  asked_at: string;
  expires_at: string;
}

export interface NotificationItem {
  id: string;
  kind: string;
  title: string;
  body: string;
  diff_before: string;
  diff_after: string;
  category_slug: string;
  origin_surface: string;
  grouped_count: number;
  memory_id: string | null;
  changeset_id: string | null;
  changeset_status: string | null;
  action: string;
  seen_at: string | null;
  created_at: string;
}

export interface SupersededMemoryItem {
  id: string;
  statement: string;
  slot: string;
  valid_from: string | null;
  valid_to: string | null;
  retired_at: string | null;
  superseded_by_id: string | null;
}

export interface CategoricalState {
  teacher: {
    teacher_id: string;
    display_name: string;
    country: string;
    cohort_key: string;
    curriculum: string;
    preferred_lang: string;
    last_active_at: string | null;
    last_dreamed_at: string | null;
  };
  settings: {
    enabled: boolean;
    share_aggregate: boolean;
    sensitive_mode: "always_ask" | "never_remember";
    banner_mode: "realtime" | "next_visit_summary";
  };
  core_profile: {
    summary: string;
    version: number;
    built_from_count: number;
  };
  memory_sections?: MemorySectionGroup[];
  core_categories: CategoryCardData[];
  life_areas: CategoryCardData[];
  pending_consents: PendingConsentItem[];
  notifications: NotificationItem[];
  unread_notification_count: number;
  superseded_history: SupersededMemoryItem[];
  tombstone_count: number;
  llm_status?: {
    chat_model: string;
    decision_model?: string;
    extraction_model: string;
    api_key_configured: boolean;
    anthropic_key_configured?: boolean;
    gemini_key_configured?: boolean;
    db_engine: string;
  };
}

export interface ChatTurnMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  chatModel?: string;
  extractionModel?: string;
  retrievedMemories?: Array<{
    id: string;
    statement: string;
    category_label: string;
    subcategory_label: string;
    rrf_score?: number;
  }>;
  extractedCandidates?: Array<{
    statement: string;
    category: string;
    subcategory: string;
    sensitivity: string;
    status?: string;
  }>;
}
