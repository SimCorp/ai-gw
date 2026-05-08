"use client";

import React, { useState, useRef, useEffect } from "react";

const LITELLM_BASE = "http://localhost:8003";
const LITELLM_KEY = "sk-litellm-local-dev";

interface Message {
  id: string;
  role: "system" | "user" | "assistant";
  content: string;
  model?: string;
  tokensIn?: number;
  tokensOut?: number;
  latency?: string;
  streaming?: boolean;
}

interface LiteLLMModel {
  id: string;
  object: string;
  created: number;
  owned_by: string;
}

export default function PlaygroundPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [models, setModels] = useState<LiteLLMModel[]>([]);
  const [selectedModelId, setSelectedModelId] = useState<string>("");
  const [input, setInput] = useState("");
  const [panelTab, setPanelTab] = useState<"params" | "tools" | "context">("params");
  const [temperature, setTemperature] = useState(0.3);
  const [topP, setTopP] = useState(0.95);
  const [maxTokens, setMaxTokens] = useState(4096);
  const [streaming] = useState(false);
  const [useCache, setUseCache] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [modelsLoading, setModelsLoading] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);

  // Load models on mount
  useEffect(() => {
    setModelsLoading(true);
    fetch(`${LITELLM_BASE}/v1/models`, {
      headers: { Authorization: `Bearer ${LITELLM_KEY}` },
    })
      .then((r) => r.json())
      .then((data: { data: LiteLLMModel[] }) => {
        setModels(data.data);
        if (data.data.length > 0) {
          setSelectedModelId(data.data[0].id);
        }
      })
      .catch(() => {})
      .finally(() => setModelsLoading(false));
  }, []);

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isLoading || !selectedModelId) return;
    const userMsg: Message = { id: `u${Date.now()}`, role: "user", content: input.trim() };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput("");
    setIsLoading(true);

    // Add placeholder for assistant response
    const assistantId = `a${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", model: selectedModelId, content: "", streaming: true },
    ]);

    const startTime = Date.now();
    try {
      const apiMessages = newMessages
        .filter((m) => m.role !== "system" || false)
        .map((m) => ({ role: m.role, content: m.content }));

      const r = await fetch(`${LITELLM_BASE}/v1/chat/completions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${LITELLM_KEY}`,
        },
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
        throw new Error(`HTTP ${r.status}: ${errorText}`);
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
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: `Error: ${e}`, streaming: false, model: selectedModelId }
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

  return (
    <main style={{ padding: 0, maxWidth: "none", flex: 1, minWidth: 0 }}>
      <style>{`
        @keyframes blink { 50% { opacity: 0; } }
        .pg-grid { display:grid; grid-template-columns:1fr 320px; height:100vh; }
        .pg-main { display:grid; grid-template-rows:56px 1fr 180px; border-right:1px solid var(--rule); min-width:0; }
        .pg-bar { display:flex; align-items:center; gap:10px; padding:0 16px; border-bottom:1px solid var(--rule); background:var(--surface); min-width:0; }
        .pg-bar h2 { font-size:14px; font-weight:600; margin:0; flex:1; min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .pg-bar .saved { font-size:11px; color:var(--fg-3); white-space:nowrap; flex-shrink:0; }
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
        .field textarea, .field select, .field input[type=number] { border:1px solid var(--rule); border-radius:6px; padding:6px 9px; font-size:12.5px; font-family:inherit; background:var(--surface); color:var(--fg-1); outline:none; width:100%; }
        .field textarea { font-family:var(--font-mono); font-size:12px; min-height:80px; resize:vertical; line-height:1.5; }
        .tog { width:28px; height:16px; background:var(--surface-soft); border:1px solid var(--rule); border-radius:9px; position:relative; cursor:pointer; flex-shrink:0; display:inline-block; }
        .tog::after { content:""; position:absolute; top:1px; left:1px; width:12px; height:12px; border-radius:50%; background:var(--surface); box-shadow:0 1px 2px rgba(0,0,0,0.2); transition:left 100ms; }
        .tog.on { background:var(--sc-blue); border-color:var(--sc-blue); }
        .tog.on::after { left:13px; }
        .model-pick { display:flex; align-items:center; gap:8px; padding:6px 10px; border:1px solid var(--rule); border-radius:6px; background:var(--surface); cursor:pointer; font-size:12.5px; }
        .model-pick .dot { width:6px; height:6px; border-radius:50%; background:#D97757; }
        .model-pick .name { font-family:var(--font-mono); font-weight:500; }
        .model-pick .caret { color:var(--fg-3); }
        .icon-btn { width:22px; height:22px; display:grid; place-items:center; border:1px solid var(--rule); border-radius:4px; background:var(--surface); color:var(--fg-2); cursor:pointer; font-size:11px; }
        .icon-btn:hover { background:var(--surface-soft); }
        .empty-thread { display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; gap:8px; color:var(--fg-3); font-size:13px; }
      `}</style>

      <div className="pg-grid">
        <div className="pg-main">
          {/* Top bar */}
          <div className="pg-bar">
            <h2>Playground</h2>
            <div className="model-pick">
              <span className="dot" />
              <span className="name">{selectedModelId || (modelsLoading ? "Loading…" : "No model")}</span>
              <span className="caret">▾</span>
            </div>
            <button className="btn btn--sm" onClick={handleClearThread} disabled={messages.length === 0}>
              Clear
            </button>
          </div>

          {/* Thread */}
          <div className="pg-thread" ref={threadRef}>
            {messages.length === 0 ? (
              <div className="empty-thread">
                <div style={{ fontSize: 32 }}>💬</div>
                <div>Start a conversation</div>
                <div style={{ fontSize: 12 }}>Type a message below and press Send or ⌘ + Enter</div>
              </div>
            ) : (
              messages.map((msg: Message) => (
                <div key={msg.id} className={`msg msg--${msg.role}`}>
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
                    {!msg.streaming && msg.role === "assistant" && msg.tokensIn != null && (
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
              className="pg-composer__input"
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
                  <h4>Model</h4>
                  <div className="field">
                    <select
                      value={selectedModelId}
                      onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setSelectedModelId(e.target.value)}
                      disabled={modelsLoading}
                    >
                      {modelsLoading && <option value="">Loading models…</option>}
                      {models.map((m) => (
                        <option key={m.id} value={m.id}>{m.id}</option>
                      ))}
                    </select>
                  </div>
                </section>
                <section>
                  <h4>System prompt</h4>
                  <div className="field">
                    <textarea defaultValue="You are a helpful assistant." />
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
                    <input type="number" value={maxTokens} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setMaxTokens(Number(e.target.value))} />
                  </div>
                </section>
                <section>
                  <h4>Caching</h4>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12.5, marginBottom: 6 }}>
                    <span>Use semantic cache</span>
                    <span className={`tog ${useCache ? "on" : ""}`} onClick={() => setUseCache(!useCache)} />
                  </div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 12.5, marginBottom: 10 }}>
                    <span>Stream response</span>
                    <span className="tog" title="Streaming disabled (use stream: false)" />
                  </div>
                </section>
              </>
            )}
            {panelTab === "tools" && (
              <section>
                <h4>Available tools</h4>
                <p style={{ fontSize: 12.5, color: "var(--fg-3)" }}>No tools configured for this session.</p>
              </section>
            )}
            {panelTab === "context" && (
              <section>
                <h4>Context files</h4>
                <p style={{ fontSize: 12.5, color: "var(--fg-3)" }}>No context files attached.</p>
                <button className="btn btn--sm" style={{ marginTop: 4 }}>+ Add file</button>
              </section>
            )}
          </div>
        </aside>
      </div>
    </main>
  );
}
