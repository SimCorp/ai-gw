"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import LevelBadge from "./_components/LevelBadge";
import XPBar from "./_components/XPBar";
import { levelFor } from "./_components/level";

const LEAGUE = process.env.NEXT_PUBLIC_LEAGUE_API ?? "http://localhost:8080/league";

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

interface PointBalance {
  balance: number;
  lifetime_earned: number;
  lifetime_spent: number;
}

export default function LeaguePage() {
  const [activeSeason, setActiveSeason] = useState<string | null>(null);

  const { data: seasonsData, isLoading: seasonsLoading } = useQuery<Season[] | { seasons?: Season[] }>({
    queryKey: ["portal-league-seasons"],
    queryFn: () => fetch(`${LEAGUE}/seasons`).then(r => r.json()),
  });

  const seasons = Array.isArray(seasonsData)
    ? seasonsData
    : seasonsData?.seasons ?? [];

  const currentSeason = seasons.find(s => s.status === "active") ?? seasons[0] ?? null;
  const selectedSeasonId = activeSeason ?? currentSeason?.id ?? null;

  const { data: challengesData, isLoading: challengesLoading } = useQuery<Challenge[] | { challenges?: Challenge[] }>({
    queryKey: ["portal-league-challenges", selectedSeasonId],
    enabled: !!selectedSeasonId,
    queryFn: () => fetch(`${LEAGUE}/seasons/${selectedSeasonId}/challenges`).then(r => r.json()),
  });

  // Same endpoint the store uses — powers the level/XP header.
  const { data: balanceData } = useQuery<PointBalance>({
    queryKey: ["portal-balance"],
    queryFn: () => fetch(`${LEAGUE}/store/balance`).then(r => r.json()),
  });

  const challenges = Array.isArray(challengesData)
    ? challengesData
    : challengesData?.challenges ?? [];

  const activeChallenges = challenges.filter(c => c.status === "active");
  const closedChallenges = challenges.filter(c => c.status === "closed");
  const level = levelFor(balanceData?.lifetime_earned ?? 0);

  return (
    <div className="page">
      {/* Hero */}
      <div className="lg-hero">
        <div className="lg-hero__glyph" />
        <div className="lg-hero__kicker">AI-League · Season {currentSeason?.name ?? "—"}</div>
        <h1>Quest board</h1>
        <p>
          Take on curated AI challenges, earn XP, climb the leaderboard, and spend your
          points in the reward shop.
        </p>
        <div className="lg-hero__actions">
          <Link href="/portal/league/leaderboard" className="btn">🏆 Leaderboard</Link>
          <Link href="/portal/league/results" className="btn">📊 My results</Link>
          <Link href="/portal/league/store" className="btn">🛒 Reward shop</Link>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
            <LevelBadge level={level.level} />
            <XPBar info={level} />
          </div>
        </div>
      </div>

      {/* Season selector */}
      {seasons.length > 1 && (
        <div className="lg-seasons">
          {seasons.map(s => (
            <button
              key={s.id}
              type="button"
              className={`lg-season${(activeSeason ?? currentSeason?.id) === s.id ? " is-active" : ""}`}
              onClick={() => setActiveSeason(s.id)}
            >
              {s.name}
              {s.status === "active" && <span style={{ marginLeft: 5, color: "var(--good)" }}>●</span>}
            </button>
          ))}
        </div>
      )}

      {/* Quests */}
      {challengesLoading ? (
        <div style={{ textAlign: "center", padding: 40, color: "var(--fg-3)" }}>Loading quests…</div>
      ) : activeChallenges.length === 0 && closedChallenges.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "60px 20px",
            border: "1px dashed var(--rule)",
            borderRadius: 10,
            color: "var(--fg-3)",
          }}
        >
          <div style={{ fontSize: 36, marginBottom: 12 }}>⚔️</div>
          <div style={{ fontWeight: 600, marginBottom: 6, color: "var(--fg-1)" }}>No quests yet</div>
          <div style={{ fontSize: 13 }}>
            {seasonsLoading ? "Loading…" : "Check back when the next challenge is published"}
          </div>
        </div>
      ) : (
        <>
          {activeChallenges.length > 0 && (
            <section style={{ marginBottom: 28 }}>
              <div className="microlabel" style={{ marginBottom: 12 }}>
                ACTIVE_QUESTS ({activeChallenges.length})
              </div>
              <div className="lg-questboard">
                {activeChallenges.map(c => (
                  <QuestCard key={c.id} challenge={c} />
                ))}
              </div>
            </section>
          )}
          {closedChallenges.length > 0 && (
            <section>
              <div className="microlabel" style={{ marginBottom: 12 }}>
                COMPLETED ({closedChallenges.length})
              </div>
              <div className="lg-questboard">
                {closedChallenges.map(c => (
                  <QuestCard key={c.id} challenge={c} />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}

function QuestCard({ challenge }: { challenge: Challenge }) {
  const mod =
    challenge.status === "active" ? "lg-quest--active" : challenge.status === "closed" ? "lg-quest--closed" : "";
  return (
    <div className={`lg-quest ${mod}`}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
        <div className="lg-quest__title">{challenge.title}</div>
        <span className={`lg-quest__ribbon lg-quest__ribbon--${challenge.status}`}>{challenge.status}</span>
      </div>
      <div className="lg-quest__goal">{challenge.goal}</div>
      <div className="lg-quest__meta">
        <span className="lg-quest__attempts">ATTEMPTS ×{challenge.max_league_attempts}</span>
        {challenge.status === "active" ? (
          <Link href={`/portal/playground?challenge=${challenge.id}`} className="lg-btn-gold">
            ▶ Start quest
          </Link>
        ) : (
          <Link href={`/portal/league/results?challenge=${challenge.id}`} className="btn btn--sm">
            View results
          </Link>
        )}
      </div>
    </div>
  );
}
