"use client";

import React, { useEffect, useRef, useState } from "react";
import { ChatTurnMessage } from "../types";

interface ChatPanelProps {
  messages: ChatTurnMessage[];
  sending: boolean;
  chatModel: string;
  extractionModel: string;
  apiKeyConfigured: boolean;
  sessionApiKey: string;
  onChangeSessionApiKey: (val: string) => void;
  onSendMessage: (messageText: string) => Promise<void>;
  onClearChat: () => void;
}

const SAMPLE_PROMPTS = [
  "I built a Socratic tutor skill using the skill-creator system and I do prompt optimization for WhatsApp agents.",
  "I teach Grade 6 Mathematics and Science with 65 learners, and we have no projector.",
  "I co-plan my Science lessons with my colleague Wanjiru.",
  "Help me create a 20-minute Hisabati lesson plan for my class",
  "What do you remember about me?",
];

export default function ChatPanel({
  messages,
  sending,
  chatModel,
  extractionModel,
  apiKeyConfigured,
  sessionApiKey,
  onChangeSessionApiKey,
  onSendMessage,
  onClearChat,
}: ChatPanelProps) {
  const [input, setInput] = useState("");
  const [showKeyInput, setShowKeyInput] = useState(false);
  const streamRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (streamRef.current) {
      streamRef.current.scrollTop = streamRef.current.scrollHeight;
    }
  }, [messages, sending]);

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || sending) return;
    setInput("");
    await onSendMessage(trimmed);
  };

  return (
    <section className="chat-shell" id="amal-chat-panel" aria-label="Chat with Amal">
      <div className="chat-header">
        <div>
          <div className="chat-header-title">Amal Teaching Assistant</div>
          <div className="chat-header-sub">
            Chat: {chatModel} · Extractor: {extractionModel}
          </div>
        </div>
        <div style={{ display: "flex", gap: "6px" }}>
          <button
            className="btn btn-xs"
            onClick={() => setShowKeyInput((prev) => !prev)}
          >
            {showKeyInput ? "Hide API Key" : "API Key"}
          </button>
          <button className="btn btn-xs" onClick={onClearChat}>
            Clear
          </button>
        </div>
      </div>

      {showKeyInput && (
        <div className="api-key-bar">
          <span style={{ color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
            Anthropic Key:
          </span>
          <input
            type="password"
            className="input"
            style={{ flex: 1, padding: "4px 8px", fontSize: "12px" }}
            placeholder={
              apiKeyConfigured
                ? "Using ANTHROPIC_API_KEY from .env (or paste override)"
                : "sk-ant-api03-... (paste key for live Claude Haiku)"
            }
            value={sessionApiKey}
            onChange={(e) => onChangeSessionApiKey(e.target.value)}
          />
        </div>
      )}

      <div className="chat-stream" ref={streamRef}>
        {messages.map((msg) => (
          <div key={msg.id} className={`chat-bubble-wrap ${msg.role}`}>
            <div className={`chat-bubble ${msg.role}`}>{msg.content}</div>

            {msg.role === "assistant" &&
              ((msg.retrievedMemories && msg.retrievedMemories.length > 0) ||
                (msg.extractedCandidates && msg.extractedCandidates.length > 0)) && (
                <div className="turn-trace">
                  {msg.retrievedMemories && msg.retrievedMemories.length > 0 && (
                    <div>
                      <strong>Retrieved ({msg.retrievedMemories.length}):</strong>{" "}
                      {msg.retrievedMemories.map((rm, idx) => (
                        <span key={idx} className="trace-chip">
                          {rm.category_label}: {rm.statement}
                        </span>
                      ))}
                    </div>
                  )}
                  {msg.extractedCandidates && msg.extractedCandidates.length > 0 && (
                    <div>
                      <strong>Saved by LLM ({msg.extractedCandidates.length}):</strong>{" "}
                      {msg.extractedCandidates.map((ec, idx) => (
                        <span key={idx} className="trace-chip">
                          [{ec.category}] {ec.statement}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
          </div>
        ))}

        {sending && (
          <div className="chat-bubble-wrap assistant">
            <div className="chat-bubble assistant" style={{ color: "var(--text-muted)" }}>
              Amal is thinking and extracting memories...
            </div>
          </div>
        )}
      </div>

      <div className="chat-prompts-strip" aria-label="Sample prompts">
        {SAMPLE_PROMPTS.map((prompt, idx) => (
          <button
            key={idx}
            type="button"
            className="prompt-pill"
            onClick={() => onSendMessage(prompt)}
            disabled={sending}
          >
            {prompt.length > 56 ? `${prompt.slice(0, 56)}...` : prompt}
          </button>
        ))}
      </div>

      <form className="chat-composer" onSubmit={handleSubmit}>
        <input
          id="chat-message-input"
          type="text"
          className="chat-composer-input"
          placeholder="Message Amal or share something about your classroom..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={sending}
        />
        <button
          id="chat-send-button"
          type="submit"
          className="btn btn-primary"
          disabled={sending || !input.trim()}
        >
          Send
        </button>
      </form>
    </section>
  );
}
