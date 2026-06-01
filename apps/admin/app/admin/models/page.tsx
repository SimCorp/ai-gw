'use client';

import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { LoadingState, ErrorState, EmptyState } from '../_components/PageStates';

const BASE = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

interface Model {
  id: string;
  model_id: string;
  name: string;
  provider: string;
  enabled: boolean;
  created_at: string;
}

const PROVIDER_COLORS: Record<string, string> = {
  anthropic: '#D97757',
  openai: '#10A37F',
  google: '#4285F4',
  gemini: '#4285F4',
  'github-copilot': '#24292F',
  azure: '#0078D4',
  'github-models': '#1A1D31',
  ollama: '#1D958E',
};

const PROVIDER_OPTIONS = [
  'anthropic',
  'openai',
  'github-copilot',
  'azure',
  'github-models',
  'google',
  'ollama',
  'other',
];

function getProviderColor(provider: string): string {
  const key = provider.toLowerCase();
  for (const [k, color] of Object.entries(PROVIDER_COLORS)) {
    if (key.includes(k)) return color;
  }
  return '#888';
}

function enabledPill(enabled: boolean, onClick: () => void) {
  return (
    <span
      className={`pill ${enabled ? 'pill--good' : 'pill--bad'}`}
      style={{ cursor: 'pointer', userSelect: 'none' }}
      onClick={onClick}
      title="Click to toggle"
    >
      <span className="dot"></span>{enabled ? 'enabled' : 'disabled'}
    </span>
  );
}

interface RegisterModalProps {
  onClose: () => void;
  onSaved: () => void;
}

function RegisterModelModal({ onClose, onSaved }: RegisterModalProps) {
  const [form, setForm] = useState({
    name: '',
    model_id: '',
    provider: 'openai',
    enabled: true,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  function set(key: string, value: string | boolean) {
    setForm(prev => ({ ...prev, [key]: value }));
  }

  async function handleSave() {
    if (!form.name.trim() || !form.model_id.trim()) {
      setError('Display name and Model ID are required.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const res = await fetch(BASE + '/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (res.ok) {
        onSaved();
        onClose();
      } else {
        const body = await res.json().catch(() => ({}));
        setError(body?.detail ?? 'Error saving model.');
      }
    } catch {
      setError('Request failed.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--rule)',
        borderRadius: 12, width: 440, padding: 24, display: 'flex',
        flexDirection: 'column', gap: 16,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>Register model</h2>
          <button className="btn btn--sm btn--ghost" onClick={onClose} style={{ padding: '2px 8px' }}>✕</button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--fg-2)' }}>Display name</span>
            <input
              type="text"
              value={form.name}
              onChange={e => set('name', e.target.value)}
              placeholder="e.g. GPT-4o"
              style={{
                height: 32, padding: '0 10px', fontSize: 13,
                background: 'var(--surface-2)', border: '1px solid var(--rule)',
                borderRadius: 6, color: 'var(--fg-1)', outline: 'none',
              }}
            />
          </label>

          <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--fg-2)' }}>Model ID</span>
            <input
              type="text"
              value={form.model_id}
              onChange={e => set('model_id', e.target.value)}
              placeholder="e.g. gpt-4o"
              style={{
                height: 32, padding: '0 10px', fontSize: 13,
                background: 'var(--surface-2)', border: '1px solid var(--rule)',
                borderRadius: 6, color: 'var(--fg-1)', outline: 'none',
                fontFamily: 'var(--font-mono)',
              }}
            />
          </label>

          <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--fg-2)' }}>Provider</span>
            <select
              value={form.provider}
              onChange={e => set('provider', e.target.value)}
              style={{
                height: 32, padding: '0 10px', fontSize: 13,
                background: 'var(--surface-2)', border: '1px solid var(--rule)',
                borderRadius: 6, color: 'var(--fg-1)', outline: 'none',
              }}
            >
              {PROVIDER_OPTIONS.map(opt => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          </label>

          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={e => set('enabled', e.target.checked)}
              style={{ width: 14, height: 14 }}
            />
            <span style={{ fontSize: 13, color: 'var(--fg-1)' }}>Enabled</span>
          </label>
        </div>

        {error && <span style={{ fontSize: 12, color: 'var(--bad)' }}>{error}</span>}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button className="btn btn--sm btn--ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn--sm btn--primary" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Register'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ModelsPage() {
  const [search, setSearch] = useState('');
  const [providerFilter, setProviderFilter] = useState('All');
  const [showModal, setShowModal] = useState(false);
  const queryClient = useQueryClient();

  const { data, isLoading, isError, error, refetch } = useQuery<Model[]>({
    queryKey: ['models'],
    queryFn: () => fetch(BASE + '/models').then(r => r.json()),
  });

  async function toggleEnabled(m: Model) {
    try {
      await fetch(`${BASE}/models/${m.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !m.enabled }),
      });
      queryClient.invalidateQueries({ queryKey: ['models'] });
    } catch {
      // silently fail — UI will stay unchanged until next refresh
    }
  }

  if (isLoading) return <section className="page"><LoadingState rows={12} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;

  const allModels = data ?? [];
  const providerSet = Array.from(new Set(allModels.map(m => m.provider))).sort();
  const enabledCount = allModels.filter(m => m.enabled).length;

  const rows = allModels.filter(m => {
    const matchesSearch =
      !search ||
      m.name.toLowerCase().includes(search.toLowerCase()) ||
      m.provider.toLowerCase().includes(search.toLowerCase()) ||
      m.model_id.toLowerCase().includes(search.toLowerCase());
    const matchesProvider = providerFilter === 'All' || m.provider === providerFilter;
    return matchesSearch && matchesProvider;
  });

  return (
    <section className="page">
      {showModal && (
        <RegisterModelModal
          onClose={() => setShowModal(false)}
          onSaved={() => { refetch(); }}
        />
      )}

      <div className="page__head">
        <div>
          <h1 className="page__title">Model registry</h1>
          <p className="page__sub">{allModels.length} models across {providerSet.length} providers · OpenAI-compatible endpoints · LiteLLM-routed</p>
        </div>
        <div className="page__actions">
          <button className="btn" onClick={() => refetch()}>Reload</button>
          <button className="btn btn--primary" onClick={() => setShowModal(true)}>+ Register model</button>
        </div>
      </div>

      <div className="minimet-row" style={{ marginBottom: 18 }}>
        <div className="minimet"><div className="minimet__l">Models</div><div className="minimet__v">{allModels.length}</div></div>
        <div className="minimet"><div className="minimet__l">Enabled</div><div className="minimet__v">{enabledCount}</div></div>
        <div className="minimet"><div className="minimet__l">Disabled</div><div className="minimet__v">{allModels.length - enabledCount}</div></div>
        <div className="minimet"><div className="minimet__l">Providers</div><div className="minimet__v">{providerSet.length}</div></div>
      </div>

      <div className="filters" style={{ marginBottom: 12, gap: 8, alignItems: 'center' }}>
        <div className="seg" style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {['All', ...providerSet].map(prov => (
            <button
              key={prov}
              className={`btn btn--sm ${providerFilter === prov ? 'btn--primary' : 'btn--ghost'}`}
              onClick={() => setProviderFilter(prov)}
              style={{ display: 'flex', alignItems: 'center', gap: 5 }}
            >
              {prov !== 'All' && (
                <span style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: getProviderColor(prov),
                  display: 'inline-block', flexShrink: 0,
                }} />
              )}
              {prov}
            </button>
          ))}
        </div>
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
                  <tr key={m.id} tabIndex={0}>
                    <td><span className="mono" style={{ fontWeight: 500 }}>{m.name}</span></td>
                    <td><span className="mono lo" style={{ fontSize: 12 }}>{m.model_id}</span></td>
                    <td>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                        <span style={{
                          width: 8, height: 8, borderRadius: '50%',
                          background: getProviderColor(m.provider),
                          display: 'inline-block', flexShrink: 0,
                        }} />
                        {m.provider}
                      </span>
                    </td>
                    <td>{enabledPill(m.enabled, () => toggleEnabled(m))}</td>
                    <td className="mono lo" style={{ fontSize: 12 }}>{new Date(m.created_at).toLocaleDateString()}</td>
                    <td></td>
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
