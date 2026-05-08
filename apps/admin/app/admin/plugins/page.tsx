'use client';

import React, { useState } from 'react';
import { EmptyState } from '../_components/PageStates';

type PluginStatus = 'enabled' | 'conditional' | 'blocked';
type PluginScope = 'required' | 'opt-in' | 'per-user' | '—';

type Plugin = {
  name: string;
  desc: string;
  category: string;
  source: 'first-party' | 'community';
  scope: PluginScope;
  teamsUsing: string;
  policyGate: string;
  status: PluginStatus;
};

const PLUGINS_DATA: Plugin[] = [
  { name: 'Datadog tracing',        desc: 'OTel spans — gateway / model / tool',           category: 'Observability', source: 'first-party', scope: 'required',  teamsUsing: '42 / 42',  policyGate: 'none',         status: 'enabled'     },
  { name: 'Guardrails · PII',       desc: 'redact / block per policy',                     category: 'Safety',        source: 'first-party', scope: 'required',  teamsUsing: '42 / 42',  policyGate: 'always-on',    status: 'enabled'     },
  { name: 'Semantic cache',         desc: 'embedding-backed dedupe',                       category: 'Routing',       source: 'first-party', scope: 'opt-in',    teamsUsing: '31 / 42',  policyGate: 'none',         status: 'enabled'     },
  { name: 'VS Code · Inline complete',desc: 'routes Copilot-style completions',            category: 'Editor',        source: 'first-party', scope: 'per-user',  teamsUsing: '348 users', policyGate: 'cost-cap',    status: 'enabled'     },
  { name: 'Eval harness · Inspect', desc: 'scheduled regression evals',                   category: 'Eval',          source: 'first-party', scope: 'opt-in',    teamsUsing: '8 / 42',   policyGate: 'none',         status: 'enabled'     },
  { name: 'Smart router',           desc: 'complexity-classifier model picker',            category: 'Routing',       source: 'first-party', scope: 'opt-in',    teamsUsing: '6 / 42',   policyGate: 'cost-cap',     status: 'enabled'     },
  { name: 'Slack notifier',         desc: 'community/oren — agent + budget alerts',        category: 'Observability', source: 'community',   scope: 'opt-in',    teamsUsing: '14 / 42',  policyGate: 'review · 30d', status: 'conditional' },
  { name: 'External LLM router',    desc: 'community/x — routes to non-vendor APIs',       category: 'Routing',       source: 'community',   scope: '—',         teamsUsing: '0 / 42',   policyGate: 'blocked',      status: 'blocked'     },
];

function statusPill(s: PluginStatus) {
  if (s === 'enabled') return <span className="pill pill--good"><span className="dot"></span>enabled</span>;
  if (s === 'conditional') return <span className="pill pill--warn"><span className="dot"></span>conditional</span>;
  if (s === 'blocked') return <span className="pill pill--bad"><span className="dot"></span>blocked · data-egress</span>;
  return <span className="pill">{s}</span>;
}

function scopePill(s: PluginScope) {
  if (s === 'required') return <span className="pill pill--info">required</span>;
  return <span>{s}</span>;
}

export default function PluginsPage() {
  const [filter, setFilter] = useState('All');

  const rows = PLUGINS_DATA;

  return (
    <section className="page">
      <div className="pill pill--warn" style={{ marginBottom: 12 }}>Live data not yet available for this page · showing representative data</div>

      <div className="page__head">
        <div>
          <h1 className="page__title">Plugins</h1>
          <p className="page__sub">Gateway / playground / CLI extensions · per-team install policy · 6 enabled org-wide</p>
        </div>
        <div className="page__actions">
          <button className="btn">Allowlist</button>
          <button className="btn btn--primary">+ Submit plugin</button>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 18 }}>
        <div className="kpi"><div className="kpi__label">Org-wide enabled</div><div className="kpi__value">6</div><div className="kpi__delta flat">required: Datadog, Guardrails</div></div>
        <div className="kpi"><div className="kpi__label">Per-team enabled</div><div className="kpi__value">14</div><div className="kpi__delta up">▲ 2 this week</div></div>
        <div className="kpi"><div className="kpi__label">Pending install</div><div className="kpi__value">3</div><div className="kpi__delta flat">awaiting approval</div></div>
        <div className="kpi"><div className="kpi__label">Blocked</div><div className="kpi__value">2</div><div className="kpi__delta down">policy violations</div></div>
      </div>

      <div className="filters">
        <button className="filter"><span className="lbl">Category</span><span className="val">All</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Source</span><span className="val">All</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Scope</span><span className="val">Any</span><span className="caret">▾</span></button>
        <span style={{ flex: 1 }} />
        <div className="seg">
          {['All','Enabled','Available','Blocked'].map(f => (
            <button key={f} className={filter === f ? 'is-active' : undefined} onClick={() => setFilter(f)}>{f}</button>
          ))}
        </div>
      </div>

      {rows.length === 0 ? <EmptyState message="No plugins found." /> : (
        <div className="card">
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 30 }}><input type="checkbox" /></th>
                  <th>Plugin</th><th>Category</th><th>Source</th><th>Scope</th>
                  <th>Teams using</th><th>Policy gate</th><th>Status</th><th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map(p => (
                  <tr key={p.name} tabIndex={0} style={{ cursor: 'pointer' }}>
                    <td><input type="checkbox" defaultChecked={p.status === 'enabled'} /></td>
                    <td><div className="cell-2"><span style={{ fontWeight: 500 }}>{p.name}</span><span className="lo">{p.desc}</span></div></td>
                    <td>{p.category}</td>
                    <td><span className="pill">{p.source}</span></td>
                    <td>{scopePill(p.scope)}</td>
                    <td className="num mono">{p.teamsUsing}</td>
                    <td>
                      {p.policyGate === 'always-on' ? <span className="pill pill--good">always-on</span>
                        : p.policyGate === 'review · 30d' ? <span className="pill pill--warn">review · 30d</span>
                        : p.policyGate === 'blocked' ? <span className="pill pill--bad">blocked</span>
                        : <span className="pill">{p.policyGate}</span>}
                    </td>
                    <td>{statusPill(p.status)}</td>
                    <td>
                      <button className="btn btn--sm">
                        {p.status === 'conditional' ? 'Review' : p.status === 'blocked' ? 'Reasons' : 'Configure'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p className="muted" style={{ fontSize: 12, marginTop: 14 }}>
        Plugins marked <span className="pill pill--info" style={{ display: 'inline-flex' }}>required</span> are auto-enabled on every team and cannot be disabled by team admins.
      </p>
    </section>
  );
}
