'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { LoadingState, ErrorState, EmptyState } from '../_components/PageStates';
import { APPROVALS_DATA } from '../_mocks/data';

type Approval = typeof APPROVALS_DATA[number];

export default function ApprovalsPage() {
  const [filter, setFilter] = useState('Pending');
  const qc = useQueryClient();

  const { data, isLoading, isError, error, refetch } = useQuery<Approval[]>({
    queryKey: ['approvals'],
    queryFn: () => fetch('/api/v1/approvals').then(r => r.json()),
  });

  const approve = useMutation({
    mutationFn: (idx: number) => fetch(`/api/v1/approvals/${idx}/approve`, { method: 'POST' }).then(r => r.json()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['approvals'] }),
  });

  const deny = useMutation({
    mutationFn: (idx: number) => fetch(`/api/v1/approvals/${idx}/deny`, { method: 'POST' }).then(r => r.json()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['approvals'] }),
  });

  if (isLoading) return <section className="page"><LoadingState rows={8} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;

  const rows = data ?? APPROVALS_DATA;

  return (
    <section className="page">
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
                      <button className="btn btn--sm" onClick={() => deny.mutate(i)}>Deny</button>
                      {' '}
                      <button className="btn btn--sm btn--primary" onClick={() => approve.mutate(i)}>Approve</button>
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
