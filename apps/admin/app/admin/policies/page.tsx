'use client';

import React, { useState } from 'react';
import { EmptyState } from '../_components/PageStates';

type PolicyStatus = 'active' | 'draft';

type Policy = {
  name: string;
  desc: string;
  domain: string;
  scope: string;
  owner: string;
  version: string;
  hits7d: string;
  status: PolicyStatus;
};

const POLICIES_DATA: Policy[] = [
  { name: 'Allowed models',               desc: 'sonnet-4.5, haiku-4.5 · vendor allowlist', domain: 'model',     scope: 'org',          owner: 'jbach',        version: 'v8',       hits7d: '14,208', status: 'active' },
  { name: 'Rate limits · per-key',        desc: '60 RPM dev · 600 RPM prod',                domain: 'rate',      scope: 'org',          owner: 'platform-eng', version: 'v3',       hits7d: '412',    status: 'active' },
  { name: 'Cache TTL · semantic',         desc: '24h default · research-eu 1h override',    domain: 'cache',     scope: 'org + 1 team', owner: 'platform-data',version: 'v2',       hits7d: '—',      status: 'active' },
  { name: 'Tool-scope grants',            desc: 'orders:write → compliance only · pr:write → dev-ex', domain: 'tool', scope: '2 teams',   owner: 'security',     version: 'v5',       hits7d: '68',     status: 'active' },
  { name: 'Retention · prompts',          desc: '30d · client-services-eu = 0d (immediate purge)', domain: 'retention', scope: 'org + 1 team', owner: 'legal',  version: 'v4',       hits7d: '—',      status: 'active' },
  { name: 'Region pinning · EU residency',desc: 'routes to eu-central deployments',         domain: 'routing',   scope: '2 teams',      owner: 'legal',        version: 'v2',       hits7d: '5,108',  status: 'active' },
  { name: 'Per-call token cap',           desc: '80k input · 8k output',                    domain: 'rate',      scope: 'org',          owner: 'finance-ops',  version: 'v1',       hits7d: '9',      status: 'active' },
  { name: 'External egress · vendor allowlist', desc: 'Anthropic, Bedrock-EU only',         domain: 'routing',   scope: 'org',          owner: 'security',     version: 'v6',       hits7d: '2',      status: 'active' },
  { name: 'Approver matrix · skill publish', desc: 'team lead + security for org-wide',     domain: 'workflow',  scope: 'org',          owner: 'jbach',        version: 'v3-draft', hits7d: '—',      status: 'draft'  },
];

export default function PoliciesPage() {
  const [filter, setFilter] = useState('All');

  const rows = POLICIES_DATA.filter(p => {
    if (filter === 'Active') return p.status === 'active';
    if (filter === 'Draft') return p.status === 'draft';
    return true;
  });

  return (
    <section className="page">
      <div className="pill pill--warn" style={{ marginBottom: 12 }}>Live data not yet available for this page · showing representative data</div>

      <div className="page__head">
        <div>
          <h1 className="page__title">Policies</h1>
          <p className="page__sub">Org defaults + per-team overrides · 18 active policies · last edit 2d ago by jbach</p>
        </div>
        <div className="page__actions">
          <button className="btn">Version history</button>
          <button className="btn btn--primary">+ New policy</button>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 18 }}>
        <div className="kpi"><div className="kpi__label">Active</div><div className="kpi__value">18</div><div className="kpi__delta flat">12 org · 6 team</div></div>
        <div className="kpi"><div className="kpi__label">Drafts</div><div className="kpi__value">3</div><div className="kpi__delta flat">awaiting review</div></div>
        <div className="kpi"><div className="kpi__label">Denials · 24h</div><div className="kpi__value">87</div><div className="kpi__delta down">▲ 14% vs prior</div></div>
        <div className="kpi"><div className="kpi__label">Audit refs</div><div className="kpi__value">412</div><div className="kpi__delta flat">last 7d</div></div>
      </div>

      <div className="filters">
        <button className="filter"><span className="lbl">Domain</span><span className="val">All</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Scope</span><span className="val">Any</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Owner</span><span className="val">Any</span><span className="caret">▾</span></button>
        <span style={{ flex: 1 }} />
        <div className="seg">
          {['All','Active','Draft'].map(f => (
            <button key={f} className={filter === f ? 'is-active' : undefined} onClick={() => setFilter(f)}>{f}</button>
          ))}
        </div>
      </div>

      {rows.length === 0 ? <EmptyState message="No policies match the current filter." /> : (
        <div className="card">
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Policy</th><th>Domain</th><th>Scope</th><th>Owner</th>
                  <th>Version</th><th className="num">Hits 7d</th><th>Status</th><th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map(p => (
                  <tr
                    key={p.name}
                    style={{ cursor: 'pointer' }}
                    onKeyDown={e => { if (e.key === 'Enter') {} }}
                    tabIndex={0}
                  >
                    <td><div className="cell-2"><span style={{ fontWeight: 500 }}>{p.name}</span><span className="lo">{p.desc}</span></div></td>
                    <td><span className="pill">{p.domain}</span></td>
                    <td>{p.scope}</td>
                    <td>{p.owner}</td>
                    <td className="mono">{p.version}</td>
                    <td className="num mono">{p.hits7d}</td>
                    <td>
                      {p.status === 'active'
                        ? <span className="pill pill--good"><span className="dot"></span>active</span>
                        : <span className="pill pill--warn"><span className="dot"></span>draft</span>}
                    </td>
                    <td><button className="btn btn--sm">{p.status === 'draft' ? 'Review' : 'Edit'}</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p className="muted" style={{ fontSize: 12, marginTop: 14 }}>
        All policy edits are versioned and recorded in the{' '}
        <a href="/admin/audit" style={{ color: 'var(--sc-link)' }}>Audit log</a> with diff. Reverts are one-click.
      </p>
    </section>
  );
}
