"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

const LEAGUE = process.env.NEXT_PUBLIC_LEAGUE_API ?? "http://localhost:8080/league";

interface LeaderboardEntry {
  rank: number;
  engineer_id: string;
  display_name: string;
  composite_score: number;
  points_earned: number;
  challenges_completed?: number;
}

interface Season {
  id: string;
  name: string;
  status: string;
}

const MEDAL: Record<number, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };

function RankBadge({ rank }: { rank: number }) {
  if (rank <= 3) return <span style={{ fontSize: 22 }}>{MEDAL[rank]}</span>;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      width: 30, height: 30, borderRadius: "50%",
      background: "var(--surface-soft, rgba(0,0,0,0.08))", color: "var(--fg-3)",
      fontSize: 13, fontWeight: 600, fontFamily: "var(--font-mono)",
    }}>#{rank}</span>
  );
}

export default function LeaderboardPage() {
  const [selectedSeason, setSelectedSeason] = useState<string | null>(null);

  const { data: seasonsData } = useQuery<Season[] | { seasons?: Season[] }>({
    queryKey: ["portal-lb-seasons"],
    queryFn: () => fetch(`${LEAGUE}/seasons`).then(r => r.json()),
  });

  const seasons = Array.isArray(seasonsData)
    ? seasonsData
    : seasonsData?.seasons ?? [];

  const activeSeason = seasons.find(s => s.status === "active") ?? seasons[0] ?? null;
  const seasonId = selectedSeason ?? activeSeason?.id ?? null;

  const { data, isLoading } = useQuery<LeaderboardEntry[] | { entries?: LeaderboardEntry[] }>({
    queryKey: ["portal-leaderboard", seasonId],
    enabled: !!seasonId,
    queryFn: () => fetch(`${LEAGUE}/seasons/${seasonId}/leaderboard`).then(r => r.json()),
  });

  const entries = Array.isArray(data) ? data : data?.entries ?? [];

  const topThree = entries.slice(0, 3);
  const rest = entries.slice(3);

  return (
    <div className="page">
      <div className="page__header">
        <div>
          <h1 className="page__title">Leaderboard</h1>
          <p className="page__sub">Top engineers for the current AI-League season</p>
        </div>
        <Link href="/portal/league" style={{
          padding: "7px 14px", borderRadius: 6, border: "1px solid var(--rule)",
          background: "transparent", color: "var(--fg-2)", textDecoration: "none", fontSize: 13,
        }}>← Challenges</Link>
      </div>

      {/* Season picker */}
      {seasons.length > 1 && (
        <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
          {seasons.map(s => (
            <button key={s.id} onClick={() => setSelectedSeason(s.id)} style={{
              padding: "6px 14px", borderRadius: 20, fontSize: 12.5, fontWeight: 500,
              border: "1px solid var(--rule)", cursor: "pointer",
              background: (selectedSeason ?? activeSeason?.id) === s.id ? "var(--sc-blue, #083EA7)" : "transparent",
              color: (selectedSeason ?? activeSeason?.id) === s.id ? "#fff" : "var(--fg-2)",
            }}>{s.name}</button>
          ))}
        </div>
      )}

      {isLoading ? (
        <div style={{ textAlign: "center", padding: "60px", color: "var(--fg-3)" }}>Loading…</div>
      ) : entries.length === 0 ? (
        <div style={{
          textAlign: "center", padding: "60px 20px",
          border: "1px dashed var(--rule)", borderRadius: 10, color: "var(--fg-3)",
        }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>🏆</div>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>No rankings yet</div>
          <div style={{ fontSize: 13 }}>Be the first to submit a league entry!</div>
        </div>
      ) : (
        <>
          {/* Podium */}
          {topThree.length > 0 && (
            <div style={{
              display: "flex", gap: 12, justifyContent: "center",
              marginBottom: 28, padding: "24px",
              background: "linear-gradient(135deg, rgba(8,62,167,0.1) 0%, rgba(124,58,237,0.07) 100%)",
              border: "1px solid rgba(8,62,167,0.2)", borderRadius: 12,
            }}>
              {topThree.map(e => (
                <div key={e.engineer_id} style={{
                  flex: 1, maxWidth: 200, textAlign: "center",
                  padding: "16px 12px",
                  background: "var(--surface)", border: "1px solid var(--rule)",
                  borderRadius: 10,
                  marginTop: e.rank === 1 ? 0 : e.rank === 2 ? 20 : 30,
                }}>
                  <div style={{ marginBottom: 8 }}>
                    <RankBadge rank={e.rank} />
                  </div>
                  <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>{e.display_name}</div>
                  <div style={{
                    fontSize: 20, fontWeight: 700, fontFamily: "var(--font-mono)",
                    color: "var(--sc-blue, #083EA7)", marginBottom: 2,
                  }}>{Math.round(e.composite_score)}</div>
                  <div style={{ fontSize: 11, color: "var(--fg-3)" }}>★ {e.points_earned.toLocaleString()} pts</div>
                </div>
              ))}
            </div>
          )}

          {/* Rest of rankings */}
          {rest.length > 0 && (
            <div style={{
              background: "var(--surface)", border: "1px solid var(--rule)", borderRadius: 10, overflow: "hidden",
            }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--rule)" }}>
                    {["Rank", "Engineer", "Score", "Points"].map(h => (
                      <th key={h} style={{
                        padding: "10px 16px", textAlign: h === "Rank" ? "center" : "left",
                        fontSize: 11.5, fontWeight: 600, color: "var(--fg-3)",
                        textTransform: "uppercase", letterSpacing: "0.05em",
                        background: "var(--bg)",
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rest.map((e, i) => (
                    <tr key={e.engineer_id} style={{
                      borderBottom: i < rest.length - 1 ? "1px solid var(--rule)" : "none",
                    }}>
                      <td style={{ padding: "12px 16px", textAlign: "center" }}>
                        <RankBadge rank={e.rank} />
                      </td>
                      <td style={{ padding: "12px 16px", fontWeight: 500, fontSize: 13 }}>
                        {e.display_name}
                      </td>
                      <td style={{ padding: "12px 16px", fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 600, color: "var(--sc-blue, #083EA7)" }}>
                        {Math.round(e.composite_score)}
                      </td>
                      <td style={{ padding: "12px 16px", fontSize: 13, color: "var(--warn, #B45309)", fontWeight: 500 }}>
                        ★ {e.points_earned.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
