"use client";

import React, { useState } from "react";
import { CategoryCardData, MemoryEntry } from "../types";

interface MemoryCategoryCardProps {
  category: CategoryCardData;
  isLifeArea?: boolean;
  onEditMemory: (memoryId: string, newStatement: string) => Promise<void>;
  onDeleteMemory: (memoryId: string) => Promise<void>;
  onDeleteCategory: (categoryId: string, isLifeArea: boolean) => Promise<void>;
  onRenameLifeArea?: (categoryId: string, newName: string) => Promise<void>;
  onRestoreLifeArea?: (categoryId: string) => Promise<void>;
  onAddMemory?: (categorySlug: string, statement: string) => Promise<void>;
}

export default function MemoryCategoryCard({
  category,
  isLifeArea = false,
  onEditMemory,
  onDeleteMemory,
  onDeleteCategory,
  onRenameLifeArea,
  onRestoreLifeArea,
  onAddMemory,
}: MemoryCategoryCardProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState<string>("");
  const [renamingArea, setRenamingArea] = useState<boolean>(false);
  const [areaNameInput, setAreaNameInput] = useState<string>(category.label_en);
  const [addingNote, setAddingNote] = useState<boolean>(false);
  const [newNoteText, setNewNoteText] = useState<string>("");

  const startEditing = (mem: MemoryEntry) => {
    setEditingId(mem.id);
    setEditingText(mem.statement);
  };

  const commitEdit = async (memoryId: string) => {
    const trimmed = editingText.trim();
    setEditingId(null);
    if (!trimmed) return;
    await onEditMemory(memoryId, trimmed);
  };

  const commitRename = async () => {
    const trimmed = areaNameInput.trim();
    setRenamingArea(false);
    if (!trimmed || !onRenameLifeArea) return;
    await onRenameLifeArea(category.id, trimmed);
  };

  const commitAddMemory = async () => {
    const trimmed = newNoteText.trim();
    if (!trimmed || !onAddMemory) return;
    setNewNoteText("");
    setAddingNote(false);
    await onAddMemory(category.slug, trimmed);
  };

  return (
    <article className="memory-card" id={`category-card-${category.slug}`}>
      <div className="memory-card-header">
        <div className="memory-card-title-group">
          {renamingArea ? (
            <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
              <input
                type="text"
                className="input"
                value={areaNameInput}
                onChange={(e) => setAreaNameInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitRename();
                  if (e.key === "Escape") setRenamingArea(false);
                }}
                autoFocus
              />
              <button className="btn btn-xs btn-primary" onClick={commitRename}>
                Save
              </button>
              <button className="btn btn-xs" onClick={() => setRenamingArea(false)}>
                Cancel
              </button>
            </div>
          ) : (
            <>
              <h3 className="memory-card-title">{category.label_en}</h3>
              {isLifeArea && <span className="tag life-area">Life Area</span>}
              {category.status === "archived" && <span className="tag">Archived</span>}
              {category.sensitivity === "consent" && (
                <span className="tag consent">Consent required</span>
              )}
            </>
          )}
        </div>

        <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
          {isLifeArea && !renamingArea && onRenameLifeArea && (
            <button
              className="btn btn-xs"
              onClick={() => {
                setAreaNameInput(category.label_en);
                setRenamingArea(true);
              }}
            >
              Rename
            </button>
          )}
          {isLifeArea && category.status === "archived" && onRestoreLifeArea && (
            <button
              className="btn btn-xs"
              onClick={() => onRestoreLifeArea(category.id)}
            >
              Restore
            </button>
          )}
          <button
            className="btn btn-danger-ghost"
            onClick={() => onDeleteCategory(category.id, isLifeArea)}
          >
            Delete
          </button>
        </div>
      </div>

      <div className="memory-field-block">
        <div className="memory-field-label">Last updated</div>
        <div className="memory-field-value">{category.last_updated}</div>
      </div>

      <div className="memory-field-block">
        <div className="memory-field-label">Summary</div>
        <div className="memory-field-value">{category.summary}</div>
      </div>

      <div className="memory-field-block" style={{ marginBottom: 0 }}>
        <div className="memory-field-label">Details</div>
        {category.memories.length > 0 ? (
          <ul className="memory-details-list">
            {category.memories.map((mem) => (
              <li key={mem.id} className="memory-details-item">
                {editingId === mem.id ? (
                  <div style={{ display: "flex", gap: "6px", alignItems: "center", marginTop: "2px" }}>
                    <input
                      type="text"
                      className="input"
                      style={{ flex: 1 }}
                      value={editingText}
                      onChange={(e) => setEditingText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitEdit(mem.id);
                        if (e.key === "Escape") setEditingId(null);
                      }}
                      autoFocus
                    />
                    <button
                      className="btn btn-xs btn-primary"
                      onClick={() => commitEdit(mem.id)}
                    >
                      Save
                    </button>
                    <button
                      className="btn btn-xs"
                      onClick={() => setEditingId(null)}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div className="memory-bullet-row">
                    <span>{mem.statement}</span>
                    <div className="memory-bullet-actions">
                      <button
                        className="btn btn-xs"
                        onClick={() => startEditing(mem)}
                      >
                        Edit
                      </button>
                      <button
                        className="btn btn-xs btn-danger-ghost"
                        onClick={() => onDeleteMemory(mem.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <div style={{ fontSize: "13px", color: "var(--text-muted)", marginTop: "4px" }}>
            No details saved in this category yet.
          </div>
        )}
      </div>

      <div className="memory-card-footer">
        <span style={{ fontSize: "11.5px", color: "var(--text-muted)" }}>
          {category.label_sw}
          {category.subcategories.length > 0
            ? ` · ${category.subcategories.map((s) => s.label_en).join(", ")}`
            : ""}
        </span>

        {addingNote ? (
          <div style={{ display: "flex", gap: "6px", width: "100%", marginTop: "6px" }}>
            <input
              type="text"
              className="input"
              style={{ flex: 1 }}
              placeholder="Add a concise verb-led detail (e.g. Built an Anki card creator skill)"
              value={newNoteText}
              onChange={(e) => setNewNoteText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") commitAddMemory();
                if (e.key === "Escape") setAddingNote(false);
              }}
              autoFocus
            />
            <button className="btn btn-xs btn-primary" onClick={commitAddMemory}>
              Add
            </button>
            <button className="btn btn-xs" onClick={() => setAddingNote(false)}>
              Cancel
            </button>
          </div>
        ) : (
          <button className="btn btn-xs" onClick={() => setAddingNote(true)}>
            Add detail
          </button>
        )}
      </div>
    </article>
  );
}
