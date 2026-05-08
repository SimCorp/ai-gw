"use client";

import Link from "next/link";
import { useState, useEffect, useCallback } from "react";
import { useTeam } from "../_lib/teamContext";
import { useAuth } from "../_lib/authContext";

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";

const LANG_TABS = ["curl", "python", "ts", "anthropic"] as const;
type Lang = (typeof LANG_TABS)[number];

const CODE: Record<Lang, string> = {
  curl: `# Drop-in OpenAI replacement — same client, different base URL
curl https://aigw.simcorp.internal/v1/chat/completions \\
  -H "authorization: Bearer $AIGW_KEY" \\
  -H "content-type: application/json" \\
  -d '{
    "model": "claude-sonnet-4.5",
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
    model="claude-sonnet-4.5",
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
  model: "claude-sonnet-4.5",
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
  model: "claude-sonnet-4.5",
  max_tokens: 1024,
  messages: [{ role: "user", content: "Hello" }],
});`,
};

interface ApiKey {
  id: string;
  team_id: string;
  name: string;
  key_hash: string;
  revoked_at: string | null;
  monthly_budget_usd: number | null;
  created_at: string;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export default function KeysPage() {
  const { teamId, teamName } = useTeam();
  const { token } = useAuth();
  const [lang, setLang] = useState<Lang>("curl");
  const [copied, setCopied] = useState<string | null>(null);
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newKeyValue, setNewKeyValue] = useState<string | null>(null);
  const [newKeyName, setNewKeyName] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

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

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(id);
      setTimeout(() => setCopied(null), 2000);
    });
  };

  const handleCreateKey = async () => {
    const name = prompt("Enter a name for the new key:");
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
          <button className="btn btn--primary" onClick={handleCreateKey} disabled={creating}>
            {creating ? "Creating…" : "+ Issue key"}
          </button>
        </div>
      </div>

      {/* New key reveal */}
      {newKeyValue && (
        <div
          className="card"
          style={{
            borderColor: "var(--good)",
            background: "linear-gradient(180deg,rgba(31,138,91,0.04),transparent 40%)",
            marginBottom: 20,
          }}
        >
          <div className="card__head">
            <h3 className="card__title">
              Your new key — <span className="mono">{newKeyName}</span>
            </h3>
            <span className="card__sub">copy it now · we won&apos;t show it again</span>
          </div>
          <div className="card__body">
            <div className="code-block" style={{ marginBottom: 10 }}>
              {newKeyValue}
              <button className="copy-btn" onClick={() => handleCopy(newKeyValue, "newkey")}>
                {copied === "newkey" ? "Copied!" : "Copy"}
              </button>
            </div>
            <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 12.5, color: "var(--fg-2)" }}>
              <span style={{ color: "var(--good)" }}>✓ store this somewhere safe — it will not be shown again</span>
              <button
                className="btn btn--sm btn--ghost"
                style={{ marginLeft: "auto" }}
                onClick={() => { setNewKeyValue(null); setNewKeyName(null); }}
              >
                Dismiss
              </button>
            </div>
          </div>
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
          <div className="card__body" style={{ padding: 0 }}>
            {loading ? (
              <div style={{ padding: 16, fontSize: 13, color: "var(--fg-3)" }}>Loading keys…</div>
            ) : keys.length === 0 ? (
              <div style={{ padding: 16, fontSize: 13, color: "var(--fg-3)" }}>
                No keys yet. Issue your first key above.
              </div>
            ) : (
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Key prefix</th>
                    <th>Budget</th>
                    <th>Created</th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {keys.map((k) => (
                    <tr key={k.id}>
                      <td><strong>{k.name}</strong></td>
                      <td><span className="mono">{k.key_hash.slice(0, 8)}…</span></td>
                      <td>{k.monthly_budget_usd != null ? `$${k.monthly_budget_usd}/mo` : <span className="muted">unlimited</span>}</td>
                      <td>{formatDate(k.created_at)}</td>
                      <td>
                        {k.revoked_at ? (
                          <span className="pill pill--bad"><span className="dot" />revoked</span>
                        ) : (
                          <span className="pill pill--good"><span className="dot" />active</span>
                        )}
                      </td>
                      <td>
                        {!k.revoked_at && (
                          <button
                            className="btn btn--sm btn--ghost"
                            style={{ color: "var(--bad)" }}
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

      {/* Code samples */}
      <div className="section-h">
        <h2>Use it in code</h2>
        <Link className="a" href="/portal/docs">Full quickstart →</Link>
      </div>

      <div className="tabs-pills">
        {LANG_TABS.map((l) => (
          <button key={l} className={lang === l ? "is-active" : ""} onClick={() => setLang(l)}>
            {l}
          </button>
        ))}
      </div>

      <div className="code-block">
        <pre style={{ margin: 0, fontFamily: "var(--font-mono)", fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{CODE[lang as Lang]}</pre>
        <button className="copy-btn" onClick={() => handleCopy(CODE[lang as Lang], "code")}>
          {copied === "code" ? "Copied!" : "Copy"}
        </button>
      </div>

      <div style={{ display: "flex", gap: 18, marginTop: 18, fontSize: 12.5, color: "var(--fg-2)" }}>
        <span><span className="muted">Base URL:</span> <span className="mono">https://aigw.simcorp.internal/v1</span></span>
        <span><span className="muted">Anthropic-shaped:</span> <span className="mono">/anthropic</span></span>
        <span><span className="muted">Status:</span> <a href="#" style={{ color: "var(--sc-blue)" }}>aigw.simcorp.internal/status</a></span>
      </div>
    </main>
  );
}
