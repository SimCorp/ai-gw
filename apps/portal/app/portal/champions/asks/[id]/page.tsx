"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "../../../_lib/authContext";

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

interface Champion {
  developer_id: string;
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        display: "inline-block",
        fontSize: 11,
        padding: "2px 8px",
        borderRadius: 999,
        background: "rgba(8,62,167,0.08)",
        color: "var(--sc-blue)",
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
      return { bg: "rgba(8,62,167,0.10)", fg: "var(--sc-blue)" };
    case "claimed":
      return { bg: "rgba(245,158,11,0.14)", fg: "#b45309" };
    case "resolved_pending":
      return { bg: "rgba(168,85,247,0.14)", fg: "#7c3aed" };
    case "resolved":
      return { bg: "rgba(34,197,94,0.14)", fg: "#15803d" };
    default:
      return { bg: "rgba(0,0,0,0.06)", fg: "var(--fg-3)" };
  }
}

export default function AskDetailPage() {
  const params = useParams<{ id: string }>();
  const askId = params?.id;
  const router = useRouter();
  const { developer, token } = useAuth();
  const [ask, setAsk] = useState<Ask | null>(null);
  const [champions, setChampions] = useState<Champion[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    if (!askId) return;
    Promise.all([
      fetch(`${ADMIN_BASE}/champions/asks`).then((r) =>
        r.ok ? r.json() : Promise.reject(`asks ${r.status}`),
      ),
      fetch(`${ADMIN_BASE}/champions`).then((r) =>
        r.ok ? r.json() : Promise.reject(`champions ${r.status}`),
      ),
    ])
      .then(([asks, dir]: [Ask[], Champion[]]) => {
        const found = asks.find((a) => a.id === askId) ?? null;
        setAsk(found);
        setChampions(dir);
      })
      .catch((e) => setError(String(e)));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [askId]);

  async function act(path: string, body: Record<string, unknown>) {
    if (!ask) return;
    setBusy(true);
    setError(null);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(`${ADMIN_BASE}/champions/asks/${ask.id}/${path}`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const b = await res.json().catch(() => ({}));
        throw new Error(b.detail ?? `${path} failed (${res.status})`);
      }
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (error && !ask) {
    return (
      <main className="pmain">
        <div style={{ color: "var(--bad)", fontSize: 13 }}>Failed to load: {error}</div>
      </main>
    );
  }

  if (!ask) {
    return (
      <main className="pmain">
        <div style={{ color: "var(--fg-3)", fontSize: 13 }}>Loading…</div>
      </main>
    );
  }

  const sc = statusColor(ask.status);
  const myId = developer?.developer_id;
  const isChampion = !!myId && champions.some((c) => c.developer_id === myId);
  const isAsker = !!myId && myId === ask.created_by;
  const isClaimer = !!myId && myId === ask.claimed_by;

  const canClaim = isChampion && ask.status === "open";
  const canResolve = isClaimer && ask.status === "claimed";
  const canConfirm = isAsker && ask.status === "resolved_pending";

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <Link
            href="/portal/champions/asks"
            style={{ fontSize: 12, color: "var(--fg-3)", textDecoration: "none" }}
          >
            ← Back to asks
          </Link>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 4 }}>
            <h1 style={{ margin: 0 }}>{ask.title}</h1>
            <span
              style={{
                fontSize: 12,
                padding: "3px 10px",
                borderRadius: 999,
                background: sc.bg,
                color: sc.fg,
              }}
            >
              {ask.status.replace("_", " ")}
            </span>
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: "20px 24px", marginBottom: 18 }}>
        <div style={{ fontSize: 11, color: "var(--fg-3)", marginBottom: 8 }}>
          Asked by {ask.created_by.slice(0, 8)}…
          {ask.created_at && ` · ${new Date(ask.created_at).toLocaleString()}`}
          {ask.claimed_by && ` · claimed by ${ask.claimed_by.slice(0, 8)}…`}
        </div>
        <div
          style={{
            fontSize: 13.5,
            color: "var(--fg-1)",
            lineHeight: 1.6,
            whiteSpace: "pre-wrap",
            marginBottom: 10,
          }}
        >
          {ask.description}
        </div>
        <div>
          {(ask.tags ?? []).map((t) => (
            <Chip key={t}>{t}</Chip>
          ))}
        </div>
      </div>

      {error && (
        <div style={{ color: "var(--bad)", fontSize: 12, marginBottom: 10 }}>{error}</div>
      )}

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        {canClaim && (
          <button
            disabled={busy}
            onClick={() => act("claim", { champion_id: myId })}
            className="btn btn--primary"
            style={{ fontSize: 13, padding: "8px 14px" }}
          >
            {busy ? "Working…" : "Claim this ask"}
          </button>
        )}
        {canResolve && (
          <button
            disabled={busy}
            onClick={() => act("resolve", { champion_id: myId })}
            className="btn btn--primary"
            style={{ fontSize: 13, padding: "8px 14px" }}
          >
            {busy ? "Working…" : "Mark resolved"}
          </button>
        )}
        {canConfirm && (
          <button
            disabled={busy}
            onClick={() => act("confirm", { asker_id: myId })}
            className="btn btn--primary"
            style={{ fontSize: 13, padding: "8px 14px" }}
          >
            {busy ? "Working…" : "Confirm resolved (+200 to champion)"}
          </button>
        )}
        {!canClaim && !canResolve && !canConfirm && (
          <div style={{ fontSize: 12, color: "var(--fg-3)" }}>
            No actions available for you on this ask.
          </div>
        )}
      </div>
    </main>
  );
}
