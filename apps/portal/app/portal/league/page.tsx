"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

const LEAGUE = process.env.NEXT_PUBLIC_LEAGUE_API ?? "http://localhost:8080/league";
const ADMIN_API = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";

type ChallengeStatus = "draft" | "active" | "closed";

interface Challenge {
  id: string;
  title: string;
  goal: string;
  status: ChallengeStatus;
  max_league_attempts: number;
  scores_revealed_at: string | null;
}

interface Season {
  id: string;
  name: string;
  status: string;
  starts_at: string;
  ends_at: string;
}

const STATUS_STYLES: Record<ChallengeStatus, { bg: string; color: string; label: string }> = {
  draft: { bg: "rgba(153,153,153,0.12)", color: "var(--fg-3)", label: "Draft" },
  active: { bg: "rgba(31,138,91,0.12)", color: "var(--good, #1F8A5B)", label: "Active" },
  closed: { bg: "rgba(180,83,9,0.12)", color: "var(--warn, #B45309)", label: "Closed" },
};

function StatusPill({ status }: { status: ChallengeStatus }) {
  const s = STATUS_STYLES[status];
  return (
    <span style={{
      display: "inline-block", padding: "2px 10px", borderRadius: 20,
      fontSize: 11.5, fontWeight: 600,
      background: s.bg, color: s.color,
    }}>{s.label}</span>
  );
}

export default function LeaguePage() {
  const [activeSeason, setActiveSeason] = useState<string | null>(null);

  const { data: seasonsData, isLoading: seasonsLoading } = useQuery<Season[]>({
    queryKey: ["portal-league-seasons"],
    queryFn: () => fetch(`${LEAGUE}/seasons`).then(r => r.json()),
  });

  const seasons = Array.isArray(seasonsData)
    ? seasonsData
    : (seasonsData as { seasons?: Season[] })?.seasons ?? [];

  const currentSeason = seasons.find(s => s.status === "active") ?? seasons[0] ?? null;
  const selectedSeasonId = activeSeason ?? currentSeason?.id ?? null;

  const { data: challengesData, isLoading: challengesLoading } = useQuery<Challenge[]>({
    queryKey: ["portal-league-challenges", selectedSeasonId],
    enabled: !!selectedSeasonId,
    queryFn: () => fetch(`${LEAGUE}/challenges?season_id=${selectedSeasonId}`).then(r => r.json()),
  });

  const challenges = Array.isArray(challengesData)
    ? challengesData
    : (challengesData as { challenges?: Challenge[] })?.challenges ?? [];

  const activeChallenges = challenges.filter(c => c.status === "active");
  const closedChallenges = challenges.filter(c => c.status === "closed");

  return (
    <div className="page">
      {/* Hero banner */}
      <div style={{
        background: "linear-gradient(135deg, rgba(8,62,167,0.25) 0%, rgba(124,58,237,0.15) 100%)",
        border: "1px solid rgba(8,62,167,0.3)",
        borderRadius: 12, padding: "28px 28px 24px",
        marginBottom: 24,
        position: "relative", overflow: "hidden",
      }}>
        <div style={{
          position: "absolute", right: 24, top: 0, bottom: 0,
          display: "flex", alignItems: "center", fontSize: 80, opacity: 0.12,
          pointerEvents: "none",
        }}>⚔️</div>
        <div style={{ fontSize: 12.5, fontWeight: 600, color: "rgba(147,197,253,0.8)", marginBottom: 8, letterSpacing: "0.06em", textTransform: "uppercase" }}>
          AI-League
        </div>
        <h1 style={{ margin: "0 0 8px", fontSize: 26, fontWeight: 700, color: "#fff" }}>
          Challenges
        </h1>
        <p style={{ margin: 0, fontSize: 13.5, color: "rgba(200,205,220,0.8)", maxWidth: 500 }}>
          Design agent configurations to solve curated challenges. Earn points, climb the leaderboard, and unlock cosmetics.
        </p>
        <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
          <Link href="/portal/league/leaderboard" style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            padding: "8px 16px", borderRadius: 8, fontSize: 13, fontWeight: 600,
            background: "rgba(255,255,255,0.1)", color: "#fff", textDecoration: "none",
            border: "1px solid rgba(255,255,255,0.15)",
          }}>🏆 Leaderboard</Link>
          <Link href="/portal/league/results" style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            padding: "8px 16px", borderRadius: 8, fontSize: 13, fontWeight: 600,
            background: "rgba(255,255,255,0.06)", color: "rgba(200,205,220,0.9)", textDecoration: "none",
            border: "1px solid rgba(255,255,255,0.1)",
          }}>📊 My Results</Link>
          <Link href="/portal/league/store" style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            padding: "8px 16px", borderRadius: 8, fontSize: 13, fontWeight: 600,
            background: "rgba(255,255,255,0.06)", color: "rgba(200,205,220,0.9)", textDecoration: "none",
            border: "1px solid rgba(255,255,255,0.1)",
          }}>🛒 Store</Link>
        </div>
      </div>

      {/* Season selector */}
      {seasons.length > 1 && (
        <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
          {seasons.map(s => (
            <button
              key={s.id}
              onClick={() => setActiveSeason(s.id)}
              style={{
                padding: "6px 14px", borderRadius: 20, fontSize: 12.5, fontWeight: 500,
                border: "1px solid var(--rule)", cursor: "pointer",
                background: (activeSeason ?? currentSeason?.id) === s.id ? "var(--sc-blue, #083EA7)" : "transparent",
                color: (activeSeason ?? currentSeason?.id) === s.id ? "#fff" : "var(--fg-2)",
              }}
            >
              {s.name} {s.status === "active" && <span style={{ marginLeft: 4, color: "var(--good, #1F8A5B)" }}>●</span>}
            </button>
          ))}
        </div>
      )}

      {/* Active challenges */}
      {challengesLoading ? (
        <div style={{ textAlign: "center", padding: "40px", color: "var(--fg-3)" }}>Loading challenges…</div>
      ) : activeChallenges.length === 0 && closedChallenges.length === 0 ? (
        <div style={{
          textAlign: "center", padding: "60px 20px",
          border: "1px dashed var(--rule)", borderRadius: 10, color: "var(--fg-3)",
        }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>⚔️</div>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>No challenges yet</div>
          <div style={{ fontSize: 13 }}>
            {seasonsLoading ? "Loading…" : "Check back when the next challenge is published"}
          </div>
        </div>
      ) : (
        <>
          {activeChallenges.length > 0 && (
            <section style={{ marginBottom: 28 }}>
              <h2 style={{ margin: "0 0 12px", fontSize: 14, fontWeight: 600, color: "var(--fg-2)" }}>
                Active challenges
              </h2>
              <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))" }}>
                {activeChallenges.map(c => <ChallengeCard key={c.id} challenge={c} />)}
              </div>
            </section>
          )}
          {closedChallenges.length > 0 && (
            <section>
              <h2 style={{ margin: "0 0 12px", fontSize: 14, fontWeight: 600, color: "var(--fg-2)" }}>
                Past challenges
              </h2>
              <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))" }}>
                {closedChallenges.map(c => <ChallengeCard key={c.id} challenge={c} />)}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}

function ChallengeCard({ challenge }: { challenge: Challenge }) {
  return (
    <div style={{
      background: "var(--surface)", border: "1px solid var(--rule)",
      borderRadius: 10, padding: "18px",
      display: "flex", flexDirection: "column", gap: 12,
      opacity: challenge.status === "closed" ? 0.75 : 1,
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
        <div style={{ fontWeight: 600, fontSize: 14, lineHeight: 1.3 }}>{challenge.title}</div>
        <StatusPill status={challenge.status} />
      </div>
      <div style={{ fontSize: 12.5, color: "var(--fg-3)", lineHeight: 1.5, flex: 1 }}>{challenge.goal}</div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", paddingTop: 10, borderTop: "1px solid var(--rule)" }}>
        <span style={{ fontSize: 11.5, color: "var(--fg-3)" }}>
          {challenge.max_league_attempts} attempts
        </span>
        {challenge.status === "active" ? (
          <Link
            href={`/portal/playground?challenge=${challenge.id}`}
            style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              padding: "6px 14px", borderRadius: 6, fontSize: 12.5, fontWeight: 600,
              background: "var(--sc-blue, #083EA7)", color: "#fff", textDecoration: "none",
            }}
          >
            ▶ Attempt
          </Link>
        ) : (
          <Link
            href={`/portal/league/results?challenge=${challenge.id}`}
            style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              padding: "6px 14px", borderRadius: 6, fontSize: 12.5, fontWeight: 500,
              background: "transparent", color: "var(--fg-2)", textDecoration: "none",
              border: "1px solid var(--rule)",
            }}
          >
            View results
          </Link>
        )}
      </div>
    </div>
  );
}
