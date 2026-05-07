'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { LoadingState, ErrorState, EmptyState } from '../_components/PageStates';
import { MCP_DATA } from '../_mocks/data';

type McpServer = typeof MCP_DATA[number];

function statusPill(s: McpServer['status']) {
  if (s === 'good') return <span className="pill pill--good"><span className="dot"></span>healthy</span>;
  if (s === 'warn') return <span className="pill pill--warn"><span className="dot"></span>degraded</span>;
  if (s === 'bad') return <span className="pill pill--bad"><span className="dot"></span>auth failing</span>;
  return <span className="pill pill--warn"><span className="dot"></span>pending review</span>;
}

function scopePill(scope: string) {
  if (scope.includes('write') || scope === 'orders:write') return <span className="pill pill--bad">{scope}</span>;
  return <span className="pill pill--info">{scope}</span>;
}

export default function McpPage() {
  const [filter, setFilter] = useState('All');

  const { data, isLoading, isError, error, refetch } = useQuery<McpServer[]>({
    queryKey: ['mcp-servers'],
    queryFn: () => fetch('/api/v1/mcp/servers').then(r => r.json()),
  });

  if (isLoading) return <section className="page"><LoadingState rows={6} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;

  const rows = data ?? MCP_DATA;

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">MCP server registry</h1>
          <p className="page__sub">14 servers · 11 internal · 3 vendored · 87 tools governed by org policy</p>
        </div>
        <div className="page__actions">
          <button className="btn">Audit log</button>
          <button className="btn btn--primary">+ Register server</button>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 18 }}>
        <div className="kpi"><div className="kpi__label">Connected</div><div className="kpi__value">14</div><div className="kpi__delta flat">11 internal · 3 vendored</div></div>
        <div className="kpi"><div className="kpi__label">Tools exposed</div><div className="kpi__value">87</div><div className="kpi__delta flat">52 read · 35 write</div></div>
        <div className="kpi"><div className="kpi__label">Calls · 24h</div><div className="kpi__value">12,408</div><div className="kpi__delta up">▲ 8.0%</div></div>
        <div className="kpi"><div className="kpi__label">Failing</div><div className="kpi__value">1</div><div className="kpi__delta down">confluence-mcp · auth</div></div>
      </div>

      <div className="filters">
        <button className="filter"><span className="lbl">Status</span><span className="val">All</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Source</span><span className="val">All</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Owner</span><span className="val">Any</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Scope</span><span className="val">Any</span><span className="caret">▾</span></button>
        <span style={{ flex: 1 }} />
        <div className="seg">
          {['All','Approved','Pending'].map(f => (
            <button key={f} className={filter === f ? 'is-active' : undefined} onClick={() => setFilter(f)}>{f}</button>
          ))}
        </div>
      </div>

      {rows.length === 0 ? <EmptyState message="No MCP servers registered." /> : (
        <div className="card">
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 30 }}><input type="checkbox" /></th>
                  <th>Server</th><th>Owner</th><th>Source</th><th>Tools</th><th>Scopes</th>
                  <th className="num">Calls (24h)</th><th className="num">P50</th><th className="num">Err</th>
                  <th>Status</th><th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map(s => (
                  <tr key={s.name} tabIndex={0} style={{ cursor: 'pointer' }} onKeyDown={e => { if (e.key === 'Enter') {} }}>
                    <td><input type="checkbox" /></td>
                    <td><div className="cell-2"><span className="mono">{s.name}</span><span className="lo">{s.version} · {s.transport}</span></div></td>
                    <td>{s.owner}</td>
                    <td><span className="pill">{s.source}</span></td>
                    <td className="num mono">{s.tools}</td>
                    <td>
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {s.scopes.map(sc => scopePill(sc))}
                      </div>
                    </td>
                    <td className="num mono">{s.calls24h}</td>
                    <td className="num mono">{s.p50}</td>
                    <td className="num mono" style={{ color: parseFloat(s.err) > 5 ? 'var(--bad)' : undefined }}>{s.err}</td>
                    <td>{statusPill(s.status)}</td>
                    <td><button className="btn btn--sm">{s.btn}</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p className="muted" style={{ fontSize: 12, marginTop: 14 }}>
        Tip: write-scoped tools (orange/red pills) require an approved tool-scope policy on the calling team. See{' '}
        <a href="/admin/policies" style={{ color: 'var(--sc-link)' }}>Policies</a>.
      </p>
    </section>
  );
}
