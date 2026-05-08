'use client';

import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

const BASE = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

type GuardrailAction = 'block' | 'flag' | 'redact' | 'rewrite' | 'truncate' | 'route';
type AppliesTo = 'input' | 'output' | 'both';
type Severity = 'low' | 'medium' | 'high' | 'critical';

interface Guardrail {
  id: string;
  name: string;
  description: string | null;
  type: string;
  applies_to: AppliesTo;
  action: GuardrailAction;
  severity: Severity;
  priority: number;
  config: Record<string, unknown>;
  enabled: boolean;
  version: number;
  team_id: string | null;
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
  hits_24h: number;
  blocks_24h: number;
}

interface Summary {
  active_count: number;
  input_count: number;
  output_count: number;
  both_count: number;
  hits_24h: number;
  blocked_24h: number;
}

interface HitRow {
  id: string;
  created_at: string;
  guardrail_type: string;
  input_or_output: string;
  action_taken: string;
  severity: string;
  match_count: number;
  redacted_excerpt: string | null;
  request_id: string | null;
  model: string | null;
  team_name: string | null;
}

function actionPill(a: GuardrailAction) {
  const cls: Record<GuardrailAction, string> = {
    block: 'pill--bad', flag: 'pill--warn', redact: 'pill--info',
    rewrite: 'pill--info', truncate: 'pill--info', route: 'pill--info',
  };
  return <span className={`pill ${cls[a]}`}>{a}</span>;
}

function severityDot(s: Severity) {
  const color: Record<Severity, string> = {
    low: 'var(--fg-3)', medium: 'var(--warn)', high: 'var(--bad)', critical: '#c026d3',
  };
  return <span style={{ display: 'inline-block', width: 7, height: 7, borderRadius: '50%', background: color[s], marginRight: 4 }} />;
}

function fmtTime(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

const NEW_FORM_DEFAULTS = {
  name: '', description: '', type: 'pii_detector',
  applies_to: 'input' as AppliesTo, action: 'block' as GuardrailAction,
  severity: 'high' as Severity, priority: 100,
};

export default function GuardrailsPage() {
  const queryClient = useQueryClient();
  const [showNew, setShowNew] = useState(false);
  const [form, setForm] = useState(NEW_FORM_DEFAULTS);
  const [saving, setSaving] = useState(false);

  const guardrailsQ = useQuery<Guardrail[]>({
    queryKey: ['guardrails'],
    queryFn: () => fetch(`${BASE}/guardrails`).then(r => {
      if (!r.ok) throw new Error(`Failed: ${r.status}`);
      return r.json();
    }),
  });

  const summaryQ = useQuery<Summary>({
    queryKey: ['guardrails-summary'],
    queryFn: () => fetch(`${BASE}/guardrails/summary`).then(r => {
      if (!r.ok) throw new Error(`Failed: ${r.status}`);
      return r.json();
    }),
  });

  const hitsQ = useQuery<HitRow[]>({
    queryKey: ['guardrail-hits'],
    queryFn: () => fetch(`${BASE}/guardrails/hits?limit=8`).then(r => {
      if (!r.ok) throw new Error(`Failed: ${r.status}`);
      return r.json();
    }),
    refetchInterval: 30_000,
  });

  async function toggleEnabled(g: Guardrail) {
    await fetch(`${BASE}/guardrails/${g.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !g.enabled }),
    });
    queryClient.invalidateQueries({ queryKey: ['guardrails'] });
    queryClient.invalidateQueries({ queryKey: ['guardrails-summary'] });
  }

  async function handleDelete(g: Guardrail) {
    if (!confirm(`Delete guardrail "${g.name}"?`)) return;
    await fetch(`${BASE}/guardrails/${g.id}`, { method: 'DELETE' });
    queryClient.invalidateQueries({ queryKey: ['guardrails'] });
    queryClient.invalidateQueries({ queryKey: ['guardrails-summary'] });
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await fetch(`${BASE}/guardrails`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, config: {} }),
      });
      if (!res.ok) { alert(`Failed: ${res.status}`); return; }
      queryClient.invalidateQueries({ queryKey: ['guardrails'] });
      queryClient.invalidateQueries({ queryKey: ['guardrails-summary'] });
      setShowNew(false);
      setForm(NEW_FORM_DEFAULTS);
    } finally {
      setSaving(false);
    }
  }

  const guardrails = guardrailsQ.data ?? [];
  const summary = summaryQ.data;
  const hits = hitsQ.data ?? [];

  const inputRules = guardrails.filter(g => g.applies_to === 'input' || g.applies_to === 'both');
  const outputRules = guardrails.filter(g => g.applies_to === 'output' || g.applies_to === 'both');

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Guardrails</h1>
          <p className="page__sub">
            {summary
              ? `${summary.active_count} active · ${summary.input_count} input · ${summary.output_count} output · evaluated on every request`
              : 'Loading…'}
          </p>
        </div>
        <div className="page__actions">
          <button className="btn btn--primary" onClick={() => setShowNew(true)}>+ New guardrail</button>
        </div>
      </div>

      {/* KPI strip */}
      <div className="kpi-grid" style={{ marginBottom: 18 }}>
        <div className="kpi">
          <div className="kpi__label">Active</div>
          <div className="kpi__value">{summary?.active_count ?? '—'}</div>
          <div className="kpi__delta flat">
            {summary ? `${summary.input_count} input · ${summary.output_count} output` : ''}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Hits · 24h</div>
          <div className="kpi__value">{summary?.hits_24h?.toLocaleString() ?? '—'}</div>
          <div className="kpi__delta flat">all types</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Blocked · 24h</div>
          <div className="kpi__value">{summary?.blocked_24h?.toLocaleString() ?? '—'}</div>
          <div className="kpi__delta flat">
            {summary && summary.hits_24h > 0
              ? `${Math.round((summary.blocked_24h / summary.hits_24h) * 100)}% of hits`
              : 'of hits'}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Total rules</div>
          <div className="kpi__value">{guardrails.length}</div>
          <div className="kpi__delta flat">{guardrails.filter(g => !g.enabled).length} disabled</div>
        </div>
      </div>

      {guardrailsQ.isError && (
        <div className="pill pill--bad" style={{ marginBottom: 12 }}>
          Failed to load guardrails: {(guardrailsQ.error as Error).message}
        </div>
      )}

      <div className="grid grid--2" style={{ gridTemplateColumns: '1.5fr 1fr', alignItems: 'start' }}>
        {/* Main table */}
        <div className="card">
          <div className="card__head">
            <div className="card__title">Active guardrails</div>
            <div className="card__sub">evaluated in priority order · lower = first</div>
          </div>
          <div className="card__body" style={{ padding: 0 }}>
            {guardrails.length === 0 && !guardrailsQ.isLoading ? (
              <div style={{ padding: '32px 20px', color: 'var(--fg-2)', textAlign: 'center' }}>
                No guardrails configured.
              </div>
            ) : (
              <table className="tbl">
                <thead>
                  <tr>
                    <th style={{ width: 50 }}>Priority</th>
                    <th>Guardrail</th>
                    <th>Stage</th>
                    <th>Action</th>
                    <th>Severity</th>
                    <th className="num">Hits 24h</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {guardrails.map(g => (
                    <tr key={g.id} tabIndex={0} style={{ opacity: g.enabled ? 1 : 0.5 }}>
                      <td className="mono lo" style={{ textAlign: 'center' }}>{g.priority}</td>
                      <td>
                        <div className="cell-2">
                          <span style={{ fontWeight: 500 }}>{g.name}</span>
                          <span className="lo">{g.description ?? g.type}</span>
                        </div>
                      </td>
                      <td><span className="pill">{g.applies_to}</span></td>
                      <td>{actionPill(g.action)}</td>
                      <td>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
                          {severityDot(g.severity)}{g.severity}
                        </span>
                      </td>
                      <td className="num mono">
                        {g.hits_24h > 0
                          ? <span style={{ color: g.blocks_24h > 0 ? 'var(--bad)' : 'var(--warn)' }}>{g.hits_24h}</span>
                          : <span className="muted">0</span>}
                      </td>
                      <td>
                        <button
                          className={`pill ${g.enabled ? 'pill--good' : ''}`}
                          style={{ cursor: 'pointer', border: 'none', background: 'none', padding: 0 }}
                          onClick={() => toggleEnabled(g)}
                          title={g.enabled ? 'Click to disable' : 'Click to enable'}
                        >
                          <span className="dot"></span>{g.enabled ? 'on' : 'off'}
                        </button>
                      </td>
                      <td>
                        <button
                          className="btn btn--sm btn--ghost"
                          onClick={() => handleDelete(g)}
                          title="Delete"
                        >✕</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Right column */}
        <div className="grid" style={{ gap: 18 }}>
          {/* Recent hits */}
          <div className="card">
            <div className="card__head">
              <div className="card__title">Recent hits</div>
              <div className="card__sub">last 30s auto-refresh</div>
            </div>
            <div className="card__body" style={{ padding: 0 }}>
              {hits.length === 0 ? (
                <div style={{ padding: '20px 16px', color: 'var(--fg-2)', fontSize: 13 }}>
                  No hits recorded yet. Hits are logged when guardrails fire on real requests.
                </div>
              ) : (
                <table className="tbl">
                  <tbody>
                    {hits.map(h => (
                      <tr key={h.id}>
                        <td>{actionPill(h.action_taken as GuardrailAction)}</td>
                        <td>
                          <div className="cell-2">
                            <span>{h.guardrail_type.replace(/_/g, ' ')}</span>
                            <span className="lo mono">{h.request_id ? `${h.request_id.slice(0, 8)}…` : h.team_name ?? '—'}</span>
                          </div>
                        </td>
                        <td className="mono lo num">{fmtTime(h.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* Coverage breakdown */}
          <div className="card">
            <div className="card__head"><div className="card__title">Coverage</div></div>
            <div className="card__body">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 12, color: 'var(--fg-2)' }}>
                    <span>Input rules</span>
                    <span>{inputRules.filter(g => g.enabled).length} active</span>
                  </div>
                  <div style={{ height: 6, borderRadius: 3, background: 'var(--surface-soft)', overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${guardrails.length ? (inputRules.filter(g => g.enabled).length / guardrails.length) * 100 : 0}%`, background: 'var(--sc-blue)', borderRadius: 3 }} />
                  </div>
                </div>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 12, color: 'var(--fg-2)' }}>
                    <span>Output rules</span>
                    <span>{outputRules.filter(g => g.enabled).length} active</span>
                  </div>
                  <div style={{ height: 6, borderRadius: 3, background: 'var(--surface-soft)', overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${guardrails.length ? (outputRules.filter(g => g.enabled).length / guardrails.length) * 100 : 0}%`, background: 'var(--sc-teal)', borderRadius: 3 }} />
                  </div>
                </div>
                {guardrails.length > 0 && (
                  <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {['block', 'flag', 'redact', 'rewrite', 'truncate', 'route'].map(a => {
                      const count = guardrails.filter(g => g.action === a && g.enabled).length;
                      if (!count) return null;
                      return (
                        <span key={a} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11 }}>
                          {actionPill(a as GuardrailAction)}
                          <span className="muted">{count}</span>
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* New guardrail modal */}
      {showNew && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100
        }} onClick={() => setShowNew(false)}>
          <div className="card" style={{ width: 480, maxWidth: '90vw' }} onClick={e => e.stopPropagation()}>
            <div className="card__head" style={{ display: 'flex', justifyContent: 'space-between' }}>
              <div className="card__title">New guardrail</div>
              <button className="icon-btn" onClick={() => setShowNew(false)}>✕</button>
            </div>
            <div className="card__body">
              <form onSubmit={handleCreate} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div>
                  <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Name</label>
                  <input
                    className="input" style={{ width: '100%' }}
                    value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                    required placeholder="My guardrail"
                  />
                </div>
                <div>
                  <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Description</label>
                  <input
                    className="input" style={{ width: '100%' }}
                    value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                    placeholder="Optional description"
                  />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div>
                    <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Type</label>
                    <select className="input" style={{ width: '100%' }} value={form.type} onChange={e => setForm(f => ({ ...f, type: e.target.value }))}>
                      {['pii_detector','secrets_scanner','prompt_injection','topic_block','mnpi_detector',
                        'token_budget_cap','output_pii_redactor','citation_check','toxicity_filter',
                        'confidence_floor','custom'].map(t => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Applies to</label>
                    <select className="input" style={{ width: '100%' }} value={form.applies_to} onChange={e => setForm(f => ({ ...f, applies_to: e.target.value as AppliesTo }))}>
                      <option value="input">input</option>
                      <option value="output">output</option>
                      <option value="both">both</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Action</label>
                    <select className="input" style={{ width: '100%' }} value={form.action} onChange={e => setForm(f => ({ ...f, action: e.target.value as GuardrailAction }))}>
                      {['block','flag','redact','rewrite','truncate','route'].map(a => (
                        <option key={a} value={a}>{a}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Severity</label>
                    <select className="input" style={{ width: '100%' }} value={form.severity} onChange={e => setForm(f => ({ ...f, severity: e.target.value as Severity }))}>
                      {['low','medium','high','critical'].map(s => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: 12, color: 'var(--fg-2)', display: 'block', marginBottom: 4 }}>Priority (lower = first)</label>
                    <input
                      className="input" type="number" style={{ width: '100%' }}
                      value={form.priority} onChange={e => setForm(f => ({ ...f, priority: parseInt(e.target.value) || 100 }))}
                    />
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
                  <button type="button" className="btn" onClick={() => setShowNew(false)}>Cancel</button>
                  <button type="submit" className="btn btn--primary" disabled={saving}>
                    {saving ? 'Creating…' : 'Create guardrail'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
