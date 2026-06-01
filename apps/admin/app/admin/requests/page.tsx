'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

const BASE = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

interface RequestRow {
  id: string;
  created_at: string;
  team_name: string;
  key_hash: string | null;
  model: string;
  tokens_input: number;
  tokens_output: number;
  cost_usd: number;
  cache_hit: boolean;
  latency_ms: number | null;
}

interface Summary {
  request_count: number | null;
  cache_hit_pct: number | null;
  p50_ms: number | null;
  p99_ms: number | null;
  total_tokens: number | null;
}

function statusPill(r: RequestRow) {
  return <span className="pill pill--good"><span className="dot"></span>200</span>;
}

function cachePill(cacheHit: boolean) {
  if (cacheHit) return <span className="pill pill--info">hit</span>;
  return <span className="pill">miss</span>;
}

function fmtTime(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => n < 10 ? '0' + n : '' + n;
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function fmtMs(ms: number | null): string {
  if (ms == null) return '—';
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms}ms`;
}

export default function RequestsPage() {
  const [selected, setSelected] = useState<string | null>(null);

  const rowsQuery = useQuery<RequestRow[]>({
    queryKey: ['requests'],
    queryFn: () => fetch(`${BASE}/requests?limit=100`).then(r => {
      if (!r.ok) throw new Error(`Failed: ${r.status}`);
      return r.json();
    }),
    refetchInterval: 10_000,
  });

  const summaryQuery = useQuery<Summary>({
    queryKey: ['requests-summary'],
    queryFn: () => fetch(`${BASE}/requests/summary`).then(r => {
      if (!r.ok) throw new Error(`Failed: ${r.status}`);
      return r.json();
    }),
    refetchInterval: 10_000,
  });

  const rows = rowsQuery.data ?? [];
  const summary = summaryQuery.data;
  const selectedRow = rows.find(r => r.id === selected) ?? null;

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Live requests</h1>
          <p className="page__sub">
            <span className="statusdot statusdot--good"></span>
            {rows.length > 0 ? `${rows.length} records · auto-refreshes every 10s` : 'Loading…'}
          </p>
        </div>
        <div className="page__actions">
          <button className="btn" onClick={() => { rowsQuery.refetch(); summaryQuery.refetch(); }}>↻ Refresh</button>
        </div>
      </div>

      <div className="minimet-row" style={{ marginBottom: 14 }}>
        <div className="minimet">
          <div className="minimet__l">Requests (10 min)</div>
          <div className="minimet__v">{summary?.request_count?.toLocaleString() ?? '—'}</div>
        </div>
        <div className="minimet">
          <div className="minimet__l">Cache hit</div>
          <div className="minimet__v" style={{ color: 'var(--good)' }}>
            {summary?.cache_hit_pct != null ? `${summary.cache_hit_pct}` : '—'}<span className="unit">%</span>
          </div>
        </div>
        <div className="minimet">
          <div className="minimet__l">p50 / p99</div>
          <div className="minimet__v">
            {summary?.p50_ms != null ? fmtMs(Math.round(summary.p50_ms)) : '—'}
            {' / '}
            {summary?.p99_ms != null ? fmtMs(Math.round(summary.p99_ms)) : '—'}
          </div>
        </div>
        <div className="minimet">
          <div className="minimet__l">Tokens (10 min)</div>
          <div className="minimet__v">
            {summary?.total_tokens != null
              ? summary.total_tokens >= 1000
                ? `${(summary.total_tokens / 1000).toFixed(0)}K`
                : `${summary.total_tokens}`
              : '—'}
          </div>
        </div>
      </div>

      {rowsQuery.isError && (
        <div className="pill pill--bad" style={{ marginBottom: 12 }}>
          Failed to load requests: {(rowsQuery.error as Error).message}
        </div>
      )}

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        <div className="card" style={{ flex: 1, minWidth: 0 }}>
          <div className="card__body" style={{ padding: 0 }}>
            {rows.length === 0 && !rowsQuery.isLoading ? (
              <div style={{ padding: '32px 20px', color: 'var(--fg-2)', textAlign: 'center' }}>
                No requests recorded yet. Send a request through the gateway to see data here.
              </div>
            ) : (
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Team</th>
                    <th>Model</th>
                    <th>Cache</th>
                    <th className="num">Tokens (in / out)</th>
                    <th className="num">Latency</th>
                    <th className="num">Cost</th>
                    <th>Request ID</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(r => (
                    <tr
                      key={r.id}
                      style={{ cursor: 'pointer' }}
                      className={selected === r.id ? 'is-selected' : undefined}
                      onClick={() => setSelected(r.id === selected ? null : r.id)}
                      onKeyDown={e => { if (e.key === 'Enter') setSelected(r.id); }}
                      tabIndex={0}
                    >
                      <td className="mono" style={{ fontSize: 12 }}>{fmtTime(r.created_at)}</td>
                      <td style={{ fontWeight: 500 }}>{r.team_name}</td>
                      <td className="mono" style={{ fontSize: 12 }}>{r.model}</td>
                      <td>{cachePill(r.cache_hit)}</td>
                      <td className="num mono">
                        {r.tokens_input.toLocaleString()} / {r.tokens_output.toLocaleString()}
                      </td>
                      <td className="num mono">{fmtMs(r.latency_ms)}</td>
                      <td className="num mono">
                        {r.cost_usd === 0 ? '—' : `€${r.cost_usd.toFixed(4)}`}
                      </td>
                      <td>
                        <span className="mono" style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>
                          {r.id.slice(0, 8)}…
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {selectedRow && (
          <div className="card" style={{ width: 360, flexShrink: 0 }}>
            <div className="drawer__head" style={{ padding: '12px 16px', borderBottom: '1px solid var(--rule)', display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ flex: 1 }}>
                <span className="pill pill--good"><span className="dot"></span>200</span>
                <span className="mono" style={{ fontWeight: 500, marginLeft: 8 }}>{selectedRow.model}</span>
              </div>
              <button className="icon-btn" onClick={() => setSelected(null)} style={{ width: 28, height: 28 }}>✕</button>
            </div>
            <div style={{ padding: '14px 16px', overflowY: 'auto', maxHeight: 600 }}>
              <div className="dl" style={{ marginBottom: 14 }}>
                <dt>Request ID</dt><dd className="mono" style={{ fontSize: 11 }}>{selectedRow.id}</dd>
                <dt>Time</dt><dd>{new Date(selectedRow.created_at).toLocaleString()}</dd>
                <dt>Team</dt><dd>{selectedRow.team_name}</dd>
                {selectedRow.key_hash && (
                  <><dt>API key</dt><dd className="mono">{selectedRow.key_hash}</dd></>
                )}
                <dt>Model</dt><dd className="mono">{selectedRow.model}</dd>
                <dt>Cache</dt><dd>{cachePill(selectedRow.cache_hit)}</dd>
                <dt>Tokens</dt><dd>{selectedRow.tokens_input.toLocaleString()} in · {selectedRow.tokens_output.toLocaleString()} out</dd>
                <dt>Cost</dt><dd>{selectedRow.cost_usd === 0 ? '€0.00' : `€${selectedRow.cost_usd.toFixed(6)}`}</dd>
                <dt>Latency</dt><dd>{fmtMs(selectedRow.latency_ms)}</dd>
              </div>

              {selectedRow.latency_ms != null && (
                <>
                  <h4 style={{ margin: '14px 0 6px', fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--fg-2)' }}>
                    Trace <span style={{ fontWeight: 400, textTransform: 'none', fontSize: 10.5, color: 'var(--fg-3)' }}>· estimated from total latency</span>
                  </h4>
                  {(() => {
                    const total = selectedRow.latency_ms;
                    const auth = Math.min(8, total * 0.05);
                    const cacheLookup = selectedRow.cache_hit ? total - auth : Math.min(35, total * 0.08);
                    const provider = selectedRow.cache_hit ? 0 : (total - auth - cacheLookup);
                    const pct = [auth, cacheLookup, provider].map(v => Math.max(0, v) / total * 100);
                    return (
                      <>
                        <div style={{ display: 'flex', height: 22, borderRadius: 4, overflow: 'hidden', background: 'var(--surface-soft)' }}>
                          <span style={{ background: 'var(--sc-purple)', width: `${pct[0]}%` }}></span>
                          <span style={{ background: 'var(--sc-teal)', width: `${pct[1]}%` }}></span>
                          {provider > 0 && <span style={{ background: 'var(--sc-blue)', width: `${pct[2]}%` }}></span>}
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--fg-2)', marginTop: 6 }}>
                          <span><span className="statusdot" style={{ background: 'var(--sc-purple)', boxShadow: 'none' }}></span>auth {auth.toFixed(0)}ms</span>
                          <span><span className="statusdot" style={{ background: 'var(--sc-teal)', boxShadow: 'none' }}></span>cache {cacheLookup.toFixed(0)}ms</span>
                          {provider > 0 && <span><span className="statusdot" style={{ background: 'var(--sc-blue)', boxShadow: 'none' }}></span>provider {provider.toFixed(0)}ms</span>}
                          <span className="mono">total {total}ms</span>
                        </div>
                      </>
                    );
                  })()}
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
