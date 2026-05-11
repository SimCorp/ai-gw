'use client';

import { useState, useEffect } from 'react';

const BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? 'http://localhost:8005';

interface Agent {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  image: string;
  category: string | null;
  managed: boolean;
}

const CATEGORY_COLOR: Record<string, string> = {
  utility:     'var(--fg-3)',
  llm:         'var(--blue)',
  integration: 'var(--teal, #14b8a6)',
  data:        'var(--purple, #8b5cf6)',
};

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${BASE}/agents`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => setAgents(d.agents ?? []))
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <h1>Agents</h1>
          <p>Registered agent images available on the workflow designer palette.</p>
        </div>
      </div>

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
    </main>
  );
}
