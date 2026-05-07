"use client";

import Link from "next/link";
import { useState } from "react";
import { MOCK_REQUESTS, MOCK_KEYS, MOCK_SESSIONS } from "./_lib/mock-data";

export default function PortalHome() {
  const [newKeyOpen, setNewKeyOpen] = useState(false);

  return (
    <main className="pmain">
      {/* Hero */}
      <div className="phero">
        <div>
          <h1>Welcome back, Maja</h1>
          <p>
            You&apos;re on <strong>agent-platform</strong>. Build agents, ship to prod, watch the bill.
            Same OpenAI SDK, internal models.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn">View team</button>
          <button className="btn btn--primary" onClick={() => setNewKeyOpen(true)}>+ New API key</button>
        </div>
      </div>

      {/* Stat strip */}
      <div className="stat-strip">
        <div className="s">
          <div className="l">Your spend MTD</div>
          <div className="v">$284.10</div>
          <div className="d">of team cap $9,150</div>
        </div>
        <div className="s">
          <div className="l">Requests · 7d</div>
          <div className="v">38,412</div>
          <div className="d">+12% vs last week</div>
        </div>
        <div className="s">
          <div className="l">Cache hit</div>
          <div className="v good">42%</div>
          <div className="d">team avg, last 24h</div>
        </div>
        <div className="s">
          <div className="l">Avg latency</div>
          <div className="v">820 ms</div>
          <div className="d">p99 4.2s</div>
        </div>
      </div>

      {/* Quick actions */}
      <div className="qg">
        <Link className="qa" href="/portal/playground">
          <div className="qa__icon">
            <svg viewBox="0 0 16 16" fill="currentColor"><path d="M5 3.5v9l8-4.5-8-4.5z"/></svg>
          </div>
          <div className="qa__t">Open Playground</div>
          <div className="qa__d">Try Claude, Gemini, GPT-5 side-by-side. Tune prompts, attach tools, then export the code.</div>
          <div className="qa__cta">Start a new chat →</div>
        </Link>
        <Link className="qa" href="/portal/agents">
          <div className="qa__icon">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <rect x="3" y="5" width="10" height="8" rx="2"/>
              <path d="M8 2v3M5.5 9h0M10.5 9h0"/>
            </svg>
          </div>
          <div className="qa__t">Build an Agent</div>
          <div className="qa__d">Compose tool-using agents from MCP servers, schedule runs, and watch them work step-by-step.</div>
          <div className="qa__cta">Create agent →</div>
        </Link>
        <Link className="qa" href="/portal/docs">
          <div className="qa__icon">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M2.5 3.5h5a1 1 0 011 1v9a1 1 0 00-1-1h-5v-9zM13.5 3.5h-5a1 1 0 00-1 1v9a1 1 0 011-1h5v-9z"/>
            </svg>
          </div>
          <div className="qa__t">Quickstart</div>
          <div className="qa__d">Five-minute curl, Python, and TypeScript walkthroughs. SDK packages live on the internal registry.</div>
          <div className="qa__cta">Read docs →</div>
        </Link>
      </div>

      {/* Requests + Keys */}
      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 18 }}>
        <div className="card">
          <div className="card__head">
            <h3 className="card__title">Your recent requests</h3>
            <span className="card__sub">last hour · all keys</span>
            <div className="card__actions">
              <Link href="/portal/usage" className="muted" style={{ fontSize: 12 }}>View all →</Link>
            </div>
          </div>
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Model</th>
                  <th>Status</th>
                  <th className="num">Tokens</th>
                  <th className="num">Cost</th>
                </tr>
              </thead>
              <tbody>
                {MOCK_REQUESTS.map((req, i) => (
                  <tr key={i}>
                    <td><span className="mono">{req.time}</span></td>
                    <td><span className="mono">{req.model}</span></td>
                    <td>
                      {req.status === "200" && req.cached
                        ? <span className="pill pill--info">cache</span>
                        : req.status === "200"
                        ? <span className="pill pill--good"><span className="dot"></span>200</span>
                        : req.status === "429"
                        ? <span className="pill pill--warn"><span className="dot"></span>429</span>
                        : <span className="pill pill--bad"><span className="dot"></span>{req.status}</span>
                      }
                    </td>
                    <td className="num">
                      <span className="mono">
                        {req.tokensIn > 0 ? `${req.tokensIn.toLocaleString()} / ${req.tokensOut.toLocaleString()}` : "—"}
                      </span>
                    </td>
                    <td className="num">
                      <span className="mono">
                        {req.cost === null ? "—" : req.cost === 0 ? "$0" : `$${req.cost.toFixed(4)}`}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <div className="card__head">
            <h3 className="card__title">Your API keys</h3>
            <div className="card__actions">
              <Link href="/portal/keys" className="muted" style={{ fontSize: 12 }}>Manage →</Link>
            </div>
          </div>
          <div className="card__body" style={{ padding: "14px 16px" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {MOCK_KEYS.map((key) => (
                <div
                  key={key.id}
                  style={{
                    display: "flex", alignItems: "center", gap: 10,
                    padding: 10,
                    border: "1px solid var(--rule)",
                    borderRadius: 8,
                    background: key.status === "expiring" ? "var(--warn-soft)" : undefined,
                  }}
                >
                  <div style={{
                    width: 6, height: 6, borderRadius: "50%",
                    background: key.status === "expiring" ? "var(--warn)" : "var(--good)",
                  }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 500, fontSize: 13 }}>{key.name}</div>
                    <div className="mono" style={{ fontSize: 11.5, color: "var(--fg-3)" }}>{key.prefix}</div>
                  </div>
                  {key.status === "expiring" ? (
                    <button className="btn btn--sm">Rotate</button>
                  ) : (
                    <span className="muted" style={{ fontSize: 11 }}>{key.lastUsed}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Recent sessions */}
      <div className="section-h">
        <h2>Pick up where you left off</h2>
        <Link className="a" href="/portal/playground">All sessions →</Link>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 14 }}>
        {MOCK_SESSIONS.map((s) => (
          <div className="card" key={s.id} style={{ cursor: "pointer" }}>
            <div className="card__body" style={{ padding: 16 }}>
              <div className="muted" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600 }}>
                {s.label}
              </div>
              <div style={{ fontWeight: 600, fontSize: 14, margin: "6px 0 4px" }}>
                {s.type === "playground" ? "Codebase Q&A · monorepo"
                 : s.type === "agent" ? "pr-review-bot"
                 : "PR review · Python style"}
              </div>
              <div style={{ fontSize: 12.5, color: "var(--fg-2)", lineHeight: 1.5 }}>{s.description}</div>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
