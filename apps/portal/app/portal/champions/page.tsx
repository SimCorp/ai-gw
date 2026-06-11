"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "../_lib/authContext";

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";

interface Champion {
  developer_id: string;
  bio: string | null;
  focus_areas: string[];
  office_hours_text: string | null;
  active: boolean;
}

interface ContentItem {
  id: string;
  champion_id: string;
  type: string;
  submitted_at: string | null;
  metadata: {
    title?: string;
    summary?: string;
    tags?: string[];
    flag_count?: number;
  };
  upvotes: number;
  views: number;
}

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

function shortId(id: string) {
  return id.slice(0, 8);
}

// Local upvote/flag state per content card
interface CardState {
  upvotes: number;
  upvoted: boolean;
  flagged: boolean;
  flagFormOpen: boolean;
  flagReason: string;
  flagBusy: boolean;
}

function ContentCard({ item }: { item: ContentItem }) {
  const { developer, token } = useAuth();
  const [state, setState] = useState<CardState>({
    upvotes: item.upvotes,
    upvoted: false,
    flagged: false,
    flagFormOpen: false,
    flagReason: "",
    flagBusy: false,
  });

  async function toggleUpvote() {
    if (!developer) return;
    // Optimistic
    const prev = state;
    setState((s) => ({
      ...s,
      upvoted: !s.upvoted,
      upvotes: s.upvoted ? Math.max(0, s.upvotes - 1) : s.upvotes + 1,
    }));
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(`${ADMIN_BASE}/champions/content/${item.id}/upvote`, {
        method: "POST",
        headers,
        body: JSON.stringify({ developer_id: developer.developer_id }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const data: { upvoted: boolean; upvotes: number } = await res.json();
      setState((s) => ({ ...s, upvoted: data.upvoted, upvotes: data.upvotes }));
    } catch {
      setState(prev); // revert
    }
  }

  async function submitFlag() {
    if (!developer || state.flagBusy) return;
    setState((s) => ({ ...s, flagBusy: true }));
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(`${ADMIN_BASE}/champions/content/${item.id}/flag`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          developer_id: developer.developer_id,
          reason: state.flagReason.trim() || null,
        }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      setState((s) => ({
        ...s,
        flagged: true,
        flagFormOpen: false,
        flagReason: "",
        flagBusy: false,
      }));
    } catch {
      setState((s) => ({ ...s, flagBusy: false }));
    }
  }

  return (
    <div className="card" style={{ padding: "14px 18px" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 6,
        }}
      >
        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--fg-1)" }}>
          {item.metadata.title || `${item.type} contribution`}
        </div>
        <div style={{ fontSize: 11, color: "var(--fg-3)" }}>{item.type}</div>
      </div>
      {item.metadata.summary && (
        <div style={{ fontSize: 12, color: "var(--fg-3)", lineHeight: 1.5, marginBottom: 6 }}>
          {item.metadata.summary}
        </div>
      )}
      <div style={{ marginBottom: 8 }}>
        {(item.metadata.tags ?? []).map((t) => (
          <Chip key={t}>{t}</Chip>
        ))}
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 14,
          fontSize: 12,
          color: "var(--fg-3)",
        }}
      >
        <button
          onClick={toggleUpvote}
          disabled={!developer}
          title={developer ? "Upvote" : "Sign in to upvote"}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
            padding: "4px 10px",
            borderRadius: 999,
            border: "1px solid var(--rule)",
            background: state.upvoted ? "var(--accent-soft)" : "transparent",
            color: state.upvoted ? "var(--accent)" : "var(--fg-2)",
            cursor: developer ? "pointer" : "not-allowed",
            fontSize: 12,
            fontFamily: "inherit",
            fontWeight: state.upvoted ? 600 : 400,
          }}
        >
          ▲ {state.upvotes}
        </button>
        {!state.flagged ? (
          <button
            onClick={() => setState((s) => ({ ...s, flagFormOpen: !s.flagFormOpen }))}
            disabled={!developer}
            style={{
              background: "none",
              border: "none",
              padding: 0,
              cursor: developer ? "pointer" : "not-allowed",
              fontSize: 12,
              color: "var(--fg-3)",
              fontFamily: "inherit",
              textDecoration: "underline",
            }}
          >
            🚩 Flag
          </button>
        ) : (
          <span style={{ fontSize: 11, color: "var(--fg-3)", fontStyle: "italic" }}>Flagged</span>
        )}
      </div>

      {state.flagFormOpen && !state.flagged && (
        <div
          style={{
            marginTop: 10,
            padding: 10,
            borderRadius: 6,
            border: "1px solid var(--rule)",
            background: "var(--surface-soft)",
          }}
        >
          <textarea
            value={state.flagReason}
            onChange={(e) => setState((s) => ({ ...s, flagReason: e.target.value }))}
            placeholder="Reason (optional)…"
            rows={2}
            style={{
              width: "100%",
              padding: "6px 8px",
              borderRadius: 6,
              border: "1px solid var(--rule)",
              background: "var(--bg)",
              color: "var(--fg-1)",
              fontSize: 12,
              fontFamily: "inherit",
              resize: "vertical",
              marginBottom: 6,
            }}
          />
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={submitFlag}
              disabled={state.flagBusy}
              className="btn btn--primary"
              style={{ fontSize: 12, padding: "5px 10px" }}
            >
              {state.flagBusy ? "Submitting…" : "Submit flag"}
            </button>
            <button
              onClick={() => setState((s) => ({ ...s, flagFormOpen: false, flagReason: "" }))}
              style={{
                fontSize: 12,
                padding: "5px 10px",
                background: "transparent",
                border: "1px solid var(--rule)",
                borderRadius: 6,
                color: "var(--fg-2)",
                cursor: "pointer",
                fontFamily: "inherit",
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ChampionsHubPage() {
  const [champions, setChampions] = useState<Champion[] | null>(null);
  const [content, setContent] = useState<ContentItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetch(`${ADMIN_BASE}/champions`).then((r) =>
        r.ok ? r.json() : Promise.reject(`directory ${r.status}`),
      ),
      fetch(`${ADMIN_BASE}/champions/content`).then((r) =>
        r.ok ? r.json() : Promise.reject(`content ${r.status}`),
      ),
    ])
      .then(([dir, feed]) => {
        setChampions(dir);
        // Client-side filter for tombstoned content (flag_count >= 999)
        const visible = (feed as ContentItem[]).filter(
          (c) => (c.metadata?.flag_count ?? 0) < 999,
        );
        setContent(visible);
      })
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <main className="pmain">
      <div
        className="phero"
        style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}
      >
        <div>
          <h1>AI Champions</h1>
          <p>People driving AI adoption across SimCorp — find a mentor, share what you&apos;ve learned.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Link
            href="/portal/champions/asks"
            className="btn"
            style={{ fontSize: 13, padding: "8px 14px" }}
          >
            Asks board
          </Link>
          <Link
            href="/portal/champions/new-content"
            className="btn btn--primary"
            style={{ fontSize: 13, padding: "8px 14px" }}
          >
            Share content
          </Link>
        </div>
      </div>

      {error && (
        <div style={{ color: "var(--bad)", fontSize: 13, marginBottom: 20 }}>
          Failed to load: {error}
        </div>
      )}

      <section style={{ marginTop: 8, marginBottom: 32 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg-2)", marginBottom: 12 }}>
          Champions
        </h2>
        {champions === null ? (
          <div style={{ color: "var(--fg-3)", fontSize: 13 }}>Loading…</div>
        ) : champions.length === 0 ? (
          <div style={{ color: "var(--fg-3)", fontSize: 13 }}>No champions yet.</div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
              gap: 12,
            }}
          >
            {champions.map((c) => (
              <Link
                key={c.developer_id}
                href={`/portal/champions/${c.developer_id}`}
                className="card"
                style={{
                  padding: "16px 18px",
                  textDecoration: "none",
                  color: "inherit",
                  display: "block",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
                  <div
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: "50%",
                      background: "var(--accent)",
                      color: "var(--accent-fg)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontWeight: 600,
                      fontSize: 14,
                    }}
                  >
                    {c.developer_id.slice(0, 2).toUpperCase()}
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "var(--fg-1)" }}>
                    Champion {shortId(c.developer_id)}
                  </div>
                </div>
                {c.bio && (
                  <div style={{ fontSize: 12, color: "var(--fg-3)", lineHeight: 1.5, marginBottom: 8 }}>
                    {c.bio}
                  </div>
                )}
                <div>
                  {c.focus_areas.map((f) => (
                    <Chip key={f}>{f}</Chip>
                  ))}
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--fg-2)", marginBottom: 12 }}>
          Recent content
        </h2>
        {content === null ? (
          <div style={{ color: "var(--fg-3)", fontSize: 13 }}>Loading…</div>
        ) : content.length === 0 ? (
          <div style={{ color: "var(--fg-3)", fontSize: 13 }}>No content yet.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {content.map((item) => (
              <ContentCard key={item.id} item={item} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
