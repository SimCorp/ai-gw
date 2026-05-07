'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { LoadingState, ErrorState, EmptyState } from '../_components/PageStates';
import { SKILLS_DATA } from '../_mocks/data';

type Skill = typeof SKILLS_DATA[number];

function statusPill(s: Skill['status']) {
  if (s === 'published') return <span className="pill pill--good"><span className="dot"></span>published</span>;
  if (s === 'review') return <span className="pill pill--warn"><span className="dot"></span>review</span>;
  if (s === 'frozen') return <span className="pill pill--info"><span className="dot"></span>frozen</span>;
  if (s === 'blocked') return <span className="pill pill--bad"><span className="dot"></span>blocked</span>;
  return <span className="pill pill--warn"><span className="dot"></span>draft</span>;
}

export default function SkillsPage() {
  const [filter, setFilter] = useState('All');

  const { data, isLoading, isError, error, refetch } = useQuery<Skill[]>({
    queryKey: ['skills'],
    queryFn: () => fetch('/api/v1/skills').then(r => r.json()),
  });

  if (isLoading) return <section className="page"><LoadingState rows={7} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;

  const rows = data ?? SKILLS_DATA;

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Skills catalog</h1>
          <p className="page__sub">22 published · 4 awaiting review · publish rights gated by team role</p>
        </div>
        <div className="page__actions">
          <button className="btn">Publish-rights matrix</button>
          <button className="btn btn--primary">+ Add skill</button>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 18 }}>
        <div className="kpi"><div className="kpi__label">Published</div><div className="kpi__value">22</div><div className="kpi__delta up">▲ 3 this month</div></div>
        <div className="kpi"><div className="kpi__label">Pending</div><div className="kpi__value">4</div><div className="kpi__delta flat">awaiting review</div></div>
        <div className="kpi"><div className="kpi__label">Frozen</div><div className="kpi__value">2</div><div className="kpi__delta flat">no new versions allowed</div></div>
        <div className="kpi"><div className="kpi__label">Uses · 7d</div><div className="kpi__value">8.4<span className="unit">k</span></div><div className="kpi__delta up">▲ 12.4%</div></div>
      </div>

      <div className="filters">
        <button className="filter"><span className="lbl">Visibility</span><span className="val">Org</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Status</span><span className="val">All</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Owner team</span><span className="val">Any</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Model</span><span className="val">Any</span><span className="caret">▾</span></button>
        <span style={{ flex: 1 }} />
        <div className="seg">
          {['All','Published','Draft','Frozen'].map(f => (
            <button key={f} className={filter === f ? 'is-active' : undefined} onClick={() => setFilter(f)}>{f}</button>
          ))}
        </div>
      </div>

      {rows.length === 0 ? <EmptyState message="No skills found." /> : (
        <div className="card">
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 30 }}><input type="checkbox" /></th>
                  <th>Skill</th><th>Owner team</th><th>Version</th><th>Model</th>
                  <th>Tools</th><th className="num">Uses (7d)</th><th>Visibility</th><th>Status</th><th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map(s => (
                  <tr key={s.name} tabIndex={0} style={{ cursor: 'pointer' }} onKeyDown={e => { if (e.key === 'Enter') {} }}>
                    <td><input type="checkbox" /></td>
                    <td><div className="cell-2"><span style={{ fontWeight: 500 }}>{s.name}</span><span className="lo">{s.desc}</span></div></td>
                    <td>{s.owner}</td>
                    <td><span className="mono">{s.version}</span></td>
                    <td className="mono">{s.model}</td>
                    <td className="num mono">{s.tools}</td>
                    <td className="num mono">{s.uses7d}</td>
                    <td><span className="pill">{s.visibility}</span></td>
                    <td>{statusPill(s.status)}</td>
                    <td><button className="btn btn--sm">{s.status === 'review' || s.status === 'blocked' ? 'Review' : 'Manage'}</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p className="muted" style={{ fontSize: 12, marginTop: 14 }}>
        Skills marked <span className="pill pill--info" style={{ display: 'inline-flex' }}>frozen</span> can still be invoked but cannot publish new versions.
        Use this for skills under regulatory review.
      </p>
    </section>
  );
}
