'use client';

import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { LoadingState, ErrorState, EmptyState } from '../_components/PageStates';

const BASE = 'http://localhost:8005';

interface Team {
  id: string;
  slug: string;
  name: string;
  created_at: string;
  monthly_budget_usd: number | null;
  budget_alert_pct: number;
  budget_action: string;
}

interface DashboardStat {
  team_name: string;
  request_count: number | null;
  total_tokens: number | null;
  total_cost_usd: number | null;
  cache_hit_pct: number | null;
}

interface TeamRow extends Team {
  stat: DashboardStat | null;
}

const COLORS = ['#083EA7','#1D958E','#4B17B6','#FB9B2A','#9D2E7B','#0A7BD7','#1A1D31','#EF3E4A'];
function avatarColor(seed: string): string {
  let h = 0;
  for (const c of seed) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return COLORS[h % COLORS.length];
}

function budgetPct(team: Team, stat: DashboardStat | null): number {
  if (!stat || !team.monthly_budget_usd || stat.total_cost_usd == null) return 0;
  return Math.min(Math.round((stat.total_cost_usd / team.monthly_budget_usd) * 100), 100);
}

function statusPill(pct: number) {
  if (pct >= 100) return <span className="pill pill--bad"><span className="dot"></span>Frozen</span>;
  if (pct >= (80)) return <span className="pill pill--warn"><span className="dot"></span>Attention</span>;
  return <span className="pill pill--good"><span className="dot"></span>Active</span>;
}

function alertPill(team: Team, pct: number) {
  if (pct >= team.budget_alert_pct * 100) return <span className="pill pill--warn">budget {pct}%</span>;
  return null;
}

function formatCost(usd: number | null | undefined): string {
  if (usd == null || usd === 0) return '$0.00';
  if (usd < 0.01) return `$${usd.toFixed(6)}`;
  if (usd < 1) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

export default function TeamsPage() {
  const [range, setRange] = useState('24h');
  const queryClient = useQueryClient();

  const teamsQuery = useQuery<Team[]>({
    queryKey: ['teams'],
    queryFn: () => fetch(`${BASE}/teams`).then(r => {
      if (!r.ok) throw new Error(`Failed to fetch teams: ${r.status}`);
      return r.json();
    }),
  });

  const statsQuery = useQuery<DashboardStat[]>({
    queryKey: ['dashboard-stats'],
    queryFn: () => fetch(`${BASE}/dashboard/stats`).then(r => {
      if (!r.ok) throw new Error(`Failed to fetch stats: ${r.status}`);
      return r.json();
    }),
  });

  async function handleNewTeam() {
    const name = window.prompt('Team name:');
    if (!name?.trim()) return;
    const slug = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    const res = await fetch(`${BASE}/teams`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim(), slug }),
    });
    if (!res.ok) {
      window.alert(`Failed to create team: ${res.status}`);
      return;
    }
    queryClient.invalidateQueries({ queryKey: ['teams'] });
  }

  const isLoading = teamsQuery.isLoading || statsQuery.isLoading;
  const isError = teamsQuery.isError || statsQuery.isError;
  const error = teamsQuery.error || statsQuery.error;

  if (isLoading) return <section className="page"><LoadingState rows={13} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => { teamsQuery.refetch(); statsQuery.refetch(); }} /></section>;

  const teams = teamsQuery.data ?? [];
  const stats = statsQuery.data ?? [];

  if (teams.length === 0) return <section className="page"><EmptyState message="No teams found." /></section>;

  const statsMap = new Map<string, DashboardStat>(stats.map(s => [s.team_name, s]));

  const rows: TeamRow[] = teams.map(t => ({
    ...t,
    stat: statsMap.get(t.name) ?? null,
  }));

  const totalSpend = stats.reduce((sum, s) => sum + (s.total_cost_usd ?? 0), 0);

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Teams</h1>
          <p className="page__sub">{teams.length} teams · ${totalSpend.toFixed(2)} month-to-date</p>
        </div>
        <div className="page__actions">
          <button className="btn">Import from Entra</button>
          <button className="btn btn--primary" onClick={handleNewTeam}>+ New team</button>
        </div>
      </div>

      <div className="filters">
        <button className="filter"><span className="lbl">Status</span><span className="val">Active</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Owner</span><span className="val">Any</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Tier</span><span className="val">All</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Spend</span><span className="val">Any</span><span className="caret">▾</span></button>
        <span style={{ flex: 1 }} />
        <div className="seg">
          {['24h','7d','30d','MTD'].map(r => (
            <button key={r} className={range === r ? 'is-active' : undefined} onClick={() => setRange(r)}>{r}</button>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card__body" style={{ padding: 0 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th style={{ width: 30 }}><input type="checkbox" /></th>
                <th>Team</th>
                <th>Members</th>
                <th>API keys</th>
                <th className="num">Requests (24h)</th>
                <th className="num">Spend (MTD)</th>
                <th className="num">Cache hit</th>
                <th>Budget</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(t => {
                const pct = budgetPct(t, t.stat);
                const cacheHit = t.stat?.cache_hit_pct != null ? Math.round(t.stat.cache_hit_pct) : 0;
                const budgetColor = pct >= 80 ? 'var(--bad)' : pct >= 60 ? 'var(--warn)' : 'var(--good)';
                const hitColor = cacheHit >= 30 ? 'var(--good)' : cacheHit >= 15 ? 'var(--warn)' : 'var(--bad)';
                return (
                  <tr
                    key={t.id}
                    className="is-row-link"
                    style={{ cursor: 'pointer' }}
                    onClick={() => { window.location.href = `/admin/teams/${t.id}`; }}
                    onKeyDown={e => { if (e.key === 'Enter') window.location.href = `/admin/teams/${t.id}`; }}
                    tabIndex={0}
                  >
                    <td><input type="checkbox" onClick={e => e.stopPropagation()} /></td>
                    <td>
                      <div className="cell-2">
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: avatarColor(t.name) }}></span>
                          <Link
                            href={`/admin/teams/${t.id}`}
                            style={{ fontWeight: 500 }}
                            onClick={e => e.stopPropagation()}
                          >{t.name}</Link>
                          {alertPill(t, pct)}
                        </div>
                        <span className="lo mono">{t.slug}</span>
                      </div>
                    </td>
                    <td><span className="muted">—</span></td>
                    <td><span className="tag mono">—</span></td>
                    <td className="num mono">{t.stat?.request_count != null ? t.stat.request_count.toLocaleString() : '—'}</td>
                    <td className="num mono" style={{ fontWeight: 500 }}>{t.stat ? formatCost(t.stat.total_cost_usd) : '—'}</td>
                    <td className="num">
                      {t.stat ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
                          <span className="mono">{cacheHit}%</span>
                          <span style={{ display: 'inline-block', width: 38, height: 4, background: 'var(--surface-soft)', borderRadius: 2, position: 'relative', overflow: 'hidden' }}>
                            <span style={{ position: 'absolute', inset: `0 ${100 - cacheHit}% 0 0`, background: hitColor, borderRadius: 2 }}></span>
                          </span>
                        </div>
                      ) : <span className="muted">—</span>}
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ display: 'inline-block', width: 64, height: 4, background: 'var(--surface-soft)', borderRadius: 2, position: 'relative', overflow: 'hidden' }}>
                          <span style={{ position: 'absolute', inset: `0 ${100 - pct}% 0 0`, background: budgetColor, borderRadius: 2 }}></span>
                        </span>
                        <span className="mono" style={{ fontSize: 11.5, color: 'var(--fg-2)' }}>
                          {t.monthly_budget_usd ? `${pct}%` : '—'}
                        </span>
                      </div>
                    </td>
                    <td>{statusPill(pct)}</td>
                    <td><button className="btn btn--sm btn--ghost" onClick={e => e.stopPropagation()}>⋯</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
