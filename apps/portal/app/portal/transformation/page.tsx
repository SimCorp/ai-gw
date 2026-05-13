"use client";

import { useState, useEffect } from "react";
import { useAuth } from "../_lib/authContext";

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";

const ACHIEVEMENT_META: Record<string, { label: string; icon: string; desc: string }> = {
  first_step:       { icon: "🚀", label: "First Step",       desc: "Made your first request through the AI Gateway" },
  tool_user:        { icon: "🔧", label: "Tool User",        desc: "Completed a session that used AI tools" },
  going_agentic:    { icon: "🤖", label: "Going Agentic",    desc: "First session classified as agentic" },
  autonomous:       { icon: "⚡", label: "Autonomous",       desc: "First fully autonomous agent session" },
  agentic_majority: { icon: "🏆", label: "Agentic Majority", desc: "Over 50% of your weekly usage is agentic" },
  ten_agent_commits:{ icon: "💎", label: "10 Agent Commits", desc: "10 agent sessions that produced a commit" },
  deep_thinker:     { icon: "🧠", label: "Deep Thinker",     desc: "Single session with 100+ tool invocations" },
  consistent:       { icon: "🔥", label: "Consistent",       desc: "5 consecutive days with agentic activity" },
};

interface TransformationData {
  score: number;
  stats: {
    total_sessions: number;
    agentic_sessions: number;
    agentic_session_pct: number;
    agentic_cost_pct: number;
    agent_commits: number;
  };
  achievements: { achievement: string; earned_at: string }[];
  weekly: { week: string; total: number; agentic: number; agentic_pct: number }[];
  leaderboard: {
    opted_in: string[];
    rank_team: { rank: number; total: number } | null;
    rank_company: { rank: number; total: number } | null;
  };
}

function ScoreRing({ score }: { score: number }) {
  const r = 44;
  const circ = 2 * Math.PI * r;
  const filled = (score / 100) * circ;
  const color = score >= 70 ? "var(--sc-blue)" : score >= 40 ? "#A855F7" : "var(--fg-3)";
  return (
    <svg width={112} height={112} viewBox="0 0 112 112">
      <circle cx={56} cy={56} r={r} fill="none" stroke="var(--rule)" strokeWidth={10} />
      <circle
        cx={56} cy={56} r={r} fill="none"
        stroke={color} strokeWidth={10}
        strokeDasharray={`${filled} ${circ - filled}`}
        strokeLinecap="round"
        transform="rotate(-90 56 56)"
        style={{ transition: "stroke-dasharray 0.6s ease" }}
      />
      <text x={56} y={52} textAnchor="middle" fontSize={26} fontWeight={700} fill="var(--fg-1)">{score}</text>
      <text x={56} y={68} textAnchor="middle" fontSize={11} fill="var(--fg-3)">/ 100</text>
    </svg>
  );
}

function WeeklyChart({ data }: { data: TransformationData["weekly"] }) {
  if (!data.length) return <div style={{ color: "var(--fg-3)", fontSize: 13, padding: "20px 0" }}>No session data yet.</div>;
  const max = Math.max(...data.map(w => w.total), 1);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 80 }}>
      {data.map(w => (
        <div key={w.week} title={`Week of ${w.week}: ${w.agentic}/${w.total} agentic (${w.agentic_pct}%)`}
          style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 1 }}>
          <div style={{ width: "100%", display: "flex", flexDirection: "column", justifyContent: "flex-end", height: 72 }}>
            <div style={{
              width: "100%",
              height: `${(w.total / max) * 68}px`,
              background: "var(--rule)",
              borderRadius: "3px 3px 0 0",
              position: "relative",
              overflow: "hidden",
            }}>
              <div style={{
                position: "absolute", bottom: 0, left: 0, right: 0,
                height: `${w.agentic_pct}%`,
                background: "var(--sc-blue)",
                transition: "height 0.4s ease",
              }} />
            </div>
          </div>
          <div style={{ fontSize: 9, color: "var(--fg-3)", whiteSpace: "nowrap" }}>
            {w.week.slice(5)}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function TransformationPage() {
  const { token, developer } = useAuth();
  const [data, setData] = useState<TransformationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"journey" | "setup">("journey");
  const [leaderboardUpdating, setLeaderboardUpdating] = useState(false);

  useEffect(() => {
    if (!token) return;
    fetch(`${ADMIN_BASE}/dev-auth/me/transformation`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(setData)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, [token]);

  async function toggleLeaderboard(scope: "team" | "company") {
    if (!token || !data) return;
    const current = data.leaderboard.opted_in.includes(scope);
    setLeaderboardUpdating(true);
    try {
      const res = await fetch(`${ADMIN_BASE}/dev-auth/me/leaderboard`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ scope, opt_in: !current }),
      });
      if (res.ok) {
        setData(prev => {
          if (!prev) return prev;
          const opted_in = current
            ? prev.leaderboard.opted_in.filter(s => s !== scope)
            : [...prev.leaderboard.opted_in, scope];
          return { ...prev, leaderboard: { ...prev.leaderboard, opted_in } };
        });
      }
    } finally {
      setLeaderboardUpdating(false);
    }
  }

  const earnedSet = new Set(data?.achievements.map(a => a.achievement) ?? []);

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <h1>AI Transformation</h1>
          <p>Track your journey from interactive to agentic AI usage.</p>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", borderBottom: "1px solid var(--rule)", marginBottom: 24 }}>
        {(["journey", "setup"] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: "10px 20px", fontSize: 13.5, fontWeight: 500,
            border: 0, background: "none", cursor: "pointer", fontFamily: "inherit",
            color: tab === t ? "var(--fg-1)" : "var(--fg-3)",
            borderBottom: tab === t ? "2px solid var(--sc-blue)" : "2px solid transparent",
            marginBottom: -1,
          }}>
            {t === "journey" ? "My Journey" : "Setup & Instructions"}
          </button>
        ))}
      </div>

      {tab === "journey" && (
        <>
          {loading && <div style={{ color: "var(--fg-3)", fontSize: 14 }}>Loading…</div>}
          {error && <div style={{ color: "var(--bad)", fontSize: 13 }}>Failed to load: {error}</div>}

          {data && (
            <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

              {/* Score + stats row */}
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                <div className="card" style={{ display: "flex", alignItems: "center", gap: 24, padding: "20px 28px" }}>
                  <ScoreRing score={data.score} />
                  <div>
                    <div style={{ fontSize: 13, color: "var(--fg-3)", marginBottom: 4 }}>Agentic Score</div>
                    <div style={{ fontSize: 22, fontWeight: 700, color: "var(--fg-1)" }}>{data.score} / 100</div>
                    <div style={{ fontSize: 12, color: "var(--fg-3)", marginTop: 6 }}>
                      {data.score >= 70 ? "Power user — mostly agentic" :
                       data.score >= 40 ? "In transition — growing agentic usage" :
                       "Early stage — mostly interactive"}
                    </div>
                  </div>
                </div>

                {[
                  { label: "Sessions (30d)", value: data.stats.total_sessions },
                  { label: "Agentic Sessions", value: `${data.stats.agentic_sessions} (${data.stats.agentic_session_pct}%)` },
                  { label: "Agentic Spend", value: `${data.stats.agentic_cost_pct}%` },
                  { label: "Agent Commits", value: data.stats.agent_commits },
                ].map(s => (
                  <div key={s.label} className="card" style={{ flex: 1, minWidth: 130, padding: "16px 20px" }}>
                    <div style={{ fontSize: 12, color: "var(--fg-3)", marginBottom: 6 }}>{s.label}</div>
                    <div style={{ fontSize: 22, fontWeight: 700, color: "var(--fg-1)" }}>{s.value}</div>
                  </div>
                ))}
              </div>

              {/* Weekly chart */}
              <div className="card" style={{ padding: "20px 24px" }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-2)", marginBottom: 16 }}>
                  Weekly agentic ratio
                  <span style={{ fontSize: 11, color: "var(--fg-3)", fontWeight: 400, marginLeft: 8 }}>
                    blue = agentic, grey = interactive
                  </span>
                </div>
                <WeeklyChart data={data.weekly} />
              </div>

              {/* Achievements */}
              <div className="card" style={{ padding: "20px 24px" }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-2)", marginBottom: 16 }}>
                  Achievements
                  <span style={{ fontSize: 11, color: "var(--fg-3)", fontWeight: 400, marginLeft: 8 }}>
                    {earnedSet.size} / {Object.keys(ACHIEVEMENT_META).length} earned
                  </span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
                  {Object.entries(ACHIEVEMENT_META).map(([key, meta]) => {
                    const earned = earnedSet.has(key);
                    const earnedAt = data.achievements.find(a => a.achievement === key)?.earned_at;
                    return (
                      <div key={key} style={{
                        padding: "14px 16px",
                        borderRadius: 8,
                        border: `1px solid ${earned ? "var(--sc-blue)" : "var(--rule)"}`,
                        background: earned ? "rgba(8,62,167,0.06)" : "var(--surface-soft, rgba(0,0,0,0.02))",
                        opacity: earned ? 1 : 0.5,
                        transition: "all 0.2s",
                      }}>
                        <div style={{ fontSize: 22, marginBottom: 6 }}>{meta.icon}</div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-1)" }}>{meta.label}</div>
                        <div style={{ fontSize: 11, color: "var(--fg-3)", marginTop: 3 }}>{meta.desc}</div>
                        {earned && earnedAt && (
                          <div style={{ fontSize: 10, color: "var(--sc-blue)", marginTop: 6 }}>
                            Earned {new Date(earnedAt).toLocaleDateString()}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Leaderboard */}
              <div className="card" style={{ padding: "20px 24px" }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-2)", marginBottom: 4 }}>Leaderboard</div>
                <div style={{ fontSize: 12, color: "var(--fg-3)", marginBottom: 16 }}>
                  Opt in to see how your agentic score compares. Your ranking is only visible to you.
                </div>
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                  {(["team", "company"] as const).map(scope => {
                    const optedIn = data.leaderboard.opted_in.includes(scope);
                    const rank = scope === "team" ? data.leaderboard.rank_team : data.leaderboard.rank_company;
                    return (
                      <div key={scope} style={{
                        padding: "14px 18px", borderRadius: 8, minWidth: 180,
                        border: `1px solid ${optedIn ? "var(--sc-blue)" : "var(--rule)"}`,
                        background: optedIn ? "rgba(8,62,167,0.06)" : "transparent",
                      }}>
                        <div style={{ fontSize: 12, color: "var(--fg-3)", marginBottom: 8, textTransform: "capitalize" }}>
                          {scope} leaderboard
                        </div>
                        {optedIn && rank ? (
                          <div style={{ fontSize: 22, fontWeight: 700, color: "var(--fg-1)", marginBottom: 6 }}>
                            #{rank.rank}
                            <span style={{ fontSize: 12, color: "var(--fg-3)", fontWeight: 400 }}> / {rank.total}</span>
                          </div>
                        ) : optedIn ? (
                          <div style={{ fontSize: 13, color: "var(--fg-3)", marginBottom: 6 }}>Calculating…</div>
                        ) : (
                          <div style={{ fontSize: 13, color: "var(--fg-3)", marginBottom: 6 }}>Not opted in</div>
                        )}
                        <button
                          onClick={() => toggleLeaderboard(scope)}
                          disabled={leaderboardUpdating}
                          className={optedIn ? "btn" : "btn btn--primary"}
                          style={{ fontSize: 12, padding: "5px 12px" }}
                        >
                          {optedIn ? "Opt out" : "Opt in"}
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>

            </div>
          )}
        </>
      )}

      {tab === "setup" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 720 }}>
          <div className="card" style={{ padding: "20px 24px" }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-2)", marginBottom: 8 }}>
              Claude Code hook
            </div>
            <div style={{ fontSize: 13, color: "var(--fg-3)", marginBottom: 16, lineHeight: 1.6 }}>
              Add this hook to your Claude Code config to send richer session data to the gateway.
              It runs automatically at the end of every Claude Code session.
            </div>
            <pre style={{
              background: "var(--bg)",
              border: "1px solid var(--rule)",
              borderRadius: 6,
              padding: "14px 16px",
              fontSize: 12,
              color: "var(--fg-2)",
              overflowX: "auto",
              lineHeight: 1.6,
            }}>{`# Add to ~/.claude/settings.json under "hooks":
{
  "hooks": {
    "PostToolUse": [],
    "Stop": [
      {
        "matcher": "",
        "hooks": [{
          "type": "command",
          "command": "curl -s -X POST ${ADMIN_BASE}/observe/session-end -H 'Content-Type: application/json' -H 'X-Developer-Token: YOUR_API_KEY' -d \\"{\\\\"repo\\\\":\\\\"$(git remote get-url origin 2>/dev/null | sed s/.*github.com.//)\\\\"}\\"  || true"
        }]
      }
    ]
  }
}`}</pre>
            <div style={{ fontSize: 12, color: "var(--fg-3)", marginTop: 12 }}>
              Replace <code style={{ background: "var(--bg)", padding: "1px 5px", borderRadius: 3 }}>YOUR_API_KEY</code> with one of your API keys from the{" "}
              <a href="/portal/keys" style={{ color: "var(--sc-link, var(--sc-blue))" }}>Keys page</a>.
            </div>
          </div>

          <div className="card" style={{ padding: "20px 24px" }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-2)", marginBottom: 8 }}>
              How classification works
            </div>
            <div style={{ fontSize: 13, color: "var(--fg-3)", lineHeight: 1.7 }}>
              <p style={{ margin: "0 0 10px" }}>Sessions are automatically classified based on your request patterns:</p>
              <ul style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 6 }}>
                <li><strong style={{ color: "var(--fg-2)" }}>Interactive</strong> — Single-turn or conversational usage, longer pauses between turns</li>
                <li><strong style={{ color: "var(--sc-blue)" }}>Agentic</strong> — Tool-heavy sessions or sustained multi-turn work with quick cadence</li>
                <li><strong style={{ color: "#A855F7" }}>Autonomous</strong> — Long-running agent loops with high tool density and minimal human input</li>
              </ul>
              <p style={{ margin: "12px 0 0" }}>The classifier runs nightly on completed sessions. Your score updates each morning.</p>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
