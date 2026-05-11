'use client';

import { useEffect, useState } from 'react';

const LIBRARIAN_BASE = process.env.NEXT_PUBLIC_LIBRARIAN_BASE_URL ?? 'http://localhost:8008';

interface TopicSummary {
  topic: string;
  item_count: number;
  last_ingested_at: string | null;
}

interface KnowledgeItem {
  id: string;
  title: string;
  content: string;
  source_url: string | null;
  topic: string | null;
  tags: string[];
  ingested_at: string | null;
  score?: number;
}

function formatDate(iso: string | null): string {
  if (!iso) return 'Never';
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  } catch {
    return iso;
  }
}

function SearchModal({
  topic,
  onClose,
}: {
  topic: string;
  onClose: () => void;
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<KnowledgeItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const url = `${LIBRARIAN_BASE}/search?q=${encodeURIComponent(query)}&topic=${encodeURIComponent(topic)}&limit=10`;
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setResults(data.results ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.45)',
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{
          background: 'var(--bg)',
          borderRadius: 10,
          padding: '28px 32px',
          width: '100%',
          maxWidth: 700,
          maxHeight: '85vh',
          overflowY: 'auto',
          boxShadow: '0 8px 40px rgba(0,0,0,0.3)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>Search: {topic}</h3>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontSize: 20,
              color: 'var(--fg-3)',
              lineHeight: 1,
            }}
          >
            &times;
          </button>
        </div>

        <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
          <input
            type="text"
            placeholder="Enter a search query..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSearch(); }}
            autoFocus
            style={{
              flex: 1,
              padding: '8px 12px',
              borderRadius: 6,
              border: '1px solid var(--rule)',
              background: 'var(--bg-2)',
              color: 'var(--fg)',
              fontSize: 13,
            }}
          />
          <button
            onClick={handleSearch}
            disabled={loading || !query.trim()}
            style={{
              padding: '8px 18px',
              borderRadius: 6,
              border: 'none',
              background: 'var(--accent)',
              color: '#fff',
              fontSize: 13,
              fontWeight: 600,
              cursor: loading ? 'default' : 'pointer',
              opacity: loading || !query.trim() ? 0.6 : 1,
            }}
          >
            {loading ? 'Searching...' : 'Search'}
          </button>
        </div>

        {error && (
          <div style={{ color: 'var(--error, #e53e3e)', fontSize: 13, marginBottom: 16 }}>
            Error: {error}
          </div>
        )}

        {results.length === 0 && !loading && query && (
          <div style={{ color: 'var(--fg-3)', fontSize: 13 }}>No results found.</div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {results.map((item) => (
            <div
              key={item.id}
              style={{
                border: '1px solid var(--rule)',
                borderRadius: 8,
                padding: '14px 16px',
                background: 'var(--bg-2)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                <div style={{ fontWeight: 600, fontSize: 13.5 }}>{item.title}</div>
                {item.score !== undefined && (
                  <span style={{
                    fontSize: 11,
                    color: 'var(--fg-3)',
                    background: 'var(--bg-3, var(--rule))',
                    padding: '2px 7px',
                    borderRadius: 10,
                    whiteSpace: 'nowrap',
                    flexShrink: 0,
                  }}>
                    {(item.score * 100).toFixed(1)}% match
                  </span>
                )}
              </div>
              <div style={{
                fontSize: 12.5,
                color: 'var(--fg-2)',
                marginTop: 6,
                lineHeight: 1.55,
                display: '-webkit-box',
                WebkitLineClamp: 4,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden',
              }}>
                {item.content}
              </div>
              <div style={{ display: 'flex', gap: 10, marginTop: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                {item.tags.map((tag) => (
                  <span key={tag} style={{
                    fontSize: 11,
                    padding: '2px 8px',
                    borderRadius: 10,
                    border: '1px solid var(--rule)',
                    color: 'var(--fg-3)',
                  }}>{tag}</span>
                ))}
                <span style={{ fontSize: 11, color: 'var(--fg-3)', marginLeft: 'auto' }}>
                  {formatDate(item.ingested_at)}
                </span>
              </div>
              {item.source_url && (
                <a
                  href={item.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ fontSize: 11.5, color: 'var(--accent)', marginTop: 6, display: 'block' }}
                >
                  {item.source_url}
                </a>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function PromptsPage() {
  const [topics, setTopics] = useState<TopicSummary[]>([]);
  const [loadingTopics, setLoadingTopics] = useState(true);
  const [topicsError, setTopicsError] = useState<string | null>(null);
  const [activeModal, setActiveModal] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadTopics() {
      try {
        const resp = await fetch(`${LIBRARIAN_BASE}/topics`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data: TopicSummary[] = await resp.json();
        if (!cancelled) setTopics(data);
      } catch (e: unknown) {
        if (!cancelled) setTopicsError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoadingTopics(false);
      }
    }
    loadTopics();
    return () => { cancelled = true; };
  }, []);

  return (
    <main className="pmain">
      {/* Existing prompts section */}
      <div className="phero">
        <div>
          <h1>Prompts</h1>
          <p>Save, version, and share prompt templates across your team.</p>
        </div>
        <span style={{
          padding: '4px 10px', borderRadius: 6,
          border: '1px solid var(--rule)',
          fontSize: 11.5, fontWeight: 600, color: 'var(--fg-3)',
          letterSpacing: '0.04em', textTransform: 'uppercase' as const,
        }}>Coming soon</span>
      </div>
      <div className="card">
        <div className="card__body" style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--fg-3)' }}>
          <div style={{ fontSize: 13, color: 'var(--fg-2)', marginBottom: 6 }}>Not yet implemented</div>
          <div style={{ fontSize: 12.5 }}>Prompt library is planned for a future release.</div>
        </div>
      </div>

      {/* Research Knowledge Base section */}
      <div style={{ marginTop: 40 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Research Knowledge Base</h2>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--fg-3)' }}>
              Continuously researched topics available for agent grounding and semantic search.
            </p>
          </div>
        </div>

        {loadingTopics && (
          <div className="card">
            <div className="card__body" style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
              Loading topics...
            </div>
          </div>
        )}

        {topicsError && (
          <div className="card">
            <div className="card__body" style={{ padding: '24px 20px', color: 'var(--fg-3)', fontSize: 13 }}>
              <span style={{ color: 'var(--error, #e53e3e)' }}>Could not reach the AI Librarian service.</span>{' '}
              Make sure the librarian is running at <code>{LIBRARIAN_BASE}</code>.
            </div>
          </div>
        )}

        {!loadingTopics && !topicsError && topics.length === 0 && (
          <div className="card">
            <div className="card__body" style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
              No topics indexed yet. The research agent will populate them shortly.
            </div>
          </div>
        )}

        {!loadingTopics && !topicsError && topics.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
            {topics.map((t) => (
              <div
                key={t.topic}
                className="card"
                style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}
              >
                <div className="card__body" style={{ padding: '18px 20px 14px' }}>
                  <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>
                    {t.topic}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--fg-3)', marginBottom: 4 }}>
                    {t.item_count} {t.item_count === 1 ? 'document' : 'documents'}
                  </div>
                  <div style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>
                    Last updated: {formatDate(t.last_ingested_at)}
                  </div>
                </div>
                <div style={{ padding: '0 20px 16px' }}>
                  <button
                    onClick={() => setActiveModal(t.topic)}
                    style={{
                      width: '100%',
                      padding: '7px 0',
                      borderRadius: 6,
                      border: '1px solid var(--accent)',
                      background: 'transparent',
                      color: 'var(--accent)',
                      fontSize: 12.5,
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    Search
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {activeModal && (
        <SearchModal topic={activeModal} onClose={() => setActiveModal(null)} />
      )}
    </main>
  );
}
