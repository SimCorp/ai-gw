"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";

interface Ask {
  id: string;
  title: string;
  description: string;
  status: string;
  created_by: string;
  claimed_by: string | null;
  created_at: string | null;
  team_id: string | null;
  tags: string[];
}

type Filter = "all" | "open" | "claimed" | "resolved";

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        display: "inline-block",
        fontSize: 11,
        padding: "2px 8px",
        borderRadius: 999,
        background: "var(--accent-soft)",
        color: "var(--accent)",
        marginRight: 4,
        marginTop: 4,
      }}
    >
      {children}
    </span>
  );
}

function statusColor(status: string): { bg: string; fg: string } {
  switch (status) {
    case "open":
      return { bg: "var(--accent-soft)", fg: "var(--accent)" };
    case "claimed":
      return { bg: "var(--warn-soft)", fg: "var(--warn)" };
    case "resolved_pending":
      return { bg: "var(--surface-soft)", fg: "var(--cat-purple)" };
    case "resolved":
      return { bg: "var(--good-soft)", fg: "var(--good)" };
    default:
      return { bg: "var(--surface-soft)", fg: "var(--fg-3)" };
  }
}

function truncate(s: string, n = 180) {
  return s.length > n ? s.slice(0, n).trimEnd() + "…" : s;
}

export default function AsksBoardPage() {
  const [asks, setAsks] = useState<Ask[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    fetch(`${ADMIN_BASE}/champions/asks`)
      .then((r) => (r.ok ? r.json() : Promise.reject(`asks ${r.status}`)))
      .then((data) => setAsks(data))
      .catch((e) => setError(String(e)));
  }, []);

  const filtered = useMemo(() => {
    if (!asks) return null;
    if (filter === "all") return asks;
    if (filter === "resolved")
      return asks.filter((a) => a.status === "resolved" || a.status === "resolved_pending");
    return asks.filter((a) => a.status === filter);
  }, [asks, filter]);

  const filters: { value: Filter; label: string }[] = [
    { value: "all", label: "All" },
    { value: "open", label: "Open" },
    { value: "claimed", label: "Claimed" },
    { value: "resolved", label: "Resolved" },
  ];

  return (
    <main className="pmain">
      <div
        className="phero"
        style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}
      >
        <div>
          <Link
            href="/portal/champions"
            style={{ fontSize: 12, color: "var(--fg-3)", textDecoration: "none" }}
          >
            ← Champions
          </Link>
          <h1 style={{ marginTop: 4 }}>Asks board</h1>
          <p>Questions for AI Champions — claim one, resolve it, earn recognition.</p>
        </div>
        <Link
          href="/portal/champions/asks/new"
          className="btn btn--primary"
          style={{ fontSize: 13, padding: "8px 14px" }}
        >
          Create ask
        </Link>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 18, flexWrap: "wrap" }}>
        {filters.map((f) => {
          const active = filter === f.value;
          return (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              style={{
                fontSize: 12,
                padding: "6px 12px",
                borderRadius: 999,
                border: "1px solid var(--rule)",
                background: active ? "var(--accent)" : "transparent",
                color: active ? "var(--accent-fg)" : "var(--fg-2)",
                cursor: "pointer",
                fontFamily: "inherit",
              }}
            >
              {f.label}
            </button>
          );
        })}
      </div>

      {error && (
        <div style={{ color: "var(--bad)", fontSize: 13, marginBottom: 20 }}>
          Failed to load: {error}
        </div>
      )}

      {filtered === null ? (
        <div style={{ color: "var(--fg-3)", fontSize: 13 }}>Loading…</div>
      ) : filtered.length === 0 ? (
        <div style={{ color: "var(--fg-3)", fontSize: 13 }}>No asks in this view.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {filtered.map((a) => {
            const sc = statusColor(a.status);
            return (
              <Link
                key={a.id}
                href={`/portal/champions/asks/${a.id}`}
                className="card"
                style={{
                  padding: "14px 18px",
                  textDecoration: "none",
                  color: "inherit",
                  display: "block",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: 6,
                    gap: 8,
                  }}
                >
                  <div style={{ fontSize: 14, fontWeight: 600, color: "var(--fg-1)" }}>
                    {a.title}
                  </div>
                  <span
                    style={{
                      fontSize: 11,
                      padding: "2px 8px",
                      borderRadius: 999,
                      background: sc.bg,
                      color: sc.fg,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {a.status.replace("_", " ")}
                  </span>
                </div>
                <div
                  style={{
                    fontSize: 12,
                    color: "var(--fg-3)",
                    lineHeight: 1.5,
                    marginBottom: 6,
                  }}
                >
                  {truncate(a.description)}
                </div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: 8,
                    flexWrap: "wrap",
                  }}
                >
                  <div>
                    {(a.tags ?? []).map((t) => (
                      <Chip key={t}>{t}</Chip>
                    ))}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--fg-3)" }}>
                    {a.claimed_by ? `Claimed by ${a.claimed_by.slice(0, 8)}…` : "Unclaimed"}
                    {a.created_at && ` · ${new Date(a.created_at).toLocaleDateString()}`}
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </main>
  );
}
