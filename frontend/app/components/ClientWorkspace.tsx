"use client";

import React, { useCallback, useEffect, useState } from "react";
import ChatPanel from "./ChatPanel";
import MemoryDashboard from "./MemoryDashboard";
import { CategoricalState, ChatTurnMessage } from "../types";

const INITIAL_ASSISTANT_MESSAGE: ChatTurnMessage = {
  id: "welcome-1",
  role: "assistant",
  content:
    "Habari Mwalimu! I am Amal, your teaching assistant. Ask for help planning a lesson or share something about your classroom — your context is organized into the memory categories automatically.",
};

type ViewMode = "split" | "memory" | "chat";

interface ClientWorkspaceProps {
  initialState: CategoricalState;
}

export default function ClientWorkspace({ initialState }: ClientWorkspaceProps) {
  const [teacherId, setTeacherId] = useState(
    initialState.teacher?.teacher_id || "teacher-wambui-ke"
  );
  const [teacherInput, setTeacherInput] = useState(
    initialState.teacher?.teacher_id || "teacher-wambui-ke"
  );
  const [viewMode, setViewMode] = useState<ViewMode>("split");
  const [state, setState] = useState<CategoricalState>(initialState);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatTurnMessage[]>([
    INITIAL_ASSISTANT_MESSAGE,
  ]);
  const [sendingChat, setSendingChat] = useState(false);
  const [sessionApiKey, setSessionApiKey] = useState("");

  const fetchState = useCallback(async (tid: string) => {
    try {
      const res = await fetch(
        `/api/memories?teacher_id=${encodeURIComponent(tid)}`,
        { cache: "no-store" }
      );
      if (!res.ok) return;
      const data: CategoricalState = await res.json();
      if (data && data.teacher) {
        setState(data);
      }
    } catch {
      // Keep existing state if background refresh fails
    }
  }, []);

  useEffect(() => {
    fetchState(teacherId);
  }, [teacherId, fetchState]);

  const handleSwitchTeacher = (e: React.FormEvent) => {
    e.preventDefault();
    const cleaned = teacherInput.trim() || "teacher-wambui-ke";
    setTeacherId(cleaned);
    setMessages([INITIAL_ASSISTANT_MESSAGE]);
  };

  const handleSendMessage = async (text: string) => {
    const userTurn: ChatTurnMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
    };
    setMessages((prev) => [...prev, userTurn]);
    setSendingChat(true);

    try {
      const historyPayload = messages
        .filter((m) => m.id !== "welcome-1")
        .map((m) => ({ role: m.role, content: m.content }));

      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          teacher_id: teacherId,
          message: text,
          history: historyPayload,
          surface: "web",
          product_area: "chat",
          api_key: sessionApiKey.trim() || undefined,
        }),
      });
      const data = await res.json();

      const assistantTurn: ChatTurnMessage = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: data.reply || data.error || "Done.",
        chatModel: data.chat_model,
        extractionModel: data.extraction_model,
        retrievedMemories: data.turn_context?.retrieved_memories || [],
        extractedCandidates: data.extracted_candidates || [],
      };
      setMessages((prev) => [...prev, assistantTurn]);
      if (data.state) {
        setState(data.state);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: "assistant",
          content: `Unable to reach the Amal backend: ${String(err)}`,
        },
      ]);
    } finally {
      setSendingChat(false);
    }
  };

  const handleSeedDemo = async () => {
    setBusyAction("seed");
    try {
      const res = await fetch("/api/seed-demo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ teacher_id: teacherId }),
      });
      const data = await res.json();
      if (data.state) setState(data.state);
    } finally {
      setBusyAction(null);
    }
  };

  const handleRunDreaming = async () => {
    setBusyAction("dream");
    try {
      const res = await fetch("/api/dream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ teacher_id: teacherId }),
      });
      const data = await res.json();
      if (data.state) setState(data.state);
    } finally {
      setBusyAction(null);
    }
  };

  const handleEditMemory = async (memoryId: string, newStatement: string) => {
    const res = await fetch(`/api/memories/${memoryId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ teacher_id: teacherId, statement: newStatement }),
    });
    const data = await res.json();
    if (data.state) setState(data.state);
  };

  const handleDeleteMemory = async (memoryId: string) => {
    const res = await fetch(
      `/api/memories/${memoryId}?teacher_id=${encodeURIComponent(teacherId)}`,
      { method: "DELETE" }
    );
    const data = await res.json();
    if (data.state) setState(data.state);
  };

  const handleDeleteCategory = async (
    categoryId: string,
    isLifeArea: boolean
  ) => {
    if (isLifeArea) {
      const res = await fetch("/api/life-areas", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          teacher_id: teacherId,
          action: "delete",
          category_id: categoryId,
        }),
      });
      const data = await res.json();
      if (data.state) setState(data.state);
      return;
    }

    const res = await fetch(`/api/categories/${categoryId}/clear`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ teacher_id: teacherId }),
    });
    const data = await res.json();
    if (data.state) setState(data.state);
  };

  const handleRenameLifeArea = async (categoryId: string, newName: string) => {
    const res = await fetch("/api/life-areas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        teacher_id: teacherId,
        action: "rename",
        category_id: categoryId,
        label_en: newName,
      }),
    });
    const data = await res.json();
    if (data.state) setState(data.state);
  };

  const handleRestoreLifeArea = async (categoryId: string) => {
    const res = await fetch("/api/life-areas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        teacher_id: teacherId,
        action: "restore",
        category_id: categoryId,
      }),
    });
    const data = await res.json();
    if (data.state) setState(data.state);
  };

  const handleCreateLifeArea = async (labelEn: string, labelSw: string) => {
    const res = await fetch("/api/life-areas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        teacher_id: teacherId,
        action: "create",
        label_en: labelEn,
        label_sw: labelSw,
      }),
    });
    const data = await res.json();
    if (data.state) setState(data.state);
  };

  const handleAddMemory = async (categorySlug: string, statement: string) => {
    const res = await fetch("/api/memories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        teacher_id: teacherId,
        statement,
        category_slug: categorySlug,
        source: "stated",
        surface: "web",
        created_by: "teacher",
        explicit_consent_granted: true,
      }),
    });
    const data = await res.json();
    if (data.state) setState(data.state);
  };

  const handleResolveConsent = async (
    consentId: string,
    answer: "yes" | "no"
  ) => {
    const res = await fetch(`/api/consent/${consentId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ teacher_id: teacherId, answer }),
    });
    const data = await res.json();
    if (data.state) setState(data.state);
  };

  const handleNotificationAction = async (
    notificationId: string,
    action: string
  ) => {
    const res = await fetch(`/api/notifications/${notificationId}/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ teacher_id: teacherId, action }),
    });
    const data = await res.json();
    if (data.state) setState(data.state);
  };

  const handleUndoTaxonomyChangeset = async (changesetId: string) => {
    const res = await fetch(`/api/taxonomy/undo/${changesetId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ teacher_id: teacherId }),
    });
    const data = await res.json();
    if (data.state) setState(data.state);
  };

  const handleUpdateSettings = async (
    partial: Partial<CategoricalState["settings"]>
  ) => {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        teacher_id: teacherId,
        ...state.settings,
        ...partial,
      }),
    });
    const data = await res.json();
    if (data.state) setState(data.state);
  };

  const handleDeleteAllMemories = async () => {
    const res = await fetch("/api/memories/delete-all", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ teacher_id: teacherId }),
    });
    const data = await res.json();
    if (data.state) setState(data.state);
  };

  const isLiveKey = Boolean(
    sessionApiKey.trim() || state?.llm_status?.api_key_configured
  );

  return (
    <div>
      {/* Minimalist Top Bar */}
      <header className="topbar">
        <div className="brand-group">
          <div>
            <h1 className="brand-title">Amal</h1>
            <div className="brand-subtitle">
              {state?.teacher
                ? `${state.teacher.display_name} · ${state.teacher.curriculum}`
                : "Teaching Assistant & Categorical Memory"}
            </div>
          </div>

          <span className="status-pill">
            <span className={`status-dot ${isLiveKey ? "" : "offline"}`} />
            {state?.llm_status?.chat_model || "claude-3-5-haiku-latest"}
          </span>
        </div>

        {/* View Mode Switcher */}
        <div className="segmented-tabs" role="tablist" aria-label="Workspace view">
          <button
            type="button"
            className={`seg-btn ${viewMode === "split" ? "active" : ""}`}
            onClick={() => setViewMode("split")}
          >
            Split View
          </button>
          <button
            type="button"
            className={`seg-btn ${viewMode === "memory" ? "active" : ""}`}
            onClick={() => setViewMode("memory")}
          >
            Memories
          </button>
          <button
            type="button"
            className={`seg-btn ${viewMode === "chat" ? "active" : ""}`}
            onClick={() => setViewMode("chat")}
          >
            Chat
          </button>
        </div>

        {/* Right Controls */}
        <div className="topbar-controls">
          <form
            onSubmit={handleSwitchTeacher}
            style={{ display: "flex", gap: "6px", alignItems: "center" }}
          >
            <input
              id="teacher-id-input"
              type="text"
              className="input"
              style={{ width: "155px" }}
              value={teacherInput}
              onChange={(e) => setTeacherInput(e.target.value)}
              placeholder="Teacher ID"
            />
            <button type="submit" className="btn">
              Load
            </button>
          </form>

          <button
            id="seed-demo-btn"
            type="button"
            className="btn"
            onClick={handleSeedDemo}
            disabled={busyAction === "seed"}
          >
            {busyAction === "seed" ? "Seeding..." : "Seed Demo"}
          </button>

          <button
            id="run-dream-btn"
            type="button"
            className="btn btn-accent"
            onClick={handleRunDreaming}
            disabled={busyAction === "dream"}
          >
            {busyAction === "dream" ? "Dreaming..." : "Run Dreaming"}
          </button>

          <a
            className="btn"
            href={`/api/memories/export?teacher_id=${encodeURIComponent(
              teacherId
            )}`}
          >
            Export JSON
          </a>
        </div>
      </header>

      {/* Main Content Area — Always rendered immediately without blocking */}
      <main className="workspace">
        {viewMode === "split" ? (
          <div className="workspace-split">
            <ChatPanel
              messages={messages}
              sending={sendingChat}
              chatModel={
                state.llm_status?.chat_model || "claude-3-5-haiku-latest"
              }
              extractionModel={
                state.llm_status?.extraction_model || "claude-3-5-haiku-latest"
              }
              apiKeyConfigured={Boolean(state.llm_status?.api_key_configured)}
              sessionApiKey={sessionApiKey}
              onChangeSessionApiKey={setSessionApiKey}
              onSendMessage={handleSendMessage}
              onClearChat={() => setMessages([INITIAL_ASSISTANT_MESSAGE])}
            />

            <MemoryDashboard
              state={state}
              onEditMemory={handleEditMemory}
              onDeleteMemory={handleDeleteMemory}
              onDeleteCategory={handleDeleteCategory}
              onRenameLifeArea={handleRenameLifeArea}
              onRestoreLifeArea={handleRestoreLifeArea}
              onCreateLifeArea={handleCreateLifeArea}
              onAddMemory={handleAddMemory}
              onResolveConsent={handleResolveConsent}
              onNotificationAction={handleNotificationAction}
              onUndoTaxonomyChangeset={handleUndoTaxonomyChangeset}
              onUpdateSettings={handleUpdateSettings}
              onDeleteAllMemories={handleDeleteAllMemories}
            />
          </div>
        ) : viewMode === "chat" ? (
          <div className="workspace-single">
            <ChatPanel
              messages={messages}
              sending={sendingChat}
              chatModel={
                state.llm_status?.chat_model || "claude-3-5-haiku-latest"
              }
              extractionModel={
                state.llm_status?.extraction_model || "claude-3-5-haiku-latest"
              }
              apiKeyConfigured={Boolean(state.llm_status?.api_key_configured)}
              sessionApiKey={sessionApiKey}
              onChangeSessionApiKey={setSessionApiKey}
              onSendMessage={handleSendMessage}
              onClearChat={() => setMessages([INITIAL_ASSISTANT_MESSAGE])}
            />
          </div>
        ) : (
          <div className="workspace-single" style={{ maxWidth: "1180px" }}>
            <MemoryDashboard
              state={state}
              onEditMemory={handleEditMemory}
              onDeleteMemory={handleDeleteMemory}
              onDeleteCategory={handleDeleteCategory}
              onRenameLifeArea={handleRenameLifeArea}
              onRestoreLifeArea={handleRestoreLifeArea}
              onCreateLifeArea={handleCreateLifeArea}
              onAddMemory={handleAddMemory}
              onResolveConsent={handleResolveConsent}
              onNotificationAction={handleNotificationAction}
              onUndoTaxonomyChangeset={handleUndoTaxonomyChangeset}
              onUpdateSettings={handleUpdateSettings}
              onDeleteAllMemories={handleDeleteAllMemories}
            />
          </div>
        )}
      </main>
    </div>
  );
}
