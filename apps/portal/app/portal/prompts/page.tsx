'use client';

import { useEffect, useState, useCallback } from 'react';

const LIBRARIAN_BASE = process.env.NEXT_PUBLIC_LIBRARIAN_BASE_URL ?? 'http://localhost:8008';

interface TopicSummary {
  topic: string;
  item_count: number;
  last_ingested_at: string | null;
}

// ---------------------------------------------------------------------------
// Research topic management types
// ---------------------------------------------------------------------------
interface ResearchTopic {
  topic: string;
  description: string;
  interval_hours: number;
  last_researched_at: string | null;
  enabled: boolean;
  search_query?: string;
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

// ---------------------------------------------------------------------------
// Manage Topics panel
// ---------------------------------------------------------------------------

interface AddTopicForm {
  topic: string;
  description: string;
  search_query: string;
  interval_hours: string;
}

function ManageTopicsPanel() {
  const [researchTopics, setResearchTopics] = useState<ResearchTopic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState<string | null>(null);
  const [togglingTopic, setTogglingTopic] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [addForm, setAddForm] = useState<AddTopicForm>({
    topic: '', description: '', search_query: '', interval_hours: '24',
  });
  const [addError, setAddError] = useState<string | null>(null);
  const [addBusy, setAddBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ topic: string; msg: string; ok: boolean } | null>(null);

  const loadTopics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${LIBRARIAN_BASE}/research/topics`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data: ResearchTopic[] = await resp.json();
      setResearchTopics(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadTopics(); }, [loadTopics]);

  async function triggerNow(topic: string) {
    setTriggering(topic);
    setStatusMsg(null);
    try {
      const resp = await fetch(`${LIBRARIAN_BASE}/research/topics/${encodeURIComponent(topic)}/trigger`, {
        method: 'POST',
      });
      if (resp.ok) {
        setStatusMsg({ topic, msg: 'Triggered successfully', ok: true });
      } else {
        setStatusMsg({ topic, msg: `Failed: HTTP ${resp.status}`, ok: false });
      }
    } catch (e: unknown) {
      setStatusMsg({ topic, msg: e instanceof Error ? e.message : 'Request failed', ok: false });
    } finally {
      setTriggering(null);
    }
  }

  async function toggleEnabled(t: ResearchTopic) {
    setTogglingTopic(t.topic);
    try {
      await fetch(`${LIBRARIAN_BASE}/research/topics/${encodeURIComponent(t.topic)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !t.enabled }),
      });
      setResearchTopics(prev =>
        prev.map(rt => rt.topic === t.topic ? { ...rt, enabled: !rt.enabled } : rt)
      );
    } catch {
      // silently fail
    } finally {
      setTogglingTopic(null);
    }
  }

  async function addTopic() {
    setAddError(null);
    if (!addForm.topic.trim()) { setAddError('Topic slug is required.'); return; }
    if (!addForm.description.trim()) { setAddError('Description is required.'); return; }
    if (!addForm.search_query.trim()) { setAddError('Search query is required.'); return; }
    const hours = parseInt(addForm.interval_hours, 10);
    if (isNaN(hours) || hours < 1) { setAddError('Interval must be a positive number.'); return; }

    setAddBusy(true);
    try {
      const resp = await fetch(`${LIBRARIAN_BASE}/research/topics`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic: addForm.topic.trim(),
          description: addForm.description.trim(),
          search_query: addForm.search_query.trim(),
          interval_hours: hours,
        }),
      });
      if (resp.ok) {
        setAddForm({ topic: '', description: '', search_query: '', interval_hours: '24' });
        setShowAddForm(false);
        await loadTopics();
      } else {
        const body = await resp.json().catch(() => ({}));
        setAddError(body?.detail ?? `HTTP ${resp.status}`);
      }
    } catch (e: unknown) {
      setAddError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setAddBusy(false);
    }
  }

  async function deleteTopic(topic: string) {
    setDeleteBusy(true);
    try {
      await fetch(`${LIBRARIAN_BASE}/research/topics/${encodeURIComponent(topic)}`, { method: 'DELETE' });
      setResearchTopics(prev => prev.filter(t => t.topic !== topic));
    } catch {
      // silently fail
    } finally {
      setDeleteBusy(false);
      setConfirmDelete(null);
    }
  }

  const inputStyle: React.CSSProperties = {
    width: '100%', boxSizing: 'border-box',
    padding: '7px 10px', borderRadius: 6,
    border: '1px solid var(--rule)',
    background: 'var(--bg-2, var(--surface))',
    color: 'var(--fg)',
    fontSize: 13,
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <p style={{ margin: 0, fontSize: 13, color: 'var(--fg-3)' }}>
          Manage scheduled research topics that the AI Librarian ingests automatically.
        </p>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={loadTopics}
            style={{
              padding: '6px 14px', borderRadius: 6, border: '1px solid var(--rule)',
              background: 'transparent', color: 'var(--fg-2)', fontSize: 12.5, cursor: 'pointer',
            }}
          >
            Reload
          </button>
          <button
            onClick={() => setShowAddForm(s => !s)}
            style={{
              padding: '6px 14px', borderRadius: 6, border: 'none',
              background: 'var(--accent)', color: '#fff', fontSize: 12.5,
              fontWeight: 600, cursor: 'pointer',
            }}
          >
            + Add topic
          </button>
        </div>
      </div>

      {showAddForm && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card__body" style={{ padding: '18px 20px' }}>
            <h4 style={{ margin: '0 0 14px', fontSize: 14, fontWeight: 600 }}>New research topic</h4>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span style={{ fontSize: 11.5, fontWeight: 500, color: 'var(--fg-2)' }}>Topic slug *</span>
                <input
                  type="text"
                  placeholder="e.g. ai-safety"
                  value={addForm.topic}
                  onChange={e => setAddForm(f => ({ ...f, topic: e.target.value }))}
                  style={inputStyle}
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span style={{ fontSize: 11.5, fontWeight: 500, color: 'var(--fg-2)' }}>Interval (hours) *</span>
                <input
                  type="number"
                  min={1}
                  placeholder="24"
                  value={addForm.interval_hours}
                  onChange={e => setAddForm(f => ({ ...f, interval_hours: e.target.value }))}
                  style={inputStyle}
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4, gridColumn: '1 / -1' }}>
                <span style={{ fontSize: 11.5, fontWeight: 500, color: 'var(--fg-2)' }}>Description *</span>
                <input
                  type="text"
                  placeholder="Short description of what this topic covers"
                  value={addForm.description}
                  onChange={e => setAddForm(f => ({ ...f, description: e.target.value }))}
                  style={inputStyle}
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4, gridColumn: '1 / -1' }}>
                <span style={{ fontSize: 11.5, fontWeight: 500, color: 'var(--fg-2)' }}>Search query *</span>
                <input
                  type="text"
                  placeholder="Query string used to fetch new content"
                  value={addForm.search_query}
                  onChange={e => setAddForm(f => ({ ...f, search_query: e.target.value }))}
                  style={inputStyle}
                />
              </label>
            </div>
            {addError && (
              <div style={{ fontSize: 12.5, color: 'var(--error, #e53e3e)', marginTop: 10 }}>{addError}</div>
            )}
            <div style={{ display: 'flex', gap: 8, marginTop: 14, justifyContent: 'flex-end' }}>
              <button
                onClick={() => { setShowAddForm(false); setAddError(null); }}
                style={{
                  padding: '6px 16px', borderRadius: 6, border: '1px solid var(--rule)',
                  background: 'transparent', color: 'var(--fg-2)', fontSize: 13, cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={addTopic}
                disabled={addBusy}
                style={{
                  padding: '6px 18px', borderRadius: 6, border: 'none',
                  background: 'var(--accent)', color: '#fff', fontSize: 13,
                  fontWeight: 600, cursor: addBusy ? 'default' : 'pointer',
                  opacity: addBusy ? 0.7 : 1,
                }}
              >
                {addBusy ? 'Adding…' : 'Add topic'}
              </button>
            </div>
          </div>
        </div>
      )}

      {loading && (
        <div className="card">
          <div className="card__body" style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
            Loading topics…
          </div>
        </div>
      )}

      {error && (
        <div className="card">
          <div className="card__body" style={{ padding: '24px 20px', fontSize: 13 }}>
            <span style={{ color: 'var(--error, #e53e3e)' }}>Could not reach the AI Librarian service.</span>{' '}
            Make sure it is running at <code>{LIBRARIAN_BASE}</code>.
          </div>
        </div>
      )}

      {!loading && !error && researchTopics.length === 0 && (
        <div className="card">
          <div className="card__body" style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
            No research topics configured yet. Click "+ Add topic" to create one.
          </div>
        </div>
      )}

      {!loading && !error && researchTopics.length > 0 && (
        <div className="card">
          <div className="card__body" style={{ padding: 0 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--rule)' }}>
                  {['Topic', 'Description', 'Interval', 'Last researched', 'Enabled', ''].map(h => (
                    <th key={h} style={{
                      padding: '10px 14px', textAlign: 'left', fontSize: 11,
                      fontWeight: 600, color: 'var(--fg-3)',
                      textTransform: 'uppercase', letterSpacing: '0.04em',
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {researchTopics.map(t => (
                  <tr key={t.topic} style={{ borderBottom: '1px solid var(--rule)' }}>
                    <td style={{ padding: '10px 14px', fontWeight: 600, fontFamily: 'var(--font-mono)', fontSize: 12.5 }}>
                      {t.topic}
                    </td>
                    <td style={{ padding: '10px 14px', color: 'var(--fg-2)', fontSize: 12.5, maxWidth: 260 }}>
                      {t.description || '—'}
                    </td>
                    <td style={{ padding: '10px 14px', color: 'var(--fg-2)', fontSize: 12.5, whiteSpace: 'nowrap' }}>
                      {t.interval_hours}h
                    </td>
                    <td style={{ padding: '10px 14px', color: 'var(--fg-3)', fontSize: 12, whiteSpace: 'nowrap' }}>
                      {formatDate(t.last_researched_at)}
                    </td>
                    <td style={{ padding: '10px 14px' }}>
                      <button
                        onClick={() => toggleEnabled(t)}
                        disabled={togglingTopic === t.topic}
                        style={{
                          padding: '3px 10px', borderRadius: 12,
                          border: `1px solid ${t.enabled ? 'var(--green, #22c55e)' : 'var(--rule)'}`,
                          background: t.enabled ? 'rgba(34,197,94,0.12)' : 'transparent',
                          color: t.enabled ? 'var(--green, #22c55e)' : 'var(--fg-3)',
                          fontSize: 11.5, fontWeight: 600, cursor: 'pointer',
                        }}
                      >
                        {togglingTopic === t.topic ? '…' : t.enabled ? 'Enabled' : 'Disabled'}
                      </button>
                    </td>
                    <td style={{ padding: '10px 14px' }}>
                      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                        <button
                          onClick={() => triggerNow(t.topic)}
                          disabled={triggering === t.topic}
                          style={{
                            padding: '4px 10px', borderRadius: 6,
                            border: '1px solid var(--rule)', background: 'transparent',
                            color: 'var(--fg-2)', fontSize: 12, cursor: 'pointer',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {triggering === t.topic ? 'Triggering…' : 'Trigger now'}
                        </button>
                        <button
                          onClick={() => setConfirmDelete(t.topic)}
                          style={{
                            padding: '4px 10px', borderRadius: 6,
                            border: '1px solid var(--rule)', background: 'transparent',
                            color: 'var(--error, #e53e3e)', fontSize: 12, cursor: 'pointer',
                          }}
                        >
                          Delete
                        </button>
                        {statusMsg?.topic === t.topic && (
                          <span style={{ fontSize: 11.5, color: statusMsg.ok ? 'var(--green, #22c55e)' : 'var(--error, #e53e3e)', whiteSpace: 'nowrap' }}>
                            {statusMsg.msg}
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Delete confirm dialog */}
      {confirmDelete && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)',
            zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
          onClick={(e) => { if (e.target === e.currentTarget) setConfirmDelete(null); }}
        >
          <div style={{
            background: 'var(--bg)', borderRadius: 10, padding: '28px 32px',
            maxWidth: 420, width: '100%', boxShadow: '0 8px 40px rgba(0,0,0,0.3)',
          }}>
            <h4 style={{ margin: '0 0 10px', fontSize: 15 }}>Delete topic "{confirmDelete}"?</h4>
            <p style={{ margin: '0 0 20px', fontSize: 13, color: 'var(--fg-3)' }}>
              This will remove the topic and stop future research runs. Indexed documents are not deleted.
            </p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button
                onClick={() => setConfirmDelete(null)}
                style={{
                  padding: '7px 16px', borderRadius: 6, border: '1px solid var(--rule)',
                  background: 'transparent', color: 'var(--fg-2)', fontSize: 13, cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={() => deleteTopic(confirmDelete)}
                disabled={deleteBusy}
                style={{
                  padding: '7px 16px', borderRadius: 6, border: 'none',
                  background: 'var(--error, #e53e3e)', color: '#fff', fontSize: 13,
                  fontWeight: 600, cursor: deleteBusy ? 'default' : 'pointer',
                  opacity: deleteBusy ? 0.7 : 1,
                }}
              >
                {deleteBusy ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function PromptsPage() {
  const [topics, setTopics] = useState<TopicSummary[]>([]);
  const [loadingTopics, setLoadingTopics] = useState(true);
  const [topicsError, setTopicsError] = useState<string | null>(null);
  const [activeModal, setActiveModal] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'browse' | 'manage'>('browse');

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

  const tabBtnStyle = (active: boolean): React.CSSProperties => ({
    padding: '6px 16px', borderRadius: 6, border: '1px solid var(--rule)',
    background: active ? 'var(--accent)' : 'transparent',
    color: active ? '#fff' : 'var(--fg-2)',
    fontSize: 13, fontWeight: active ? 600 : 400, cursor: 'pointer',
  });

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

      {/* Research Knowledge Base section with tabs */}
      <div style={{ marginTop: 40 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Research Knowledge Base</h2>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--fg-3)' }}>
              Continuously researched topics available for agent grounding and semantic search.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button style={tabBtnStyle(activeTab === 'browse')} onClick={() => setActiveTab('browse')}>
              Browse
            </button>
            <button style={tabBtnStyle(activeTab === 'manage')} onClick={() => setActiveTab('manage')}>
              Manage Topics
            </button>
          </div>
        </div>

        {activeTab === 'browse' && (
          <>
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
          </>
        )}

        {activeTab === 'manage' && <ManageTopicsPanel />}
      </div>

      {activeModal && (
        <SearchModal topic={activeModal} onClose={() => setActiveModal(null)} />
      )}
    </main>
  );
}
