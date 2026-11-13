"use client";

import React, { useState } from "react";
import { CategoricalState } from "../types";
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
  const [searchQuery, setSearchQuery] = useState("");
  const [creatingArea, setCreatingArea] = useState(false);
  const [newAreaEn, setNewAreaEn] = useState("");
  const [newAreaSw, setNewAreaSw] = useState("");

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

  const handleCreateAreaSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAreaEn.trim()) return;
    await onCreateLifeArea(newAreaEn.trim(), newAreaSw.trim());
    setNewAreaEn("");
    setNewAreaSw("");
    setCreatingArea(false);
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

      {/* Filter & Search Toolbar */}
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
            onClick={() => setFilterTab("system")}
          >
            Core Profile &amp; Settings
          </button>
        </div>

        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <input
            type="text"
            className="input"
            placeholder="Filter categories or memories..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ width: "220px" }}
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
                  Injected into Claude Haiku on every turn (max ~300 tokens, Redis-cached)
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

                <div>
                  <div className="memory-field-label">Sensitive Memory Mode</div>
                  <select
                    className="input"
                    style={{ width: "100%", marginTop: "4px" }}
                    value={state.settings.sensitive_mode}
                    onChange={(e) =>
                      onUpdateSettings({
                        sensitive_mode: e.target.value as
                          | "always_ask"
                          | "never_remember",
                      })
                    }
                  >
                    <option value="always_ask">
                      Always ask me before saving personal things
                    </option>
                    <option value="never_remember">
                      Never remember personal things
                    </option>
                  </select>
                </div>

                <div>
                  <div className="memory-field-label">Web Notification Mode</div>
                  <select
                    className="input"
                    style={{ width: "100%", marginTop: "4px" }}
                    value={state.settings.banner_mode}
                    onChange={(e) =>
                      onUpdateSettings({
                        banner_mode: e.target.value as
                          | "realtime"
                          | "next_visit_summary",
                      })
                    }
                  >
                    <option value="realtime">
                      Show realtime banner during web sessions
                    </option>
                    <option value="next_visit_summary">
                      Summary on next visit only
                    </option>
                  </select>
                </div>

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
                  No superseded memories yet. Updating a singleton slot (like class size or grade) preserves the prior version here with valid_to and retired_at timestamps.
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
      ) : (
        /* Category Cards Grid (Exact Layout from image.png) */
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
              />
            ))}

          {filteredLifeAreas.length === 0 && filteredCoreCategories.length === 0 && (
            <div className="minimal-panel" style={{ gridColumn: "1 / -1" }}>
              <div style={{ fontSize: "14px", color: "var(--text-secondary)" }}>
                No categories with active memories match the current filter. Switch to{" "}
                <button
                  className="btn btn-xs"
                  onClick={() => setFilterTab("all")}
                  style={{ margin: "0 4px" }}
                >
                  All Categories
                </button>{" "}
                or click <strong>Seed Demo</strong> in the top bar.
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
