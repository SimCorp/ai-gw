"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../_lib/authContext";

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";

interface CitedSource {
  contribution_id?: string;
  title: string;
  source_url?: string | null;
}

interface AskPrefill {
  title: string;
  description: string;
}

interface ChampionCard {
  developer_id: string;
  focus_areas?: string[];
  bio?: string | null;
}

interface ContentItem {
  id?: string;
  title: string;
  summary?: string | null;
  source_url?: string | null;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  type?: "text" | "ask_cta" | "champions" | "content" | "book_cta";
  prefill?: AskPrefill | null;
  cited_sources?: CitedSource[];
  champions?: ChampionCard[];
  items?: ContentItem[];
  champion_id?: string | null;
}

const STARTERS = [
  "How do I create an API key?",
  "Which model should I use?",
  "Why am I getting a 429 error?",
  "How does the semantic cache work?",
];

export default function AiHelpWidget() {
  const { token } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (open) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
      inputRef.current?.focus();
    }
  }, [open, messages]);

  async function send(text: string) {
    const userMsg: Message = { role: "user", content: text };
    const next = [...messages, userMsg];
    setMessages(next);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${ADMIN_BASE}/ai-help/chat/portal`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ messages: next, context: "portal" }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      // Supported shapes: text | ask_cta | champions | content | book_cta
      const t = data.type;
      const kind: Message["type"] =
        t === "ask_cta" || t === "champions" || t === "content" || t === "book_cta" ? t : "text";
      const body =
        kind === "ask_cta"
          ? (data.message ?? data.reply ?? data.content ?? "")
          : (data.reply ?? data.content ?? data.message ?? "");
      setMessages([
        ...next,
        {
          role: "assistant",
          content: body,
          type: kind,
          prefill: kind === "ask_cta" ? (data.prefill ?? null) : null,
          cited_sources: Array.isArray(data.cited_sources) ? data.cited_sources : [],
          champions: Array.isArray(data.champions) ? data.champions : undefined,
          items: Array.isArray(data.items) ? data.items : undefined,
          champion_id: data.champion_id ?? null,
        },
      ]);
    } catch {
      setMessages([...next, { role: "assistant", content: "Sorry, I couldn't reach the AI backend right now. Try again in a moment." }]);
    } finally {
      setLoading(false);
    }
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (input.trim()) send(input.trim());
    }
  }

  return (
    <>
      {/* Floating button */}
      <button
        onClick={() => setOpen(v => !v)}
        title="AI Help"
        style={{
          position: "fixed", bottom: 24, right: 24, zIndex: 1000,
          width: 44, height: 44, borderRadius: "50%",
          background: "var(--accent)",
          border: "none", cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: "0 2px 12px rgba(0,0,0,0.18)",
          color: "#fff", fontSize: 20,
          transition: "transform 0.15s",
        }}
        onMouseEnter={e => (e.currentTarget.style.transform = "scale(1.08)")}
        onMouseLeave={e => (e.currentTarget.style.transform = "scale(1)")}
      >
        {open ? "✕" : "✦"}
      </button>

      {/* Chat panel */}
      {open && (
        <div style={{
          position: "fixed", bottom: 80, right: 24, zIndex: 999,
          width: 360, maxHeight: "70vh",
          display: "flex", flexDirection: "column",
          background: "var(--surface, #fff)",
          border: "1px solid var(--rule, #e5e7eb)",
          borderRadius: 12,
          boxShadow: "0 8px 32px rgba(0,0,0,0.14)",
          overflow: "hidden",
        }}>
          {/* Header */}
          <div style={{
            padding: "12px 16px",
            borderBottom: "1px solid var(--rule, #e5e7eb)",
            display: "flex", alignItems: "center", gap: 10,
            background: "var(--surface-soft, rgba(10,123,215,0.04))",
          }}>
            <span style={{ fontSize: 18 }}>✦</span>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13.5 }}>Gateway Assistant</div>
              <div style={{ fontSize: 11.5, color: "var(--fg-3, #888)" }}>Ask me anything about the portal</div>
            </div>
          </div>

          {/* Messages */}
          <div style={{ flex: 1, overflowY: "auto", padding: "12px 14px", display: "flex", flexDirection: "column", gap: 10 }}>
            {messages.length === 0 && (
              <div>
                <div style={{ fontSize: 12.5, color: "var(--fg-3, #888)", marginBottom: 10 }}>
                  Quick questions:
                </div>
                {STARTERS.map(s => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    style={{
                      display: "block", width: "100%", textAlign: "left",
                      padding: "7px 10px", marginBottom: 4,
                      background: "var(--surface-soft, rgba(0,0,0,0.04))",
                      border: "1px solid var(--rule, #e5e7eb)",
                      borderRadius: 8, cursor: "pointer",
                      fontSize: 12.5, color: "var(--fg-1, #111)",
                      fontFamily: "inherit",
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} style={{
                display: "flex",
                flexDirection: "column",
                alignItems: m.role === "user" ? "flex-end" : "flex-start",
              }}>
                <div style={{
                  maxWidth: "85%",
                  padding: "8px 12px",
                  borderRadius: m.role === "user" ? "12px 12px 2px 12px" : "12px 12px 12px 2px",
                  background: m.role === "user"
                    ? "var(--accent)"
                    : "var(--surface-soft, rgba(0,0,0,0.06))",
                  color: m.role === "user" ? "#fff" : "var(--fg-1, #111)",
                  fontSize: 13,
                  lineHeight: 1.5,
                  whiteSpace: "pre-wrap",
                }}>
                  {m.content}
                </div>
                {m.role === "assistant" && m.type === "ask_cta" && m.prefill && (
                  <button
                    onClick={() => {
                      const qs = new URLSearchParams({
                        title: m.prefill?.title ?? "",
                        description: m.prefill?.description ?? "",
                      });
                      setOpen(false);
                      router.push(`/champions/asks/new?${qs.toString()}`);
                    }}
                    style={{
                      marginTop: 6,
                      padding: "6px 12px",
                      background: "var(--accent)",
                      color: "#fff",
                      border: "none",
                      borderRadius: 8,
                      cursor: "pointer",
                      fontSize: 12.5,
                      fontFamily: "inherit",
                    }}
                  >
                    Ask a champion →
                  </button>
                )}
                {m.role === "assistant" && m.type === "champions" && m.champions && m.champions.length > 0 && (
                  <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 6, width: "100%" }}>
                    {m.champions.map((c) => (
                      <a
                        key={c.developer_id}
                        href={`/champions/${c.developer_id}`}
                        onClick={() => setOpen(false)}
                        style={{
                          display: "block",
                          padding: "8px 10px",
                          border: "1px solid var(--rule, #e5e7eb)",
                          borderRadius: 8,
                          background: "var(--surface, #fff)",
                          textDecoration: "none",
                          color: "var(--fg-1, #111)",
                        }}
                      >
                        <div style={{ fontSize: 12.5, fontWeight: 600 }}>
                          Champion {c.developer_id.slice(0, 8)}
                        </div>
                        {c.focus_areas && c.focus_areas.length > 0 && (
                          <div style={{ marginTop: 4, display: "flex", flexWrap: "wrap", gap: 4 }}>
                            {c.focus_areas.map((f) => (
                              <span key={f} style={{
                                fontSize: 10.5, padding: "1px 6px", borderRadius: 999,
                                background: "rgba(10,123,215,0.10)",
                                color: "var(--accent)",
                              }}>{f}</span>
                            ))}
                          </div>
                        )}
                      </a>
                    ))}
                  </div>
                )}

                {m.role === "assistant" && m.type === "content" && m.items && m.items.length > 0 && (
                  <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 6, width: "100%" }}>
                    {m.items.map((it, j) => (
                      <div
                        key={it.id ?? j}
                        style={{
                          padding: "8px 10px",
                          border: "1px solid var(--rule, #e5e7eb)",
                          borderRadius: 8,
                          background: "var(--surface, #fff)",
                        }}
                      >
                        <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--fg-1, #111)" }}>{it.title}</div>
                        {it.summary && (
                          <div style={{ fontSize: 11.5, color: "var(--fg-3, #666)", marginTop: 3, lineHeight: 1.5 }}>{it.summary}</div>
                        )}
                        {it.source_url && (
                          <a
                            href={it.source_url}
                            target="_blank"
                            rel="noreferrer noopener"
                            style={{ fontSize: 11, color: "var(--accent)", marginTop: 4, display: "inline-block" }}
                          >
                            Open source →
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {m.role === "assistant" && m.type === "book_cta" && m.champion_id && (
                  <button
                    onClick={() => {
                      setOpen(false);
                      router.push(`/champions/${m.champion_id}`);
                    }}
                    style={{
                      marginTop: 6,
                      padding: "6px 12px",
                      background: "var(--accent)",
                      color: "#fff",
                      border: "none",
                      borderRadius: 8,
                      cursor: "pointer",
                      fontSize: 12.5,
                      fontFamily: "inherit",
                    }}
                  >
                    Open profile →
                  </button>
                )}

                {m.role === "assistant" && m.cited_sources && m.cited_sources.length > 0 && (
                  <div style={{ marginTop: 6, display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {m.cited_sources.map((s, j) => {
                      const label = `Source: ${s.title}`;
                      const chipStyle: React.CSSProperties = {
                        fontSize: 11,
                        padding: "2px 8px",
                        borderRadius: 999,
                        background: "var(--surface-soft, rgba(0,0,0,0.05))",
                        color: "var(--fg-3, #666)",
                        textDecoration: "none",
                        border: "1px solid var(--rule, #e5e7eb)",
                        display: "inline-block",
                      };
                      return s.source_url ? (
                        <a
                          key={j}
                          href={s.source_url}
                          target="_blank"
                          rel="noreferrer noopener"
                          style={chipStyle}
                        >
                          {label}
                        </a>
                      ) : (
                        <span key={j} style={chipStyle}>{label}</span>
                      );
                    })}
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div style={{ color: "var(--fg-3, #888)", fontSize: 13, fontStyle: "italic" }}>
                Thinking…
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div style={{
            padding: "10px 12px",
            borderTop: "1px solid var(--rule, #e5e7eb)",
            display: "flex", gap: 8, alignItems: "flex-end",
          }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder="Ask a question… (Enter to send)"
              rows={1}
              disabled={loading}
              style={{
                flex: 1, resize: "none", border: "1px solid var(--rule, #e5e7eb)",
                borderRadius: 8, padding: "7px 10px",
                fontSize: 13, fontFamily: "inherit",
                background: "var(--surface, #fff)", color: "var(--fg-1, #111)",
                outline: "none", lineHeight: 1.4,
                maxHeight: 100, overflowY: "auto",
              }}
            />
            <button
              onClick={() => { if (input.trim()) send(input.trim()); }}
              disabled={loading || !input.trim()}
              style={{
                padding: "7px 14px",
                background: "var(--accent)",
                color: "#fff", border: "none", borderRadius: 8,
                cursor: loading || !input.trim() ? "not-allowed" : "pointer",
                fontSize: 13, fontFamily: "inherit",
                opacity: loading || !input.trim() ? 0.5 : 1,
                flexShrink: 0,
              }}
            >
              Send
            </button>
          </div>
        </div>
      )}
    </>
  );
}
