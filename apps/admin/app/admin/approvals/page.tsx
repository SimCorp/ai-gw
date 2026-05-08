'use client';

import React, { useState } from 'react';
import { EmptyState } from '../_components/PageStates';

type ApprovalsRow = {
  type: string;
  typePill: 'bad' | 'warn' | 'default';
  subject: string;
  desc: string;
  requester: string;
  team: string;
  age: string;
  sla: boolean;
  risk: 'high' | 'med' | 'low';
};

const APPROVALS_DATA: ApprovalsRow[] = [
  { type: 'tool scope',    typePill: 'bad',     subject: 'Grant orders:write to trade-mcp',      desc: 'justification: pre-trade ticket validator agent (rc.2)',   requester: 'g.olsen@simcorp',   team: 'trading',             age: '2h 18m',  sla: false, risk: 'high' },
  { type: 'skill publish', typePill: 'warn',    subject: 'Anomaly explainer · v2.0',              desc: 'adds Datadog tool · diff +118 / -42',                     requester: 'k.weiss@simcorp',   team: 'risk-engineering',    age: '5h 04m',  sla: false, risk: 'med'  },
  { type: 'budget raise',  typePill: 'warn',    subject: 'research-eu · +$3,500 May cap',         desc: 'projected overrun $13.4k vs $12.75k cap',                 requester: 'r.holm@simcorp',    team: 'research-eu',         age: '7h 41m',  sla: true,  risk: 'med'  },
  { type: 'plugin install',typePill: 'default', subject: 'Slack notifier · per-team',             desc: 'scope: agent + budget alerts → #ai-gw-trading',           requester: 'g.olsen@simcorp',   team: 'trading',             age: '12h 02m', sla: true,  risk: 'low'  },
  { type: 'model deploy',  typePill: 'default', subject: 'sonnet-4.5 · eu-west deployment',       desc: 'capacity addition · +200 RPM',                            requester: 'n.persson@simcorp', team: 'platform-engineering',age: '14h 21m', sla: true,  risk: 'low'  },
  { type: 'mcp register',  typePill: 'warn',    subject: 'trade-mcp · v1.0-rc.2',                desc: 'scopes: orders:read, orders:write',                        requester: 'g.olsen@simcorp',   team: 'trading',             age: '1d 03h',  sla: false, risk: 'med'  },
  { type: 'key issue',     typePill: 'default', subject: 'Production key · client-services-eu',  desc: 'rate 600 RPM · region eu-central only',                   requester: 'm.larsen@simcorp',  team: 'client-services-ai',  age: '1d 14h',  sla: false, risk: 'low'  },
  { type: 'team add',      typePill: 'default', subject: 'New team · nordic-research-quant',      desc: '5 members · region eu-central · cap $4,000/mo',           requester: 'a.singh@simcorp',   team: '(new)',               age: '2d 08h',  sla: false, risk: 'low'  },
];

export default function ApprovalsPage() {
  const [filter, setFilter] = useState('Pending');

  const rows = APPROVALS_DATA;

  return (
    <section className="page">
      <div className="pill pill--warn" style={{ marginBottom: 12 }}>Live data not yet available for this page · showing representative data</div>

      <div className="page__head">
        <div>
          <h1 className="page__title">Approvals inbox</h1>
          <p className="page__sub">8 pending · 3 SLA at-risk · approver: jbach@simcorp + delegates</p>
        </div>
        <div className="page__actions">
          <button className="btn">Delegate</button>
          <button className="btn btn--primary">Bulk approve</button>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 18 }}>
        <div className="kpi"><div className="kpi__label">Pending</div><div className="kpi__value">8</div><div className="kpi__delta flat">3 SLA at-risk</div></div>
        <div className="kpi"><div className="kpi__label">Median age</div><div className="kpi__value">4<span className="unit">h</span></div><div className="kpi__delta up">▼ 32% vs prior week</div></div>
        <div className="kpi"><div className="kpi__label">Approved · 7d</div><div className="kpi__value">42</div><div className="kpi__delta up">▲ 14% vs prior</div></div>
        <div className="kpi"><div className="kpi__label">Denied · 7d</div><div className="kpi__value">5</div><div className="kpi__delta flat">policy violations</div></div>
      </div>

      <div className="filters">
        <button className="filter"><span className="lbl">Type</span><span className="val">All</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Requester</span><span className="val">Any</span><span className="caret">▾</span></button>
        <button className="filter"><span className="lbl">Team</span><span className="val">Any</span><span className="caret">▾</span></button>
        <span style={{ flex: 1 }} />
        <div className="seg">
          {['Pending','Approved','Denied'].map(f => (
            <button key={f} className={filter === f ? 'is-active' : undefined} onClick={() => setFilter(f)}>{f}</button>
          ))}
        </div>
      </div>

      {rows.length === 0 ? <EmptyState message="No approvals pending." /> : (
        <div className="card">
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 30 }}><input type="checkbox" /></th>
                  <th>Type</th><th>Request</th><th>Requester</th><th>Team</th>
                  <th>Age</th><th>Risk</th><th style={{ width: 200 }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a, i) => (
                  <tr key={i} tabIndex={0} style={{ cursor: 'default' }}>
                    <td><input type="checkbox" /></td>
                    <td>
                      {a.typePill === 'bad' ? <span className="pill pill--bad">{a.type}</span>
                        : a.typePill === 'warn' ? <span className="pill pill--warn">{a.type}</span>
                        : <span className="pill">{a.type}</span>}
                    </td>
                    <td><div className="cell-2"><span style={{ fontWeight: 500 }}>{a.subject}</span><span className="lo">{a.desc}</span></div></td>
                    <td>{a.requester}</td>
                    <td>{a.team}</td>
                    <td className="mono lo">
                      {a.age}
                      {a.sla && <span style={{ color: 'var(--bad)' }}> · SLA</span>}
                    </td>
                    <td>
                      {a.risk === 'high' ? <span className="pill pill--bad">high</span>
                        : a.risk === 'med' ? <span className="pill pill--warn">med</span>
                        : <span className="pill">low</span>}
                    </td>
                    <td>
                      <button className="btn btn--sm">Deny</button>
                      {' '}
                      <button className="btn btn--sm btn--primary">Approve</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p className="muted" style={{ fontSize: 12, marginTop: 14 }}>
        SLA = first response within 8 business hours. Approvals + denials are recorded in the{' '}
        <a href="/admin/audit" style={{ color: 'var(--sc-link)' }}>Audit log</a>.
      </p>
    </section>
  );
}
