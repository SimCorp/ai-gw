'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { LoadingState, ErrorState, EmptyState } from '../_components/PageStates';
import { TEAMS_DATA } from '../_mocks/data';

type TeamRow = typeof TEAMS_DATA[number];

const COLORS = ['#083EA7','#1D958E','#4B17B6','#FB9B2A','#9D2E7B','#0A7BD7','#1A1D31','#EF3E4A'];
function avatarColor(seed: string): string {
  let h = 0;
  for (const c of seed) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return COLORS[h % COLORS.length];
}
function initials2(s: string) {
  return s.split(/[-._\s]/).filter(Boolean).slice(0, 2).map(p => p[0]).join('').toUpperCase();
}

function statusPill(t: TeamRow) {
  if (t.status === 'good') return <span className="pill pill--good"><span className="dot"></span>Active</span>;
  if (t.status === 'warn') return <span className="pill pill--warn"><span className="dot"></span>Attention</span>;
  return <span className="pill pill--bad"><span className="dot"></span>Frozen</span>;
}

function alertPill(t: TeamRow) {
  if (t.alert === 'budget') return <span className="pill pill--warn">budget 84%</span>;
  if (t.alert === 'rate') return <span className="pill pill--warn">rate-limited</span>;
  if (t.alert === 'low_hit') return <span className="pill pill--info">low cache</span>;
  if ((t as { isNew?: boolean }).isNew) return <span className="pill pill--info">new</span>;
  if (t.alert === 'frozen') return <span className="pill pill--bad">frozen</span>;
  return null;
}

export default function TeamsPage() {
  const [range, setRange] = useState('24h');

  const { data, isLoading, isError, error, refetch } = useQuery<TeamRow[]>({
    queryKey: ['teams'],
    queryFn: () => fetch('/api/v1/teams').then(r => r.json()),
  });

  if (isLoading) return <section className="page"><LoadingState rows={13} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;
  if (!data || data.length === 0) return <section className="page"><EmptyState message="No teams found." /></section>;

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Teams</h1>
          <p className="page__sub">42 teams · 1,184 active members · $87,420 month-to-date</p>
        </div>
        <div className="page__actions">
          <button className="btn">Import from Entra</button>
          <button className="btn btn--primary">+ New team</button>
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
                <th>Owner</th>
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
              {data.map(t => {
                const budgetColor = t.budgetPct >= 80 ? 'var(--bad)' : t.budgetPct >= 60 ? 'var(--warn)' : 'var(--good)';
                const hitColor = t.cacheHit >= 30 ? 'var(--good)' : t.cacheHit >= 15 ? 'var(--warn)' : 'var(--bad)';
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
                          {alertPill(t)}
                        </div>
                        <span className="lo mono">tm_{t.name.replace(/-/g, '').slice(0, 6)}_xxxx</span>
                      </div>
                    </td>
                    <td><span className="muted">{t.ownerEmail.split('@')[0]}</span></td>
                    <td>
                      <div className="avatar-row">
                        {[0, 1, 2].map(i => (
                          <span key={i} className="avatar avatar--stack" style={{ background: avatarColor(t.name + i) }}>
                            {String.fromCharCode(65 + (i * 3 + t.name.length) % 26)}{String.fromCharCode(65 + (i * 7 + t.name.length) % 26)}
                          </span>
                        ))}
                        {t.members > 3 && (
                          <span className="avatar avatar--stack" style={{ background: 'var(--surface-soft)', color: 'var(--fg-2)', border: '2px solid var(--surface)' }}>+{t.members - 3}</span>
                        )}
                      </div>
                    </td>
                    <td><span className="tag mono">{t.keys}</span></td>
                    <td className="num mono">{t.req24h}</td>
                    <td className="num mono" style={{ fontWeight: 500 }}>{t.spendMtd}</td>
                    <td className="num">
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
                        <span className="mono">{t.cacheHit}%</span>
                        <span style={{ display: 'inline-block', width: 38, height: 4, background: 'var(--surface-soft)', borderRadius: 2, position: 'relative', overflow: 'hidden' }}>
                          <span style={{ position: 'absolute', inset: `0 ${100 - t.cacheHit}% 0 0`, background: hitColor, borderRadius: 2 }}></span>
                        </span>
                      </div>
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ display: 'inline-block', width: 64, height: 4, background: 'var(--surface-soft)', borderRadius: 2, position: 'relative', overflow: 'hidden' }}>
                          <span style={{ position: 'absolute', inset: `0 ${100 - t.budgetPct}% 0 0`, background: budgetColor, borderRadius: 2 }}></span>
                        </span>
                        <span className="mono" style={{ fontSize: 11.5, color: 'var(--fg-2)' }}>{t.budgetPct}%</span>
                      </div>
                    </td>
                    <td>{statusPill(t)}</td>
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
