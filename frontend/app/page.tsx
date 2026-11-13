import React from "react";
import ClientWorkspace from "./components/ClientWorkspace";
import { CategoricalState } from "./types";

export const dynamic = "force-dynamic";

const FALLBACK_INITIAL_STATE: CategoricalState = {
  teacher: {
    teacher_id: "teacher-wambui-ke",
    display_name: "Mwalimu Wambui (Kisumu Primary)",
    country: "KE",
    cohort_key: "kisumu-cohort-1",
    curriculum: "CBC",
    preferred_lang: "en",
    last_active_at: null,
    last_dreamed_at: null,
  },
  settings: {
    enabled: true,
    share_aggregate: true,
    sensitive_mode: "always_ask",
    banner_mode: "realtime",
  },
  core_profile: {
    summary:
      "Profile: Teaches at a public primary school in Kisumu County\nTeaching context: Teaches Grade 6 Mathematics and Science under CBC; Has around 60 learners per class\nPreferences: Prefers Kiswahili and English mix, short answers, and bullet-point plans\nActive life areas: AI Tooling",
    version: 1,
    built_from_count: 8,
  },
  life_areas: [
    {
      id: "fallback-ai-tooling",
      slug: "ai_tooling",
      label_en: "AI Tooling",
      label_sw: "Zana za AI",
      summary: "Reusable AI tooling, skills, and prompt work Wambui has built",
      last_updated: "Nov 13, 2026",
      status: "active",
      created_by: "teacher",
      frozen_until: null,
      subcategories: [],
      memory_count: 4,
      memories: [
        {
          id: "m-ai-1",
          statement:
            "Built a gradual-release-instructor skill using the skill-creator system",
          slot: "ai_tooling.skills_built",
          lang: "en",
          source: "stated",
          sensitivity: "normal",
          confidence: 0.95,
          salience: 0.85,
          subcategory_id: null,
          subcategory_slug: "skills_built",
          subcategory_label_en: "Skills built",
          subcategory_label_sw: "Ujuzi",
          surface: "web",
          product_area: "chat",
          conversation_id: "conv-ai-1",
          created_by: "live_pass",
          valid_from: null,
          recorded_at: null,
        },
        {
          id: "m-ai-2",
          statement:
            "Built a Socratic tutor skill using the skill-creator system",
          slot: "ai_tooling.skills_built",
          lang: "en",
          source: "stated",
          sensitivity: "normal",
          confidence: 0.95,
          salience: 0.85,
          subcategory_id: null,
          subcategory_slug: "skills_built",
          subcategory_label_en: "Skills built",
          subcategory_label_sw: "Ujuzi",
          surface: "web",
          product_area: "chat",
          conversation_id: "conv-ai-1",
          created_by: "live_pass",
          valid_from: null,
          recorded_at: null,
        },
        {
          id: "m-ai-3",
          statement: "Built an Anki card creator skill",
          slot: "ai_tooling.anki_skill",
          lang: "en",
          source: "stated",
          sensitivity: "normal",
          confidence: 0.95,
          salience: 0.85,
          subcategory_id: null,
          subcategory_slug: "anki_skill",
          subcategory_label_en: "Anki skill",
          subcategory_label_sw: "Anki",
          surface: "web",
          product_area: "chat",
          conversation_id: "conv-ai-1",
          created_by: "live_pass",
          valid_from: null,
          recorded_at: null,
        },
        {
          id: "m-ai-4",
          statement: "Does prompt optimization for WhatsApp agents",
          slot: "ai_tooling.prompt_optimization",
          lang: "en",
          source: "stated",
          sensitivity: "normal",
          confidence: 0.95,
          salience: 0.85,
          subcategory_id: null,
          subcategory_slug: "prompt_optimization",
          subcategory_label_en: "Prompt optimization",
          subcategory_label_sw: "Uboreshaji",
          surface: "web",
          product_area: "chat",
          conversation_id: "conv-ai-2",
          created_by: "live_pass",
          valid_from: null,
          recorded_at: null,
        },
      ],
    },
  ],
  core_categories: [],
  pending_consents: [],
  notifications: [],
  unread_notification_count: 0,
  superseded_history: [],
  tombstone_count: 0,
  llm_status: {
    chat_model: "claude-3-5-haiku-latest",
    extraction_model: "claude-3-5-haiku-latest",
    api_key_configured: false,
    db_engine: "postgresql",
  },
};

async function getInitialTeacherState(): Promise<CategoricalState> {
  const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000";
  try {
    const res = await fetch(
      `${backendUrl}/api/memories/?teacher_id=teacher-wambui-ke`,
      { cache: "no-store" }
    );
    if (res.ok) {
      const data: CategoricalState = await res.json();
      if (data && data.teacher) {
        return data;
      }
    }
  } catch {
    // Fallback to pre-populated state if backend is starting
  }
  return FALLBACK_INITIAL_STATE;
}

export default async function HomePage() {
  const initialState = await getInitialTeacherState();
  return <ClientWorkspace initialState={initialState} />;
}
