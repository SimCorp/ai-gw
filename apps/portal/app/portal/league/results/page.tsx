"use client";

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

const LEAGUE = process.env.NEXT_PUBLIC_LEAGUE_API ?? "http://localhost:8080/league";

interface Submission {
  id: string;
  challenge_id: string;
  challenge_title?: string;
  mode: "training" | "league";
  attempt_number: number;
  submitted_at: string;
  scores?: {
    quality: number;
    robustness: number;
    token_efficiency: number;
    speed: number;
    cost_efficiency: number;
    improvement_rate: number;
    creativity: number;
    composite: number;
  };
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = Math.min(100, Math.max(0, value));
  const color = pct >= 70 ? "var(--good, #1F8A5B)" : pct >= 40 ? "var(--warn, #B45309)" : "var(--bad, #DC2626)";
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 12.5 }}>
        <span style={{ color: "var(--fg-2)" }}>{label}</span>
        <span style={{ fontWeight: 600, color }}>{Math.round(pct)}</span>
      </div>
      <div style={{ height: 6, background: "var(--rule)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{
          height: "100%", width: `${pct}%`, borderRadius: 3,
          background: color, transition: "width 0.5s ease",
        }} />
      </div>
    </div>
  );
}

function CompositeRing({ score }: { score: number }) {
  const norm = Math.min(1000, Math.max(0, score)) / 1000;
  const r = 36, cx = 44, cy = 44;
  const circ = 2 * Math.PI * r;
  const dash = norm * circ;
  const color = norm >= 0.7 ? "var(--good, #1F8A5B)" : norm >= 0.4 ? "var(--warn, #B45309)" : "var(--bad, #DC2626)";

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
      <svg width={88} height={88} viewBox="0 0 88 88">
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--rule)" strokeWidth={10} />
        <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth={10}
          strokeDasharray={`${dash} ${circ - dash}`}
          strokeDashoffset={circ / 4}
          strokeLinecap="round"
          style={{ transition: "stroke-dasharray 0.5s ease" }}
        />
        <text x={cx} y={cy - 4} textAnchor="middle" fill="var(--fg-1)" fontSize="14" fontWeight="700"
          fontFamily="var(--font-mono)">{Math.round(score)}</text>
        <text x={cx} y={cy + 12} textAnchor="middle" fill="var(--fg-3)" fontSize="10">/ 1000</text>
      </svg>
      <span style={{ fontSize: 11.5, color: "var(--fg-3)" }}>Composite</span>
    </div>
  );
}

export default function ResultsPage() {
  const params = useSearchParams();
  const challengeFilter = params.get("challenge");

  const { data, isLoading, error } = useQuery<Submission[]>({
    queryKey: ["portal-my-submissions", challengeFilter],
    queryFn: () => {
      const url = challengeFilter
        ? `${LEAGUE}/submissions/mine?challenge_id=${challengeFilter}`
        : `${LEAGUE}/submissions/mine`;
      return fetch(url).then(r => r.json());
    },
  });

  const submissions = Array.isArray(data) ? data : (data as { submissions?: Submission[] })?.submissions ?? [];
  const leagueSubmissions = submissions.filter(s => s.mode === "league");
  const trainingSubmissions = submissions.filter(s => s.mode === "training");

  if (isLoading) return (
    <div className="page">
      <h1 className="page__title">My Results</h1>
      <div style={{ textAlign: "center", padding: "60px", color: "var(--fg-3)" }}>Loading results…</div>
    </div>
  );

  if (error) return (
    <div className="page">
      <h1 className="page__title">My Results</h1>
      <div style={{ textAlign: "center", padding: "60px", color: "var(--bad)" }}>Could not load results</div>
    </div>
  );

  return (
    <div className="page">
      <div className="page__header">
        <div>
          <h1 className="page__title">My Results</h1>
          <p className="page__sub">Your AI-League submission history and scores</p>
        </div>
        <Link href="/portal/league" style={{
          padding: "7px 14px", borderRadius: 6, border: "1px solid var(--rule)",
          background: "transparent", color: "var(--fg-2)", textDecoration: "none", fontSize: 13,
        }}>← Back to challenges</Link>
      </div>

      {submissions.length === 0 ? (
        <div style={{
          textAlign: "center", padding: "60px 20px",
          border: "1px dashed var(--rule)", borderRadius: 10, color: "var(--fg-3)",
        }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>📊</div>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>No submissions yet</div>
          <div style={{ fontSize: 13, marginBottom: 18 }}>
            Attempt an active challenge to see your scores here
          </div>
          <Link href="/portal/league" style={{
            display: "inline-flex", padding: "8px 18px", borderRadius: 7,
            background: "var(--sc-blue, #083EA7)", color: "#fff", textDecoration: "none",
            fontSize: 13, fontWeight: 600,
          }}>View challenges</Link>
        </div>
      ) : (
        <>
          {leagueSubmissions.length > 0 && (
            <section style={{ marginBottom: 28 }}>
              <h2 style={{ margin: "0 0 14px", fontSize: 14, fontWeight: 600, color: "var(--fg-2)" }}>
                League attempts ({leagueSubmissions.length})
              </h2>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {leagueSubmissions.map(s => <SubmissionCard key={s.id} submission={s} />)}
              </div>
            </section>
          )}
          {trainingSubmissions.length > 0 && (
            <section>
              <h2 style={{ margin: "0 0 14px", fontSize: 14, fontWeight: 600, color: "var(--fg-2)" }}>
                Training runs ({trainingSubmissions.length})
              </h2>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {trainingSubmissions.map(s => (
                  <div key={s.id} style={{
                    background: "var(--surface)", border: "1px solid var(--rule)",
                    borderRadius: 8, padding: "12px 16px",
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                  }}>
                    <div>
                      <span style={{ fontWeight: 500, fontSize: 13 }}>{s.challenge_title ?? "Challenge"}</span>
                      <span style={{ marginLeft: 10, fontSize: 12, color: "var(--fg-3)" }}>
                        Attempt #{s.attempt_number} · {new Date(s.submitted_at).toLocaleDateString()}
                      </span>
                    </div>
                    {s.scores && (
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--fg-2)" }}>
                        Q: {Math.round(s.scores.quality)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}

function SubmissionCard({ submission }: { submission: Submission }) {
  const scores = submission.scores;
  return (
    <div style={{
      background: "var(--surface)", border: "1px solid var(--rule)",
      borderRadius: 10, padding: "20px",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 18 }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>
            {submission.challenge_title ?? "Challenge"} — Attempt #{submission.attempt_number}
          </div>
          <div style={{ fontSize: 12.5, color: "var(--fg-3)" }}>
            {new Date(submission.submitted_at).toLocaleString()}
          </div>
        </div>
        {scores && <CompositeRing score={scores.composite} />}
      </div>
      {scores ? (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 24px" }}>
          <ScoreBar label="Quality" value={scores.quality} />
          <ScoreBar label="Robustness" value={scores.robustness} />
          <ScoreBar label="Token efficiency" value={scores.token_efficiency} />
          <ScoreBar label="Speed" value={scores.speed} />
          <ScoreBar label="Cost efficiency" value={scores.cost_efficiency} />
          <ScoreBar label="Creativity" value={scores.creativity} />
        </div>
      ) : (
        <div style={{ fontSize: 13, color: "var(--fg-3)", fontStyle: "italic" }}>
          Scores will be revealed when the challenge closes
        </div>
      )}
    </div>
  );
}
