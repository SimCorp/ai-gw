'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../_components/PageStates';
import { ALERTS_DATA, ALERT_RULES, ALERT_CHANNELS } from '../_mocks/data';

type AlertsData = {
  alerts: typeof ALERTS_DATA;
  rules: typeof ALERT_RULES;
  channels: typeof ALERT_CHANNELS;
};

function alertStatusPill(s: string, ackedBy?: string) {
  if (s === 'firing') return <span className="pill pill--bad"><span className="dot"></span>firing</span>;
  if (s === 'acked') return <span className="pill pill--warn"><span className="dot"></span>acked · {ackedBy}</span>;
  if (s === 'acked_resolved') return <span className="pill pill--info"><span className="dot"></span>acked · {ackedBy}</span>;
  return <span className="pill">{s}</span>;
}

function severityPill(s: string) {
  if (s === 'P1') return <span className="pill pill--bad">P1</span>;
  if (s === 'P2') return <span className="pill pill--warn">P2</span>;
  return <span className="pill pill--info">P3</span>;
}

export default function AlertsPage() {
  const { data, isLoading, isError, error, refetch } = useQuery<AlertsData>({
    queryKey: ['alerts'],
    queryFn: () => fetch('/api/v1/alerts').then(r => r.json()),
  });

  const d = data ?? { alerts: ALERTS_DATA, rules: ALERT_RULES, channels: ALERT_CHANNELS };

  if (isLoading) return <section className="page"><LoadingState rows={5} /></section>;
  if (isError) return <section className="page"><ErrorState error={error as Error} retry={() => refetch()} /></section>;

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Alerts</h1>
          <p className="page__sub">2 firing · 3 acknowledged · 24 rules across budget, latency, error-rate, drift, and policy</p>
        </div>
        <div className="page__actions">
          <button className="btn">Notification channels</button>
          <button className="btn btn--primary">+ New rule</button>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 18 }}>
        <div className="kpi"><div className="kpi__label">Firing</div><div className="kpi__value" style={{ color: 'var(--bad)' }}>2</div><div className="kpi__delta down">filings-mcp · trade-mcp drift</div></div>
        <div className="kpi"><div className="kpi__label">Acknowledged</div><div className="kpi__value">3</div><div className="kpi__delta flat">avg ack 4m 12s</div></div>
        <div className="kpi"><div className="kpi__label">MTTR · 7d</div><div className="kpi__value">18<span className="unit">m</span></div><div className="kpi__delta up">▼ 32% vs prior week</div></div>
        <div className="kpi"><div className="kpi__label">Rules</div><div className="kpi__value">24</div><div className="kpi__delta flat">21 active · 3 paused</div></div>
      </div>

      <div className="grid grid--2" style={{ gridTemplateColumns: '1.4fr 1fr', alignItems: 'start' }}>
        <div className="card">
          <div className="card__head"><div className="card__title">Active alerts</div><div className="card__sub">last 24h</div></div>
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead>
                <tr><th>Severity</th><th>Rule</th><th>Triggered</th><th>Owner</th><th>Status</th><th></th></tr>
              </thead>
              <tbody>
                {d.alerts.map((a, i) => (
                  <tr key={i} tabIndex={0} style={{ cursor: 'pointer' }}>
                    <td>{severityPill(a.severity)}</td>
                    <td><div className="cell-2"><span style={{ fontWeight: 500 }}>{a.ruleName}</span><span className="lo">{a.desc}</span></div></td>
                    <td className="mono lo">{a.triggered}</td>
                    <td>{a.owner}</td>
                    <td>{alertStatusPill(a.status, a.ackedBy)}</td>
                    <td><button className="btn btn--sm">{a.btn}</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="grid" style={{ gap: 18 }}>
          <div className="card">
            <div className="card__head"><div className="card__title">Rule index</div></div>
            <div className="card__body">
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                {d.rules.map((r, i) => (
                  <div key={i} style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '11px 0',
                    borderTop: i > 0 ? '1px solid var(--rule)' : undefined,
                  }}>
                    <div style={{ fontSize: 13.5, color: 'var(--fg-1)' }}>{r.name}</div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <span className="pill">{r.scope}</span>
                      <span className="lo mono">{r.severity}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card__head"><div className="card__title">Channels</div></div>
            <div className="card__body">
              {d.channels.map((c, i) => (
                <div key={i} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '10px 0',
                  borderTop: i > 0 ? '1px solid var(--rule)' : undefined,
                }}>
                  <div style={{ fontWeight: 500, fontSize: 13.5 }}>{c.name}</div>
                  <div style={{ fontSize: 12.5, color: 'var(--fg-2)' }}>{c.type}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
