"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import { useTeam } from "./_lib/teamContext";
import { useAuth } from "./_lib/authContext";
import type { TeamMembership } from "./_lib/authContext";

interface AiInsight {
  id: string;
  category: string;
  severity: "critical" | "warning" | "info";
  title: string;
  description: string;
  action: string | null;
  team_name: string | null;
}

const _INSIGHT_COLOR = {
  critical: "var(--bad, #EF3E4A)",
  warning: "var(--warn, #F59E0B)",
  info: "var(--sc-link, #0A7BD7)",
};
const _INSIGHT_ICON: Record<string, string> = {
  cache: "⚡", model: "🤖", budget: "💰", error: "🚨", health: "🩺", usage: "📊",
};

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";

interface TeamDetail {
  id: string;
  name: string;
  slug: string;
  area_id: string | null;
  area_name: string | null;
  area_slug: string | null;
  area_color: string | null;
}

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
  const { developer, memberships, token } = useAuth();
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loadingKeys, setLoadingKeys] = useState(false);
  const [loadingStats, setLoadingStats] = useState(false);
  const [teamDetail, setTeamDetail] = useState<TeamDetail | null>(null);
  const [loadingTeamDetail, setLoadingTeamDetail] = useState(false);
  const [insights, setInsights] = useState<AiInsight[]>([]);
  const [dismissedInsights, setDismissedInsights] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!teamId) { setTeamDetail(null); return; }
    setLoadingTeamDetail(true);
    fetch(`${ADMIN_BASE}/teams/${teamId}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data: TeamDetail | null) => setTeamDetail(data))
      .catch(() => setTeamDetail(null))
      .finally(() => setLoadingTeamDetail(false));
  }, [teamId]);

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

  // Fetch AI recommendations for this developer
  useEffect(() => {
    if (!token) return;
    fetch(`${ADMIN_BASE}/insights/developer/me`, {
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) } as Record<string, string>,
    })
      .then(r => r.ok ? r.json() : [])
      .then((data: AiInsight[]) => setInsights(Array.isArray(data) ? data.slice(0, 5) : []))
      .catch(() => setInsights([]));
  }, [token]);

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
        <div className="card" style={{ padding: 24, marginTop: 24 }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
            <div style={{
              width: 10, height: 10, borderRadius: "50%",
              background: "var(--fg-3)", flexShrink: 0, marginTop: 3,
            }} />
            <div>
              <div style={{ fontWeight: 500, fontSize: 13 }}>No team assigned</div>
              <div style={{ color: "var(--fg-2)", fontSize: 12.5, marginTop: 2 }}>
                Contact your admin to be added to a team, or use the team picker in the sidebar.
              </div>
            </div>
          </div>
        </div>
        <div style={{ textAlign: "center", marginTop: 16 }}>
          <Link href="/portal/playground" className="btn btn--primary">Open Playground →</Link>
        </div>
      </main>
    );
  }

  const spendDisplay = stats ? `€${stats.spend_mtd?.toFixed(2) ?? "—"}` : "—";
  const budgetDisplay = stats?.budget_cap ? `of team cap €${stats.budget_cap.toLocaleString()}` : "";
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

      {/* Workspace context */}
      {(loadingTeamDetail || teamDetail) && (
        <div className="card" style={{ padding: "14px 20px", marginBottom: 4 }}>
          {loadingTeamDetail ? (
            <div style={{ color: "var(--fg-3)", fontSize: 13 }}>Loading workspace…</div>
          ) : teamDetail ? (
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{
                  width: 10, height: 10, borderRadius: "50%", flexShrink: 0,
                  background: teamDetail.area_color ?? "var(--fg-3)",
                }} />
                <div style={{ display: "flex", alignItems: "baseline", gap: 6, flexWrap: "wrap" }}>
                  {teamDetail.area_name && (
                    <>
                      <span style={{ fontSize: 13, color: "var(--fg-2)" }}>{teamDetail.area_name}</span>
                      <span style={{ fontSize: 12, color: "var(--fg-3)" }}>/</span>
                    </>
                  )}
                  <span style={{ fontSize: 13, fontWeight: 500 }}>{teamDetail.name}</span>
                </div>
                <div style={{ marginLeft: "auto", fontSize: 11.5, color: "var(--fg-3)" }}>Your workspace</div>
              </div>
              {/* Other team memberships */}
              {memberships.filter((m: TeamMembership) => m.team_id !== teamId).length > 0 && (
                <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--rule)" }}>
                  <div style={{ fontSize: 11, color: "var(--fg-3)", fontWeight: 500, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.04em" }}>
                    Also a member of
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {memberships
                      .filter((m: TeamMembership) => m.team_id !== teamId)
                      .map((m: TeamMembership) => (
                        <div key={m.membership_id} style={{
                          display: "flex", alignItems: "center", gap: 5,
                          padding: "3px 8px",
                          border: "1px solid var(--rule)",
                          borderRadius: 6,
                          fontSize: 12,
                        }}>
                          <span style={{
                            width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
                            background: m.area_color ?? "var(--fg-3)",
                          }} />
                          <span style={{ fontWeight: 500 }}>{m.team_name}</span>
                          {m.area_name && (
                            <span style={{ color: "var(--fg-3)", fontSize: 11 }}>{m.area_name}</span>
                          )}
                          <span style={{
                            fontSize: 10.5, padding: "1px 4px",
                            borderRadius: 4,
                            background: m.role === "admin" ? "var(--accent-soft, rgba(10,123,215,0.1))" : "var(--surface-soft, rgba(0,0,0,0.06))",
                            color: m.role === "admin" ? "var(--sc-link, #0A7BD7)" : "var(--fg-3)",
                            fontWeight: 500,
                          }}>
                            {m.role}
                          </span>
                        </div>
                      ))}
                  </div>
                </div>
              )}
            </div>
          ) : null}
        </div>
      )}

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

      {/* AI Recommendations */}
      {insights.filter(i => !dismissedInsights.has(i.id)).length > 0 && (
        <div className="card" style={{ padding: "14px 16px", marginBottom: 4 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <span style={{ fontSize: 14 }}>✦</span>
            <span style={{ fontWeight: 600, fontSize: 13 }}>AI Recommendations</span>
            <span style={{ fontSize: 11.5, color: "var(--fg-3)" }}>for your team · refreshed every 6h</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {insights
              .filter(i => !dismissedInsights.has(i.id))
              .map(ins => {
                const color = _INSIGHT_COLOR[ins.severity] ?? "var(--sc-link)";
                const icon = _INSIGHT_ICON[ins.category] ?? "✦";
                return (
                  <div key={ins.id} style={{
                    display: "flex", gap: 10, alignItems: "flex-start",
                    padding: "10px 12px",
                    background: "var(--surface-soft, rgba(0,0,0,0.03))",
                    borderLeft: `3px solid ${color}`,
                    borderRadius: "0 8px 8px 0",
                  }}>
                    <span style={{ fontSize: 16, flexShrink: 0 }}>{icon}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 500, fontSize: 13, color: "var(--fg-1)" }}>{ins.title}</div>
                      <div style={{ fontSize: 12.5, color: "var(--fg-2)", marginTop: 2, lineHeight: 1.5 }}>{ins.description}</div>
                      {ins.action && (
                        <div style={{ fontSize: 12, color: "var(--sc-link)", marginTop: 4, fontStyle: "italic" }}>
                          → {ins.action}
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => setDismissedInsights(prev => new Set([...prev, ins.id]))}
                      style={{
                        background: "none", border: "none", cursor: "pointer",
                        color: "var(--fg-3)", fontSize: 16, padding: 2, flexShrink: 0,
                      }}
                      title="Dismiss"
                    >
                      ×
                    </button>
                  </div>
                );
              })}
          </div>
        </div>
      )}

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
