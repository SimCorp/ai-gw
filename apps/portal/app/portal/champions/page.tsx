"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

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

function shortId(id: string) {
  return id.slice(0, 8);
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
        setContent(feed);
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
        <Link
          href="/portal/champions/new-content"
          className="btn btn--primary"
          style={{ fontSize: 13, padding: "8px 14px" }}
        >
          Share content
        </Link>
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
                      background: "var(--sc-blue)",
                      color: "white",
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
              <div key={item.id} className="card" style={{ padding: "14px 18px" }}>
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
                <div>
                  {(item.metadata.tags ?? []).map((t) => (
                    <Chip key={t}>{t}</Chip>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
