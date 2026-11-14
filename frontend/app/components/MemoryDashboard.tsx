"use client";

import React, { useState } from "react";
import { CategoricalState, CategoryCardData } from "../types";
import MemoryCategoryCard from "./MemoryCategoryCard";

interface MemoryDashboardProps {
  state: CategoricalState;
  onEditMemory: (memoryId: string, newStatement: string) => Promise<void>;
  onDeleteMemory: (memoryId: string) => Promise<void>;
  onDeleteCategory: (categoryId: string, isLifeArea: boolean) => Promise<void>;
  onRenameLifeArea: (categoryId: string, newName: string) => Promise<void>;
  onRestoreLifeArea: (categoryId: string) => Promise<void>;
  onCreateLifeArea: (labelEn: string, labelSw: string) => Promise<void>;
  onAddMemory: (categorySlug: string, statement: string) => Promise<void>;
  onResolveConsent: (consentId: string, answer: "yes" | "no") => Promise<void>;
  onNotificationAction: (notificationId: string, action: string) => Promise<void>;
  onUndoTaxonomyChangeset: (changesetId: string) => Promise<void>;
  onUpdateSettings: (partial: Partial<CategoricalState["settings"]>) => Promise<void>;
  onDeleteAllMemories: () => Promise<void>;
}

type FilterTab = "populated" | "all" | "life_areas" | "core" | "system";
type DisplayMode = "list" | "cards";

const YOU_SLUGS = new Set([
  "preferences",
  "profile",
  "teaching_context",
  "classroom",
  "people",
  "wellbeing",
  "named_learners",
]);

export default function MemoryDashboard({
  state,
  onEditMemory,
  onDeleteMemory,
  onDeleteCategory,
  onRenameLifeArea,
  onRestoreLifeArea,
  onCreateLifeArea,
  onAddMemory,
  onResolveConsent,
  onNotificationAction,
  onUndoTaxonomyChangeset,
  onUpdateSettings,
  onDeleteAllMemories,
}: MemoryDashboardProps) {
  const [filterTab, setFilterTab] = useState<FilterTab>("populated");
  const [displayMode, setDisplayMode] = useState<DisplayMode>("list");
  const [searchQuery, setSearchQuery] = useState("");
  const [creatingArea, setCreatingArea] = useState(false);
  const [newAreaEn, setNewAreaEn] = useState("");
  const [newAreaSw, setNewAreaSw] = useState("");
  const [activeCategorySlug, setActiveCategorySlug] = useState<string | null>(null);
  const [activeSubcategorySlug, setActiveSubcategorySlug] = useState<string | null>(null);
  const [quickMemoryText, setQuickMemoryText] = useState("");

  const activeBanners = state.notifications.filter(
    (n) =>
      (n.kind === "saved" || n.kind === "updated") &&
      n.action === "pending" &&
      !n.seen_at
  );
  const latestBanner =
    state.settings.banner_mode === "realtime" && activeBanners.length > 0
      ? activeBanners[0]
      : null;

  const taxonomyNotifs = state.notifications.filter(
    (n) =>
      n.kind === "taxonomy_change" &&
      n.action === "pending" &&
      n.changeset_status === "applied"
  );

  const matchesSearch = (label: string, summary: string, statements: string[]) => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return true;
    if (label.toLowerCase().includes(q) || summary.toLowerCase().includes(q)) {
      return true;
    }
    return statements.some((s) => s.toLowerCase().includes(q));
  };

  const filteredLifeAreas = state.life_areas.filter((la) =>
    matchesSearch(
      la.label_en,
      la.summary,
      la.memories.map((m) => m.statement)
    )
  );

  const filteredCoreCategories = state.core_categories.filter((cat) => {
    const hasMatch = matchesSearch(
      cat.label_en,
      cat.summary,
      cat.memories.map((m) => m.statement)
    );
    if (!hasMatch) return false;
    if (filterTab === "populated") {
      return cat.memories.length > 0;
    }
    return true;
  });

  const allFilteredCategories: CategoryCardData[] = [
    ...(filterTab !== "life_areas" ? filteredCoreCategories : []),
    ...(filterTab !== "core" ? filteredLifeAreas : []),
  ];

  const youItems = allFilteredCategories.filter(
    (c) => (c.section || (YOU_SLUGS.has(c.slug) && !c.is_life_area ? "you" : "topics")) === "you"
  );
  const topicItems = allFilteredCategories.filter(
    (c) => (c.section || (YOU_SLUGS.has(c.slug) && !c.is_life_area ? "you" : "topics")) === "topics"
  );

  const allCategories = [...state.core_categories, ...state.life_areas];
  const activeCategory = activeCategorySlug
    ? allCategories.find((c) => c.slug === activeCategorySlug) || null
    : null;
  const activeSubcategory =
    activeCategory && activeSubcategorySlug
      ? activeCategory.subcategories.find((s) => s.slug === activeSubcategorySlug) || null
      : null;

  const handleCreateAreaSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAreaEn.trim()) return;
    await onCreateLifeArea(newAreaEn.trim(), newAreaSw.trim());
    setNewAreaEn("");
    setNewAreaSw("");
    setCreatingArea(false);
  };

  const handleQuickAdd = async () => {
    const trimmed = quickMemoryText.trim();
    if (!trimmed) return;
    setQuickMemoryText("");
    await onAddMemory(activeCategorySlug || "preferences", trimmed);
  };

  const totalSavedMemories =
    state.life_areas.reduce((acc, c) => acc + c.memories.length, 0) +
    state.core_categories.reduce((acc, c) => acc + c.memories.length, 0);

  return (
    <div className="dashboard-col" id="memory-dashboard">
      {/* Realtime Banner, Consent Queue & Nightly Taxonomy Cards */}
      {(latestBanner ||
        state.pending_consents.length > 0 ||
        taxonomyNotifs.length > 0) && (
        <div className="alert-stack">
          {latestBanner && (
            <div className="notice-bar saved">
              <div>
                <div style={{ fontWeight: 600, fontSize: "13.5px" }}>
                  {latestBanner.title}
                </div>
                {latestBanner.grouped_count > 1 && (
                  <div className="notice-meta">{latestBanner.body}</div>
                )}
              </div>
              <div style={{ display: "flex", gap: "6px", flexShrink: 0 }}>
                <button
                  className="btn btn-xs"
                  onClick={() => onNotificationAction(latestBanner.id, "kept")}
                >
                  Keep
                </button>
                <button
                  className="btn btn-xs btn-danger-ghost"
                  onClick={() => onNotificationAction(latestBanner.id, "undo")}
                >
                  Undo
                </button>
              </div>
            </div>
          )}

          {state.pending_consents.map((c) => (
            <div key={c.consent_id} className="notice-bar consent">
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span className="tag consent">{c.category_label}</span>
                  <strong style={{ fontSize: "13.5px" }}>
                    Amal would like to remember this. Keep it?
                  </strong>
                </div>
                <div style={{ marginTop: "4px", fontSize: "13.5px" }}>
                  &ldquo;{c.statement}&rdquo;
                </div>
                <div className="notice-meta">
                  Excluded from retrieval until approved · {c.prompt_text}
                </div>
              </div>
              <div style={{ display: "flex", gap: "6px", flexShrink: 0 }}>
                <button
                  className="btn btn-xs btn-primary"
                  onClick={() => onResolveConsent(c.consent_id, "yes")}
                >
                  Yes, Keep
                </button>
                <button
                  className="btn btn-xs btn-danger-ghost"
                  onClick={() => onResolveConsent(c.consent_id, "no")}
                >
                  No, Delete
                </button>
              </div>
            </div>
          ))}

          {taxonomyNotifs.map((n) => (
            <div key={n.id} className="notice-bar">
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span className="tag life-area">Nightly Dreaming</span>
                  <strong style={{ fontSize: "13.5px" }}>{n.title}</strong>
                </div>
                <div className="notice-meta">{n.body}</div>
              </div>
              <div style={{ display: "flex", gap: "6px", flexShrink: 0 }}>
                <button
                  className="btn btn-xs"
                  onClick={() => onNotificationAction(n.id, "kept")}
                >
                  Keep
                </button>
                {n.changeset_id && (
                  <button
                    className="btn btn-xs btn-danger-ghost"
                    onClick={() => onUndoTaxonomyChangeset(n.changeset_id!)}
                  >
                    Undo
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Filter, List/Cards Toggle & Search Toolbar */}
      <div className="dashboard-toolbar">
        <div className="segmented-tabs">
          <button
            className={`seg-btn ${filterTab === "populated" ? "active" : ""}`}
            onClick={() => setFilterTab("populated")}
          >
            Active Memories ({totalSavedMemories})
          </button>
          <button
            className={`seg-btn ${filterTab === "all" ? "active" : ""}`}
            onClick={() => setFilterTab("all")}
          >
            All Categories ({state.life_areas.length + state.core_categories.length})
          </button>
          <button
            className={`seg-btn ${filterTab === "life_areas" ? "active" : ""}`}
            onClick={() => setFilterTab("life_areas")}
          >
            Life Areas ({state.life_areas.length}/8)
          </button>
          <button
            className={`seg-btn ${filterTab === "system" ? "active" : ""}`}
            onClick={() => {
              setFilterTab("system");
              setActiveCategorySlug(null);
              setActiveSubcategorySlug(null);
            }}
          >
            Core Profile &amp; Settings
          </button>
        </div>

        <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
          <div className="segmented-tabs" role="group" aria-label="Memory display layout">
            <button
              type="button"
              className={`seg-btn ${displayMode === "list" ? "active" : ""}`}
              onClick={() => setDisplayMode("list")}
            >
              List
            </button>
            <button
              type="button"
              className={`seg-btn ${displayMode === "cards" ? "active" : ""}`}
              onClick={() => setDisplayMode("cards")}
            >
              Cards
            </button>
          </div>

          <input
            type="text"
            className="input"
            placeholder="Filter categories or memories..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ width: "200px" }}
          />
          <button
            className="btn"
            onClick={() => setCreatingArea((prev) => !prev)}
          >
            {creatingArea ? "Cancel" : "New Life Area"}
          </button>
        </div>
      </div>

      {/* Inline New Life Area Form */}
      {creatingArea && (
        <form
          onSubmit={handleCreateAreaSubmit}
          className="minimal-panel"
          style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}
        >
          <strong style={{ fontSize: "13px" }}>Create Life Area:</strong>
          <input
            type="text"
            className="input"
            placeholder="Category title (e.g. AI Tooling)"
            value={newAreaEn}
            onChange={(e) => setNewAreaEn(e.target.value)}
            required
          />
          <input
            type="text"
            className="input"
            placeholder="Swahili label (optional, e.g. Zana za AI)"
            value={newAreaSw}
            onChange={(e) => setNewAreaSw(e.target.value)}
          />
          <button type="submit" className="btn btn-primary">
            Create
          </button>
        </form>
      )}

      {/* System / Core Profile / History / Privacy Settings Tab */}
      {filterTab === "system" ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <div className="minimal-panel">
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "10px",
              }}
            >
              <div>
                <h3 style={{ fontSize: "15px", fontWeight: 600 }}>
                  Always-Injected Core Profile Block
                </h3>
                <div style={{ fontSize: "12.5px", color: "var(--text-muted)" }}>
                  Injected into Claude Sonnet on every turn (max ~300 tokens, Redis-cached)
                </div>
              </div>
              <span className="tag">
                v{state.core_profile.version} · {state.core_profile.built_from_count} facts
              </span>
            </div>
            <pre className="mono-block">
              {state.core_profile.summary || "(No core profile memories yet)"}
            </pre>
          </div>

          <div className="cards-grid">
            <div className="minimal-panel">
              <h3 style={{ fontSize: "15px", fontWeight: 600, marginBottom: "12px" }}>
                Privacy &amp; Memory Settings
              </h3>
              <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                <label style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                  <input
                    type="checkbox"
                    checked={state.settings.enabled}
                    onChange={(e) =>
                      onUpdateSettings({ enabled: e.target.checked })
                    }
                  />
                  <span>
                    <strong>Memory Enabled</strong> (Unchecking opts out &amp; purges all memories)
                  </span>
                </label>

                <label style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                  <input
                    type="checkbox"
                    checked={state.settings.share_aggregate}
                    onChange={(e) =>
                      onUpdateSettings({ share_aggregate: e.target.checked })
                    }
                  />
                  <span>
                    <strong>Share in Anonymized Cohort Insights</strong> (k&ge;10 / k&ge;50)
                  </span>
                </label>

                <div
                  style={{
                    paddingTop: "12px",
                    borderTop: "1px solid var(--border-subtle)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                    HMAC Tombstones: {state.tombstone_count}
                  </span>
                  <button
                    className="btn btn-danger-ghost"
                    onClick={onDeleteAllMemories}
                  >
                    Delete All Memories
                  </button>
                </div>
              </div>
            </div>

            <div className="minimal-panel">
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: "10px",
                }}
              >
                <h3 style={{ fontSize: "15px", fontWeight: 600 }}>
                  Bi-Temporal Superseded History
                </h3>
                <span className="tag">{state.superseded_history.length} retired</span>
              </div>
              {state.superseded_history.length === 0 ? (
                <div style={{ fontSize: "13px", color: "var(--text-muted)" }}>
                  No superseded memories yet. Updating a singleton slot preserves the prior version here with valid_to and retired_at timestamps.
                </div>
              ) : (
                <ul className="memory-details-list">
                  {state.superseded_history.map((item) => (
                    <li
                      key={item.id}
                      className="memory-details-item"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      <span style={{ textDecoration: "line-through" }}>
                        {item.statement}
                      </span>{" "}
                      <span className="tag">{item.slot}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      ) : activeCategory && activeSubcategory ? (
        /* LAYER 3: Subcategory Detail View */
        <div className="claude-memory-shell">
          <div className="claude-detail-view">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
              <button
                type="button"
                className="claude-back-link"
                style={{ marginBottom: 0 }}
                onClick={() => setActiveSubcategorySlug(null)}
              >
                &larr; {activeCategory.label_en}
              </button>
              <span className="tag life-area">Layer 3 of 3 &middot; Subcategory</span>
            </div>

            <div className="claude-detail-header">
              <h2 className="claude-detail-title">{activeSubcategory.label_en}</h2>
            </div>

            <div className="claude-detail-section">
              <div className="claude-detail-label">Last updated</div>
              <div className="claude-detail-text">
                {activeSubcategory.last_updated || "No memories saved yet"}
              </div>
            </div>

            <div className="claude-detail-section">
              <div className="claude-detail-label">Summary</div>
              <div className="claude-detail-text">
                {activeSubcategory.summary || ""}
              </div>
            </div>

            <div className="claude-detail-section">
              <div className="claude-detail-label">
                Details ({activeSubcategory.memories?.length || 0})
              </div>
              <ul className="claude-detail-bullets">
                {(activeSubcategory.memories || []).map((mem) => (
                  <li key={mem.id}>
                    <div className="memory-bullet-row">
                      <span>{mem.statement}</span>
                      <div className="memory-bullet-actions" style={{ opacity: 1 }}>
                        <button
                          className="btn btn-xs btn-danger-ghost"
                          onClick={() => onDeleteMemory(mem.id)}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      ) : activeCategory ? (
        /* LAYER 2: Category Detail View (matching image_2.png) */
        <div className="claude-memory-shell">
          <div className="claude-detail-view">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
              <button
                type="button"
                className="claude-back-link"
                style={{ marginBottom: 0 }}
                onClick={() => {
                  setActiveCategorySlug(null);
                  setActiveSubcategorySlug(null);
                }}
              >
                &larr; Memory
              </button>
              <span className="tag">Layer 2 of 3 &middot; {activeCategory.label_en}</span>
            </div>

            <div className="claude-detail-header">
              <h2 className="claude-detail-title">{activeCategory.label_en}</h2>
              <div className="claude-detail-actions">
                <button
                  className="btn btn-danger-ghost"
                  onClick={() =>
                    onDeleteCategory(activeCategory.id, Boolean(activeCategory.is_life_area))
                  }
                >
                  Delete
                </button>
              </div>
            </div>

            <div className="claude-detail-section">
              <div className="claude-detail-label">Last updated</div>
              <div className="claude-detail-text">{activeCategory.last_updated}</div>
            </div>

            <div className="claude-detail-section">
              <div className="claude-detail-label">Summary</div>
              <div className="claude-detail-text">{activeCategory.summary}</div>
            </div>

            {activeCategory.subcategories.length > 0 && (
              <div className="claude-detail-section">
                <div className="claude-detail-label">
                  Subcategories (Click to open Layer 3)
                </div>
                <div className="claude-list-table">
                  {activeCategory.subcategories.map((sub) => (
                    <div
                      key={sub.id}
                      className="claude-list-row"
                      onClick={() => setActiveSubcategorySlug(sub.slug)}
                    >
                      <div className="claude-list-title">
                        {sub.label_en}{" "}
                        <span className="tag">
                          {sub.memory_count ?? sub.memories?.length ?? 0}
                        </span>
                      </div>
                      <div className="claude-list-summary">{sub.summary || ""}</div>
                      <div className="claude-list-date">
                        {sub.last_updated_short || "Open Layer 3 →"}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="claude-detail-section">
              <div className="claude-detail-label">Details</div>
              <ul className="claude-detail-bullets">
                {activeCategory.memories.map((mem) => (
                  <li key={mem.id}>
                    <div className="memory-bullet-row">
                      <span>{mem.statement}</span>
                      <div className="memory-bullet-actions" style={{ opacity: 1 }}>
                        <button
                          className="btn btn-xs btn-danger-ghost"
                          onClick={() => onDeleteMemory(mem.id)}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            <div className="claude-bottom-input-wrap">
              <div className="claude-bottom-input-bar">
                <input
                  type="text"
                  className="claude-bottom-input"
                  placeholder="My dog's name is Beans"
                  value={quickMemoryText}
                  onChange={(e) => setQuickMemoryText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleQuickAdd();
                  }}
                />
                <button
                  type="button"
                  className="claude-up-btn"
                  onClick={handleQuickAdd}
                  aria-label="Save to memory"
                >
                  &uarr;
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : displayMode === "list" ? (
        /* LAYER 1: Claude-style List View (matching image.png) */
        <div className="claude-memory-shell">
          <div className="claude-breadcrumb-bar">
            <span style={{ color: "var(--text-secondary)" }}>&larr; Your Amal</span>
            <span className="sep">/</span>
            <span className="current">Memory</span>
            <span className="tag" style={{ marginLeft: "auto" }}>
              Layer 1 of 3 &middot; You &amp; Topics
            </span>
          </div>

          <div className="claude-section-block">
            <h3 className="claude-section-heading">You</h3>
            <div className="claude-list-table">
              {youItems.map((cat) => (
                <div
                  key={cat.id}
                  className="claude-list-row"
                  onClick={() => setActiveCategorySlug(cat.slug)}
                >
                  <div className="claude-list-title">{cat.label_en}</div>
                  <div className="claude-list-summary">{cat.summary}</div>
                  <div className="claude-list-date">
                    {cat.last_updated_short || `Updated ${cat.last_updated}`}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="claude-section-block">
            <h3 className="claude-section-heading">Topics</h3>
            <div className="claude-list-table">
              {topicItems.map((cat) => (
                <div
                  key={cat.id}
                  className="claude-list-row"
                  onClick={() => setActiveCategorySlug(cat.slug)}
                >
                  <div className="claude-list-title">{cat.label_en}</div>
                  <div className="claude-list-summary">{cat.summary}</div>
                  <div className="claude-list-date">
                    {cat.last_updated_short || `Updated ${cat.last_updated}`}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        /* LAYER 1: Cards View */
        <div className="cards-grid">
          {filterTab !== "core" &&
            filteredLifeAreas.map((la) => (
              <MemoryCategoryCard
                key={la.id}
                category={la}
                isLifeArea={true}
                onEditMemory={onEditMemory}
                onDeleteMemory={onDeleteMemory}
                onDeleteCategory={onDeleteCategory}
                onRenameLifeArea={onRenameLifeArea}
                onRestoreLifeArea={onRestoreLifeArea}
                onAddMemory={onAddMemory}
                onOpenCategory={(slug) => setActiveCategorySlug(slug)}
                onOpenSubcategory={(catSlug, subSlug) => {
                  setActiveCategorySlug(catSlug);
                  setActiveSubcategorySlug(subSlug);
                }}
              />
            ))}

          {filterTab !== "life_areas" &&
            filteredCoreCategories.map((cat) => (
              <MemoryCategoryCard
                key={cat.id}
                category={cat}
                isLifeArea={false}
                onEditMemory={onEditMemory}
                onDeleteMemory={onDeleteMemory}
                onDeleteCategory={onDeleteCategory}
                onAddMemory={onAddMemory}
                onOpenCategory={(slug) => setActiveCategorySlug(slug)}
                onOpenSubcategory={(catSlug, subSlug) => {
                  setActiveCategorySlug(catSlug);
                  setActiveSubcategorySlug(subSlug);
                }}
              />
            ))}
        </div>
      )}
    </div>
  );
}
