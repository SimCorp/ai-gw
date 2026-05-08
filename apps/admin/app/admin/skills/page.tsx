'use client';

import React, { useState } from 'react';
import { EmptyState } from '../_components/PageStates';

type SkillStatus = 'published' | 'review' | 'frozen' | 'blocked' | 'draft';
type SkillVisibility = 'org' | 'team' | 'draft';

type Skill = {
  name: string;
  desc: string;
  owner: string;
  version: string;
  model: string;
  tools: number;
  uses7d: string;
  visibility: SkillVisibility;
  status: SkillStatus;
};

const SKILLS_DATA: Skill[] = [
  { name: 'Portfolio analyst',    desc: 'portfolio rebalance + drift narrative',         owner: 'platform-research',    version: 'v3.2',      model: 'sonnet-4.5', tools: 4, uses7d: '418', visibility: 'org',   status: 'published' },
  { name: 'PR reviewer · Python', desc: 'enforces SimCorp Python style guide',           owner: 'developer-experience', version: 'v5.1',      model: 'sonnet-4.5', tools: 3, uses7d: '284', visibility: 'org',   status: 'published' },
  { name: 'Filing summarizer',    desc: '10-K, 10-Q, EU prospectus → 6-bullet brief',   owner: 'nordic-research',      version: 'v2.0',      model: 'haiku-4.5',  tools: 2, uses7d: '192', visibility: 'org',   status: 'published' },
  { name: 'Trade ticket validator',desc: 'pre-submit checks against compliance rules',   owner: 'compliance-automation',version: 'v1.0',      model: 'sonnet-4.5', tools: 3, uses7d: '88',  visibility: 'team',  status: 'frozen'    },
  { name: 'SQL → narrative',      desc: 'turns query result into 2-paragraph summary',  owner: 'data-platform',        version: 'v2.7',      model: 'haiku-4.5',  tools: 1, uses7d: '318', visibility: 'org',   status: 'published' },
  { name: 'Anomaly explainer',    desc: 'v2.0-draft — adds Datadog tool',               owner: 'risk-engineering',     version: 'v2.0-draft', model: 'sonnet-4.5', tools: 5, uses7d: '—',  visibility: 'draft', status: 'review'    },
  { name: 'Email drafter · client',desc: 'pulls thread for tone match — flagged: PII risk', owner: 'client-services-ai',version: 'v1.2',   model: 'sonnet-4.5', tools: 2, uses7d: '142', visibility: 'team',  status: 'blocked'   },
];

function statusPill(s: SkillStatus) {
  if (s === 'published') return <span className="pill pill--good"><span className="dot"></span>published</span>;
  if (s === 'review') return <span className="pill pill--warn"><span className="dot"></span>review</span>;
  if (s === 'frozen') return <span className="pill pill--info"><span className="dot"></span>frozen</span>;
  if (s === 'blocked') return <span className="pill pill--bad"><span className="dot"></span>blocked</span>;
  return <span className="pill pill--warn"><span className="dot"></span>draft</span>;
}

export default function SkillsPage() {
  const [filter, setFilter] = useState('All');

  const rows = SKILLS_DATA;

  return (
    <section className="page">
      <div className="pill pill--warn" style={{ marginBottom: 12 }}>Live data not yet available for this page · showing representative data</div>

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
