'use client';

import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { LoadingState, ErrorState, EmptyState } from '../_components/PageStates';

const BASE = 'http://localhost:8005';

const EMBEDDING_MODELS = [
  'text-embedding-3-small',
  'text-embedding-3-large',
  'text-embedding-ada-002',
];

interface PolicyRow {
  team_id: string;
  team_name: string;
  team_slug: string;
  policy: TeamPolicy | null;
}

interface TeamPolicy {
  id: string;
  cache_ttl_seconds: number;
  cache_similarity_threshold: number;
  cache_opt_out: boolean;
  embedding_model: string;
  rate_limit_rpm: number;
  allowed_models: string[];
  updated_at: string | null;
}

interface Model {
  id: string;
  name: string;
  model_id: string;
  provider: string;
  enabled: boolean;
}

const DEFAULTS: Omit<TeamPolicy, 'id' | 'updated_at'> = {
  cache_ttl_seconds: 3600,
  cache_similarity_threshold: 0.95,
  cache_opt_out: false,
  embedding_model: 'text-embedding-3-small',
  rate_limit_rpm: 1000,
  allowed_models: [],
};

function formatDate(iso: string | null | undefined) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function formatTtl(secs: number) {
  if (secs >= 86400) return `${secs / 86400}d`;
  if (secs >= 3600) return `${secs / 3600}h`;
  if (secs >= 60) return `${secs / 60}m`;
  return `${secs}s`;
}

// ── Edit modal ──────────────────────────────────────────────────────────────

interface EditModalProps {
  row: PolicyRow;
  models: Model[];
  onClose: () => void;
  onSaved: () => void;
}

function EditModal({ row, models, onClose, onSaved }: EditModalProps) {
  const existing = row.policy;
  const [form, setForm] = useState({
    cache_ttl_seconds: existing?.cache_ttl_seconds ?? DEFAULTS.cache_ttl_seconds,
    cache_similarity_threshold: existing?.cache_similarity_threshold ?? DEFAULTS.cache_similarity_threshold,
    cache_opt_out: existing?.cache_opt_out ?? DEFAULTS.cache_opt_out,
    embedding_model: existing?.embedding_model ?? DEFAULTS.embedding_model,
    rate_limit_rpm: existing?.rate_limit_rpm ?? DEFAULTS.rate_limit_rpm,
    allowed_models: existing?.allowed_models ?? [],
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggleModel = (modelId: string) => {
    setForm(f => ({
      ...f,
      allowed_models: f.allowed_models.includes(modelId)
        ? f.allowed_models.filter(m => m !== modelId)
        : [...f.allowed_models, modelId],
    }));
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`${BASE}/teams/${row.team_id}/policy`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError((body as { detail?: string }).detail ?? `Error ${res.status}`);
        return;
      }
      onSaved();
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const field = (label: string, children: React.ReactNode) => (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: 'block', fontSize: 12.5, color: 'var(--fg-2)', marginBottom: 5 }}>{label}</label>
      {children}
    </div>
  );

  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '7px 10px', fontSize: 13,
    background: 'var(--surface-2)', border: '1px solid var(--rule)',
    borderRadius: 6, color: 'var(--fg-1)', fontFamily: 'inherit',
  };

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--rule)',
        borderRadius: 12, padding: 28, width: 520, maxWidth: '95vw', maxHeight: '90vh', overflowY: 'auto',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: 15 }}>Edit policy — {row.team_name}</h3>
            <div style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: 3 }}>
              {existing ? `Last updated ${formatDate(existing.updated_at)}` : 'No custom policy — using org defaults'}
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 0, cursor: 'pointer', fontSize: 18, color: 'var(--fg-3)' }}>✕</button>
        </div>

        {field('Cache TTL (seconds)', (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="number" min={0} style={{ ...inputStyle, flex: 1 }}
              value={form.cache_ttl_seconds}
              onChange={e => setForm(f => ({ ...f, cache_ttl_seconds: Number(e.target.value) }))}
            />
            <span style={{ fontSize: 12.5, color: 'var(--fg-3)', whiteSpace: 'nowrap' }}>{formatTtl(form.cache_ttl_seconds)}</span>
          </div>
        ))}

        {field('Semantic similarity threshold (0–1)', (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="range" min={0.5} max={1} step={0.01}
              style={{ flex: 1 }}
              value={form.cache_similarity_threshold}
              onChange={e => setForm(f => ({ ...f, cache_similarity_threshold: Number(e.target.value) }))}
            />
            <span style={{ fontSize: 13, fontFamily: 'var(--font-mono, monospace)', width: 40, textAlign: 'right' }}>
              {form.cache_similarity_threshold.toFixed(2)}
            </span>
          </div>
        ))}

        {field('Rate limit (requests / minute)', (
          <input
            type="number" min={1} style={inputStyle}
            value={form.rate_limit_rpm}
            onChange={e => setForm(f => ({ ...f, rate_limit_rpm: Number(e.target.value) }))}
          />
        ))}

        {field('Embedding model', (
          <select
            style={inputStyle}
            value={form.embedding_model}
            onChange={e => setForm(f => ({ ...f, embedding_model: e.target.value }))}
          >
            {EMBEDDING_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        ))}

        {field('Allowed models (empty = all models permitted)', (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 180, overflowY: 'auto' }}>
            {models.filter(m => m.enabled).map(m => (
              <label key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                <input
                  type="checkbox"
                  checked={form.allowed_models.includes(m.model_id)}
                  onChange={() => toggleModel(m.model_id)}
                />
                <span>{m.name}</span>
                <span style={{ fontSize: 11.5, color: 'var(--fg-3)', fontFamily: 'monospace' }}>{m.model_id}</span>
              </label>
            ))}
          </div>
        ))}

        {field('Cache opt-out', (
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
            <input
              type="checkbox"
              checked={form.cache_opt_out}
              onChange={e => setForm(f => ({ ...f, cache_opt_out: e.target.checked }))}
            />
            Disable semantic cache for this team
          </label>
        ))}

        {error && <p style={{ color: 'var(--bad)', fontSize: 12.5, margin: '0 0 12px' }}>{error}</p>}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', paddingTop: 8, borderTop: '1px solid var(--rule)' }}>
          <button className="btn btn--sm btn--ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn--sm btn--primary" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Save policy'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main page ───────────────────────────────────────────────────────────────

export default function PoliciesPage() {
  const [editing, setEditing] = useState<PolicyRow | null>(null);
  const [filter, setFilter] = useState<'All' | 'Custom' | 'Default'>('All');
  const queryClient = useQueryClient();

  const policiesQuery = useQuery<PolicyRow[]>({
    queryKey: ['policies'],
    queryFn: () => fetch(`${BASE}/policies`).then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json(); }),
    refetchInterval: 30_000,
  });

  const modelsQuery = useQuery<Model[]>({
    queryKey: ['models'],
    queryFn: () => fetch(`${BASE}/models`).then(r => r.json()),
    staleTime: 120_000,
  });

  if (policiesQuery.isLoading) return <section className="page"><LoadingState rows={6} /></section>;
  if (policiesQuery.isError) return <section className="page"><ErrorState error={policiesQuery.error as Error} retry={() => policiesQuery.refetch()} /></section>;

  const rows = policiesQuery.data ?? [];
  const models = modelsQuery.data ?? [];

  const customCount = rows.filter(r => r.policy !== null).length;
  const defaultCount = rows.length - customCount;

  const filtered = rows.filter(r => {
    if (filter === 'Custom') return r.policy !== null;
    if (filter === 'Default') return r.policy === null;
    return true;
  });

  const eff = (row: PolicyRow, key: keyof typeof DEFAULTS) =>
    (row.policy?.[key as keyof TeamPolicy] ?? DEFAULTS[key]) as never;

  return (
    <section className="page">
      {editing && (
        <EditModal
          row={editing}
          models={models}
          onClose={() => setEditing(null)}
          onSaved={() => queryClient.invalidateQueries({ queryKey: ['policies'] })}
        />
      )}

      <div className="page__head">
        <div>
          <h1 className="page__title">Policies</h1>
          <p className="page__sub">
            Per-team cache, rate limit, and model allowlist settings.
            {' '}{customCount} team{customCount !== 1 ? 's' : ''} with custom policies · {defaultCount} on org defaults.
          </p>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 18 }}>
        <div className="kpi">
          <div className="kpi__label">Teams</div>
          <div className="kpi__value">{rows.length}</div>
          <div className="kpi__delta flat">total</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Custom policies</div>
          <div className="kpi__value">{customCount}</div>
          <div className="kpi__delta flat">overriding defaults</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Org defaults</div>
          <div className="kpi__value">{defaultCount}</div>
          <div className="kpi__delta flat">using base config</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Default TTL</div>
          <div className="kpi__value">1h</div>
          <div className="kpi__delta flat">3 600 s</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Default RPM</div>
          <div className="kpi__value">1 000</div>
          <div className="kpi__delta flat">per key</div>
        </div>
      </div>

      <div className="filters" style={{ marginBottom: 14 }}>
        <div className="seg">
          {(['All', 'Custom', 'Default'] as const).map(f => (
            <button key={f} className={filter === f ? 'is-active' : undefined} onClick={() => setFilter(f)}>{f}</button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <EmptyState message="No teams match the current filter." />
      ) : (
        <div className="card">
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Team</th>
                  <th>Cache TTL</th>
                  <th>Similarity</th>
                  <th>Cache opt-out</th>
                  <th>Rate limit</th>
                  <th>Allowed models</th>
                  <th>Policy</th>
                  <th>Last updated</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(row => {
                  const hasCustom = row.policy !== null;
                  return (
                    <tr key={row.team_id}>
                      <td>
                        <div className="cell-2">
                          <span style={{ fontWeight: 500 }}>{row.team_name}</span>
                          <span className="lo mono">{row.team_slug}</span>
                        </div>
                      </td>
                      <td className="mono">{formatTtl(eff(row, 'cache_ttl_seconds') as number)}</td>
                      <td className="mono">{(eff(row, 'cache_similarity_threshold') as number).toFixed(2)}</td>
                      <td>
                        {(eff(row, 'cache_opt_out') as boolean)
                          ? <span className="pill pill--warn">opt-out</span>
                          : <span className="muted" style={{ fontSize: 12 }}>enabled</span>}
                      </td>
                      <td className="mono">{(eff(row, 'rate_limit_rpm') as number).toLocaleString()} rpm</td>
                      <td style={{ fontSize: 12 }}>
                        {((eff(row, 'allowed_models') as string[]).length === 0)
                          ? <span className="muted">all models</span>
                          : (eff(row, 'allowed_models') as string[]).join(', ')}
                      </td>
                      <td>
                        {hasCustom
                          ? <span className="pill pill--good"><span className="dot" />custom</span>
                          : <span className="pill"><span className="dot" />default</span>}
                      </td>
                      <td style={{ fontSize: 12, color: 'var(--fg-3)' }}>
                        {formatDate(row.policy?.updated_at)}
                      </td>
                      <td>
                        <button className="btn btn--sm" onClick={() => setEditing(row)}>Edit</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p className="muted" style={{ fontSize: 12, marginTop: 14 }}>
        Policies control per-team cache behaviour, rate limits, and model allowlists.
        {' '}Empty <em>allowed models</em> means all configured models are permitted.
        {' '}Changes are applied immediately via Redis and recorded in the{' '}
        <a href="/admin/audit" style={{ color: 'var(--sc-link)' }}>audit log</a>.
      </p>
    </section>
  );
}
