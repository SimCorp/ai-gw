'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../_components/PageStates';
import { AUDIT_DATA } from '../_mocks/data';

type AuditRow = typeof AUDIT_DATA[number];

function outcomePill(o: AuditRow['outcome']) {
  if (o === 'success') return <span className="pill pill--good"><span className="dot"></span>success</span>;
  if (o === 'blocked') return <span className="pill pill--bad"><span className="dot"></span>blocked</span>;
  if (o === 'redacted') return <span className="pill pill--warn"><span className="dot"></span>redacted</span>;
  if (o === 'pending') return <span className="pill pill--info"><span className="dot"></span>pending</span>;
  if (o === 'drift') return <span className="pill pill--warn"><span className="dot"></span>drift</span>;
  return <span className="pill">{o}</span>;
}

function actionPill(a: string) {
  if (a.startsWith('request.blocked') || a.startsWith('plugin.block')) return <span className="pill pill--bad">{a}</span>;
  if (a.startsWith('output.redacted')) return <span className="pill pill--warn">{a}</span>;
  if (a.startsWith('tool.scope.request') || a.startsWith('budget.threshold') || a.startsWith('eval.regress')) return <span className="pill pill--info">{a}</span>;
  return <span className="pill">{a}</span>;
}

export default function AuditPage() {
  const [search, setSearch] = useState('');

  const { data, isLoading, isError, error, refetch } = useQuery<AuditRow[]>({
    queryKey: ['audit'],
    queryFn: () => fetch('/api/v1/audit').then(r => r.json()),
  });

  if (isLoading) return <section className="page"><LoadingState rows={12} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;

  const rows = data ?? AUDIT_DATA;

  const filtered = search
    ? rows.filter(r =>
        r.actor.includes(search) ||
        r.action.includes(search) ||
        r.resource.includes(search) ||
        r.outcome.includes(search)
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
          <button className="btn">Schedule export</button>
          <button className="btn btn--primary">Export CSV</button>
        </div>
      </div>

      <div className="filters" style={{ marginBottom: 16 }}>
        <button className="filter"><span className="lbl">Range</span><span className="val">Today</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Actor</span><span className="val">All</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Action</span><span className="val">All</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Resource</span><span className="val">All</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Outcome</span><span className="val">All</span><span className="caret">▾</span></button>
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
                <th>Outcome</th>
                <th>Trace</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row, i) => (
                <tr key={i} tabIndex={0} style={{ cursor: 'pointer' }}>
                  <td className="mono lo" style={{ whiteSpace: 'nowrap' }}>{row.ts}</td>
                  <td>
                    <div className="cell-2">
                      <span style={{ fontWeight: 500 }}>{row.actor}</span>
                      <span className="lo">{row.role}</span>
                    </div>
                  </td>
                  <td>{actionPill(row.action)}</td>
                  <td className="mono" style={{ fontSize: 12, color: 'var(--fg-2)' }}>{row.resource}</td>
                  <td>{outcomePill(row.outcome)}</td>
                  <td className="mono lo" style={{ fontSize: 12 }}>{row.trace}</td>
                  <td><button className="btn btn--sm">{row.btn}</button></td>
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
            Showing {filtered.length} of 14,208 events &middot;{' '}
            <span className="mono" style={{ fontSize: 11 }}>WORM-stored, integrity hash sha256:8a4f&hellip;20de</span>
          </span>
          <span style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <button className="btn btn--sm">‹ Newer</button>
            <span>Page 1 of 1,184</span>
            <button className="btn btn--sm">Older ›</button>
          </span>
        </div>
      </div>
    </section>
  );
}
