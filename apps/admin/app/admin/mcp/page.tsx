'use client';

import React, { useState } from 'react';
import { EmptyState } from '../_components/PageStates';

type McpStatus = 'good' | 'warn' | 'bad' | 'pending';

type McpServer = {
  name: string;
  version: string;
  transport: string;
  owner: string;
  source: 'internal' | 'vendored';
  tools: number;
  scopes: string[];
  calls24h: string;
  p50: string;
  err: string;
  status: McpStatus;
  btn: string;
};

const MCP_DATA: McpServer[] = [
  { name: 'portfolio-mcp',   version: 'v2.4.1',      transport: 'stdio',    owner: 'platform-data',       source: 'internal', tools: 9,  scopes: ['positions:read','weights:read'],  calls24h: '4,218', p50: '74 ms',  err: '0.02%', status: 'good',    btn: 'Inspect' },
  { name: 'market-data-mcp', version: 'v1.9.0',      transport: 'http+sse', owner: 'trading',             source: 'internal', tools: 14, scopes: ['quotes:read','refdata:read'],    calls24h: '3,841', p50: '48 ms',  err: '0.01%', status: 'good',    btn: 'Inspect' },
  { name: 'filings-mcp',     version: 'v0.8.3',      transport: 'http',     owner: 'research',            source: 'internal', tools: 6,  scopes: ['filings:read'],                  calls24h: '1,108', p50: '312 ms', err: '2.1%',  status: 'warn',    btn: 'Inspect' },
  { name: 'github-mcp',      version: 'v0.6.0',      transport: 'stdio',    owner: 'platform-engineering',source: 'vendored', tools: 11, scopes: ['repo:read','pr:write'],           calls24h: '1,684', p50: '128 ms', err: '0.04%', status: 'good',    btn: 'Inspect' },
  { name: 'confluence-mcp',  version: 'v0.3.1',      transport: 'http',     owner: '(third-party)',       source: 'vendored', tools: 5,  scopes: ['space:read'],                    calls24h: '0',     p50: '—',      err: '91%',   status: 'bad',     btn: 'Reconnect' },
  { name: 'trade-mcp',       version: 'v1.0.0-rc.2', transport: 'stdio',    owner: 'trading',             source: 'internal', tools: 4,  scopes: ['orders:write','orders:read'],    calls24h: '—',     p50: '—',      err: '—',     status: 'pending', btn: 'Review' },
];

function statusPill(s: McpStatus) {
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

  const rows = MCP_DATA;

  return (
    <section className="page">
      <div className="pill pill--warn" style={{ marginBottom: 12 }}>Live data not yet available for this page · showing representative data</div>

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
