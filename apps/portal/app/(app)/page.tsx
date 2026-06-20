"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import { CodeBlock, EmptyState, Pill, Skeleton } from "@aigw/ui";
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

const INSIGHT_PILL: Record<AiInsight["severity"], "bad" | "warn" | "info"> = {
  critical: "bad",
  warning: "warn",
  info: "info",
};

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";

const FIRST_CALL_SNIPPET = `curl https://aigw-dev.lab.cloud.scdom.net/v1/chat/completions \\
  -H "authorization: Bearer sk-..." \\
  -H "content-type: application/json" \\
  -d '{"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "Hello"}]}'`;

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
  revoked_at?: string | null;
}

interface DashboardStats {
  team_name: string;
  request_count: number;
  total_tokens: number | null;
  total_cost_usd: number | null;
  cache_hit_pct: number | null;
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

  const firstName = developer?.display_name ? developer.display_name.split(" ")[0] : null;

  if (!teamId) {
    return (
      <main className="pmain">
        <div className="phero">
          <div>
            <h1>Welcome{firstName ? `, ${firstName}` : ""}</h1>
            <p>Select a team in the sidebar to see your stats, keys, and activity.</p>
          </div>
        </div>
        <div className="card">
          <EmptyState
            title="No team assigned"
            description="Contact your admin to be added to a team, or use the team picker in the sidebar."
            action={<Link href="/playground" className="btn btn--primary">Open Playground →</Link>}
          />
        </div>
      </main>
    );
  }

  const spendDisplay = stats?.total_cost_usd != null
    ? `€${stats.total_cost_usd.toFixed(2)}`
    : "—";
  const requestsDisplay = stats?.request_count != null
    ? stats.request_count.toLocaleString()
    : "—";
  const cacheHitDisplay = stats?.cache_hit_pct != null
    ? `${stats.cache_hit_pct.toFixed(1)}%`
    : "—";
  const tokensDisplay = stats?.total_tokens != null
    ? stats.total_tokens >= 1_000_000
      ? `${(stats.total_tokens / 1_000_000).toFixed(1)}M`
      : stats.total_tokens >= 1_000
      ? `${(stats.total_tokens / 1_000).toFixed(0)}k`
      : String(stats.total_tokens)
    : "—";

  const firstRun = !loadingKeys && keys.length === 0;
  const visibleInsights = insights.filter((i) => !dismissedInsights.has(i.id));
  const activeKeys = keys.filter((k) => !k.revoked_at);

  return (
    <main className="pmain">
      {/* Hero */}
      <div className="phero">
        <div>
          <h1>Welcome back{firstName ? `, ${firstName}` : ""}</h1>
          <p>
            You&apos;re on <strong>{teamName}</strong>.
            {firstRun
              ? " Three steps stand between you and your first gateway request."
              : " Same OpenAI SDK, internal models — build, ship, watch the bill."}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Link href="/keys" className="btn">View keys</Link>
          <Link href="/playground" className="btn btn--primary">Open Playground</Link>
        </div>
      </div>

      {/* First-run: get to first request */}
      {firstRun && (
        <div className="card card--trace" style={{ marginBottom: 24 }}>
          <div className="card__head">
            <h3 className="card__title">Get to your first request</h3>
            <span className="card__sub">no key yet — you&apos;re three steps away</span>
          </div>
          <div className="card__body" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
              <span className="mono num" style={{ fontSize: 13, fontWeight: 600, color: "var(--accent-text)", paddingTop: 2 }}>01</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13.5, fontWeight: 600 }}>Create an API key</div>
                <div className="muted" style={{ fontSize: 12.5, marginTop: 2 }}>
                  Keys are scoped to {teamName} and authenticate every request.
                </div>
              </div>
              <Link href="/keys" className="btn btn--primary btn--sm" style={{ flexShrink: 0 }}>Create key →</Link>
            </div>

            <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
              <span className="mono num" style={{ fontSize: 13, fontWeight: 600, color: "var(--accent-text)", paddingTop: 2 }}>02</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13.5, fontWeight: 600 }}>Copy a snippet</div>
                <div className="muted" style={{ fontSize: 12.5, margin: "2px 0 8px" }}>
                  Drop-in OpenAI-compatible endpoint — swap in your key once you have it.
                </div>
                <CodeBlock code={FIRST_CALL_SNIPPET} language="bash" copyable />
              </div>
            </div>

            <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
              <span className="mono num" style={{ fontSize: 13, fontWeight: 600, color: "var(--accent-text)", paddingTop: 2 }}>03</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13.5, fontWeight: 600 }}>Watch your first request land</div>
                <div className="muted" style={{ fontSize: 12.5, marginTop: 2 }}>
                  Requests show up in the usage report within seconds.
                </div>
              </div>
              <Link href="/usage" className="btn btn--sm" style={{ flexShrink: 0 }}>Open usage →</Link>
            </div>
          </div>
        </div>
      )}

      {/* Workspace context */}
      {(loadingTeamDetail || teamDetail) && (
        <div className="card" style={{ marginBottom: 14 }}>
          <div className="card__body" style={{ padding: "14px 20px" }}>
            {loadingTeamDetail ? (
              <Skeleton width={220} height={14} />
            ) : teamDetail ? (
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{
                    width: 10, height: 10, borderRadius: "50%", flexShrink: 0,
                    background: teamDetail.area_color ?? "var(--fg-3)",
                  }} />
                  <div style={{ display: "flex", alignItems: "baseline", gap: 6, flexWrap: "wrap" }}>
                    {teamDetail.area_name && (
                      <>
                        <span className="muted" style={{ fontSize: 13 }}>{teamDetail.area_name}</span>
                        <span style={{ fontSize: 12, color: "var(--fg-3)" }}>/</span>
                      </>
                    )}
                    <span style={{ fontSize: 13, fontWeight: 500 }}>{teamDetail.name}</span>
                  </div>
                  <span className="microlabel" style={{ marginLeft: "auto" }}>Your workspace</span>
                </div>
                {/* Other team memberships */}
                {memberships.filter((m: TeamMembership) => m.team_id !== teamId).length > 0 && (
                  <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--rule)" }}>
                    <div className="microlabel" style={{ marginBottom: 6 }}>Also a member of</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {memberships
                        .filter((m: TeamMembership) => m.team_id !== teamId)
                        .map((m: TeamMembership) => (
                          <span key={m.membership_id} style={{
                            display: "inline-flex", alignItems: "center", gap: 6,
                            padding: "3px 8px",
                            border: "1px solid var(--rule)",
                            borderRadius: "var(--r-2)",
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
                            <Pill variant={m.role === "admin" ? "info" : "default"}>{m.role}</Pill>
                          </span>
                        ))}
                    </div>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>
      )}

      {/* Stat strip — returning users */}
      {!firstRun && (
        <div className="stat-strip">
          <div className="s">
            <div className="l">Team spend MTD</div>
            <div className="v">{loadingStats ? <Skeleton width={64} height={22} /> : spendDisplay}</div>
          </div>
          <div className="s">
            <div className="l">Requests · all time</div>
            <div className="v">{loadingStats ? <Skeleton width={64} height={22} /> : requestsDisplay}</div>
          </div>
          <div className="s">
            <div className="l">Cache hit rate</div>
            <div className="v good">{loadingStats ? <Skeleton width={64} height={22} /> : cacheHitDisplay}</div>
            <div className="d">team avg</div>
          </div>
          <div className="s">
            <div className="l">Tokens used</div>
            <div className="v">{loadingStats ? <Skeleton width={64} height={22} /> : tokensDisplay}</div>
          </div>
        </div>
      )}

      {/* AI Recommendations */}
      {visibleInsights.length > 0 && (
        <div className="card" style={{ marginBottom: 14 }}>
          <div className="card__head">
            <h3 className="card__title">AI Recommendations</h3>
            <span className="card__sub">for your team · refreshed every 6h</span>
          </div>
          <div className="card__body" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {visibleInsights.map((ins) => (
              <div key={ins.id} className="callout" style={{
                display: "flex", gap: 12, alignItems: "flex-start",
                padding: "10px 14px",
                borderLeftColor: ins.severity === "critical" ? "var(--bad)" : ins.severity === "warning" ? "var(--warn)" : "var(--accent)",
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontWeight: 500, fontSize: 13 }}>{ins.title}</span>
                    <Pill variant={INSIGHT_PILL[ins.severity] ?? "info"}>{ins.category}</Pill>
                  </div>
                  <div className="muted" style={{ fontSize: 12.5, marginTop: 2, lineHeight: 1.5 }}>{ins.description}</div>
                  {ins.action && (
                    <div style={{ fontSize: 12, color: "var(--accent-text)", marginTop: 4 }}>
                      → {ins.action}
                    </div>
                  )}
                </div>
                <button
                  onClick={() => setDismissedInsights(prev => new Set([...prev, ins.id]))}
                  className="btn btn--ghost btn--sm"
                  style={{ flexShrink: 0 }}
                  title="Dismiss"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quick actions */}
      <div className="qg">
        <Link className="qa" href="/playground">
          <div className="qa__icon">
            <svg viewBox="0 0 16 16" fill="currentColor"><path d="M5 3.5v9l8-4.5-8-4.5z"/></svg>
          </div>
          <div className="qa__t">Open Playground</div>
          <div className="qa__d">Try Claude, Gemini, GPT-5 side-by-side. Tune prompts, attach tools, then export the code.</div>
          <div className="qa__cta">Start a new chat →</div>
        </Link>
        <Link className="qa" href="/agents">
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
        <Link className="qa" href="/docs">
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

      {/* Detail grid — returning users */}
      {!firstRun && (
        <div className="split-3">
          <div className="card">
            <div className="card__body" style={{ padding: "16px 20px" }}>
              <div className="microlabel" style={{ marginBottom: 10 }}>Your API keys</div>
              {loadingKeys ? (
                <Skeleton width="80%" height={13} style={{ marginBottom: 10 }} />
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 7, marginBottom: 12 }}>
                  {activeKeys.slice(0, 4).map((key) => (
                    <div key={key.id} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--good)", flexShrink: 0 }} />
                      <span style={{ fontSize: 13, fontWeight: 500, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{key.name}</span>
                      {(key.key_prefix ?? key.prefix) && (
                        <span className="tag">{(key.key_prefix ?? key.prefix)?.slice(0, 8)}…</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
              <Link href="/keys" className="btn btn--sm">
                {activeKeys.length > 0 ? "Manage keys →" : "+ Create key →"}
              </Link>
            </div>
          </div>

          <div className="card">
            <div className="card__body" style={{ padding: "16px 20px" }}>
              <div className="microlabel" style={{ marginBottom: 10 }}>Quick access</div>
              <div style={{ display: "flex", flexDirection: "column" }}>
                {[
                  { href: "/playground", label: "Playground", sub: "Try models interactively" },
                  { href: "/library",    label: "Knowledge library", sub: "Search shared docs & patterns" },
                  { href: "/skills",     label: "Skills catalog", sub: "Pre-built AI skill bundles" },
                  { href: "/prompts",    label: "Prompt library", sub: "Reusable team prompts" },
                ].map((l) => (
                  <Link key={l.href} href={l.href} style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 0", textDecoration: "none", borderBottom: "1px solid var(--rule)" }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 500, color: "var(--fg-1)" }}>{l.label}</div>
                      <div style={{ fontSize: 11.5, color: "var(--fg-3)" }}>{l.sub}</div>
                    </div>
                    <span style={{ fontSize: 12, color: "var(--fg-3)" }}>→</span>
                  </Link>
                ))}
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card__body" style={{ padding: "16px 20px" }}>
              <div className="microlabel" style={{ marginBottom: 10 }}>Team usage</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
                {[
                  { label: "Spend MTD", value: spendDisplay },
                  { label: "Requests", value: requestsDisplay },
                  { label: "Cache hit rate", value: cacheHitDisplay, good: true },
                  { label: "Tokens used", value: tokensDisplay },
                ].map((row) => (
                  <div key={row.label} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                    <span className="muted" style={{ fontSize: 12.5 }}>{row.label}</span>
                    <span className="num" style={{ fontSize: 13, fontWeight: 600, color: row.good ? "var(--good)" : undefined }}>
                      {loadingStats ? "…" : row.value}
                    </span>
                  </div>
                ))}
              </div>
              <Link href="/usage" className="btn btn--sm">Full usage report →</Link>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
