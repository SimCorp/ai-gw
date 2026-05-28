"use client";

import { useEffect, useState } from "react";

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";

interface ContentItem {
  id: string;
  champion_id: string;
  type: string;
  submitted_at: string | null;
  source_url?: string | null;
  metadata: {
    title?: string;
    summary?: string;
    tags?: string[];
    flag_count?: number;
  };
}

export default function RelatedChampionContent({ tags, label = "Related champion content" }: { tags: string[]; label?: string }) {
  const [items, setItems] = useState<ContentItem[] | null>(null);

  useEffect(() => {
    fetch(`${ADMIN_BASE}/champions/content`)
      .then((r) => (r.ok ? r.json() : []))
      .then((d: ContentItem[]) => setItems(Array.isArray(d) ? d : []))
      .catch(() => setItems([]));
  }, []);

  if (!items || items.length === 0) return null;

  const tagSet = new Set(tags.map((t) => t.toLowerCase()));
  const matched = items.filter((it) => {
    if ((it.metadata.flag_count ?? 0) >= 999) return false;
    const itTags = (it.metadata.tags ?? []).map((t) => t.toLowerCase());
    return itTags.some((t) => tagSet.has(t));
  });

  const fallback = items
    .filter((it) => (it.metadata.flag_count ?? 0) < 999)
    .slice()
    .sort((a, b) => (b.submitted_at ?? "").localeCompare(a.submitted_at ?? ""));

  const picked = (matched.length > 0 ? matched : fallback).slice(0, 4);
  if (picked.length === 0) return null;

  return (
    <div className="card" style={{ marginTop: 24, padding: "20px 24px" }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-2)", marginBottom: 12 }}>
        {label}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 10 }}>
        {picked.map((it) => {
          const title = it.metadata.title ?? `Content ${it.id.slice(0, 8)}`;
          const summary = it.metadata.summary;
          const inner = (
            <>
              <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--fg-1)" }}>{title}</div>
              {summary && (
                <div style={{ fontSize: 11.5, color: "var(--fg-3)", marginTop: 4, lineHeight: 1.5 }}>
                  {summary.length > 120 ? summary.slice(0, 120) + "…" : summary}
                </div>
              )}
              {(it.metadata.tags ?? []).length > 0 && (
                <div style={{ marginTop: 6, display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {(it.metadata.tags ?? []).slice(0, 3).map((t) => (
                    <span key={t} style={{
                      fontSize: 10.5, padding: "1px 6px", borderRadius: 999,
                      background: "rgba(8,62,167,0.08)", color: "var(--sc-blue)",
                    }}>{t}</span>
                  ))}
                </div>
              )}
            </>
          );
          const cardStyle: React.CSSProperties = {
            display: "block",
            padding: "12px 14px",
            border: "1px solid var(--rule)",
            borderRadius: 8,
            background: "var(--surface)",
            textDecoration: "none",
            color: "var(--fg-1)",
          };
          return it.source_url ? (
            <a key={it.id} href={it.source_url} target="_blank" rel="noreferrer noopener" style={cardStyle}>
              {inner}
            </a>
          ) : (
            <div key={it.id} style={cardStyle}>{inner}</div>
          );
        })}
      </div>
    </div>
  );
}
