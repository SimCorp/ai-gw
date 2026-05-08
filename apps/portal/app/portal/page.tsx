"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import { useTeam } from "./_lib/teamContext";
import { useAuth } from "./_lib/authContext";

const ADMIN_BASE = "http://localhost:8005";

interface ApiKey {
  id: string;
  name: string;
  key_prefix?: string;
  prefix?: string;
  status?: string;
  last_used?: string | null;
  created_at?: string;
}

interface DashboardStats {
  team_name: string;
  spend_mtd: number;
  budget_cap: number;
  requests_7d: number;
  requests_7d_prev?: number;
  cache_hit_rate_24h?: number;
  avg_latency_ms?: number;
  p99_latency_ms?: number;
}

export default function PortalHome() {
  const { teamId, teamName } = useTeam();
  const { developer } = useAuth();
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loadingKeys, setLoadingKeys] = useState(false);
  const [loadingStats, setLoadingStats] = useState(false);

  useEffect(() => {
    if (!teamId) return;

    setLoadingKeys(true);
    fetch(`${ADMIN_BASE}/teams/${teamId}/keys`)
      .then((r) => r.json())
      .then((data: ApiKey[]) => {
        setKeys(Array.isArray(data) ? data : []);
      })
      .catch(() => setKeys([]))
      .finally(() => setLoadingKeys(false));
  }, [teamId]);

  useEffect(() => {
    if (!teamName) return;

    setLoadingStats(true);
    fetch(`${ADMIN_BASE}/dashboard/stats`)
      .then((r) => r.json())
      .then((data: DashboardStats[] | DashboardStats) => {
        const list = Array.isArray(data) ? data : [data];
        const match = list.find((s) => s.team_name === teamName) ?? list[0] ?? null;
        setStats(match);
      })
      .catch(() => setStats(null))
      .finally(() => setLoadingStats(false));
  }, [teamName]);

  if (!teamId) {
    return (
      <main className="pmain">
        <div className="phero">
          <div>
            <h1>Welcome{developer?.display_name ? `, ${developer.display_name.split(" ")[0]}` : ""}</h1>
            <p>Select a team in the sidebar to see your stats, keys, and activity.</p>
          </div>
        </div>
        <div className="card" style={{ padding: 32, textAlign: "center", marginTop: 24 }}>
          <p style={{ marginBottom: 16, color: "var(--fg-2)" }}>No team selected. Use the team picker in the sidebar to get started.</p>
          <Link href="/portal/playground" className="btn btn--primary">Open Playground →</Link>
        </div>
      </main>
    );
  }

  const spendDisplay = stats ? `$${stats.spend_mtd?.toFixed(2) ?? "—"}` : "—";
  const budgetDisplay = stats?.budget_cap ? `of team cap $${stats.budget_cap.toLocaleString()}` : "";
  const requests7dDisplay = stats ? (stats.requests_7d?.toLocaleString() ?? "—") : "—";
  const cacheHitDisplay = stats?.cache_hit_rate_24h != null
    ? `${(stats.cache_hit_rate_24h * 100).toFixed(1)}%`
    : "—";
  const latencyDisplay = stats?.avg_latency_ms != null
    ? `${Math.round(stats.avg_latency_ms)} ms`
    : "—";
  const p99Display = stats?.p99_latency_ms != null
    ? `p99 ${Math.round(stats.p99_latency_ms / 1000).toFixed(1)}s`
    : "";

  return (
    <main className="pmain">
      {/* Hero */}
      <div className="phero">
        <div>
          <h1>Welcome back{developer?.display_name ? `, ${developer.display_name.split(" ")[0]}` : ""}</h1>
          <p>
            You&apos;re on <strong>{teamName}</strong>. Build agents, ship to prod, watch the bill.
            Same OpenAI SDK, internal models.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Link href="/portal/keys" className="btn">View keys</Link>
          <Link href="/portal/playground" className="btn btn--primary">Open Playground</Link>
        </div>
      </div>

      {/* Stat strip */}
      <div className="stat-strip">
        <div className="s">
          <div className="l">Team spend MTD</div>
          <div className="v">{loadingStats ? "…" : spendDisplay}</div>
          {budgetDisplay && <div className="d">{budgetDisplay}</div>}
        </div>
        <div className="s">
          <div className="l">Requests · 7d</div>
          <div className="v">{loadingStats ? "…" : requests7dDisplay}</div>
        </div>
        <div className="s">
          <div className="l">Cache hit</div>
          <div className="v good">{loadingStats ? "…" : cacheHitDisplay}</div>
          <div className="d">team avg, last 24h</div>
        </div>
        <div className="s">
          <div className="l">Avg latency</div>
          <div className="v">{loadingStats ? "…" : latencyDisplay}</div>
          {p99Display && <div className="d">{p99Display}</div>}
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

      {/* Recent requests + API keys */}
      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 18 }}>
        <div className="card">
          <div className="card__head">
            <h3 className="card__title">Recent requests</h3>
            <span className="card__sub">no per-user history endpoint yet</span>
            <div className="card__actions">
              <Link href="/portal/usage" className="muted" style={{ fontSize: 12 }}>View all →</Link>
            </div>
          </div>
          <div className="card__body" style={{ padding: "24px 20px", display: "flex", flexDirection: "column", gap: 8 }}>
            <p style={{ color: "var(--fg-2)", fontSize: 13, margin: 0 }}>
              Per-request history is not available on the dashboard yet.
            </p>
            <Link href="/portal/usage" className="btn" style={{ alignSelf: "flex-start", marginTop: 4 }}>
              View detailed usage in Usage &amp; spend →
            </Link>
          </div>
        </div>

        <div className="card">
          <div className="card__head">
            <h3 className="card__title">Your API keys</h3>
            <span className="card__sub">
              {loadingKeys ? "loading…" : `${keys.length} key${keys.length === 1 ? "" : "s"}`}
            </span>
            <div className="card__actions">
              <Link href="/portal/keys" className="muted" style={{ fontSize: 12 }}>Manage →</Link>
            </div>
          </div>
          <div className="card__body" style={{ padding: "14px 16px" }}>
            {loadingKeys ? (
              <div style={{ color: "var(--fg-3)", fontSize: 13 }}>Loading keys…</div>
            ) : keys.length === 0 ? (
              <div style={{ color: "var(--fg-3)", fontSize: 13 }}>
                No API keys yet.{" "}
                <Link href="/portal/keys" style={{ color: "var(--sc-link)" }}>Create one →</Link>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {keys.slice(0, 6).map((key) => {
                  const isExpiring = key.status === "expiring";
                  const prefix = key.key_prefix ?? key.prefix ?? "";
                  const lastUsed = key.last_used ?? null;
                  return (
                    <div
                      key={key.id}
                      style={{
                        display: "flex", alignItems: "center", gap: 10,
                        padding: 10,
                        border: "1px solid var(--rule)",
                        borderRadius: 8,
                        background: isExpiring ? "var(--warn-soft)" : undefined,
                      }}
                    >
                      <div style={{
                        width: 6, height: 6, borderRadius: "50%",
                        background: isExpiring ? "var(--warn)" : "var(--good)",
                      }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 500, fontSize: 13 }}>{key.name}</div>
                        {prefix && (
                          <div className="mono" style={{ fontSize: 11.5, color: "var(--fg-3)" }}>{prefix}</div>
                        )}
                      </div>
                      {isExpiring ? (
                        <button className="btn btn--sm">Rotate</button>
                      ) : (
                        <span className="muted" style={{ fontSize: 11 }}>
                          {lastUsed ?? "—"}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Recent sessions replaced with playground link */}
      <div className="section-h">
        <h2>Playground sessions</h2>
        <Link className="a" href="/portal/playground">All sessions →</Link>
      </div>
      <div className="card" style={{ padding: "24px 20px" }}>
        <p style={{ color: "var(--fg-2)", fontSize: 13, margin: "0 0 12px" }}>
          Session history is stored in the Playground. Open it to pick up where you left off.
        </p>
        <Link href="/portal/playground" className="btn btn--primary">
          Go to Playground →
        </Link>
      </div>
    </main>
  );
}
