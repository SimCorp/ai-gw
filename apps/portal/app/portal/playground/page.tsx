"use client";

import React, { useState, useRef, useEffect } from "react";

interface Message {
  id: string;
  role: "system" | "user" | "assistant";
  content: string;
  model?: string;
  tokensIn?: number;
  tokensOut?: number;
  cost?: number;
  latency?: string;
  streaming?: boolean;
  toolCall?: { name: string; args: string; result: string; latencyMs: number };
}

const INITIAL_MESSAGES: Message[] = [
  {
    id: "s1",
    role: "system",
    content: "You answer questions about the SimCorp monorepo. Cite source files with line ranges. Prefer code examples over prose. When unsure, say so and suggest where to look.",
  },
  {
    id: "u1",
    role: "user",
    content: "Where do we handle rate-limit retries in the gateway? Show me the policy and the call sites.",
  },
  {
    id: "a1",
    role: "assistant",
    model: "claude-sonnet-4.5",
    content: `I'll search the index for retry policy, then look up the call sites that wrap it.

The retry policy lives in \`services/litellm/app/retry.py\` — exponential backoff with jitter, max 3 attempts, honoring \`Retry-After\` when the upstream sets it. It's wired into the proxy at \`services/litellm/app/proxy.py:142\` and reused by the cache prefetcher at \`services/cache/app/prefetch.py:88\`.

Notable call sites:
- \`services/litellm/app/proxy.py:142\` — main request path, wraps every upstream call
- \`services/cache/app/prefetch.py:88\` — used to refresh hot keys; lower max-attempts (2)
- \`services/observability/app/forwarder.py:51\` — telemetry forwarder, retries log shipments`,
    tokensIn: 2108,
    tokensOut: 412,
    cost: 0.0124,
    latency: "1.8s",
    toolCall: { name: "retrieval.search", args: '{ "query": "rate limit retry policy", "limit": 12 }', result: "→ 12 documents · top match score 0.94", latencyMs: 428 },
  },
  {
    id: "u2",
    role: "user",
    content: "Got it — now write me a unit test that simulates 429 and asserts we back off correctly.",
  },
];

const MODELS = [
  "claude-sonnet-4.5 · Anthropic",
  "claude-haiku-4.5 · Anthropic",
  "claude-opus-4.5 · Anthropic",
  "gemini-2.5-pro · Google",
  "gpt-5 · Azure OpenAI",
  "ollama/llama-3.1-70b · BYO",
];

const MOCK_STREAM_RESPONSE = `Here's a unit test for the 429 retry behaviour:

\`\`\`python
import pytest
import time
from unittest.mock import patch, MagicMock
from services.litellm.app.retry import RetryPolicy

def test_429_exponential_backoff():
    policy = RetryPolicy(max_attempts=3, base_delay=0.1)
    mock_call = MagicMock(side_effect=[
        Exception("429 Too Many Requests"),
        Exception("429 Too Many Requests"),
        {"choices": [{"message": {"content": "ok"}}]},
    ])

    with patch("time.sleep") as mock_sleep:
        result = policy.execute(mock_call)

    assert result["choices"][0]["message"]["content"] == "ok"
    assert mock_sleep.call_count == 2
    # Check exponential backoff: first delay ~0.1s, second ~0.2s
    delays = [c.args[0] for c in mock_sleep.call_args_list]
    assert delays[1] > delays[0]
\`\`\`

This test patches \`time.sleep\` to avoid actually waiting, then asserts that the retry policy calls sleep twice (once per failed attempt) and that delays grow exponentially.`;

export default function PlaygroundPage() {
  const [messages, setMessages] = useState<Message[]>(INITIAL_MESSAGES);
  const [input, setInput] = useState("");
  const [panelTab, setPanelTab] = useState<"params" | "tools" | "context">("params");
  const [model, setModel] = useState(0);
  const [temperature, setTemperature] = useState(0.3);
  const [topP, setTopP] = useState(0.95);
  const [maxTokens, setMaxTokens] = useState(4096);
  const [streaming, setStreaming] = useState(true);
  const [useCache, setUseCache] = useState(true);
  const [isStreaming, setIsStreaming] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = () => {
    if (!input.trim() || isStreaming) return;
    const userMsg: Message = { id: `u${Date.now()}`, role: "user", content: input };
    setMessages((prev: Message[]) => [...prev, userMsg]);
    setInput("");
    setIsStreaming(true);

    // Simulate streaming
    const streamingMsg: Message = {
      id: `a${Date.now()}`,
      role: "assistant",
      model: "claude-sonnet-4.5",
      content: "",
      streaming: true,
    };
    setMessages((prev: Message[]) => [...prev, streamingMsg]);

    const words = MOCK_STREAM_RESPONSE.split(" ");
    let idx = 0;
    const iv = setInterval(() => {
      if (idx >= words.length) {
        clearInterval(iv);
        setMessages((prev: Message[]) =>
          prev.map((m: Message) =>
            m.streaming
              ? { ...m, streaming: false, content: MOCK_STREAM_RESPONSE, tokensIn: 820, tokensOut: 388, cost: 0.0089, latency: "2.1s" }
              : m
          )
        );
        setIsStreaming(false);
        return;
      }
      const chunk = words.slice(0, idx + 1).join(" ");
      setMessages((prev: Message[]) =>
        prev.map((m: Message) => (m.streaming ? { ...m, content: chunk } : m))
      );
      idx += Math.ceil(Math.random() * 3);
    }, 40);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") handleSend();
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
        .tool-call { border:1px solid var(--rule); border-radius:7px; background:var(--surface); margin:6px 0; font-size:12.5px; }
        .tool-call__head { padding:8px 12px; display:flex; align-items:center; gap:8px; border-bottom:1px solid var(--rule); background:var(--surface-soft); border-radius:7px 7px 0 0; }
        .tool-call__head .name { font-family:var(--font-mono); font-weight:600; font-size:12px; }
        .tool-call__body { padding:10px 12px; font-family:var(--font-mono); font-size:11.5px; color:var(--fg-2); }
        .pg-composer { border-top:1px solid var(--rule); background:var(--surface); padding:14px 20px; display:flex; flex-direction:column; gap:10px; }
        .pg-composer textarea { border:1px solid var(--rule); border-radius:8px; padding:10px 12px; font-size:14px; min-height:60px; font-family:inherit; resize:none; outline:none; background:var(--surface); color:var(--fg-1); width:100%; }
        .pg-composer textarea:focus { border-color:var(--sc-blue); box-shadow:0 0 0 3px var(--sc-blue-soft); }
        .pg-composer__bar { display:flex; align-items:center; gap:8px; }
        .att { display:flex; align-items:center; gap:5px; padding:4px 9px; border:1px solid var(--rule); border-radius:14px; font-size:11.5px; color:var(--fg-2); background:var(--surface); cursor:pointer; }
        .att:hover { border-color:var(--sc-blue); color:var(--sc-blue); }
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
        .meter { display:flex; flex-direction:column; gap:4px; padding:10px; border:1px solid var(--rule); border-radius:7px; background:var(--surface-2); }
        .meter .row { display:flex; justify-content:space-between; font-size:11.5px; }
        .meter .bar { height:4px; background:var(--surface-soft); border-radius:2px; overflow:hidden; position:relative; }
        .meter .bar i { position:absolute; inset:0 32% 0 0; background:var(--sc-blue); border-radius:2px; }
        .model-pick { display:flex; align-items:center; gap:8px; padding:6px 10px; border:1px solid var(--rule); border-radius:6px; background:var(--surface); cursor:pointer; font-size:12.5px; }
        .model-pick .dot { width:6px; height:6px; border-radius:50%; background:#D97757; }
        .model-pick .name { font-family:var(--font-mono); font-weight:500; }
        .model-pick .caret { color:var(--fg-3); }
        .icon-btn { width:22px; height:22px; display:grid; place-items:center; border:1px solid var(--rule); border-radius:4px; background:var(--surface); color:var(--fg-2); cursor:pointer; font-size:11px; }
        .icon-btn:hover { background:var(--surface-soft); }
      `}</style>

      <div className="pg-grid">
        <div className="pg-main">
          {/* Top bar */}
          <div className="pg-bar">
            <h2>Codebase Q&A · monorepo</h2>
            <span className="saved">Auto-saved · 2 min ago</span>
            <div className="model-pick">
              <span className="dot" />
              <span className="name">{MODELS[model].split(" · ")[0]}</span>
              <span className="caret">▾</span>
            </div>
            <button className="btn btn--sm">Compare</button>
            <button className="btn btn--sm">Share</button>
            <button className="btn btn--sm btn--primary">Export code</button>
          </div>

          {/* Thread */}
          <div className="pg-thread" ref={threadRef}>
            {messages.map((msg: Message) => (
              <div key={msg.id} className={`msg msg--${msg.role}`}>
                <div className="msg__avatar">
                  {msg.role === "system" ? "SYS" : msg.role === "user" ? "MW" : "A"}
                </div>
                <div className="msg__body">
                  <div className="msg__role">
                    {msg.role === "system" ? "System"
                      : msg.role === "user" ? "Maja Weber"
                      : `Assistant${msg.model ? ` · ${msg.model}` : ""}${msg.streaming ? " · streaming…" : ""}`}
                  </div>
                  {msg.toolCall && (
                    <div className="tool-call">
                      <div className="tool-call__head">
                        <span className="name">{msg.toolCall.name}</span>
                        <span className="muted" style={{ fontSize: 11, marginLeft: "auto" }}>{msg.toolCall.latencyMs} ms</span>
                      </div>
                      <div className="tool-call__body">{msg.toolCall.args}<br />{msg.toolCall.result}</div>
                    </div>
                  )}
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
                  {!msg.streaming && msg.role === "assistant" && msg.tokensIn && (
                    <div className="msg__meta">
                      <span>{msg.tokensIn.toLocaleString()} in · {msg.tokensOut?.toLocaleString()} out · ${msg.cost?.toFixed(4)}</span>
                      <span>{msg.latency} · cache miss</span>
                      <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                        <button className="icon-btn" title="Copy">⎘</button>
                        <button className="icon-btn" title="Regenerate">↺</button>
                        <button className="icon-btn" title="Branch">⑂</button>
                      </span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Composer */}
          <div className="pg-composer">
            <textarea
              className="pg-composer__input"
              placeholder="Ask anything, attach a file, or pick a tool…"
              value={input}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
            />
            <div className="pg-composer__bar">
              <button className="att">📎 Attach</button>
              <button className="att">🔧 Tools · 3</button>
              <button className="att">📄 monorepo-index.json</button>
              <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--fg-3)" }}>⌘ + Enter to send</span>
              <button
                className="btn btn--primary"
                onClick={handleSend}
                disabled={isStreaming || !input.trim()}
              >
                Send
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
                    <select value={model} onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setModel(Number(e.target.value))}>
                      {MODELS.map((m, i) => <option key={i} value={i}>{m}</option>)}
                    </select>
                  </div>
                  <div style={{ fontSize: 11.5, color: "var(--fg-3)", marginTop: -4 }}>200K context · $3.00/M in · $15.00/M out · vision, tools</div>
                </section>
                <section>
                  <h4>System prompt</h4>
                  <div className="field">
                    <textarea defaultValue="You answer questions about the SimCorp monorepo. Cite source files with line ranges. Prefer code examples over prose. When unsure, say so and suggest where to look." />
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
                    <span className={`tog ${streaming ? "on" : ""}`} onClick={() => setStreaming(!streaming)} />
                  </div>
                  <div className="meter">
                    <div className="row"><span>Tokens used in session</span><span className="mono">38,210 / ∞</span></div>
                    <div className="bar"><i /></div>
                    <div className="row" style={{ color: "var(--fg-3)" }}>
                      <span>~$0.42 spent</span><span>cache hit 38%</span>
                    </div>
                  </div>
                </section>
              </>
            )}
            {panelTab === "tools" && (
              <section>
                <h4>Available tools</h4>
                {[
                  { name: "retrieval.search", desc: "Semantic search over the monorepo index" },
                  { name: "github.get_diff",  desc: "Fetch PR diff by PR number" },
                  { name: "jira.create_issue",desc: "Create a Jira issue" },
                ].map((t) => (
                  <div key={t.name} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 10px", border: "1px solid var(--rule)", borderRadius: 7, marginBottom: 6, fontSize: 12.5 }}>
                    <div style={{ flex: 1, fontFamily: "var(--font-mono)", fontSize: 12 }}>{t.name}</div>
                    <div style={{ color: "var(--fg-3)", fontSize: 11 }}>{t.desc}</div>
                    <span className={`tog on`} />
                  </div>
                ))}
              </section>
            )}
            {panelTab === "context" && (
              <section>
                <h4>Context files</h4>
                {[
                  { name: "monorepo-index.json", size: "2.4 MB" },
                  { name: "services/litellm/**", size: "84 files" },
                ].map((f) => (
                  <div key={f.name} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", border: "1px solid var(--rule)", borderRadius: 7, marginBottom: 6, fontSize: 12.5 }}>
                    <span style={{ flex: 1, fontFamily: "var(--font-mono)", fontSize: 12 }}>{f.name}</span>
                    <span style={{ color: "var(--fg-3)" }}>{f.size}</span>
                    <button className="btn btn--sm btn--ghost" style={{ color: "var(--bad)" }}>×</button>
                  </div>
                ))}
                <button className="btn btn--sm" style={{ marginTop: 4 }}>+ Add file</button>
              </section>
            )}
          </div>
        </aside>
      </div>
    </main>
  );
}
