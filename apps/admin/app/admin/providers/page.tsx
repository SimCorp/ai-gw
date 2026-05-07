'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../_components/PageStates';
import { PROVIDERS_DATA } from '../_mocks/data';

type Provider = typeof PROVIDERS_DATA[number];

function statusPill(s: Provider['status']) {
  if (s === 'good') return <span className="pill pill--good"><span className="dot"></span>healthy</span>;
  if (s === 'warn') return <span className="pill pill--warn"><span className="dot"></span>degraded · 187ms p99</span>;
  return <span className="pill pill--bad"><span className="dot"></span>5xx 8.2%</span>;
}

export default function ProvidersPage() {
  const { data, isLoading, isError, error, refetch } = useQuery<Provider[]>({
    queryKey: ['providers'],
    queryFn: () => fetch('/api/v1/providers').then(r => r.json()),
  });

  if (isLoading) return <section className="page"><LoadingState rows={6} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;

  const providers = data ?? PROVIDERS_DATA;

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Providers</h1>
          <p className="page__sub">Upstream model providers · API keys in Azure Key Vault · LiteLLM-routed</p>
        </div>
        <div className="page__actions">
          <button className="btn">View Key Vault</button>
          <button className="btn btn--primary">+ Add provider</button>
        </div>
      </div>

      <div className="prov">
        {providers.map(p => (
          <div key={p.name} className="prov-card">
            <div className="prov-card__head">
              <div className="prov-logo" style={{ background: p.color }}>{p.abbr}</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 13.5 }}>{p.name}</div>
                <div className="muted" style={{ fontSize: 12 }}>{p.desc}</div>
              </div>
              {statusPill(p.status)}
            </div>
            <div className="prov-card__body">
              <div className="prov-stat">
                <span className="prov-stat__l">Endpoint</span>
                <span className="prov-stat__v mono" style={{ fontSize: 12 }}>{p.endpoint}</span>
              </div>
              <div className="prov-stat">
                <span className="prov-stat__l">Region</span>
                <span className="prov-stat__v" style={{ fontSize: 12.5 }}>{p.region}</span>
              </div>
              <div className="prov-stat">
                <span className="prov-stat__l">p99 latency</span>
                <span className="prov-stat__v" style={{ color: p.status === 'bad' ? 'var(--bad)' : p.status === 'warn' ? 'var(--warn)' : undefined }}>{p.p99}</span>
              </div>
              <div className="prov-stat">
                <span className="prov-stat__l">Success · 24h</span>
                <span className="prov-stat__v" style={{ color: parseFloat(p.success) > 99 ? 'var(--good)' : parseFloat(p.success) < 95 ? 'var(--bad)' : undefined }}>{p.success}</span>
              </div>
              <div className="prov-stat">
                <span className="prov-stat__l">Models</span>
                <span className="prov-stat__v">{p.models}</span>
              </div>
              <div className="prov-stat">
                <span className="prov-stat__l">Spend MTD</span>
                <span className="prov-stat__v">{p.spend}</span>
              </div>
            </div>
            {p.failover ? (
              <div className="prov-card__foot" style={{ background: 'var(--bad-soft)' }}>
                <span style={{ color: 'var(--bad)', fontWeight: 500 }}>⚠ {p.failoverMsg}</span>
                <span className="muted">{p.failoverTo}</span>
                <button className="btn btn--sm" style={{ marginLeft: 'auto' }}>Investigate</button>
              </div>
            ) : (
              <div className="prov-card__foot">
                <span>{p.authLabel}</span>
                <span className="mono">{p.authValue}</span>
                <span style={{ marginLeft: 'auto' }} className="muted">{p.rotated}</span>
              </div>
            )}
          </div>
        ))}
      </div>

      <style>{`
        .prov {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: var(--gap-card);
          margin-top: 16px;
        }
        .prov-card { background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius-3); overflow: hidden; }
        .prov-card__head { display:flex; align-items:center; gap:12px; padding: 14px 16px; border-bottom: 1px solid var(--rule); }
        .prov-logo { width: 36px; height: 36px; border-radius: 8px; display:grid; place-items:center; color:#fff; font-weight: 700; font-size: 13px; flex-shrink: 0; }
        .prov-card__body { padding: 14px 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px 14px; }
        .prov-stat { display:flex; flex-direction:column; gap:2px; }
        .prov-stat__l { font-size: 10.5px; color: var(--fg-2); text-transform: uppercase; letter-spacing: 0.04em; font-weight: 500; }
        .prov-stat__v { font-size: 14.5px; font-weight: 600; font-variant-numeric: tabular-nums; }
        .prov-card__foot { padding: 10px 16px; border-top: 1px solid var(--rule); background: var(--surface-2); display:flex; align-items:center; gap: 8px; font-size: 11.5px; color: var(--fg-2); }
        .prov-card__foot .mono { color: var(--fg-1); }
      `}</style>
    </section>
  );
}
