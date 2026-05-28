"use client";

import React, { useState, useRef, useEffect } from "react";
import { useAuth } from "../_lib/authContext";
import RelatedChampionContent from "../_components/RelatedChampionContent";

const CACHE_BASE = process.env.NEXT_PUBLIC_CACHE_BASE_URL ?? "http://localhost:8002";
const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";

// Fallback model list when the gateway is unreachable
const FALLBACK_MODELS = [
  "claude-sonnet-4-6",
  "claude-opus-4-7",
  "claude-haiku-4-5",
  "gpt-4o",
  "gpt-4o-mini",
];

interface Message {
  id: string;
  role: "system" | "user" | "assistant";
  content: string;
  model?: string;
  tokensIn?: number;
  tokensOut?: number;
  latency?: string;
  streaming?: boolean;
  error?: boolean;
}

interface LiteLLMModel {
  id: string;
}

export default function PlaygroundPage() {
  const { token, developer } = useAuth();

  const [messages, setMessages] = useState<Message[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [selectedModelId, setSelectedModelId] = useState<string>("");
  const [systemPrompt, setSystemPrompt] = useState("You are a helpful assistant.");
  const [input, setInput] = useState("");
  const [panelTab, setPanelTab] = useState<"params" | "tools" | "context">("params");
  const [temperature, setTemperature] = useState(0.3);
  const [topP, setTopP] = useState(0.95);
  const [maxTokens, setMaxTokens] = useState(4096);
  const [useCache, setUseCache] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [apiKeySource, setApiKeySource] = useState<"auto" | "manual">("auto");
  const threadRef = useRef<HTMLDivElement>(null);

  // Try to load the developer's first active API key from the portal
  useEffect(() => {
    if (!token || !developer?.team_id) return;
    fetch(`${ADMIN_BASE}/teams/${developer.team_id}/keys`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : []))
      .then((keys: Array<{ revoked_at: string | null; key_hash?: string; key_prefix?: string; prefix?: string }>) => {
        const active = keys.find((k) => !k.revoked_at);
        if (active) {
          setApiKeySource("auto");
        }
      })
      .catch(() => {});
  }, [token, developer?.team_id]);

  // Load models — try gateway first, fall back to static list
  useEffect(() => {
    setModelsLoading(true);
    const headers: Record<string, string> = {};
    const effectiveKey = apiKey.trim() || "sk-dev";
    headers["Authorization"] = `Bearer ${effectiveKey}`;

    fetch(`${CACHE_BASE}/v1/models`, { headers })
      .then((r) => (r.ok ? r.json() : { data: [] }))
      .then((data: { data: LiteLLMModel[] }) => {
        const ids = (data.data ?? []).map((m: LiteLLMModel) => m.id).filter(Boolean);
        const list = ids.length > 0 ? ids : FALLBACK_MODELS;
        setModels(list);
        if (!selectedModelId || !list.includes(selectedModelId)) {
          setSelectedModelId(list[0] ?? "");
        }
      })
      .catch(() => {
        setModels(FALLBACK_MODELS);
        if (!selectedModelId) setSelectedModelId(FALLBACK_MODELS[0]);
      })
      .finally(() => setModelsLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiKey]);

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading || !selectedModelId) return;

    const effectiveKey = apiKey.trim() || "sk-dev";
    const userMsg: Message = { id: `u${Date.now()}`, role: "user", content: input.trim() };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput("");
    setIsLoading(true);

    const assistantId = `a${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", model: selectedModelId, content: "", streaming: true },
    ]);

    const startTime = Date.now();
    try {
      // Build message list — include system prompt if set
      const apiMessages: Array<{ role: string; content: string }> = [];
      if (systemPrompt.trim()) {
        apiMessages.push({ role: "system", content: systemPrompt.trim() });
      }
      apiMessages.push(
        ...newMessages
          .filter((m) => m.role !== "system")
          .map((m) => ({ role: m.role, content: m.content }))
      );

      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${effectiveKey}`,
      };
      if (!useCache) headers["x-cache"] = "bypass";

      const r = await fetch(`${CACHE_BASE}/v1/chat/completions`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          model: selectedModelId,
          messages: apiMessages,
          stream: false,
          temperature,
          top_p: topP,
          max_tokens: maxTokens,
        }),
      });

      if (!r.ok) {
        const errorText = await r.text();
        throw new Error(`HTTP ${r.status}: ${errorText.slice(0, 300)}`);
      }

      const data = await r.json();
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1) + "s";
      const content = data.choices?.[0]?.message?.content ?? "(no response)";
      const tokensIn = data.usage?.prompt_tokens;
      const tokensOut = data.usage?.completion_tokens;

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content, streaming: false, tokensIn, tokensOut, latency: elapsed, model: selectedModelId }
            : m
        )
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: msg, streaming: false, model: selectedModelId, error: true }
            : m
        )
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") handleSend();
  };

  const handleClearThread = () => {
    setMessages([]);
  };

  const needsKey = !apiKey.trim();

  return (
    <main style={{ padding: 0, maxWidth: "none", flex: 1, minWidth: 0 }}>
      <style>{`
        @keyframes blink { 50% { opacity: 0; } }
        .pg-grid { display:grid; grid-template-columns:1fr 320px; height:100vh; }
        .pg-main { display:grid; grid-template-rows:56px 1fr 180px; border-right:1px solid var(--rule); min-width:0; }
        .pg-bar { display:flex; align-items:center; gap:10px; padding:0 16px; border-bottom:1px solid var(--rule); background:var(--surface); min-width:0; }
        .pg-bar h2 { font-size:14px; font-weight:600; margin:0; flex:1; min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .pg-thread { overflow-y:auto; padding:24px 28px; background:var(--surface-2); }
        .msg { display:flex; gap:14px; margin-bottom:22px; max-width:820px; }
        .msg__avatar { width:28px; height:28px; border-radius:7px; display:grid; place-items:center; font-weight:600; font-size:11px; color:#fff; flex-shrink:0; margin-top:2px; }
        .msg__body { flex:1; min-width:0; }
        .msg__role { font-size:11.5px; font-weight:600; text-transform:uppercase; letter-spacing:0.04em; color:var(--fg-2); margin-bottom:4px; }
        .msg__content { font-size:14px; line-height:1.6; color:var(--fg-1); }
        .msg__content p { margin:0 0 10px; }
        .msg__content code { background:var(--surface-soft); padding:1px 5px; border-radius:3px; font-size:12.5px; font-family:var(--font-mono); }
        .msg__content ul { margin:0 0 10px 18px; }
        .msg__content li { margin-bottom:4px; }
        .msg__meta { font-size:11px; color:var(--fg-3); margin-top:6px; display:flex; gap:14px; align-items:center; }
        .msg--system .msg__avatar { background:var(--fg-3); }
        .msg--user .msg__avatar { background:#1D958E; }
        .msg--assistant .msg__avatar { background:linear-gradient(135deg,#D97757,#B8541F); }
        .msg--error .msg__content { color:var(--warn, #c0392b); font-family:var(--font-mono); font-size:12px; }
        .pg-composer { border-top:1px solid var(--rule); background:var(--surface); padding:14px 20px; display:flex; flex-direction:column; gap:10px; }
        .pg-composer textarea { border:1px solid var(--rule); border-radius:8px; padding:10px 12px; font-size:14px; min-height:60px; font-family:inherit; resize:none; outline:none; background:var(--surface); color:var(--fg-1); width:100%; }
        .pg-composer textarea:focus { border-color:var(--sc-blue); box-shadow:0 0 0 3px var(--sc-blue-soft); }
        .pg-composer__bar { display:flex; align-items:center; gap:8px; }
        .pg-panel { background:var(--surface); overflow-y:auto; display:flex; flex-direction:column; }
        .pg-panel__tabs { display:flex; border-bottom:1px solid var(--rule); }
        .pg-panel__tabs button { flex:1; background:none; border:0; padding:12px 0; font-size:12.5px; font-weight:500; color:var(--fg-2); cursor:pointer; border-bottom:2px solid transparent; }
        .pg-panel__tabs button.is-active { color:var(--fg-1); border-bottom-color:var(--sc-blue); }
        .pg-panel__body { padding:16px 18px; flex:1; }
        .pg-panel__body section { margin-bottom:22px; }
        .pg-panel__body h4 { font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:0.06em; color:var(--fg-2); margin:0 0 10px; }
        .field { display:flex; flex-direction:column; gap:5px; margin-bottom:12px; }
        .field label { font-size:12px; color:var(--fg-2); font-weight:500; display:flex; justify-content:space-between; }
        .field label .val { font-family:var(--font-mono); color:var(--fg-1); }
        .field input[type=range] { width:100%; accent-color:var(--sc-blue); }
        .field textarea, .field select, .field input[type=number], .field input[type=text], .field input[type=password] { border:1px solid var(--rule); border-radius:6px; padding:6px 9px; font-size:12.5px; font-family:inherit; background:var(--surface); color:var(--fg-1); outline:none; width:100%; }
        .field textarea { font-family:var(--font-mono); font-size:12px; min-height:80px; resize:vertical; line-height:1.5; }
        .tog { width:28px; height:16px; background:var(--surface-soft); border:1px solid var(--rule); border-radius:9px; position:relative; cursor:pointer; flex-shrink:0; display:inline-block; }
        .tog::after { content:""; position:absolute; top:1px; left:1px; width:12px; height:12px; border-radius:50%; background:var(--surface); box-shadow:0 1px 2px rgba(0,0,0,0.2); transition:left 100ms; }
        .tog.on { background:var(--sc-blue); border-color:var(--sc-blue); }
        .tog.on::after { left:13px; }
        .model-pick { display:flex; align-items:center; gap:8px; padding:6px 10px; border:1px solid var(--rule); border-radius:6px; background:var(--surface); font-size:12.5px; min-width:0; overflow:hidden; }
        .model-pick .dot { width:6px; height:6px; border-radius:50%; background:#D97757; flex-shrink:0; }
        .model-pick .name { font-family:var(--font-mono); font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .icon-btn { width:22px; height:22px; display:grid; place-items:center; border:1px solid var(--rule); border-radius:4px; background:var(--surface); color:var(--fg-2); cursor:pointer; font-size:11px; }
        .icon-btn:hover { background:var(--surface-soft); }
        .empty-thread { display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; gap:8px; color:var(--fg-3); font-size:13px; }
        .key-banner { background:var(--warn-soft,rgba(255,200,0,0.1)); border:1px solid var(--warn,#e6a817); border-radius:8px; padding:10px 14px; margin-bottom:12px; font-size:12.5px; color:var(--fg-2); display:flex; align-items:center; gap:8px; }
      `}</style>

      <div className="pg-grid">
        <div className="pg-main">
          {/* Top bar */}
          <div className="pg-bar">
            <h2>Playground</h2>
            <div className="model-pick">
              <span className="dot" />
              <span className="name">{selectedModelId || (modelsLoading ? "Loading…" : "No models — check gateway")}</span>
            </div>
            {!useCache && (
              <span style={{ fontSize: 10.5, padding: "2px 6px", borderRadius: 4, background: "var(--surface-soft)", color: "var(--fg-3)", flexShrink: 0 }}>
                cache off
              </span>
            )}
            <button className="btn btn--sm" onClick={handleClearThread} disabled={messages.length === 0}>
              Clear
            </button>
          </div>

          {/* Thread */}
          <div className="pg-thread" ref={threadRef}>
            {needsKey && (
              <div className="key-banner">
                ⚠ Paste your API key in the panel → to authenticate requests.{" "}
                <a href="/portal/keys" style={{ color: "var(--sc-blue)", marginLeft: 2 }}>Get a key →</a>
              </div>
            )}
            {messages.length === 0 && !needsKey ? (
              <div className="empty-thread">
                <div style={{ fontSize: 32 }}>💬</div>
                <div>Start a conversation</div>
                <div style={{ fontSize: 12 }}>Type a message below and press Send or ⌘ + Enter</div>
              </div>
            ) : (
              messages.map((msg: Message) => (
                <div key={msg.id} className={`msg msg--${msg.role}${msg.error ? " msg--error" : ""}`}>
                  <div className="msg__avatar">
                    {msg.role === "system" ? "SYS" : msg.role === "user" ? "ME" : "A"}
                  </div>
                  <div className="msg__body">
                    <div className="msg__role">
                      {msg.role === "system" ? "System"
                        : msg.role === "user" ? "You"
                        : `Assistant${msg.model ? ` · ${msg.model}` : ""}${msg.streaming ? " · thinking…" : ""}`}
                    </div>
                    <div className="msg__content">
                      {msg.content.split("\n").map((line: string, i: number) => (
                        <p key={i} style={{ margin: "0 0 6px" }}>
                          {line.replace(/`([^`]+)`/g, "CODEMARKER$1CODEMARKEREND").split("CODEMARKER").map((part: string, j: number) => {
                            if (j % 2 === 1) return <code key={j}>{part.replace("CODEMARKEREND", "")}</code>;
                            return part.replace("CODEMARKEREND", "");
                          })}
                        </p>
                      ))}
                      {msg.streaming && (
                        <span style={{ display: "inline-block", width: 6, height: 14, background: "var(--fg-1)", verticalAlign: -2, marginLeft: 2, animation: "blink 1s steps(2) infinite" }} />
                      )}
                    </div>
                    {!msg.streaming && msg.role === "assistant" && !msg.error && msg.tokensIn != null && (
                      <div className="msg__meta">
                        <span>{msg.tokensIn.toLocaleString()} in · {msg.tokensOut?.toLocaleString()} out</span>
                        <span>{msg.latency}</span>
                        <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                          <button className="icon-btn" title="Copy" onClick={() => navigator.clipboard.writeText(msg.content)}>⎘</button>
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Composer */}
          <div className="pg-composer">
            <textarea
              placeholder={selectedModelId ? "Ask anything… (⌘ + Enter to send)" : "Select a model first"}
              value={input}
              disabled={!selectedModelId || isLoading}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
            />
            <div className="pg-composer__bar">
              <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--fg-3)" }}>⌘ + Enter to send</span>
              <button
                className="btn btn--primary"
                onClick={handleSend}
                disabled={isLoading || !input.trim() || !selectedModelId}
              >
                {isLoading ? "Sending…" : "Send"}
              </button>
            </div>
          </div>
        </div>

        {/* Right panel */}
        <aside className="pg-panel">
          <div className="pg-panel__tabs">
            {(["params", "tools", "context"] as const).map((t) => (
              <button
                key={t}
                className={panelTab === t ? "is-active" : ""}
                onClick={() => setPanelTab(t)}
              >
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </button>
            ))}
          </div>
          <div className="pg-panel__body">
            {panelTab === "params" && (
              <>
                <section>
                  <h4>API key</h4>
                  <div className="field">
                    <input
                      type="password"
                      placeholder="sk-…  (from your Keys page)"
                      value={apiKey}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => setApiKey(e.target.value)}
                      autoComplete="off"
                    />
                    {apiKeySource === "auto" && !apiKey && (
                      <span style={{ fontSize: 11, color: "var(--fg-3)", marginTop: 2 }}>
                        Using dev passthrough. Paste your actual key above.
                      </span>
                    )}
                  </div>
                </section>
                <section>
                  <h4>Model</h4>
                  <div className="field">
                    <select
                      value={selectedModelId}
                      onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setSelectedModelId(e.target.value)}
                      disabled={modelsLoading}
                    >
                      {modelsLoading && <option value="">Loading models…</option>}
                      {models.map((id) => (
                        <option key={id} value={id}>{id}</option>
                      ))}
                    </select>
                  </div>
                </section>
                <section>
                  <h4>System prompt</h4>
                  <div className="field">
                    <textarea
                      value={systemPrompt}
                      onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setSystemPrompt(e.target.value)}
                      placeholder="You are a helpful assistant."
                    />
                  </div>
                </section>
                <section>
                  <h4>Sampling</h4>
                  <div className="field">
                    <label>Temperature <span className="val">{temperature.toFixed(2)}</span></label>
                    <input type="range" min={0} max={1} step={0.05} value={temperature} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTemperature(Number(e.target.value))} />
                  </div>
                  <div className="field">
                    <label>Top-p <span className="val">{topP.toFixed(2)}</span></label>
                    <input type="range" min={0} max={1} step={0.05} value={topP} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTopP(Number(e.target.value))} />
                  </div>
                  <div className="field">
                    <label>Max tokens</label>
                    <input type="number" value={maxTokens} min={1} max={32768} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setMaxTokens(Number(e.target.value))} />
                  </div>
                </section>
                <section>
                  <h4>Options</h4>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12.5, marginBottom: 8 }}>
                    <span>Semantic cache</span>
                    <span className={`tog ${useCache ? "on" : ""}`} onClick={() => setUseCache(!useCache)} role="switch" aria-checked={useCache} />
                  </div>
                  <div style={{ fontSize: 11, color: "var(--fg-3)", marginTop: 4 }}>
                    {useCache ? "Cache enabled — repeated prompts return instantly." : "Cache bypassed — always hits the model."}
                  </div>
                </section>
              </>
            )}
            {panelTab === "tools" && (
              <section>
                <h4>Available tools</h4>
                <p style={{ fontSize: 12.5, color: "var(--fg-3)" }}>Tool definitions coming soon. Use the API directly to pass <code>tools</code>.</p>
              </section>
            )}
            {panelTab === "context" && (
              <section>
                <h4>Session info</h4>
                <div style={{ fontSize: 12, color: "var(--fg-3)", lineHeight: 1.7 }}>
                  <div><strong>Endpoint:</strong> {CACHE_BASE}/v1</div>
                  <div><strong>Model:</strong> {selectedModelId || "—"}</div>
                  <div><strong>Turns:</strong> {messages.filter(m => m.role !== "system").length}</div>
                  <div style={{ marginTop: 10, fontSize: 11 }}>
                    Requests flow: portal → cache (:8002) → auth (:8001) → litellm (:8003) → provider
                  </div>
                </div>
              </section>
            )}
          </div>
        </aside>
      </div>
      <RelatedChampionContent tags={["playground", "prompts"]} />
    </main>
  );
}
