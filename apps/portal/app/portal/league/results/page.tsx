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

function ScoreBar({ label, value, index }: { label: string; value: number; index: number }) {
  const pct = Math.min(100, Math.max(0, value));
  const color = pct >= 70 ? "var(--good)" : pct >= 40 ? "var(--warn)" : "var(--bad)";
  return (
    <div className="lg-scorebar">
      <div className="lg-scorebar__head">
        <span style={{ color: "var(--fg-2)" }}>{label}</span>
        <span className="lg-scorebar__val" style={{ color }}>
          {Math.round(pct)}
        </span>
      </div>
      <div className="lg-scorebar__track">
        <div
          className="lg-scorebar__fill"
          style={{ width: `${pct}%`, background: color, animationDelay: `${index * 80}ms` }}
        />
      </div>
    </div>
  );
}

function CompositeRing({ score }: { score: number }) {
  const norm = Math.min(1000, Math.max(0, score)) / 1000;
  const r = 36, cx = 44, cy = 44;
  const circ = 2 * Math.PI * r;
  const dash = norm * circ;
  const color = norm >= 0.7 ? "var(--good)" : norm >= 0.4 ? "var(--warn)" : "var(--bad)";

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
      <span className="microlabel">Composite</span>
    </div>
  );
}

export default function ResultsPage() {
  const params = useSearchParams();
  const challengeFilter = params.get("challenge");

  const { data, isLoading, error } = useQuery<Submission[] | { submissions?: Submission[] }>({
    queryKey: ["portal-my-submissions", challengeFilter],
    queryFn: () => {
      const url = challengeFilter
        ? `${LEAGUE}/submissions/mine?challenge_id=${challengeFilter}`
        : `${LEAGUE}/submissions/mine`;
      return fetch(url).then(r => r.json());
    },
  });

  const submissions = Array.isArray(data) ? data : data?.submissions ?? [];
  const leagueSubmissions = submissions.filter(s => s.mode === "league");
  const trainingSubmissions = submissions.filter(s => s.mode === "training");

  if (isLoading) return (
    <div className="page">
      <h1 className="page__title">My Results</h1>
      <div style={{ textAlign: "center", padding: 60, color: "var(--fg-3)" }}>Loading results…</div>
    </div>
  );

  if (error) return (
    <div className="page">
      <h1 className="page__title">My Results</h1>
      <div style={{ textAlign: "center", padding: 60, color: "var(--bad)" }}>Could not load results</div>
    </div>
  );

  return (
    <div className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">My Results</h1>
          <p className="page__sub">Your AI-League submission history and scores</p>
        </div>
        <div className="page__actions">
          <Link href="/portal/league" className="btn">
            ← Quest board
          </Link>
        </div>
      </div>

      {submissions.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "60px 20px",
            border: "1px dashed var(--rule)",
            borderRadius: 10,
            color: "var(--fg-3)",
          }}
        >
          <div style={{ fontSize: 36, marginBottom: 12 }}>📊</div>
          <div style={{ fontWeight: 600, marginBottom: 6, color: "var(--fg-1)" }}>No submissions yet</div>
          <div style={{ fontSize: 13, marginBottom: 18 }}>
            Attempt an active quest to see your scores here
          </div>
          <Link href="/portal/league" className="lg-btn-gold">
            View quests
          </Link>
        </div>
      ) : (
        <>
          {leagueSubmissions.length > 0 && (
            <section style={{ marginBottom: 28 }}>
              <div className="microlabel" style={{ marginBottom: 14 }}>
                LEAGUE_ATTEMPTS ({leagueSubmissions.length})
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {leagueSubmissions.map((s, i) => (
                  <SubmissionCard key={s.id} submission={s} index={i} />
                ))}
              </div>
            </section>
          )}
          {trainingSubmissions.length > 0 && (
            <section>
              <div className="microlabel" style={{ marginBottom: 14 }}>
                TRAINING_RUNS ({trainingSubmissions.length})
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {trainingSubmissions.map(s => (
                  <div
                    key={s.id}
                    className="card"
                    style={{
                      padding: "12px 16px",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <div>
                      <span style={{ fontWeight: 500, fontSize: 13 }}>{s.challenge_title ?? "Challenge"}</span>
                      <span style={{ marginLeft: 10, fontSize: 12, color: "var(--fg-3)" }}>
                        Attempt #{s.attempt_number} · {new Date(s.submitted_at).toLocaleDateString()}
                      </span>
                    </div>
                    {s.scores && (
                      <span className="mono" style={{ fontSize: 13, color: "var(--fg-2)" }}>
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

function SubmissionCard({ submission, index }: { submission: Submission; index: number }) {
  const scores = submission.scores;
  return (
    <div className="card lg-result" style={{ padding: 20, animationDelay: `${index * 60}ms` }}>
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
          <ScoreBar label="Quality" value={scores.quality} index={0} />
          <ScoreBar label="Robustness" value={scores.robustness} index={1} />
          <ScoreBar label="Token efficiency" value={scores.token_efficiency} index={2} />
          <ScoreBar label="Speed" value={scores.speed} index={3} />
          <ScoreBar label="Cost efficiency" value={scores.cost_efficiency} index={4} />
          <ScoreBar label="Creativity" value={scores.creativity} index={5} />
        </div>
      ) : (
        <div style={{ fontSize: 13, color: "var(--fg-3)", fontStyle: "italic" }}>
          Scores will be revealed when the quest closes
        </div>
      )}
    </div>
  );
}
