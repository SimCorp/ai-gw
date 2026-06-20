"use client";

import React, { Suspense, useState, useRef, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { Button, EmptyState, Pill, SegmentedControl } from "@aigw/ui";
import { useAuth } from "../_lib/authContext";
import RelatedChampionContent from "../_components/RelatedChampionContent";

const CACHE_BASE = process.env.NEXT_PUBLIC_CACHE_BASE_URL ?? "http://localhost:8002";
const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";
const LEAGUE = process.env.NEXT_PUBLIC_LEAGUE_API ?? "http://localhost:8080/league";

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
  cacheHit?: boolean;
  /** Groups assistant responses born from the same send (compare mode). */
  group?: string;
  /** Column index within a compare group; col 0 is the primary model. */
  col?: number;
}

interface LiteLLMModel {
  id: string;
}

interface ChatUsage {
  prompt_tokens?: number;
  completion_tokens?: number;
}

interface StreamChunk {
  choices?: Array<{ delta?: { content?: string } }>;
  usage?: ChatUsage;
}

interface ChatCompletion {
  choices?: Array<{ message?: { content?: string } }>;
  usage?: ChatUsage;
}

/** Render `inline code` spans within a line. */
function renderInline(text: string): React.ReactNode[] {
  return text.split(/(`[^`]+`)/g).map((part, i) =>
    part.startsWith("`") && part.endsWith("`") && part.length > 2 ? (
      <code key={i}>{part.slice(1, -1)}</code>
    ) : (
      <React.Fragment key={i}>{part}</React.Fragment>
    )
  );
}

function renderContent(content: string): React.ReactNode {
  return content.split("\n").map((line, i) => <p key={i}>{renderInline(line)}</p>);
}

function AssistantBlock({ msg }: { msg: Message }) {
  return (
    <div className={`pg-asst${msg.error ? " pg-asst--error" : ""}`}>
      <div className="pg-asst__head">
        <span className="tag">{msg.model ?? "assistant"}</span>
        {msg.streaming && (
          <span className="microlabel pg-streaming">
            streaming<span className="pg-ellipsis" aria-hidden="true" />
          </span>
        )}
        {!msg.streaming && msg.cacheHit && <Pill variant="good">cache hit</Pill>}
        {!msg.streaming && msg.error && <Pill variant="bad">error</Pill>}
        {!msg.streaming && !msg.error && msg.content && (
          <button
            className="pg-copy"
            title="Copy response"
            onClick={() => navigator.clipboard.writeText(msg.content)}
          >
            ⎘
          </button>
        )}
      </div>
      <div className={`pg-asst__content${msg.error ? " mono pg-asst__content--err" : ""}`}>
        {renderContent(msg.content)}
        {msg.streaming && <span className="pg-cursor" aria-hidden="true" />}
      </div>
      {!msg.streaming && !msg.error && (msg.latency || msg.tokensIn != null) && (
        <div className="microlabel pg-asst__meta">
          {msg.latency && <span>{msg.latency}</span>}
          {msg.tokensIn != null && (
            <span>
              {msg.tokensIn.toLocaleString()} in · {(msg.tokensOut ?? 0).toLocaleString()} out
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function PlaygroundPageInner() {
  const { token, developer } = useAuth();

  const searchParams = useSearchParams();
  const challengeId = searchParams.get("challenge");
  const skillSystemPrompt = searchParams.get("skill_system_prompt");
  const skillName = searchParams.get("skill_name");
  const promptContent = searchParams.get("prompt_content");
  const promptTitle = searchParams.get("prompt_title");

  const [messages, setMessages] = useState<Message[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [selectedModelId, setSelectedModelId] = useState<string>("");
  const [compare, setCompare] = useState(false);
  const [modelBId, setModelBId] = useState<string>("");
  const [systemPrompt, setSystemPrompt] = useState("You are a helpful assistant.");
  const [input, setInput] = useState("");
  const [panelTab, setPanelTab] = useState<"params" | "tools" | "context">("params");
  const [temperature, setTemperature] = useState(0.3);
  const [topP, setTopP] = useState(0.95);
  const [maxTokens, setMaxTokens] = useState(4096);
  const [useCache, setUseCache] = useState(true);
  const [streamEnabled, setStreamEnabled] = useState(true);
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

  // Pre-load skill system prompt when navigated from skills page
  useEffect(() => {
    if (!skillSystemPrompt) return;
    setSystemPrompt(skillSystemPrompt);
  }, [skillSystemPrompt]);

  // Pre-load prompt content when navigated from prompts library
  useEffect(() => {
    if (!promptContent) return;
    setSystemPrompt(promptContent);
  }, [promptContent]);

  // Pre-load challenge context when navigated from league page
  useEffect(() => {
    if (!challengeId) return;
    fetch(`${LEAGUE}/challenges/${challengeId}`)
      .then(r => r.ok ? r.json() : null)
      .then((ch: { title?: string; goal?: string; prompt_context?: string } | null) => {
        if (!ch) return;
        const ctx = ch.prompt_context ?? ch.goal ?? '';
        if (ctx) setSystemPrompt(`You are helping with the AI League challenge: "${ch.title ?? 'Challenge'}"\n\n${ctx}`);
      })
      .catch(() => {});
  }, [challengeId]);

  const patchMsg = (id: string, patch: Partial<Message>) =>
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)));

  /**
   * Run one chat completion against the gateway and patch the assistant
   * message in place. When streaming is on, parses OpenAI-compatible SSE
   * (`data: {...}` chunks, `[DONE]` sentinel) and appends deltas token-by-token.
   */
  const runCompletion = async (
    model: string,
    apiMessages: Array<{ role: string; content: string }>,
    assistantId: string,
    effectiveKey: string
  ) => {
    const startTime = Date.now();
    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${effectiveKey}`,
      };
      if (!useCache) headers["x-cache"] = "bypass";

      const r = await fetch(`${CACHE_BASE}/v1/chat/completions`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          model,
          messages: apiMessages,
          stream: streamEnabled,
          temperature,
          top_p: topP,
          max_tokens: maxTokens,
        }),
      });

      if (!r.ok) {
        const errorText = await r.text();
        throw new Error(`HTTP ${r.status}: ${errorText.slice(0, 300)}`);
      }

      const cacheHit = (r.headers.get("x-cache") ?? "").toUpperCase() === "HIT";
      const contentType = r.headers.get("content-type") ?? "";
      let content = "";
      let tokensIn: number | undefined;
      let tokensOut: number | undefined;

      if (streamEnabled && r.body && contentType.includes("text/event-stream")) {
        const reader = r.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        let finished = false;
        while (!finished) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const events = buf.split("\n\n");
          buf = events.pop() ?? "";
          for (const evt of events) {
            for (const line of evt.split("\n")) {
              if (!line.startsWith("data:")) continue;
              const payload = line.slice(5).trim();
              if (payload === "[DONE]") {
                finished = true;
                continue;
              }
              try {
                const chunk = JSON.parse(payload) as StreamChunk;
                const delta = chunk.choices?.[0]?.delta?.content;
                if (delta) {
                  content += delta;
                  patchMsg(assistantId, { content });
                }
                if (chunk.usage) {
                  tokensIn = chunk.usage.prompt_tokens;
                  tokensOut = chunk.usage.completion_tokens;
                }
              } catch {
                // Ignore malformed chunks
              }
            }
          }
        }
        if (!content) content = "(no response)";
      } else {
        const data = (await r.json()) as ChatCompletion;
        content = data.choices?.[0]?.message?.content ?? "(no response)";
        tokensIn = data.usage?.prompt_tokens;
        tokensOut = data.usage?.completion_tokens;
      }

      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1) + "s";
      patchMsg(assistantId, { content, streaming: false, tokensIn, tokensOut, latency: elapsed, cacheHit });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      patchMsg(assistantId, { content: msg, streaming: false, error: true });
    }
  };

  const handleSend = async () => {
    if (!input.trim() || isLoading || !selectedModelId) return;

    const effectiveKey = apiKey.trim() || "sk-dev";
    const userMsg: Message = { id: `u${Date.now()}`, role: "user", content: input.trim() };
    const history = [...messages, userMsg];
    setInput("");
    setIsLoading(true);

    // Build message list — system prompt + history. In compare mode only the
    // primary column (col 0) feeds back into the conversation context.
    const apiMessages: Array<{ role: string; content: string }> = [];
    if (systemPrompt.trim()) {
      apiMessages.push({ role: "system", content: systemPrompt.trim() });
    }
    apiMessages.push(
      ...history
        .filter((m) => m.role !== "system" && !m.error && (m.role !== "assistant" || (m.col ?? 0) === 0))
        .map((m) => ({ role: m.role, content: m.content }))
    );

    const targets = compare && modelBId ? [selectedModelId, modelBId] : [selectedModelId];
    const group = `g${Date.now()}`;
    const placeholders: Message[] = targets.map((m, i) => ({
      id: `a${Date.now()}-${i}`,
      role: "assistant",
      model: m,
      content: "",
      streaming: true,
      group,
      col: i,
    }));
    setMessages([...history, ...placeholders]);

    await Promise.allSettled(
      targets.map((m, i) => runCompletion(m, apiMessages, placeholders[i].id, effectiveKey))
    );
    setIsLoading(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") handleSend();
  };

  const handleClearThread = () => {
    setMessages([]);
  };

  const toggleCompare = () => {
    setCompare((c) => {
      const next = !c;
      if (next && !modelBId) {
        setModelBId(models.find((m) => m !== selectedModelId) ?? selectedModelId);
      }
      return next;
    });
  };

  const needsKey = !apiKey.trim();

  // Group consecutive assistant messages from the same send so compare-mode
  // responses render side-by-side.
  const blocks: React.ReactNode[] = [];
  for (let i = 0; i < messages.length; i++) {
    const m = messages[i];
    if (m.role === "assistant") {
      const grp = [m];
      while (
        i + 1 < messages.length &&
        messages[i + 1].role === "assistant" &&
        m.group != null &&
        messages[i + 1].group === m.group
      ) {
        grp.push(messages[++i]);
      }
      blocks.push(
        grp.length > 1 ? (
          <div key={m.group ?? m.id} className="pg-compare">
            {grp.map((g) => (
              <AssistantBlock key={g.id} msg={g} />
            ))}
          </div>
        ) : (
          <AssistantBlock key={m.id} msg={m} />
        )
      );
    } else if (m.role === "user") {
      blocks.push(
        <div key={m.id} className="pg-user">
          <div className="microlabel pg-user__role">You</div>
          <div className="pg-user__content">{m.content}</div>
        </div>
      );
    }
  }

  return (
    <main className="pmain" style={{ flex: 1, minWidth: 0 }}>
      <style>{`
        @keyframes pg-blink { 50% { opacity: 0; } }
        @keyframes pg-dots { 0% { content: ""; } 25% { content: "."; } 50% { content: ".."; } 75% { content: "..."; } }
        .pg-grid { display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: var(--gap-card); align-items: start; }
        @media (max-width: 900px) { .pg-grid { grid-template-columns: 1fr; } }

        .pg-params { max-height: calc(100vh - 230px); min-height: 420px; overflow-y: auto; }
        .pg-params section { margin-bottom: 20px; }
        .pg-params section:last-child { margin-bottom: 0; }
        .pg-params .microlabel { display: block; margin-bottom: 8px; }
        .field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
        .field:last-child { margin-bottom: 0; }
        .field textarea { font-family: var(--font-mono); font-size: 12px; min-height: 88px; resize: vertical; line-height: 1.5; }
        .field select { font-family: var(--font-mono); font-size: 12px; width: 100%; }
        .field input[type=range] { width: 100%; padding: 0; background: transparent; border: 0; }
        .field__row { display: flex; justify-content: space-between; align-items: baseline; font-size: 12px; color: var(--fg-2); }
        .field__row .val { font-family: var(--font-mono); font-size: 11.5px; color: var(--fg-1); }
        .opt-row { display: flex; align-items: center; justify-content: space-between; font-size: 12.5px; color: var(--fg-1); margin-bottom: 10px; }
        .opt-row:last-child { margin-bottom: 0; }
        .opt-hint { font-size: 11px; color: var(--fg-3); margin-top: 2px; }
        .tog { width: 30px; height: 17px; background: var(--surface-soft); border: 1px solid var(--rule-strong); border-radius: var(--radius-pill); position: relative; cursor: pointer; flex-shrink: 0; display: inline-block; transition: background 120ms, border-color 120ms; }
        .tog::after { content: ""; position: absolute; top: 1px; left: 1px; width: 13px; height: 13px; border-radius: 50%; background: var(--surface); box-shadow: var(--shadow-1); transition: left 120ms; }
        .tog.on { background: var(--accent); border-color: var(--accent); }
        .tog.on::after { left: 14px; background: var(--accent-fg); }

        .pg-chat { display: flex; flex-direction: column; height: calc(100vh - 230px); min-height: 420px; }
        .pg-thread { flex: 1; overflow-y: auto; padding: 18px; display: flex; flex-direction: column; gap: 14px; background: var(--surface-2); border-radius: var(--radius-3) var(--radius-3) 0 0; }

        .pg-user { margin-left: auto; max-width: 78%; background: var(--accent-soft); border-left: 3px solid var(--accent); border-radius: var(--radius-2); padding: 9px 13px; }
        .pg-user__role { margin-bottom: 3px; }
        .pg-user__content { font-size: 13.5px; line-height: 1.6; color: var(--fg-1); white-space: pre-wrap; }

        .pg-asst { max-width: 92%; background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius-2); box-shadow: var(--shadow-1); padding: 11px 14px; min-width: 0; }
        .pg-asst--error { border-color: var(--bad); }
        .pg-asst__head { display: flex; align-items: center; gap: 8px; margin-bottom: 7px; }
        .pg-asst__content { font-size: 13.5px; line-height: 1.6; color: var(--fg-1); }
        .pg-asst__content p { margin: 0 0 6px; }
        .pg-asst__content p:last-child { margin-bottom: 0; }
        .pg-asst__content code { background: var(--surface-soft); padding: 1px 5px; border-radius: 3px; font-size: 12px; font-family: var(--font-mono); }
        .pg-asst__content--err { color: var(--bad); font-size: 12px; }
        .pg-asst__meta { display: flex; gap: 12px; margin-top: 8px; padding-top: 7px; border-top: 1px solid var(--rule); }
        .pg-compare { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        @media (max-width: 900px) { .pg-compare { grid-template-columns: 1fr; } }
        .pg-compare .pg-asst { max-width: none; }
        .pg-copy { margin-left: auto; width: 22px; height: 22px; display: grid; place-items: center; border: 1px solid var(--rule); border-radius: var(--radius-1); background: var(--surface); color: var(--fg-2); cursor: pointer; font-size: 11px; }
        .pg-copy:hover { background: var(--surface-soft); }

        .pg-streaming { color: var(--accent-text); }
        .pg-ellipsis::after { display: inline-block; content: "..."; width: 1.2em; text-align: left; animation: pg-dots 1.2s steps(1, end) infinite; }
        .pg-cursor { display: inline-block; width: 7px; height: 13px; background: var(--accent); vertical-align: -2px; margin-left: 2px; animation: pg-blink 1s steps(2) infinite; }
        @media (prefers-reduced-motion: reduce) {
          .pg-ellipsis::after { animation: none; }
          .pg-cursor { animation: none; opacity: 0.5; }
        }

        .pg-composer { border-top: 1px solid var(--rule); background: var(--surface); padding: 12px 16px; display: flex; flex-direction: column; gap: 8px; border-radius: 0 0 var(--radius-3) var(--radius-3); }
        .pg-composer textarea { width: 100%; min-height: 64px; resize: none; font-family: inherit; }
        .pg-composer__bar { display: flex; align-items: center; gap: 10px; }
        .pg-composer__hint { margin-left: auto; font-size: 11px; color: var(--fg-3); display: flex; align-items: center; gap: 4px; }

        .pg-banner { border-radius: var(--radius-2); padding: 9px 13px; font-size: 12.5px; }
        .pg-banner--key { background: var(--warn-soft); border: 1px solid var(--warn); color: var(--fg-2); }
        .pg-banner--key a { color: var(--accent-text); }
        .pg-banner--info { background: var(--accent-soft); border: 1px solid var(--accent); color: var(--accent-text); }

        .pg-session { font-size: 12px; color: var(--fg-2); line-height: 1.8; }
        .pg-session .mono { font-size: 11.5px; color: var(--fg-1); word-break: break-all; }
      `}</style>

      <div className="phero">
        <div>
          <h1>Playground</h1>
          <p>
            Test prompts against gateway models. Requests flow through the{" "}
            <strong>semantic cache</strong> exactly like SDK traffic.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {!useCache && <span className="tag">cache bypass</span>}
          {compare && modelBId && <Pill variant="info">compare</Pill>}
          <Button size="sm" onClick={handleClearThread} disabled={messages.length === 0}>
            Clear thread
          </Button>
        </div>
      </div>

      <div className="pg-grid">
        {/* Params panel */}
        <aside className="card pg-params">
          <div className="card__body">
            <section>
              <SegmentedControl
                options={[
                  { label: "Params", value: "params" },
                  { label: "Tools", value: "tools" },
                  { label: "Context", value: "context" },
                ]}
                value={panelTab}
                onChange={(v) => setPanelTab(v as "params" | "tools" | "context")}
              />
            </section>

            {panelTab === "params" && (
              <>
                <section>
                  <span className="microlabel">API key</span>
                  <div className="field">
                    <input
                      type="password"
                      className="input mono"
                      placeholder="sk-…  (from your Keys page)"
                      value={apiKey}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => setApiKey(e.target.value)}
                      autoComplete="off"
                    />
                    {apiKeySource === "auto" && !apiKey && (
                      <span className="opt-hint">Using dev passthrough. Paste your actual key above.</span>
                    )}
                  </div>
                </section>

                <section>
                  <span className="microlabel">Model</span>
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
                  <div className="opt-row">
                    <span>Compare models</span>
                    <span
                      className={`tog ${compare ? "on" : ""}`}
                      onClick={toggleCompare}
                      role="switch"
                      aria-checked={compare}
                      aria-label="Compare models"
                    />
                  </div>
                  {compare && (
                    <div className="field">
                      <span className="microlabel" style={{ marginBottom: 0 }}>Model B</span>
                      <select
                        value={modelBId}
                        onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setModelBId(e.target.value)}
                        disabled={modelsLoading}
                      >
                        {models.map((id) => (
                          <option key={id} value={id}>{id}</option>
                        ))}
                      </select>
                    </div>
                  )}
                </section>

                <section>
                  <span className="microlabel">System prompt</span>
                  <div className="field">
                    <textarea
                      value={systemPrompt}
                      onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setSystemPrompt(e.target.value)}
                      placeholder="You are a helpful assistant."
                    />
                  </div>
                </section>

                <section>
                  <span className="microlabel">Sampling</span>
                  <div className="field">
                    <div className="field__row">
                      <span>Temperature</span>
                      <span className="val">{temperature.toFixed(2)}</span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={temperature}
                      style={{ accentColor: "var(--accent)" }}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTemperature(Number(e.target.value))}
                    />
                  </div>
                  <div className="field">
                    <div className="field__row">
                      <span>Top-p</span>
                      <span className="val">{topP.toFixed(2)}</span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={topP}
                      style={{ accentColor: "var(--accent)" }}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTopP(Number(e.target.value))}
                    />
                  </div>
                  <div className="field">
                    <div className="field__row">
                      <span>Max tokens</span>
                      <span className="val">{maxTokens.toLocaleString()}</span>
                    </div>
                    <input
                      type="range"
                      min={256}
                      max={32768}
                      step={256}
                      value={maxTokens}
                      style={{ accentColor: "var(--accent)" }}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => setMaxTokens(Number(e.target.value))}
                    />
                  </div>
                </section>

                <section>
                  <span className="microlabel">Options</span>
                  <div className="opt-row">
                    <span>Stream responses</span>
                    <span
                      className={`tog ${streamEnabled ? "on" : ""}`}
                      onClick={() => setStreamEnabled(!streamEnabled)}
                      role="switch"
                      aria-checked={streamEnabled}
                      aria-label="Stream responses"
                    />
                  </div>
                  <div className="opt-row">
                    <span>Semantic cache</span>
                    <span
                      className={`tog ${useCache ? "on" : ""}`}
                      onClick={() => setUseCache(!useCache)}
                      role="switch"
                      aria-checked={useCache}
                      aria-label="Semantic cache"
                    />
                  </div>
                  <div className="opt-hint">
                    {useCache
                      ? "Cache enabled — repeated prompts return instantly."
                      : "Cache bypassed — always hits the model."}
                  </div>
                </section>
              </>
            )}

            {panelTab === "tools" && (
              <section>
                <span className="microlabel">Available tools</span>
                <p style={{ fontSize: 12.5, color: "var(--fg-3)", margin: 0 }}>
                  Tool definitions coming soon. Use the API directly to pass <code className="mono">tools</code>.
                </p>
              </section>
            )}

            {panelTab === "context" && (
              <section>
                <span className="microlabel">Session info</span>
                <div className="pg-session">
                  <div className="microlabel" style={{ marginBottom: 2 }}>Endpoint</div>
                  <div className="mono">{CACHE_BASE}/v1</div>
                  <div className="microlabel" style={{ margin: "10px 0 2px" }}>Model</div>
                  <div className="mono">{selectedModelId || "—"}</div>
                  {compare && modelBId && (
                    <>
                      <div className="microlabel" style={{ margin: "10px 0 2px" }}>Model B</div>
                      <div className="mono">{modelBId}</div>
                    </>
                  )}
                  <div className="microlabel" style={{ margin: "10px 0 2px" }}>Turns</div>
                  <div className="mono">{messages.filter((m) => m.role !== "system").length}</div>
                  <div style={{ marginTop: 12, fontSize: 11, color: "var(--fg-3)" }}>
                    Requests flow: portal → cache (:8002) → auth (:8001) → litellm (:8003) → provider
                  </div>
                </div>
              </section>
            )}
          </div>
        </aside>

        {/* Transcript + composer */}
        <section className="card pg-chat">
          <div className="pg-thread" ref={threadRef}>
            {needsKey && (
              <div className="pg-banner pg-banner--key">
                Paste your API key in the panel to authenticate requests.{" "}
                <a href="/keys">Get a key →</a>
              </div>
            )}
            {challengeId && (
              <div className="pg-banner pg-banner--info">
                League challenge loaded — system prompt pre-set. Make your attempt.
              </div>
            )}
            {skillName && !challengeId && (
              <div className="pg-banner pg-banner--info">
                Skill loaded: <strong>{skillName}</strong> — system prompt pre-set.
              </div>
            )}
            {promptTitle && !challengeId && (
              <div className="pg-banner pg-banner--info">
                Prompt loaded: <strong>{promptTitle}</strong> — set as system prompt.
              </div>
            )}
            {messages.length === 0 ? (
              <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <EmptyState
                  title="Start a conversation"
                  description="Type a message below — responses stream straight from the gateway."
                />
              </div>
            ) : (
              blocks
            )}
          </div>

          <div className="pg-composer">
            <textarea
              className="input"
              placeholder={selectedModelId ? "Ask anything…" : "Select a model first"}
              value={input}
              disabled={!selectedModelId || isLoading}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
            />
            <div className="pg-composer__bar">
              <span className="pg-composer__hint">
                <span className="kbd">⌘</span>+<span className="kbd">↵</span> to send
              </span>
              <Button
                variant="primary"
                onClick={handleSend}
                disabled={isLoading || !input.trim() || !selectedModelId}
              >
                {isLoading ? "Sending…" : "Send"}
              </Button>
            </div>
          </div>
        </section>
      </div>
      <RelatedChampionContent tags={["playground", "prompts"]} />
    </main>
  );
}

export default function PlaygroundPage() {
  return (
    <Suspense>
      <PlaygroundPageInner />
    </Suspense>
  );
}
