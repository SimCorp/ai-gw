"use client";

import { useState, useEffect, useCallback } from "react";

const LIB = process.env.NEXT_PUBLIC_LIBRARIAN_BASE_URL ?? "http://localhost:8080/librarian";

interface KnowledgeItem {
  id: string;
  title: string;
  content: string;
  source_url: string | null;
  topic: string;
  tags: string[];
  ingested_at: string;
  score?: number;
}

interface Topic {
  topic: string;
  item_count: number;
  description: string | null;
}

export default function LibraryPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<KnowledgeItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null);
  const [topicItems, setTopicItems] = useState<KnowledgeItem[]>([]);
  const [loadingTopicItems, setLoadingTopicItems] = useState(false);
  const [searched, setSearched] = useState(false);

  useEffect(() => {
    fetch(`${LIB}/topics`)
      .then(r => r.ok ? r.json() : [])
      .then((data: Topic[]) => setTopics(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);

  const handleSearch = useCallback(async () => {
    if (!query.trim()) return;
    setSearching(true);
    setSearched(false);
    try {
      const r = await fetch(`${LIB}/search?q=${encodeURIComponent(query.trim())}&limit=12`);
      const data = await r.json();
      setResults(Array.isArray(data.results) ? data.results : []);
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
      setSearched(true);
    }
  }, [query]);

  useEffect(() => {
    if (!selectedTopic) { setTopicItems([]); return; }
    setLoadingTopicItems(true);
    fetch(`${LIB}/topics/${encodeURIComponent(selectedTopic)}?limit=20`)
      .then(r => r.ok ? r.json() : [])
      .then((data: KnowledgeItem[]) => setTopicItems(Array.isArray(data) ? data : []))
      .catch(() => setTopicItems([]))
      .finally(() => setLoadingTopicItems(false));
  }, [selectedTopic]);

  const totalItems = topics.reduce((s, t) => s + t.item_count, 0);

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <h1>Knowledge Library</h1>
          <p>Search and browse the shared knowledge base — engineering best practices, AI patterns, platform docs.</p>
        </div>
      </div>

      {/* Stats */}
      {topics.length > 0 && (
        <div className="stat-strip" style={{ marginBottom: 20 }}>
          <div className="s">
            <div className="l">Documents</div>
            <div className="v">{totalItems}</div>
          </div>
          <div className="s">
            <div className="l">Topics</div>
            <div className="v">{topics.length}</div>
          </div>
        </div>
      )}

      {/* Search */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card__head">
          <h3 className="card__title">Semantic search</h3>
          <span className="card__sub">finds relevant content even with different wording</span>
        </div>
        <div className="card__body">
          <div style={{ display: "flex", gap: 8 }}>
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSearch()}
              placeholder="e.g. how to use prompt caching, DORA metrics, security scanning…"
              style={{
                flex: 1, padding: "8px 12px",
                border: "1px solid var(--rule)", borderRadius: 7,
                background: "var(--surface)", fontSize: 13,
                color: "var(--fg-1)", outline: "none",
              }}
            />
            <button
              className="btn btn--primary"
              onClick={handleSearch}
              disabled={searching || !query.trim()}
            >
              {searching ? "Searching…" : "Search"}
            </button>
          </div>
          {searched && results.length === 0 && (
            <div style={{ marginTop: 12, fontSize: 13, color: "var(--fg-3)" }}>No results found.</div>
          )}
          {results.length > 0 && (
            <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
              {results.map(item => (
                <ItemCard key={item.id} item={item} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Topic browser */}
      <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 16 }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--fg-3)", marginBottom: 8 }}>Topics</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {topics.map(t => (
              <button
                key={t.topic}
                onClick={() => setSelectedTopic(t.topic === selectedTopic ? null : t.topic)}
                style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "7px 10px", borderRadius: 6, border: "1px solid var(--rule)",
                  background: selectedTopic === t.topic ? "var(--sc-blue, #0A7BD7)" : "var(--surface)",
                  color: selectedTopic === t.topic ? "#fff" : "var(--fg-1)",
                  cursor: "pointer", fontSize: 13, textAlign: "left", fontFamily: "inherit",
                }}
              >
                <span>{t.topic}</span>
                <span style={{ fontSize: 11, opacity: 0.7 }}>{t.item_count}</span>
              </button>
            ))}
          </div>
        </div>

        <div>
          {selectedTopic ? (
            <div className="card">
              <div className="card__head">
                <h3 className="card__title">{selectedTopic}</h3>
                <span className="card__sub">
                  {loadingTopicItems ? "loading…" : `${topicItems.length} documents`}
                </span>
              </div>
              <div className="card__body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {loadingTopicItems ? (
                  <div style={{ fontSize: 13, color: "var(--fg-3)" }}>Loading…</div>
                ) : topicItems.length === 0 ? (
                  <div style={{ fontSize: 13, color: "var(--fg-3)" }}>No documents in this topic yet.</div>
                ) : (
                  topicItems.map(item => <ItemCard key={item.id} item={item} />)
                )}
              </div>
            </div>
          ) : (
            <div className="card">
              <div className="card__body" style={{ padding: "32px 20px", textAlign: "center", color: "var(--fg-3)", fontSize: 13 }}>
                Select a topic to browse its documents.
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

function ItemCard({ item }: { item: KnowledgeItem }) {
  const [expanded, setExpanded] = useState(false);
  const preview = item.content.length > 200 ? item.content.slice(0, 200) + "…" : item.content;
  return (
    <div style={{
      padding: "12px 14px", border: "1px solid var(--rule)", borderRadius: 8,
      background: "var(--surface)", display: "flex", flexDirection: "column", gap: 6,
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
        <div style={{ fontWeight: 500, fontSize: 13, color: "var(--fg-1)" }}>{item.title}</div>
        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
          {item.score != null && (
            <span style={{ fontSize: 10.5, padding: "2px 6px", borderRadius: 4, background: "var(--sc-blue-soft, rgba(10,123,215,0.08))", color: "var(--sc-blue, #0A7BD7)" }}>
              {(item.score * 100).toFixed(0)}% match
            </span>
          )}
          <span style={{ fontSize: 10.5, padding: "2px 6px", borderRadius: 4, background: "var(--surface-soft)", color: "var(--fg-3)" }}>
            {item.topic}
          </span>
        </div>
      </div>
      <div style={{ fontSize: 12.5, color: "var(--fg-2)", lineHeight: 1.5 }}>
        {expanded ? item.content : preview}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {item.content.length > 200 && (
          <button
            onClick={() => setExpanded(e => !e)}
            style={{ fontSize: 12, color: "var(--sc-blue, #0A7BD7)", background: "none", border: "none", cursor: "pointer", padding: 0 }}
          >
            {expanded ? "Show less" : "Show more"}
          </button>
        )}
        {item.source_url && (
          <a href={item.source_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12, color: "var(--fg-3)", textDecoration: "none" }}>
            Source ↗
          </a>
        )}
        {item.tags?.length > 0 && (
          <div style={{ display: "flex", gap: 4, marginLeft: "auto" }}>
            {item.tags.slice(0, 3).map(tag => (
              <span key={tag} style={{ fontSize: 10.5, padding: "1px 5px", borderRadius: 4, border: "1px solid var(--rule)", color: "var(--fg-3)" }}>{tag}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
