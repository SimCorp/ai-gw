'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useTeam } from '../_lib/teamContext';
import RelatedChampionContent from '../_components/RelatedChampionContent';

const BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? 'http://localhost:8005';

interface Workflow {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  latest_version: number;
  created_at: string;
}

export default function WorkflowsPage() {
  const { teamId } = useTeam();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!teamId) return;
    setLoading(true);
    fetch(`${BASE}/workflows?team_id=${teamId}`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => setWorkflows(d.workflows ?? []))
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, [teamId]);

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <h1>Workflows</h1>
          <p>Visual agent workflow definitions for your team.</p>
        </div>
      </div>

      {!teamId && (
        <div className="card"><div className="card__body" style={{ color: 'var(--fg-3)', padding: '40px 20px', textAlign: 'center' }}>
          Select a team from the sidebar.
        </div></div>
      )}
      {teamId && loading && (
        <div className="card"><div className="card__body" style={{ color: 'var(--fg-3)', padding: '40px 20px', textAlign: 'center' }}>Loading…</div></div>
      )}
      {error && (
        <div className="card" style={{ borderColor: 'var(--red)' }}>
          <div className="card__body" style={{ color: 'var(--red)' }}>{error}</div>
        </div>
      )}

      {!loading && !error && teamId && workflows.length === 0 && (
        <div className="card"><div className="card__body" style={{ color: 'var(--fg-3)', padding: '40px 20px', textAlign: 'center', fontSize: 13 }}>
          No workflows yet. Create one via the API or Admin portal.
        </div></div>
      )}

      {workflows.map(wf => (
        <div key={wf.id} className="card" style={{ marginBottom: 10 }}>
          <div className="card__body" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--fg-1)' }}>{wf.name}</div>
              <div style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: 2 }}>{wf.slug} · v{wf.latest_version}</div>
              {wf.description && <div style={{ fontSize: 12, color: 'var(--fg-2)', marginTop: 4 }}>{wf.description}</div>}
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>{new Date(wf.created_at).toLocaleDateString()}</span>
              <Link
                href={`/portal/workflows/${wf.id}/designer`}
                style={{ fontSize: 12, color: 'var(--fg-2)', textDecoration: 'none', padding: '3px 8px', border: '1px solid var(--rule)', borderRadius: 5 }}
              >
                Design
              </Link>
              <Link
                href={`/portal/workflows/${wf.id}/runs/new`}
                style={{ fontSize: 12, color: 'var(--blue)', textDecoration: 'none', padding: '3px 8px', border: '1px solid var(--blue)', borderRadius: 5 }}
              >
                View runs →
              </Link>
            </div>
          </div>
        </div>
      ))}
      <RelatedChampionContent tags={["workflows"]} />
    </main>
  );
}
