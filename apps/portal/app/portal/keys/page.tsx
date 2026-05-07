"use client";

import Link from "next/link";
import { useState } from "react";
import { MOCK_KEYS } from "../_lib/mock-data";

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

export default function KeysPage() {
  const [lang, setLang] = useState<Lang>("curl");
  const [copied, setCopied] = useState<string | null>(null);
  const [newKey] = useState("sk_live_8a31fc02e1b4d57f0c9a2e8d4f6b1a7e3d8c5b9f2e6a4d1c7b8a3");

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(id);
      setTimeout(() => setCopied(null), 2000);
    });
  };

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <h1>API keys</h1>
          <p>3 of your keys · scoped to <strong>agent-platform</strong> · governed by team rate limits and budget.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn">Rotate all</button>
          <button className="btn btn--primary">+ Issue key</button>
        </div>
      </div>

      {/* New key reveal */}
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
            Your new key — <span className="mono">prod-rag-service</span>
          </h3>
          <span className="card__sub">copy it now · we won&apos;t show it again</span>
        </div>
        <div className="card__body">
          <div className="code-block" style={{ marginBottom: 10 }}>
            {newKey}
            <button className="copy-btn" onClick={() => handleCopy(newKey, "newkey")}>
              {copied === "newkey" ? "Copied!" : "Copy"}
            </button>
            <button className="btn btn--sm" style={{ marginLeft: 8 }}>Test</button>
          </div>
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 12.5, color: "var(--fg-2)" }}>
            <span><strong style={{ color: "var(--fg-1)" }}>Scope:</strong> prod</span>
            <span><strong style={{ color: "var(--fg-1)" }}>Models:</strong> claude-*, gemini-*</span>
            <span><strong style={{ color: "var(--fg-1)" }}>Rate:</strong> 60 rpm</span>
            <span><strong style={{ color: "var(--fg-1)" }}>Expires:</strong> Aug 12, 2026</span>
            <span style={{ marginLeft: "auto", color: "var(--good)" }}>✓ stored in your clipboard</span>
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 18 }}>
        {/* Keys table */}
        <div className="card">
          <div className="card__head">
            <h3 className="card__title">Your keys</h3>
            <span className="card__sub">3 active · 1 expiring soon</span>
          </div>
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Key ID</th>
                  <th>Scope</th>
                  <th>Model</th>
                  <th>Rate</th>
                  <th>Last used</th>
                  <th>Expires</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {MOCK_KEYS.map((k) => (
                  <tr key={k.id}>
                    <td><strong>{k.name}</strong></td>
                    <td><span className="mono">{k.prefix}</span></td>
                    <td>
                      <span className={`pill ${k.scope === "prod" ? "pill--info" : ""}`}>{k.scope}</span>
                    </td>
                    <td>{k.model}</td>
                    <td>{k.rate}</td>
                    <td>{k.lastUsed}</td>
                    <td>{k.expires}</td>
                    <td>
                      {k.status === "active" && <span className="pill pill--good"><span className="dot" />active</span>}
                      {k.status === "expiring" && <span className="pill pill--warn"><span className="dot" />{k.daysToExpiry}d to expiry</span>}
                    </td>
                    <td>
                      <button className="btn btn--sm btn--ghost">⋯</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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
              <li>Compromised? Revoke from ⋯ menu — takes effect within 30s.</li>
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
