"use client";

import Link from "next/link";
import { useState, useEffect, useCallback } from "react";
import { Button, CodeBlock, EmptyState, Pill, Skeleton } from "@aigw/ui";
import { useTeam } from "../_lib/teamContext";
import { useAuth } from "../_lib/authContext";

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";
const CACHE_BASE = process.env.NEXT_PUBLIC_CACHE_BASE_URL ?? "http://localhost:8002";

const LANG_TABS = ["curl", "python", "ts", "anthropic"] as const;
type Lang = (typeof LANG_TABS)[number];

const CODE: Record<Lang, string> = {
  curl: `# Drop-in OpenAI replacement — same client, different base URL
curl https://aigw.simcorp.internal/v1/chat/completions \\
  -H "authorization: Bearer $AIGW_KEY" \\
  -H "content-type: application/json" \\
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [{"role":"user","content":"Hello from agent-platform"}],
    "stream": true
  }'`,

  python: `import os
from openai import OpenAI

client = OpenAI(
    base_url="https://aigw.simcorp.internal/v1",
    api_key=os.environ["AIGW_KEY"],
)

resp = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "Summarise Q1 EM debt flows"}],
    temperature=0.3,
)
print(resp.choices[0].message.content)`,

  ts: `import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "https://aigw.simcorp.internal/v1",
  apiKey: process.env.AIGW_KEY,
});

const resp = await client.chat.completions.create({
  model: "claude-sonnet-4-6",
  messages: [{ role: "user", content: "Hello" }],
  stream: true,
});

for await (const chunk of resp) {
  process.stdout.write(chunk.choices[0]?.delta?.content ?? "");
}`,

  anthropic: `import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic({
  baseURL: "https://aigw.simcorp.internal/anthropic",
  apiKey: process.env.AIGW_KEY,
});

const msg = await client.messages.create({
  model: "claude-sonnet-4-6",
  max_tokens: 1024,
  messages: [{ role: "user", content: "Hello" }],
});`,
};

function firstCallSnippet(key: string) {
  return `curl https://aigw-dev.lab.cloud.scdom.net/v1/chat/completions \\
  -H "authorization: Bearer ${key}" \\
  -H "content-type: application/json" \\
  -d '{"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "Hello"}]}'`;
}

interface ApiKey {
  id: string;
  team_id: string;
  name: string;
  key_hash: string;
  revoked_at: string | null;
  monthly_budget_usd: number | null;
  created_at: string;
}

function KeyVerifier({ initialKey }: { initialKey: string | null }) {
  const [keyInput, setKeyInput] = useState(initialKey ?? "");
  const [status, setStatus] = useState<"idle" | "testing" | "ok" | "error">("idle");
  const [latency, setLatency] = useState<number | null>(null);
  const [response, setResponse] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (initialKey) setKeyInput(initialKey);
  }, [initialKey]);

  const runTest = async () => {
    const key = keyInput.trim();
    if (!key) return;
    setStatus("testing");
    setResponse(null);
    setErrorMsg(null);
    const t0 = Date.now();
    try {
      const r = await fetch(`${CACHE_BASE}/v1/chat/completions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${key}`,
        },
        body: JSON.stringify({
          model: "claude-haiku-4-5",
          messages: [{ role: "user", content: "Say OK" }],
          max_tokens: 5,
        }),
      });
      const ms = Date.now() - t0;
      setLatency(ms);
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        setErrorMsg(`HTTP ${r.status}${body.detail ? `: ${body.detail}` : body.error?.message ? `: ${body.error.message}` : ""}`);
        setStatus("error");
        return;
      }
      const data = await r.json();
      const text = data.choices?.[0]?.message?.content ?? "(no content)";
      setResponse(text);
      setStatus("ok");
    } catch (e: unknown) {
      setLatency(Date.now() - t0);
      setErrorMsg(String(e));
      setStatus("error");
    }
  };

  return (
    <div className="card" style={{ marginTop: 18 }}>
      <div className="card__head">
        <h3 className="card__title">Test your key</h3>
        <span className="card__sub">verify the gateway is reachable and your key is valid</span>
      </div>
      <div className="card__body">
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="text"
            className="input mono"
            value={keyInput}
            onChange={e => setKeyInput(e.target.value)}
            placeholder="sk-..."
            style={{ flex: 1 }}
          />
          <button
            className="btn btn--primary"
            onClick={runTest}
            disabled={status === "testing" || !keyInput.trim()}
          >
            {status === "testing" ? "Testing…" : "Run test"}
          </button>
        </div>
        {status === "ok" && (
          <div style={{ marginTop: 10, padding: "10px 14px", borderRadius: "var(--r-2)", background: "var(--good-soft)", display: "flex", gap: 10, alignItems: "flex-start" }}>
            <span style={{ color: "var(--good)", fontWeight: 700, fontSize: 15 }}>✓</span>
            <div>
              <div style={{ fontSize: 13, color: "var(--good)", fontWeight: 500 }}>Key is valid · gateway responded in {latency}ms</div>
              {response && <div className="mono muted" style={{ fontSize: 12, marginTop: 3 }}>{response}</div>}
            </div>
          </div>
        )}
        {status === "error" && (
          <div style={{ marginTop: 10, padding: "10px 14px", borderRadius: "var(--r-2)", background: "var(--bad-soft)", display: "flex", gap: 10, alignItems: "flex-start" }}>
            <span style={{ color: "var(--bad)", fontWeight: 700, fontSize: 15 }}>✗</span>
            <div>
              <div style={{ fontSize: 13, color: "var(--bad)", fontWeight: 500 }}>Test failed{latency ? ` · ${latency}ms` : ""}</div>
              {errorMsg && <div className="mono muted" style={{ fontSize: 12, marginTop: 3 }}>{errorMsg}</div>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export default function KeysPage() {
  const { teamId, teamName } = useTeam();
  const { token } = useAuth();
  const [lang, setLang] = useState<Lang>("curl");
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newKeyValue, setNewKeyValue] = useState<string | null>(null);
  const [newKeyName, setNewKeyName] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [draftName, setDraftName] = useState("");

  const loadKeys = useCallback(async () => {
    if (!teamId) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${ADMIN_BASE}/portal/teams/${teamId}/keys`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setKeys(data);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [teamId, token]);

  useEffect(() => {
    loadKeys();
  }, [loadKeys]);

  const handleCreateKey = async () => {
    const name = draftName;
    if (!name?.trim() || !teamId) return;
    setCreating(true);
    try {
      const r = await fetch(`${ADMIN_BASE}/portal/teams/${teamId}/keys`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ name: name.trim() }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setNewKeyValue(data.key);
      setNewKeyName(data.name);
      setShowCreate(false);
      setDraftName("");
      await loadKeys();
    } catch (e) {
      alert(`Failed to create key: ${e}`);
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (keyId: string, keyName: string) => {
    if (!teamId) return;
    if (!confirm(`Revoke key "${keyName}"? This cannot be undone.`)) return;
    try {
      const r = await fetch(`${ADMIN_BASE}/portal/teams/${teamId}/keys/${keyId}`, {
        method: "DELETE",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      await loadKeys();
    } catch (e) {
      alert(`Failed to revoke key: ${e}`);
    }
  };

  if (!teamId) {
    return (
      <main className="pmain">
        <div className="phero">
          <div>
            <h1>API keys</h1>
            <p>Select a team from the sidebar to manage API keys.</p>
          </div>
        </div>
      </main>
    );
  }

  const activeKeys = keys.filter((k) => !k.revoked_at);

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <h1>API keys</h1>
          <p>
            {loading ? "Loading…" : `${activeKeys.length} active key${activeKeys.length !== 1 ? "s" : ""}`}
            {" · "}scoped to <strong>{teamName}</strong> · governed by team rate limits and budget.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Button variant="primary" onClick={() => setShowCreate(true)} disabled={creating || showCreate || !!newKeyValue}>
            + Create key
          </Button>
        </div>
      </div>

      {/* Create panel / one-time key reveal */}
      {(showCreate || newKeyValue) && (
        <div className="card card--trace" style={{ marginBottom: 20 }}>
          {newKeyValue ? (
            <>
              <div className="card__head">
                <h3 className="card__title">
                  Key created — <span className="mono">{newKeyName}</span>
                </h3>
                <Pill variant="warn" dot>Shown once — store it now</Pill>
                <div className="card__actions">
                  <Button variant="ghost" size="sm" onClick={() => { setNewKeyValue(null); setNewKeyName(null); }}>
                    Done
                  </Button>
                </div>
              </div>
              <div className="card__body">
                <CodeBlock code={newKeyValue} copyable />
                <div className="muted" style={{ fontSize: 12.5, margin: "8px 0 16px" }}>
                  This is the only time the full key is displayed. Store it in Key Vault before dismissing.
                </div>
                <div className="microlabel" style={{ marginBottom: 6 }}>Next: make your first call</div>
                <CodeBlock code={firstCallSnippet(newKeyValue)} language="bash" copyable />
              </div>
            </>
          ) : (
            <>
              <div className="card__head">
                <h3 className="card__title">Create a new key</h3>
                <span className="card__sub">scoped to {teamName} · one key per service</span>
              </div>
              <div className="card__body">
                <div style={{ display: "flex", gap: 8 }}>
                  <input
                    type="text"
                    className="input"
                    autoFocus
                    value={draftName}
                    onChange={(e) => setDraftName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") handleCreateKey(); }}
                    placeholder="Key name, e.g. order-enrichment-prod"
                    style={{ flex: 1 }}
                  />
                  <Button variant="primary" onClick={handleCreateKey} disabled={creating || !draftName.trim()}>
                    {creating ? "Creating…" : "Create key"}
                  </Button>
                  <Button variant="ghost" onClick={() => { setShowCreate(false); setDraftName(""); }}>
                    Cancel
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {error && (
        <div className="card" style={{ borderColor: "var(--bad)", marginBottom: 16 }}>
          <div className="card__body" style={{ color: "var(--bad)", fontSize: 13 }}>
            Failed to load keys: {error}
          </div>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 18 }}>
        {/* Keys table */}
        <div className="card">
          <div className="card__head">
            <h3 className="card__title">Your keys</h3>
            <span className="card__sub">{activeKeys.length} active</span>
          </div>
          <div className="card__body card__body--flush">
            {loading ? (
              <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
                <Skeleton width="60%" />
                <Skeleton width="80%" />
                <Skeleton width="70%" />
              </div>
            ) : keys.length === 0 ? (
              <EmptyState
                title="No API keys yet"
                description={`Create your first key to start making requests on behalf of ${teamName}.`}
                action={
                  <Button variant="primary" onClick={() => setShowCreate(true)}>
                    Create key
                  </Button>
                }
              />
            ) : (
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Key prefix</th>
                    <th>Team</th>
                    <th className="num">Budget</th>
                    <th>Created</th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {keys.map((k) => (
                    <tr key={k.id}>
                      <td><strong>{k.name}</strong></td>
                      <td><span className="tag">{k.key_hash.slice(0, 8)}…</span></td>
                      <td>{teamName}</td>
                      <td className="num">{k.monthly_budget_usd != null ? `$${k.monthly_budget_usd}/mo` : <span className="muted">unlimited</span>}</td>
                      <td className="num">{formatDate(k.created_at)}</td>
                      <td>
                        {k.revoked_at ? (
                          <Pill variant="bad" dot>revoked</Pill>
                        ) : (
                          <Pill variant="good" dot>active</Pill>
                        )}
                      </td>
                      <td>
                        {!k.revoked_at && (
                          <button
                            className="btn btn--danger btn--sm"
                            onClick={() => handleRevoke(k.id, k.name)}
                          >
                            Revoke
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Best practices */}
        <div className="card">
          <div className="card__head"><h3 className="card__title">Best practices</h3></div>
          <div className="card__body">
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.7 }}>
              <li>Use one key per service. Don&apos;t share between prod and dev.</li>
              <li>Set the narrowest scope you need — restrict models and rate limits.</li>
              <li>Store in <span className="mono">{"${AZ_KEY_VAULT}/aigw/<service>"}</span>, not in code.</li>
              <li>Keys auto-expire at 90 days; rotate before then.</li>
              <li>Compromised? Revoke from this table — takes effect within 30s.</li>
            </ul>
          </div>
        </div>
      </div>

      <KeyVerifier initialKey={newKeyValue} />

      {/* Code samples */}
      <div className="section-h">
        <h2>Use it in code</h2>
        <Link className="a" href="/docs">Full quickstart →</Link>
      </div>

      <div className="tabs-pills">
        {LANG_TABS.map((l) => (
          <button key={l} className={lang === l ? "is-active" : ""} onClick={() => setLang(l)}>
            {l}
          </button>
        ))}
      </div>

      <CodeBlock code={CODE[lang]} language={lang} copyable />

      <div style={{ display: "flex", gap: 18, marginTop: 18, fontSize: 12.5 }}>
        <span><span className="muted">Base URL:</span> <span className="mono">https://aigw.simcorp.internal/v1</span></span>
        <span><span className="muted">Anthropic-shaped:</span> <span className="mono">/anthropic</span></span>
        <span><span className="muted">Status:</span> <a href="#" style={{ color: "var(--accent-text)" }}>aigw.simcorp.internal/status</a></span>
      </div>
    </main>
  );
}
