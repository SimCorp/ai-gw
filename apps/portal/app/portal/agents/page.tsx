'use client';

import { useState, useEffect, useRef } from 'react';
import RelatedChampionContent from '../_components/RelatedChampionContent';

const BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? 'http://localhost:8005';
const IDENTITY_BASE = process.env.NEXT_PUBLIC_IDENTITY_BASE_URL ?? 'http://localhost:8006';

interface Agent {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  image: string;
  category: string | null;
  managed: boolean;
}

interface IdentityAgent {
  id: string;
  slug: string;
  name: string;
  category: string | null;
  capabilities: string[];
  endpoint: string;
  team_id: string | null;
  managed: boolean;
  online: boolean;
  registered_at: string;
  last_seen: string;
}

const CATEGORY_COLOR: Record<string, string> = {
  utility:     'var(--fg-3)',
  llm:         'var(--blue)',
  integration: 'var(--teal, #14b8a6)',
  data:        'var(--purple, #8b5cf6)',
};

function OnlineDot({ online }: { online: boolean }) {
  return (
    <span
      title={online ? 'Online' : 'Offline'}
      style={{
        display: 'inline-block',
        width: 8,
        height: 8,
        borderRadius: '50%',
        background: online ? 'var(--green, #22c55e)' : 'var(--fg-3)',
        marginRight: 5,
        flexShrink: 0,
      }}
    />
  );
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Identity search state
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState<IdentityAgent[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    fetch(`${BASE}/agents`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => setAgents(d.agents ?? []))
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  // Debounced identity resolve
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    const trimmed = query.trim();
    if (!trimmed) {
      setSearchResults(null);
      setSearchError(null);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      setSearchError(null);
      try {
        const r = await fetch(`${IDENTITY_BASE}/resolve/${encodeURIComponent(trimmed)}`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data: IdentityAgent[] = await r.json();
        setSearchResults(data);
      } catch (e) {
        setSearchError(String(e));
        setSearchResults(null);
      } finally {
        setSearching(false);
      }
    }, 300);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <h1>Agents</h1>
          <p>Registered agent images available on the workflow designer palette.</p>
        </div>
      </div>

      {/* ── Identity search ── */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card__body">
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-2)', marginBottom: 8 }}>
            Identity Lookup
            <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--fg-3)', marginLeft: 8 }}>
              search by slug, capability tag, or name
            </span>
          </div>
          <input
            type="search"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="e.g. echo-agent, transform, llm…"
            style={{
              width: '100%',
              padding: '6px 10px',
              fontSize: 13,
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              borderRadius: 4,
              color: 'var(--fg-1)',
              outline: 'none',
              boxSizing: 'border-box',
            }}
          />

          {searching && (
            <div style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: 8 }}>Searching…</div>
          )}

          {searchError && (
            <div style={{ fontSize: 12, color: 'var(--red)', marginTop: 8 }}>
              Could not reach identity service: {searchError}
            </div>
          )}

          {searchResults !== null && !searching && (
            <div style={{ marginTop: 10 }}>
              {searchResults.length === 0 ? (
                <div style={{ fontSize: 12, color: 'var(--fg-3)' }}>No agents matched "{query}"</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {searchResults.map(a => (
                    <div
                      key={a.id}
                      style={{
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: 10,
                        padding: '8px 10px',
                        background: 'var(--surface-2)',
                        borderRadius: 4,
                        border: '1px solid var(--border)',
                      }}
                    >
                      <OnlineDot online={a.online} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                          <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--fg-1)' }}>{a.name}</span>
                          <code style={{ fontSize: 11, color: 'var(--fg-3)', background: 'var(--surface-3, var(--surface-2))', padding: '1px 4px', borderRadius: 3 }}>
                            {a.slug}
                          </code>
                          {a.managed && (
                            <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.05em', color: 'var(--blue)', border: '1px solid var(--blue)', padding: '1px 5px', borderRadius: 3 }}>
                              MANAGED
                            </span>
                          )}
                          {a.category && (
                            <span style={{ fontSize: 11, color: CATEGORY_COLOR[a.category] ?? 'var(--fg-3)', border: '1px solid currentColor', padding: '1px 6px', borderRadius: 3 }}>
                              {a.category}
                            </span>
                          )}
                        </div>
                        {a.capabilities.length > 0 && (
                          <div style={{ marginTop: 4, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                            {a.capabilities.map(cap => (
                              <span
                                key={cap}
                                style={{ fontSize: 10, color: 'var(--fg-3)', background: 'var(--surface-1, var(--bg))', border: '1px solid var(--border)', padding: '1px 5px', borderRadius: 3 }}
                              >
                                {cap}
                              </span>
                            ))}
                          </div>
                        )}
                        {a.endpoint && (
                          <div style={{ marginTop: 4, fontSize: 11, color: 'var(--fg-3)', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {a.endpoint}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Agent grid ── */}
      {loading && <div className="card"><div className="card__body" style={{ color: 'var(--fg-3)', padding: '40px 20px', textAlign: 'center' }}>Loading…</div></div>}
      {error && <div className="card" style={{ borderColor: 'var(--red)' }}><div className="card__body" style={{ color: 'var(--red)' }}>{error}</div></div>}

      {!loading && !error && agents.length === 0 && (
        <div className="card"><div className="card__body" style={{ color: 'var(--fg-3)', padding: '40px 20px', textAlign: 'center', fontSize: 13 }}>
          No agents registered yet. Register one via <code style={{ fontSize: 11 }}>POST /agents</code>.
        </div></div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
        {agents.map(a => (
          <div key={a.id} className="card">
            <div className="card__body">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--fg-1)' }}>{a.name}</div>
                {a.managed && (
                  <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.05em', color: 'var(--blue)', border: '1px solid var(--blue)', padding: '1px 5px', borderRadius: 3 }}>
                    MANAGED
                  </span>
                )}
              </div>
              {a.description && <div style={{ fontSize: 12, color: 'var(--fg-2)', marginBottom: 8 }}>{a.description}</div>}
              <div style={{ fontSize: 11, color: 'var(--fg-3)', fontFamily: 'monospace', background: 'var(--surface-2)', padding: '4px 6px', borderRadius: 4, marginBottom: 6 }}>
                {a.image}
              </div>
              {a.category && (
                <span style={{ fontSize: 11, color: CATEGORY_COLOR[a.category] ?? 'var(--fg-3)', border: '1px solid currentColor', padding: '1px 6px', borderRadius: 3 }}>
                  {a.category}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
      <RelatedChampionContent tags={["agents", "agentic"]} />
    </main>
  );
}
