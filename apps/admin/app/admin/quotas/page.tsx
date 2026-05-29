'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../_components/PageStates';
import { apiFetch } from '../../../lib/apiClient';

interface Team {
  id: string;
  name: string;
  monthly_budget_usd: number | null;
  spent_usd: number;
  member_count?: number;
}

interface OrgBudget {
  monthly_budget_usd: number | null;
  budget_alert_pct: number;
  budget_action: 'alert' | 'block';
  spent_usd?: number;
}

interface BudgetStatus {
  spent_usd: number;
  monthly_budget_usd: number | null;
  pct_used: number;
  projected_usd?: number;
  teams_over_threshold?: number;
}

const BASE = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

function fmtUsd(v: number | null | undefined) {
  if (v == null) return '—';
  if (v >= 1000) return `€${(v / 1000).toFixed(1)}k`;
  return `€${v.toFixed(0)}`;
}

function pctBar(pct: number, warn: boolean) {
  return (
    <div style={{ height: 8, background: 'rgba(255,255,255,0.06)', borderRadius: 4, overflow: 'hidden' }}>
      <div style={{
        height: '100%',
        width: `${Math.min(100, pct)}%`,
        borderRadius: 4,
        background: warn
          ? 'linear-gradient(90deg,#f59e0b,#dc2626)'
          : 'linear-gradient(90deg,#5eead4,#2dd4bf)',
      }} />
    </div>
  );
}

function OrgBudgetEditor({ budget, onSaved }: { budget: OrgBudget; onSaved: () => void }) {
  const [monthly, setMonthly] = useState(String(budget.monthly_budget_usd ?? ''));
  const [alertPct, setAlertPct] = useState(String(budget.budget_alert_pct ?? 80));
  const [action, setAction] = useState<'alert' | 'block'>(budget.budget_action ?? 'alert');
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');

  async function save() {
    setSaving(true);
    setMsg('');
    try {
      const res = await fetch(`${BASE}/org/budget`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          monthly_budget_usd: monthly ? parseFloat(monthly) : null,
          budget_alert_pct: parseFloat(alertPct),
          budget_action: action,
        }),
      });
      if (res.ok) {
        setMsg('Saved');
        onSaved();
      } else {
        const err = await res.json().catch(() => ({}));
        setMsg(err?.detail ?? 'Error saving');
      }
    } catch {
      setMsg('Error saving');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card" style={{ marginBottom: 18 }}>
      <div className="card__head">
        <div className="card__title">Org-level budget</div>
        <div className="card__sub">Monthly cap, alert threshold, and enforcement action</div>
      </div>
      <div className="card__body" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
        <div>
          <label style={{ display: 'block', fontSize: 11, color: 'var(--fg-2)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Monthly budget (USD)</label>
          <input
            type="number"
            className="search"
            value={monthly}
            onChange={e => setMonthly(e.target.value)}
            placeholder="e.g. 42000"
            style={{ width: '100%', height: 32, padding: '0 10px', fontSize: 13 }}
          />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 11, color: 'var(--fg-2)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Alert threshold (%)</label>
          <input
            type="number"
            className="search"
            value={alertPct}
            onChange={e => setAlertPct(e.target.value)}
            min={1} max={100}
            style={{ width: '100%', height: 32, padding: '0 10px', fontSize: 13 }}
          />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: 11, color: 'var(--fg-2)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Enforcement action</label>
          <select
            value={action}
            onChange={e => setAction(e.target.value as 'alert' | 'block')}
            style={{ width: '100%', height: 32, padding: '0 8px', fontSize: 13, background: 'var(--surface-soft)', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-1)' }}
          >
            <option value="alert">Alert only</option>
            <option value="block">Block requests</option>
          </select>
        </div>
        <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: 10 }}>
          <button className="btn btn--primary btn--sm" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Save budget'}
          </button>
          {msg && <span style={{ fontSize: 12, color: msg === 'Saved' ? 'var(--good)' : 'var(--bad)' }}>{msg}</span>}
        </div>
      </div>
    </div>
  );
}

export default function QuotasPage() {
  const qc = useQueryClient();

  const { data: orgBudget, isLoading: loadingOrg, isError: errOrg, error: orgErr, refetch: refetchOrg } = useQuery<OrgBudget>({
    queryKey: ['org-budget'],
    queryFn: () => apiFetch('/org/budget'),
  });

  const { data: teams, isLoading: loadingTeams, isError: errTeams, error: teamsErr, refetch: refetchTeams } = useQuery<Team[]>({
    queryKey: ['teams'],
    queryFn: () => apiFetch('/nodes?type=team'),
  });

  const { data: budgetStatus } = useQuery<BudgetStatus>({
    queryKey: ['budget-status'],
    queryFn: () => fetch(`${BASE}/budget/status`).then(r => r.json()),
  });

  if (loadingOrg || loadingTeams) return <section className="page"><LoadingState rows={7} /></section>;
  if (errOrg) return <section className="page"><ErrorState error={orgErr as Error} retry={() => refetchOrg()} /></section>;
  if (errTeams) return <section className="page"><ErrorState error={teamsErr as Error} retry={() => refetchTeams()} /></section>;

  const allTeams = teams ?? [];
  const orgCap = orgBudget?.monthly_budget_usd;
  const spentMtd = budgetStatus?.spent_usd ?? 0;
  const projectedEom = budgetStatus?.projected_usd;
  const teamsOverThreshold = budgetStatus?.teams_over_threshold ?? 0;

  function onOrgSaved() {
    qc.invalidateQueries({ queryKey: ['org-budget'] });
    qc.invalidateQueries({ queryKey: ['budget-status'] });
  }

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Quotas &amp; budgets</h1>
          <p className="page__sub">
            May 2026 · org cap {orgCap != null ? fmtUsd(orgCap) : 'not set'}
            {projectedEom != null ? ` · projected ${fmtUsd(projectedEom)}` : ''}
          </p>
        </div>
        <div className="page__actions">
          <button className="btn" onClick={() => { refetchOrg(); refetchTeams(); qc.invalidateQueries({ queryKey: ['budget-status'] }); }}>Refresh</button>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 18 }}>
        <div className="kpi">
          <div className="kpi__label">Org spend · MTD</div>
          <div className="kpi__value">{fmtUsd(spentMtd)}</div>
          {orgCap && <div className="kpi__delta flat">{Math.round(spentMtd / orgCap * 100)}% of cap</div>}
        </div>
        {projectedEom != null && (
          <div className="kpi">
            <div className="kpi__label">Projected · EOM</div>
            <div className="kpi__value">{fmtUsd(projectedEom)}</div>
            {orgCap && <div className="kpi__delta flat">{Math.round(projectedEom / orgCap * 100)}% of cap</div>}
          </div>
        )}
        <div className="kpi">
          <div className="kpi__label">Teams over {orgBudget?.budget_alert_pct ?? 80}%</div>
          <div className="kpi__value" style={{ color: teamsOverThreshold > 0 ? 'var(--warn)' : undefined }}>{teamsOverThreshold}</div>
          <div className="kpi__delta flat">{teamsOverThreshold > 0 ? 'needs attention' : 'all within budget'}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Teams</div>
          <div className="kpi__value">{allTeams.length}</div>
          <div className="kpi__delta flat">{allTeams.filter(t => t.monthly_budget_usd != null).length} with budget set</div>
        </div>
      </div>

      {orgBudget && <OrgBudgetEditor budget={orgBudget} onSaved={onOrgSaved} />}

      <div className="card" style={{ marginBottom: 18 }}>
        <div className="card__head">
          <div className="card__title">Per-team budgets · May 2026</div>
          <div className="card__sub">cost cap and current spend</div>
        </div>
        <div className="card__body" style={{ padding: 0 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Team</th><th>Cap / month</th><th>MTD spend</th>
                <th style={{ width: '34%' }}>Usage</th><th></th>
              </tr>
            </thead>
            <tbody>
              {allTeams.map(q => {
                const cap = q.monthly_budget_usd;
                const spent = q.spent_usd ?? 0;
                const pct = cap ? Math.round(spent / cap * 100) : 0;
                const warn = cap != null && pct >= (orgBudget?.budget_alert_pct ?? 80);
                return (
                  <tr key={q.id} tabIndex={0} style={{ cursor: 'pointer' }}>
                    <td>
                      <div className="cell-2">
                        <span style={{ fontWeight: 500 }}>{q.name}</span>
                        {q.member_count != null && <span className="lo">{q.member_count} members</span>}
                      </div>
                    </td>
                    <td className="mono">{fmtUsd(cap)}</td>
                    <td className="mono">{fmtUsd(spent)}</td>
                    <td>
                      {cap != null ? (
                        <>
                          {pctBar(pct, warn)}
                          <div className="lo mono" style={{ marginTop: 4 }}>{pct}% of cap</div>
                        </>
                      ) : (
                        <span className="muted" style={{ fontSize: 12 }}>no cap set</span>
                      )}
                    </td>
                    <td><button className="btn btn--sm">Adjust</button></td>
                  </tr>
                );
              })}
              {allTeams.length === 0 && (
                <tr><td colSpan={5} style={{ textAlign: 'center', color: 'var(--fg-2)', padding: 24 }}>No teams found</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid--2" style={{ gridTemplateColumns: '1fr 1fr', alignItems: 'start' }}>
        <div className="card">
          <div className="card__head"><div className="card__title">Forecast vs cap</div><div className="card__sub">org spend, May 2026</div></div>
          <div className="card__body">
            <svg viewBox="0 0 320 110" width="100%" height="110" preserveAspectRatio="none" style={{ display: 'block' }}>
              <defs>
                <linearGradient id="grQ" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0" stopColor="#2dd4bf" stopOpacity="0.55"/>
                  <stop offset="1" stopColor="#2dd4bf" stopOpacity="0"/>
                </linearGradient>
              </defs>
              <line x1="0" x2="320" y1="20" y2="20" stroke="#dc2626" strokeDasharray="4 4" strokeWidth="1"/>
              <text x="316" y="16" fontSize="9" fill="#dc2626" textAnchor="end">cap {fmtUsd(orgCap)}</text>
              <path d="M0,95 L52,80 L104,68 L156,56 L208,46 L260,38 L320,28 L320,110 L0,110 Z" fill="url(#grQ)"/>
              <path d="M0,95 L52,80 L104,68 L156,56 L208,46 L260,38 L320,28" fill="none" stroke="#5eead4" strokeWidth="1.6"/>
              <circle cx="104" cy="68" r="3" fill="#5eead4"/>
              <text x="108" y="65" fontSize="9" fill="#94a3b8">today {fmtUsd(spentMtd)}</text>
            </svg>
            <div className="muted" style={{ fontSize: 12, marginTop: 6, display: 'flex', justifyContent: 'space-between' }}>
              <span>1 May</span><span>16 May</span><span>31 May</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
