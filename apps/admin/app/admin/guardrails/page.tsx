'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../_components/PageStates';
import { GUARDRAILS_DATA } from '../_mocks/data';

type Guardrail = typeof GUARDRAILS_DATA[number];

function actionPill(a: Guardrail['action']) {
  if (a === 'block') return <span className="pill pill--bad">block</span>;
  if (a === 'flag') return <span className="pill pill--warn">flag</span>;
  if (a === 'redact') return <span className="pill pill--info">redact</span>;
  if (a === 'rewrite') return <span className="pill pill--info">rewrite</span>;
  if (a === 'truncate') return <span className="pill pill--info">truncate</span>;
  return <span className="pill pill--info">route</span>;
}

export default function GuardrailsPage() {
  const { data, isLoading, isError, error, refetch } = useQuery<Guardrail[]>({
    queryKey: ['guardrails'],
    queryFn: () => fetch('/api/v1/guardrails').then(r => r.json()),
  });

  if (isLoading) return <section className="page"><LoadingState rows={10} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;

  const rows = data ?? GUARDRAILS_DATA;

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Guardrails</h1>
          <p className="page__sub">Input + output filters applied to every request · 4 always-on · 6 conditional · last edited 2d ago by jbach</p>
        </div>
        <div className="page__actions">
          <button className="btn">Test playground</button>
          <button className="btn btn--primary">+ New guardrail</button>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 18 }}>
        <div className="kpi"><div className="kpi__label">Active</div><div className="kpi__value">10</div><div className="kpi__delta flat">4 input · 6 output</div></div>
        <div className="kpi"><div className="kpi__label">Hits · 24h</div><div className="kpi__value">218</div><div className="kpi__delta down">▼ 14% vs prior</div></div>
        <div className="kpi"><div className="kpi__label">Blocked</div><div className="kpi__value">42</div><div className="kpi__delta flat">19% of hits</div></div>
        <div className="kpi"><div className="kpi__label">Avg overhead</div><div className="kpi__value">38<span className="unit">ms</span></div><div className="kpi__delta up">▼ 6 ms post-tune</div></div>
      </div>

      <div className="grid grid--2" style={{ gridTemplateColumns: '1.5fr 1fr', alignItems: 'start' }}>
        <div className="card">
          <div className="card__head">
            <div className="card__title">Active guardrails</div>
            <div className="card__sub">evaluated in order top-to-bottom</div>
          </div>
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 40 }}>#</th><th>Guardrail</th><th>Stage</th>
                  <th>Action</th><th>Scope</th><th className="num">Hits 24h</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(g => (
                  <tr key={g.order} tabIndex={0} style={{ cursor: 'pointer' }} onKeyDown={e => { if (e.key === 'Enter') {} }}>
                    <td className="mono lo">{g.order}</td>
                    <td><div className="cell-2"><span style={{ fontWeight: 500 }}>{g.name}</span><span className="lo">{g.desc}</span></div></td>
                    <td><span className="pill">{g.stage}</span></td>
                    <td>{actionPill(g.action)}</td>
                    <td>{g.scope}</td>
                    <td className="num mono">{g.hits24h}</td>
                    <td><span className="pill pill--good"><span className="dot"></span>on</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="grid" style={{ gap: 18 }}>
          <div className="card">
            <div className="card__head"><div className="card__title">Recent hits</div></div>
            <div className="card__body" style={{ padding: 0 }}>
              <table className="tbl">
                <tbody>
                  <tr><td><span className="pill pill--bad">block</span></td><td><div className="cell-2"><span>PII · client name</span><span className="lo mono">trace 1f04…b2</span></div></td><td className="mono lo num">14:38</td></tr>
                  <tr><td><span className="pill pill--warn">flag</span></td><td><div className="cell-2"><span>Prompt injection</span><span className="lo mono">trace 9a21…ee</span></div></td><td className="mono lo num">14:31</td></tr>
                  <tr><td><span className="pill pill--info">redact</span></td><td><div className="cell-2"><span>Output PII · email</span><span className="lo mono">trace 2c87…41</span></div></td><td className="mono lo num">14:27</td></tr>
                  <tr><td><span className="pill pill--bad">block</span></td><td><div className="cell-2"><span>Trading rec · advice</span><span className="lo mono">trace 5b03…7c</span></div></td><td className="mono lo num">14:18</td></tr>
                  <tr><td><span className="pill pill--warn">flag</span></td><td><div className="cell-2"><span>Hallucinated cite</span><span className="lo mono">trace 0d12…aa</span></div></td><td className="mono lo num">14:09</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <div className="card__head"><div className="card__title">Hit volume · 24h</div></div>
            <div className="card__body">
              <svg viewBox="0 0 320 80" width="100%" height="80" preserveAspectRatio="none" style={{ display: 'block' }}>
                <defs>
                  <linearGradient id="grHit" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0" stopColor="#a855f7" stopOpacity="0.6"/>
                    <stop offset="1" stopColor="#a855f7" stopOpacity="0"/>
                  </linearGradient>
                </defs>
                <path d="M0,55 L13,52 L27,48 L40,44 L53,38 L67,42 L80,30 L93,25 L107,28 L120,32 L133,22 L147,26 L160,18 L173,24 L187,20 L200,30 L213,36 L227,28 L240,22 L253,26 L267,18 L280,15 L293,22 L307,28 L320,36 L320,80 L0,80 Z" fill="url(#grHit)"/>
                <path d="M0,55 L13,52 L27,48 L40,44 L53,38 L67,42 L80,30 L93,25 L107,28 L120,32 L133,22 L147,26 L160,18 L173,24 L187,20 L200,30 L213,36 L227,28 L240,22 L253,26 L267,18 L280,15 L293,22 L307,28 L320,36" fill="none" stroke="#c084fc" strokeWidth="1.5"/>
              </svg>
              <div className="muted" style={{ fontSize: 12, marginTop: 6, display: 'flex', justifyContent: 'space-between' }}>
                <span>00:00</span><span>peak 11:48 · 18 hits</span><span>now</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
