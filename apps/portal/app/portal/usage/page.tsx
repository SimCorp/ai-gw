"use client";

import { useState, useEffect } from "react";
import { useTeam } from "../_lib/teamContext";

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";

// Pre-computed SVG bar data — decorative time series (no time-series endpoint exists)
const BAR_DATA = [
  [142,11.9,14.62],[37.46,12.87,15.22],[46.14,13.09,15.4],[53.39,8.65,15.14],[41.99,8.34,14.46],
  [45.41,8.4,13.43],[47.01,4.94,12.14],[47.27,6.52,10.7],[30.06,8.91,9.25],[29.77,7.66,7.9],
  [30.36,10.79,6.79],[32.46,13.68,6.01],[19.65,11.76,5.63],[25.62,13.22,5.69],[33.35,13.84,6.17],
  [42.33,9.61,7.04],[35.07,9.29,8.22],[44.38,9.09,9.61],[52.7,5.21,11.07],[59.45,6.31,12.48],
  [47.47,8.26,13.72],[50.32,6.74,14.67],[51.47,9.82,15.24],[51.46,12.89,15.39],[34.2,11.35,15.11],
  [34.1,13.29,14.41],[35.07,14.38,13.37],[37.69,10.48,12.06],[25.46,10.28,10.62],[31.98,9.96,9.17],
];

const RANGE_OPTS = ["24h", "7d", "30d", "MTD"] as const;

interface TeamStat {
  team_name: string;
  request_count: number;
  total_tokens: number;
  total_cost_usd: number;
  cache_hit_pct: number;
}

export default function UsagePage() {
  const { teamId, teamName } = useTeam();
  const [range, setRange] = useState<string>("30d");
  const [stat, setStat] = useState<TeamStat | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!teamId || !teamName) return;
    setLoading(true);
    setError(null);
    fetch(`${ADMIN_BASE}/dashboard/stats`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: TeamStat[]) => {
        const match = data.find((s) => s.team_name === teamName);
        setStat(match ?? { team_name: teamName, request_count: 0, total_tokens: 0, total_cost_usd: 0, cache_hit_pct: 0 });
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [teamId, teamName]);

  if (!teamId) {
    return (
      <main className="pmain">
        <div className="phero">
          <div>
            <h1>Usage &amp; spend</h1>
            <p>Select a team from the sidebar to see usage data.</p>
          </div>
        </div>
      </main>
    );
  }

  const formatCost = (v: number) => `$${v.toFixed(2)}`;
  const formatTokens = (v: number) => v >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M` : v >= 1_000 ? `${(v / 1_000).toFixed(1)}K` : String(v);
  const formatPct = (v: number) => `${v.toFixed(1)}%`;

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <h1>Usage &amp; spend</h1>
          <p>Your activity on <strong>{teamName}</strong> · last 30 days</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <div className="seg">
            {RANGE_OPTS.map((r) => (
              <button key={r} className={range === r ? "is-active" : ""} onClick={() => setRange(r)}>{r}</button>
            ))}
          </div>
          <button className="btn">Export CSV</button>
        </div>
      </div>

      {error && (
        <div className="card" style={{ borderColor: "var(--bad)", marginBottom: 16 }}>
          <div className="card__body" style={{ color: "var(--bad)", fontSize: 13 }}>
            Failed to load stats: {error}
          </div>
        </div>
      )}

      <div className="stat-strip">
        <div className="s">
          <div className="l">Spend · 30d</div>
          <div className="v">{loading ? "—" : stat ? formatCost(stat.total_cost_usd) : "—"}</div>
          <div className="d">cumulative</div>
        </div>
        <div className="s">
          <div className="l">Requests</div>
          <div className="v">{loading ? "—" : stat ? stat.request_count.toLocaleString() : "—"}</div>
          <div className="d">total requests</div>
        </div>
        <div className="s">
          <div className="l">Tokens</div>
          <div className="v" style={{ fontSize: 18 }}>{loading ? "—" : stat ? formatTokens(stat.total_tokens) : "—"}</div>
          <div className="d">total tokens</div>
        </div>
        <div className="s">
          <div className="l">Cache hit</div>
          <div className="v good">{loading ? "—" : stat ? formatPct(stat.cache_hit_pct) : "—"}</div>
          <div className="d">semantic cache</div>
        </div>
      </div>

      {/* Stacked bar chart — decorative (no time-series endpoint) */}
      <div className="card" style={{ marginBottom: 18 }}>
        <div className="card__head">
          <h3 className="card__title">Spend over time</h3>
          <span className="card__sub">stacked by model · illustrative</span>
          <div className="card__actions">
            <span className="pill"><span className="dot" style={{ background: "#D97757" }} />Sonnet</span>
            <span className="pill"><span className="dot" style={{ background: "#FB9B2A" }} />Haiku</span>
            <span className="pill"><span className="dot" style={{ background: "#4285F4" }} />Gemini</span>
          </div>
        </div>
        <div className="card__body">
          <svg viewBox="0 0 600 220" style={{ width: "100%", height: 220, display: "block" }}>
            {/* Grid lines */}
            <g stroke="var(--rule)" strokeWidth="1">
              <line x1="40" y1="20" x2="588" y2="20"/>
              <line x1="40" y1="70" x2="588" y2="70"/>
              <line x1="40" y1="120" x2="588" y2="120"/>
              <line x1="40" y1="170" x2="588" y2="170"/>
            </g>
            <g fill="var(--fg-3)" fontSize="10" fontFamily="var(--font-mono)">
              <text x="36" y="24" textAnchor="end">$20</text>
              <text x="36" y="74" textAnchor="end">$15</text>
              <text x="36" y="124" textAnchor="end">$10</text>
              <text x="36" y="174" textAnchor="end">$0</text>
            </g>
            <g>
              {BAR_DATA.map(([sonnet, haiku, gemini], i) => {
                const x = 48 + i * 18;
                const totalH = sonnet + haiku + gemini;
                const y3 = 170 - totalH;
                const y2 = 170 - sonnet - haiku;
                const y1 = 170 - sonnet;
                return (
                  <g key={i}>
                    <rect x={x} y={y1} width={12} height={sonnet} fill="#D97757" rx={1}/>
                    <rect x={x} y={y2} width={12} height={haiku} fill="#FB9B2A" rx={1}/>
                    <rect x={x} y={y3} width={12} height={gemini} fill="#4285F4" rx={1}/>
                  </g>
                );
              })}
            </g>
            <g fill="var(--fg-3)" fontSize="10" fontFamily="var(--font-mono)">
              <text x="48" y="190">Apr 7</text>
              <text x="296" y="190">Apr 22</text>
              <text x="588" y="190" textAnchor="end">May 6</text>
            </g>
          </svg>
        </div>
      </div>

      <div className="split-2">
        {/* Summary card */}
        <div className="card">
          <div className="card__head"><h3 className="card__title">Team summary</h3></div>
          <div className="card__body">
            {loading ? (
              <div style={{ fontSize: 13, color: "var(--fg-3)" }}>Loading…</div>
            ) : stat ? (
              <table className="tbl">
                <tbody>
                  <tr>
                    <td>Total spend</td>
                    <td className="num"><span className="mono">{formatCost(stat.total_cost_usd)}</span></td>
                  </tr>
                  <tr>
                    <td>Total requests</td>
                    <td className="num"><span className="mono">{stat.request_count.toLocaleString()}</span></td>
                  </tr>
                  <tr>
                    <td>Total tokens</td>
                    <td className="num"><span className="mono">{formatTokens(stat.total_tokens)}</span></td>
                  </tr>
                  <tr>
                    <td>Cache hit rate</td>
                    <td className="num"><span className="mono">{formatPct(stat.cache_hit_pct)}</span></td>
                  </tr>
                </tbody>
              </table>
            ) : (
              <div style={{ fontSize: 13, color: "var(--fg-3)" }}>No data available.</div>
            )}
          </div>
        </div>

        {/* Info card */}
        <div className="card">
          <div className="card__head"><h3 className="card__title">About these stats</h3></div>
          <div className="card__body">
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.7 }}>
              <li>Stats are aggregate for your team — all keys combined.</li>
              <li>Cache hit percentage reflects semantic cache effectiveness.</li>
              <li>Cost is approximate and billed monthly.</li>
              <li>Per-key and per-model breakdown coming soon.</li>
            </ul>
          </div>
        </div>
      </div>
    </main>
  );
}
