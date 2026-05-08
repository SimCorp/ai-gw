'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { LoadingState, ErrorState, EmptyState } from '../_components/PageStates';

interface Model {
  id: string;
  model_id: string;
  name: string;
  provider: string;
  enabled: boolean;
  created_at: string;
}

function enabledPill(enabled: boolean) {
  if (enabled) return <span className="pill pill--good"><span className="dot"></span>enabled</span>;
  return <span className="pill pill--bad"><span className="dot"></span>disabled</span>;
}

export default function ModelsPage() {
  const [search, setSearch] = useState('');

  const { data, isLoading, isError, error, refetch } = useQuery<Model[]>({
    queryKey: ['models'],
    queryFn: () => fetch('http://localhost:8005/models').then(r => r.json()),
  });

  if (isLoading) return <section className="page"><LoadingState rows={12} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;

  const rows = (data ?? []).filter(m =>
    !search ||
    m.name.toLowerCase().includes(search.toLowerCase()) ||
    m.provider.toLowerCase().includes(search.toLowerCase()) ||
    m.model_id.toLowerCase().includes(search.toLowerCase())
  );

  const enabledCount = (data ?? []).filter(m => m.enabled).length;
  const providerSet = new Set((data ?? []).map(m => m.provider));

  async function registerModel() {
    const model_id = prompt('Model ID (e.g. gpt-4o):');
    if (!model_id) return;
    const name = prompt('Display name:') ?? model_id;
    const provider = prompt('Provider (e.g. openai):') ?? 'openai';
    await fetch('http://localhost:8005/models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id, name, provider, enabled: true }),
    });
    refetch();
  }

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Model registry</h1>
          <p className="page__sub">{(data ?? []).length} models across {providerSet.size} providers · OpenAI-compatible endpoints · LiteLLM-routed</p>
        </div>
        <div className="page__actions">
          <button className="btn" onClick={() => refetch()}>Reload</button>
          <button className="btn btn--primary" onClick={registerModel}>+ Register model</button>
        </div>
      </div>

      <div className="minimet-row" style={{ marginBottom: 18 }}>
        <div className="minimet"><div className="minimet__l">Models</div><div className="minimet__v">{(data ?? []).length}</div></div>
        <div className="minimet"><div className="minimet__l">Enabled</div><div className="minimet__v">{enabledCount}</div></div>
        <div className="minimet"><div className="minimet__l">Disabled</div><div className="minimet__v">{(data ?? []).length - enabledCount}</div></div>
        <div className="minimet"><div className="minimet__l">Providers</div><div className="minimet__v">{providerSet.size}</div></div>
      </div>

      <div className="filters">
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
                  <th>Model</th><th>Model ID</th><th>Provider</th><th>Status</th><th>Registered</th><th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map(m => (
                  <tr key={m.id} tabIndex={0} style={{ cursor: 'pointer' }}>
                    <td><span className="mono" style={{ fontWeight: 500 }}>{m.name}</span></td>
                    <td><span className="mono lo" style={{ fontSize: 12 }}>{m.model_id}</span></td>
                    <td>{m.provider}</td>
                    <td>{enabledPill(m.enabled)}</td>
                    <td className="mono lo" style={{ fontSize: 12 }}>{new Date(m.created_at).toLocaleDateString()}</td>
                    <td><button className="btn btn--sm btn--ghost">⋯</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
