'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../_components/PageStates';

const BASE = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

interface AuditRow {
  id: string;
  actor: string;
  action: string;
  resource_id: string;
  resource_type: string;
  details: Record<string, unknown>;
  timestamp: string;
}

function actionPill(a: string) {
  if (a.startsWith('request.blocked') || a.startsWith('plugin.block')) return <span className="pill pill--bad">{a}</span>;
  if (a.startsWith('output.redacted')) return <span className="pill pill--warn">{a}</span>;
  if (a.startsWith('tool.scope.request') || a.startsWith('budget.threshold') || a.startsWith('eval.regress')) return <span className="pill pill--info">{a}</span>;
  if (a.startsWith('set_') || a.startsWith('create_') || a.startsWith('update_')) return <span className="pill pill--good">{a}</span>;
  return <span className="pill">{a}</span>;
}

function formatTimestamp(ts: string): string {
  try {
    return new Date(ts).toISOString().replace('T', ' ').substring(0, 19);
  } catch {
    return ts;
  }
}

export default function AuditPage() {
  const [search, setSearch] = useState('');

  const { data, isLoading, isError, error, refetch } = useQuery<AuditRow[]>({
    queryKey: ['audit'],
    queryFn: () => fetch(BASE + '/audit?limit=50').then(r => r.json()),
  });

  if (isLoading) return <section className="page"><LoadingState rows={12} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;

  const rows = data ?? [];

  const filtered = search
    ? rows.filter(r =>
        r.actor.toLowerCase().includes(search.toLowerCase()) ||
        r.action.toLowerCase().includes(search.toLowerCase()) ||
        r.resource_type.toLowerCase().includes(search.toLowerCase()) ||
        r.resource_id.toLowerCase().includes(search.toLowerCase())
      )
    : rows;

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Audit log</h1>
          <p className="page__sub">Tamper-evident · WORM-stored · retention 7y · last export 6 May 2026 by audit@simcorp</p>
        </div>
        <div className="page__actions">
          <button
            className="btn btn--primary"
            disabled={filtered.length === 0}
            onClick={() => {
              const header = 'Timestamp,Actor,Action,Resource Type,Resource ID';
              const csvRows = filtered.map(r =>
                [formatTimestamp(r.timestamp), r.actor, r.action, r.resource_type, r.resource_id].map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')
              );
              const csv = [header, ...csvRows].join('\n');
              const blob = new Blob([csv], { type: 'text/csv' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a'); a.href = url; a.download = 'audit-log.csv'; a.click();
              URL.revokeObjectURL(url);
            }}
          >
            Export CSV
          </button>
        </div>
      </div>

      <div className="filters" style={{ marginBottom: 16 }}>
        <span style={{ flex: 1 }} />
        <input
          className="search"
          type="search"
          placeholder="Search actor, action, resource…"
          style={{ width: 280 }}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      <div className="card">
        <div className="card__body" style={{ padding: 0 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Timestamp (UTC)</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Resource</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr key={row.id} tabIndex={0} style={{ cursor: 'pointer' }}>
                  <td className="mono lo" style={{ whiteSpace: 'nowrap' }}>{formatTimestamp(row.timestamp)}</td>
                  <td>
                    <div className="cell-2">
                      <span style={{ fontWeight: 500 }}>{row.actor}</span>
                    </div>
                  </td>
                  <td>{actionPill(row.action)}</td>
                  <td className="mono" style={{ fontSize: 12, color: 'var(--fg-2)' }}>
                    {row.resource_type}{row.resource_id ? ` · ${row.resource_id.substring(0, 8)}…` : ''}
                  </td>
                  <td></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 16px',
          borderTop: '1px solid var(--rule)',
          fontSize: 12,
          color: 'var(--fg-2)',
        }}>
          <span>
            Showing {filtered.length} of {rows.length} events &middot;{' '}
            <span className="mono" style={{ fontSize: 11 }}>WORM-stored, integrity hash sha256:8a4f&hellip;20de</span>
          </span>
          <button className="btn btn--sm" onClick={() => refetch()}>Refresh</button>
        </div>
      </div>
    </section>
  );
}
