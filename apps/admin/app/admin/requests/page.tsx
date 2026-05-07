'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../_components/PageStates';
import { generateRequests, type RequestRow } from '../_mocks/data';

function statusPill(s: number) {
  if (s === 200) return <span className="pill pill--good"><span className="dot"></span>200</span>;
  if (s === 429) return <span className="pill pill--warn"><span className="dot"></span>429</span>;
  if (s === 401) return <span className="pill pill--bad"><span className="dot"></span>401</span>;
  return <span className="pill pill--bad"><span className="dot"></span>{s}</span>;
}

function cachePill(c: RequestRow['cache'], sim: number | null) {
  if (c === 'exact') return <span className="pill pill--info">exact</span>;
  if (c === 'semantic') return <span className="pill pill--info">semantic <span className="mono" style={{ opacity: 0.7 }}>{sim?.toFixed(3)}</span></span>;
  return <span className="pill">miss</span>;
}

export default function RequestsPage() {
  const [paused, setPaused] = useState(false);
  const [selected, setSelected] = useState<number | null>(2);

  const { data, isLoading, isError, error, refetch } = useQuery<RequestRow[]>({
    queryKey: ['requests'],
    queryFn: () => fetch('/api/v1/requests').then(r => r.json()),
    refetchInterval: paused ? false : 5000,
  });

  const rows = data ?? generateRequests();

  const selectedRow = selected !== null ? rows[selected] : null;

  if (isLoading) return <section className="page"><LoadingState rows={10} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Live requests</h1>
          <p className="page__sub">
            <span className="statusdot statusdot--good"></span>
            Streaming · 27.8 req/s · <span className="muted">last 10 min, all teams</span>
          </p>
        </div>
        <div className="page__actions">
          <button className="btn" onClick={() => setPaused(p => !p)}>{paused ? '▶ Resume' : '⏸ Pause'}</button>
          <button className="btn" onClick={() => refetch()}>Replay</button>
          <button className="btn btn--primary">Save view</button>
        </div>
      </div>

      <div className="minimet-row" style={{ marginBottom: 14 }}>
        <div className="minimet"><div className="minimet__l">Req in window</div><div className="minimet__v">16,732</div></div>
        <div className="minimet"><div className="minimet__l">Cache hit</div><div className="minimet__v" style={{ color: 'var(--good)' }}>38<span className="unit">%</span></div></div>
        <div className="minimet"><div className="minimet__l">p50 / p99</div><div className="minimet__v">820ms / 4.2s</div></div>
        <div className="minimet"><div className="minimet__l">Errors</div><div className="minimet__v" style={{ color: 'var(--bad)' }}>0.21<span className="unit">%</span></div></div>
        <div className="minimet"><div className="minimet__l">Tokens / min</div><div className="minimet__v">412K</div></div>
        <div className="minimet"><div className="minimet__l">Active streams</div><div className="minimet__v">142</div></div>
      </div>

      <div className="filters">
        <button className="filter"><span className="lbl">Team</span><span className="val">All</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Model</span><span className="val">All</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Status</span><span className="val">2xx, 4xx, 5xx</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Cache</span><span className="val">Any</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Latency</span><span className="val">≥ 0ms</span><span className="caret">▾</span></button>
        <span style={{ flex: 1 }} />
        <div className="search" style={{ width: 'auto' }}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14"/></svg>
          <input placeholder="Filter by request_id, prompt hash, key…" />
        </div>
      </div>

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        <div className="card" style={{ flex: 1, minWidth: 0 }}>
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Time</th><th>Status</th><th>Team / key</th><th>Model</th>
                  <th>Cache</th><th className="num">Tokens (in / out)</th>
                  <th className="num">Latency</th><th className="num">Cost</th><th>Request</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr
                    key={i}
                    style={{ cursor: 'pointer' }}
                    className={selected === i ? 'is-selected' : undefined}
                    onClick={() => setSelected(i)}
                    onKeyDown={e => { if (e.key === 'Enter') setSelected(i); }}
                    tabIndex={0}
                  >
                    <td className="mono" style={{ fontSize: 12 }}>{r.t}</td>
                    <td>{statusPill(r.status)}</td>
                    <td><div className="cell-2"><span style={{ fontWeight: 500 }}>{r.team}</span><span className="lo mono">{r.key}</span></div></td>
                    <td><div className="cell-2"><span className="mono">{r.model}</span><span className="lo">{r.provider}</span></div></td>
                    <td>{cachePill(r.cache, r.similarity)}</td>
                    <td className="num mono" style={{ color: r.status === 200 ? 'var(--fg-1)' : 'var(--fg-3)' }}>
                      {r.tokIn.toLocaleString()} / {r.tokOut.toLocaleString()}
                    </td>
                    <td className="num mono">{r.latency}ms{r.streaming ? <span className="muted" style={{ fontSize: 10 }}> stream</span> : null}</td>
                    <td className="num mono">{r.cost === 0 ? '—' : '$' + r.cost.toFixed(4)}</td>
                    <td><span className="mono" style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>{r.reqId}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {selectedRow && (
          <div className="card" style={{ width: 360, flexShrink: 0 }}>
            <div className="drawer__head" style={{ padding: '12px 16px', borderBottom: '1px solid var(--rule)', display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ flex: 1 }}>
                {statusPill(selectedRow.status)}
                <span className="mono" style={{ fontWeight: 500, marginLeft: 8 }}>{selectedRow.model}</span>
              </div>
              <button className="icon-btn" onClick={() => setSelected(null)} style={{ width: 28, height: 28 }}>✕</button>
            </div>
            <div style={{ padding: '14px 16px', overflowY: 'auto', maxHeight: 600 }}>
              <div className="dl" style={{ marginBottom: 14 }}>
                <dt>Team</dt><dd>{selectedRow.team}</dd>
                <dt>API key</dt><dd className="mono">{selectedRow.key}</dd>
                <dt>Caller</dt><dd className="mono">rag-indexer-v3 · pod-04 · 10.42.7.118</dd>
                <dt>Model</dt><dd className="mono">{selectedRow.model} <span className="muted">({selectedRow.provider})</span></dd>
                <dt>Cache</dt><dd>{cachePill(selectedRow.cache, selectedRow.similarity)}</dd>
                <dt>Tokens</dt><dd>{selectedRow.tokIn.toLocaleString()} in · {selectedRow.tokOut.toLocaleString()} out</dd>
                <dt>Cost</dt><dd>{selectedRow.cost === 0 ? '$0.00 (cache hit)' : '$' + selectedRow.cost.toFixed(6)}</dd>
                <dt>Latency</dt><dd>{selectedRow.latency}ms {selectedRow.streaming ? '· streamed' : ''}</dd>
              </div>

              <h4 style={{ margin: '14px 0 6px', fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--fg-2)' }}>Trace</h4>
              {(() => {
                const total = selectedRow.latency;
                const auth = Math.min(8, total * 0.05);
                const cacheLookup = selectedRow.cache !== 'miss' ? total - auth : Math.min(35, total * 0.08);
                const provider = selectedRow.cache !== 'miss' ? 0 : (total - auth - cacheLookup);
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

              <h4 style={{ margin: '18px 0 6px', fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--fg-2)' }}>Request</h4>
              <pre className="code" style={{ fontSize: 11, overflow: 'auto' }}>{`POST /v1/chat/completions
authorization: Bearer ${selectedRow.key}
x-team: ${selectedRow.team}

{
  "model": "${selectedRow.model}",
  "messages": [
    {"role":"user","content":"Summarise the last quarter…"}
  ],
  "stream": ${selectedRow.streaming}
}`}</pre>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
