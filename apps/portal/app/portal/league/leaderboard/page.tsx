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
  if (rank <= 3) return <span style={{ fontSize: 20 }}>{MEDAL[rank]}</span>;
  return <span className="lg-rank">#{rank}</span>;
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
      <div className="page__head">
        <div>
          <h1 className="page__title">Leaderboard</h1>
          <p className="page__sub">Top engineers for the current AI-League season</p>
        </div>
        <div className="page__actions">
          <Link href="/portal/league" className="btn">
            ← Quest board
          </Link>
        </div>
      </div>

      {/* Season picker */}
      {seasons.length > 1 && (
        <div className="lg-seasons">
          {seasons.map(s => (
            <button
              key={s.id}
              type="button"
              className={`lg-season${(selectedSeason ?? activeSeason?.id) === s.id ? " is-active" : ""}`}
              onClick={() => setSelectedSeason(s.id)}
            >
              {s.name}
            </button>
          ))}
        </div>
      )}

      {isLoading ? (
        <div style={{ textAlign: "center", padding: 60, color: "var(--fg-3)" }}>Loading…</div>
      ) : entries.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "60px 20px",
            border: "1px dashed var(--rule)",
            borderRadius: 10,
            color: "var(--fg-3)",
          }}
        >
          <div style={{ fontSize: 36, marginBottom: 12 }}>🏆</div>
          <div style={{ fontWeight: 600, marginBottom: 6, color: "var(--fg-1)" }}>No rankings yet</div>
          <div style={{ fontSize: 13 }}>Be the first to submit a league entry!</div>
        </div>
      ) : (
        <>
          {/* Podium */}
          {topThree.length > 0 && (
            <div className="lg-podium">
              {topThree.map(e => (
                <div key={e.engineer_id} className={`lg-podium__slot lg-podium__slot--${e.rank}`}>
                  <div className="lg-podium__medal">{MEDAL[e.rank]}</div>
                  <div className="lg-podium__name">{e.display_name}</div>
                  <div className="lg-podium__score">{Math.round(e.composite_score)}</div>
                  <div className="lg-podium__pts">★ {e.points_earned.toLocaleString()} pts</div>
                </div>
              ))}
            </div>
          )}

          {/* Rest of rankings */}
          {rest.length > 0 && (
            <div className="card card__body--flush" style={{ overflow: "hidden" }}>
              <table className="tbl">
                <thead>
                  <tr>
                    <th style={{ width: 64, textAlign: "center" }}>Rank</th>
                    <th>Engineer</th>
                    <th className="num">Score</th>
                    <th className="num">Points</th>
                  </tr>
                </thead>
                <tbody>
                  {rest.map(e => (
                    <tr key={e.engineer_id}>
                      <td style={{ textAlign: "center" }}>
                        <RankBadge rank={e.rank} />
                      </td>
                      <td style={{ fontWeight: 500 }}>{e.display_name}</td>
                      <td className="num">
                        <span className="mono" style={{ fontWeight: 650, color: "var(--accent-text)" }}>
                          {Math.round(e.composite_score)}
                        </span>
                      </td>
                      <td className="num">
                        <span className="mono" style={{ color: "var(--league-gold)" }}>
                          ★ {e.points_earned.toLocaleString()}
                        </span>
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
