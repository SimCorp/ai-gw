'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { LoadingState, ErrorState, EmptyState } from '../_components/PageStates';
import { MODELS_DATA } from '../_mocks/data';

type Model = typeof MODELS_DATA[number];

function tierPill(t: Model['tier']) {
  if (t === 'prod') return <span className="pill pill--info">prod</span>;
  if (t === 'preview') return <span className="pill pill--warn">preview</span>;
  if (t === 'embed') return <span className="pill">embed</span>;
  return <span className="pill">dev</span>;
}

function statusPill(s: Model['status'], note?: string) {
  if (s === 'good') return <span className="pill pill--good"><span className="dot"></span>healthy</span>;
  if (s === 'warn') return <span className="pill pill--warn"><span className="dot"></span>{note ?? 'degraded'}</span>;
  return <span className="pill pill--bad"><span className="dot"></span>{note ?? 'errors'}</span>;
}

export default function ModelsPage() {
  const [search, setSearch] = useState('');

  const { data, isLoading, isError, error, refetch } = useQuery<Model[]>({
    queryKey: ['models'],
    queryFn: () => fetch('/api/v1/models').then(r => r.json()),
  });

  if (isLoading) return <section className="page"><LoadingState rows={12} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;

  const rows = (data ?? MODELS_DATA).filter(m =>
    !search || m.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Model registry</h1>
          <p className="page__sub">22 models across 5 providers · OpenAI-compatible endpoints · LiteLLM-routed</p>
        </div>
        <div className="page__actions">
          <button className="btn">Reload from config</button>
          <button className="btn btn--primary">+ Register model</button>
        </div>
      </div>

      <div className="minimet-row" style={{ marginBottom: 18 }}>
        <div className="minimet"><div className="minimet__l">Models</div><div className="minimet__v">22</div></div>
        <div className="minimet"><div className="minimet__l">Production</div><div className="minimet__v">14</div></div>
        <div className="minimet"><div className="minimet__l">Dev / preview</div><div className="minimet__v">6</div></div>
        <div className="minimet"><div className="minimet__l">BYO / self-hosted</div><div className="minimet__v">2</div></div>
        <div className="minimet"><div className="minimet__l">Avg cost / 1M tok</div><div className="minimet__v">$3.81</div></div>
      </div>

      <div className="filters">
        <button className="filter"><span className="lbl">Provider</span><span className="val">All</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Tier</span><span className="val">All</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Capability</span><span className="val">Any</span><span className="caret">▾</span></button>
        <span style={{ flex: 1 }} />
        <div className="search" style={{ width: 'auto' }}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14"/></svg>
          <input placeholder="Filter models…" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
      </div>

      {rows.length === 0 ? <EmptyState message="No models match your filter." /> : (
        <div className="card">
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Model</th><th>Provider</th><th>Tier</th><th>Capabilities</th>
                  <th className="num">Context</th><th className="num">$ / 1M in</th><th className="num">$ / 1M out</th>
                  <th>Fallback</th><th className="num">Usage 7d</th><th>Status</th><th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map(m => {
                  const usageBar = Math.min(100, Math.round(m.usage / m.usageMax * 100));
                  return (
                    <tr key={m.name} tabIndex={0} style={{ cursor: 'pointer' }} onKeyDown={e => { if (e.key === 'Enter') {} }}>
                      <td><div className="cell-2"><span className="mono" style={{ fontWeight: 500 }}>{m.name}</span><span className="lo">openai-compat · streaming</span></div></td>
                      <td>{m.provider}</td>
                      <td>{tierPill(m.tier)}</td>
                      <td><div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>{m.caps.map(c => <span key={c} className="tag">{c}</span>)}</div></td>
                      <td className="num mono">{m.ctx}</td>
                      <td className="num mono">{m.cin}</td>
                      <td className="num mono">{m.cout}</td>
                      <td>{m.fb === '—' ? <span className="muted">—</span> : <span className="mono" style={{ fontSize: 11.5 }}>{m.fb}</span>}</td>
                      <td className="num">
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
                          <span className="mono">{m.usage}K</span>
                          <span style={{ display: 'inline-block', width: 38, height: 4, background: 'var(--surface-soft)', borderRadius: 2, position: 'relative', overflow: 'hidden' }}>
                            <span style={{ position: 'absolute', inset: `0 ${100 - usageBar}% 0 0`, background: 'var(--sc-blue)', borderRadius: 2 }}></span>
                          </span>
                        </div>
                      </td>
                      <td>{statusPill(m.status, m.note)}</td>
                      <td><button className="btn btn--sm btn--ghost">⋯</button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
