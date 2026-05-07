'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../_components/PageStates';
import { QUOTAS_DATA } from '../_mocks/data';

type Quota = typeof QUOTAS_DATA[number];

export default function QuotasPage() {
  const { data, isLoading, isError, error, refetch } = useQuery<Quota[]>({
    queryKey: ['quotas'],
    queryFn: () => fetch('/api/v1/quotas').then(r => r.json()),
  });

  if (isLoading) return <section className="page"><LoadingState rows={7} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;

  const rows = data ?? QUOTAS_DATA;

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Quotas &amp; budgets</h1>
          <p className="page__sub">May 2026 · day 6 of 31 · org cap $42,000 · projected $39.8k</p>
        </div>
        <div className="page__actions">
          <button className="btn">Forecast</button>
          <button className="btn btn--primary">+ Set quota</button>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 18 }}>
        <div className="kpi"><div className="kpi__label">Org spend · MTD</div><div className="kpi__value">$8.4<span className="unit">k</span></div><div className="kpi__delta up">▲ 11% vs Apr pace</div></div>
        <div className="kpi"><div className="kpi__label">Projected · EOM</div><div className="kpi__value">$39.8<span className="unit">k</span></div><div className="kpi__delta flat">95% of cap</div></div>
        <div className="kpi"><div className="kpi__label">Teams over 80%</div><div className="kpi__value" style={{ color: 'var(--warn)' }}>1</div><div className="kpi__delta down">research-eu</div></div>
        <div className="kpi"><div className="kpi__label">RPM headroom</div><div className="kpi__value">68<span className="unit">%</span></div><div className="kpi__delta up">healthy</div></div>
      </div>

      <div className="card" style={{ marginBottom: 18 }}>
        <div className="card__head">
          <div className="card__title">Per-team budgets · May 2026</div>
          <div className="card__sub">cost cap, current spend, projected EOM</div>
        </div>
        <div className="card__body" style={{ padding: 0 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Team</th><th>Cap</th><th>MTD</th><th>Projected</th>
                <th style={{ width: '34%' }}>Usage</th><th>RPM / TPM</th><th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(q => (
                <tr key={q.name} tabIndex={0} style={{ cursor: 'pointer' }}>
                  <td><div className="cell-2"><span style={{ fontWeight: 500 }}>{q.name}</span><span className="lo">{q.members} members</span></div></td>
                  <td className="mono">{q.cap}</td>
                  <td className="mono">{q.mtd}</td>
                  <td className="mono" style={{ color: q.warn ? 'var(--warn)' : undefined }}>{q.projected}</td>
                  <td>
                    <div style={{ height: 8, background: 'rgba(255,255,255,0.06)', borderRadius: 4, overflow: 'hidden' }}>
                      <div style={{
                        height: '100%', width: `${q.pct}%`, borderRadius: 4,
                        background: q.warn
                          ? 'linear-gradient(90deg,#f59e0b,#dc2626)'
                          : 'linear-gradient(90deg,#5eead4,#2dd4bf)',
                      }} />
                    </div>
                    <div className="lo mono" style={{ marginTop: 4 }}>{q.pctLabel}</div>
                  </td>
                  <td className="mono lo">{q.rpm} / {q.tpm}</td>
                  <td><button className="btn btn--sm">Adjust</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid--2" style={{ gridTemplateColumns: '1fr 1fr', alignItems: 'start' }}>
        <div className="card">
          <div className="card__head"><div className="card__title">Top spenders · 7d</div></div>
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <tbody>
                <tr><td><div className="cell-2"><span>r.holm@simcorp</span><span className="lo">research-eu</span></div></td><td className="num mono">$842</td></tr>
                <tr><td><div className="cell-2"><span>a.singh@simcorp</span><span className="lo">research-eu</span></div></td><td className="num mono">$610</td></tr>
                <tr><td><div className="cell-2"><span>n.persson@simcorp</span><span className="lo">platform-engineering</span></div></td><td className="num mono">$508</td></tr>
                <tr><td><div className="cell-2"><span>g.olsen@simcorp</span><span className="lo">trading</span></div></td><td className="num mono">$402</td></tr>
                <tr><td><div className="cell-2"><span>m.larsen@simcorp</span><span className="lo">client-services-ai</span></div></td><td className="num mono">$318</td></tr>
              </tbody>
            </table>
          </div>
        </div>
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
              <text x="316" y="16" fontSize="9" fill="#dc2626" textAnchor="end">cap $42k</text>
              <path d="M0,95 L52,80 L104,68 L156,56 L208,46 L260,38 L320,28 L320,110 L0,110 Z" fill="url(#grQ)"/>
              <path d="M0,95 L52,80 L104,68 L156,56 L208,46 L260,38 L320,28" fill="none" stroke="#5eead4" strokeWidth="1.6"/>
              <circle cx="104" cy="68" r="3" fill="#5eead4"/>
              <text x="108" y="65" fontSize="9" fill="#94a3b8">today $8.4k</text>
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
