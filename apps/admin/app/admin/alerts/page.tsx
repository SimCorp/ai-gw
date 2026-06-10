'use client';

import React from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../_components/PageStates';
import { apiFetch } from '../../../lib/apiClient';

const BASE = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

// --- API types ---

interface BudgetSpikeAlert {
  id: string;
  timestamp: string;
  resource_id: string;
  details: { team_name?: string; daily_spend?: number; rolling_avg?: number } | null;
}

interface ServiceHealth {
  service: string;
  icon: string;
  status: string;
  code: number;
  latency_ms: number;
  error: string | null;
}

interface SystemHealth {
  overall: string;
  last_updated: string;
  services: ServiceHealth[];
  redis: { status: string; ping_ms: number; used_memory_mb: number; connected_clients: number; error: string | null };
  postgres: { status: string; ping_ms: number; active_connections: number; error: string | null };
  litellm: { status: string; models_available: number; providers_with_keys: string[]; error: string | null };
  gateway: { status: string; requests_last_60s: number; cache_hit_rate_last_60s: number; error: string | null };
  recent_errors: string[];
}

interface BudgetStatus {
  org_budget_usd: number;
  total_spend_mtd: number;
  [key: string]: unknown;
}

// --- helpers ---

interface DerivedAlert {
  severity: 'P1' | 'P2' | 'P3';
  ruleName: string;
  desc: string;
  triggered: string;
  owner: string;
  status: 'firing' | 'warn';
  btn: string;
}

function deriveAlerts(health: SystemHealth | undefined, budget: BudgetStatus | undefined): DerivedAlert[] {
  const alerts: DerivedAlert[] = [];

  if (!health) return alerts;

  const now = health.last_updated ?? 'now';

  // Services not ok
  for (const svc of health.services ?? []) {
    if (svc.status !== 'ok') {
      alerts.push({
        severity: 'P1',
        ruleName: `${svc.service} — ${svc.status}`,
        desc: svc.error ?? `HTTP ${svc.code} · ${svc.latency_ms != null ? `${svc.latency_ms.toFixed(0)}ms` : 'no latency'}`,
        triggered: now,
        owner: 'platform-engineering',
        status: svc.status === 'degraded' ? 'warn' : 'firing',
        btn: 'Investigate',
      });
    }
  }

  // Redis not ok
  if (health.redis?.status !== 'ok') {
    alerts.push({
      severity: 'P1',
      ruleName: `Redis — ${health.redis?.status ?? 'unknown'}`,
      desc: health.redis?.error ?? 'Redis health check failed',
      triggered: now,
      owner: 'platform-engineering',
      status: 'firing',
      btn: 'Investigate',
    });
  }

  // Postgres not ok
  if (health.postgres?.status !== 'ok') {
    alerts.push({
      severity: 'P1',
      ruleName: `Postgres — ${health.postgres?.status ?? 'unknown'}`,
      desc: health.postgres?.error ?? 'Postgres health check failed',
      triggered: now,
      owner: 'platform-engineering',
      status: 'firing',
      btn: 'Investigate',
    });
  }

  // LiteLLM not ok
  if (health.litellm?.status !== 'ok') {
    alerts.push({
      severity: 'P2',
      ruleName: `LiteLLM — ${health.litellm?.status ?? 'unknown'}`,
      desc: health.litellm?.error ?? 'LiteLLM health check failed',
      triggered: now,
      owner: 'platform-engineering',
      status: 'firing',
      btn: 'Investigate',
    });
  }

  // Budget warning
  if (budget && budget.org_budget_usd > 0) {
    const pct = (budget.total_spend_mtd / budget.org_budget_usd) * 100;
    if (pct >= 80) {
      alerts.push({
        severity: pct >= 95 ? 'P1' : 'P2',
        ruleName: `Org budget — ${pct.toFixed(0)}% used`,
        desc: `$${budget.total_spend_mtd.toFixed(2)} of $${budget.org_budget_usd.toFixed(2)} monthly budget`,
        triggered: now,
        owner: 'finance-ops',
        status: 'warn',
        btn: 'Review',
      });
    }
  }

  // Recent errors from health
  for (const err of health.recent_errors ?? []) {
    alerts.push({
      severity: 'P2',
      ruleName: 'Gateway error',
      desc: String(err),
      triggered: now,
      owner: 'platform-engineering',
      status: 'firing',
      btn: 'Investigate',
    });
  }

  return alerts;
}

function severityPill(s: string) {
  if (s === 'P1') return <span className="pill pill--bad">P1</span>;
  if (s === 'P2') return <span className="pill pill--warn">P2</span>;
  return <span className="pill pill--info">P3</span>;
}

function alertStatusPill(s: string) {
  if (s === 'firing') return <span className="pill pill--bad"><span className="dot"></span>firing</span>;
  if (s === 'warn') return <span className="pill pill--warn"><span className="dot"></span>warning</span>;
  return <span className="pill">{s}</span>;
}

// Static rule definitions (no backend endpoint for these)
const ALERT_RULES = [
  { name: 'Budget · team monthly > 80%',      scope: '7 teams',    severity: 'P2' },
  { name: 'Budget · org daily > $1,200',       scope: 'org',        severity: 'P1' },
  { name: 'Latency · model P95 > 4s · 5m',    scope: 'all models', severity: 'P3' },
  { name: 'Error-rate · service > 2% · 5m',   scope: 'all services',severity: 'P1' },
  { name: 'Redis health check',                scope: 'infra',      severity: 'P1' },
  { name: 'Postgres health check',             scope: 'infra',      severity: 'P1' },
  { name: 'Guardrail · PII hits > 5/h',        scope: 'org',        severity: 'P2' },
  { name: 'Cache · hit-rate < 30% · 1h',       scope: 'opt-in',     severity: 'P3' },
];

const ALERT_CHANNELS = [
  { name: '#ai-gw-incidents',           type: 'Slack · P1, P2' },
  { name: '#ai-gw-budget',              type: 'Slack · budget rules' },
  { name: 'PagerDuty · gateway-oncall', type: 'P1 only' },
  { name: 'security@simcorp.com',       type: 'guardrail violations' },
];

export default function AlertsPage() {
  const healthQuery = useQuery<SystemHealth>({
    queryKey: ['system-health'],
    queryFn: () => fetch(`${BASE}/system/health`).then(r => {
      if (!r.ok) throw new Error(`/system/health ${r.status}`);
      return r.json();
    }),
    staleTime: 15_000,
  });

  const budgetQuery = useQuery<BudgetStatus>({
    queryKey: ['budget-status'],
    queryFn: () => fetch(`${BASE}/budget/status`).then(r => {
      if (!r.ok) throw new Error(`/budget/status ${r.status}`);
      return r.json();
    }),
    staleTime: 60_000,
  });

  const spikeAlertsQuery = useQuery<BudgetSpikeAlert[]>({
    queryKey: ['budget-spike-alerts'],
    queryFn: () => apiFetch<BudgetSpikeAlert[]>('/budget/alerts').catch(() => []),
    staleTime: 30_000,
  });

  const isLoading = healthQuery.isLoading;
  const isError = healthQuery.isError;
  const firstError = healthQuery.error as Error | undefined;

  if (isLoading) return <section className="page"><LoadingState rows={5} /></section>;
  if (isError && firstError) return <section className="page"><ErrorState error={firstError} retry={() => healthQuery.refetch()} /></section>;

  const health = healthQuery.data;
  const budget = budgetQuery.data;
  const alerts = deriveAlerts(health, budget);
  const spikeAlerts = spikeAlertsQuery.data ?? [];

  const firing = alerts.filter(a => a.status === 'firing').length;
  const warning = alerts.filter(a => a.status === 'warn').length;

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Alerts</h1>
          <p className="page__sub">
            {firing > 0 ? `${firing} firing` : 'No firing alerts'}
            {warning > 0 ? ` · ${warning} warning` : ''}
            {` · ${ALERT_RULES.length} rules across budget, latency, error-rate, and health`}
          </p>
        </div>
        <div className="page__actions">
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 18 }}>
        <div className="kpi">
          <div className="kpi__label">Firing</div>
          <div className="kpi__value" style={{ color: firing > 0 ? 'var(--bad)' : 'var(--good)' }}>{firing}</div>
          <div className="kpi__delta flat">{firing === 0 ? 'all clear' : 'requires attention'}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Warning</div>
          <div className="kpi__value" style={{ color: warning > 0 ? 'var(--warn)' : undefined }}>{warning}</div>
          <div className="kpi__delta flat">{warning === 0 ? 'none' : 'review recommended'}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">System overall</div>
          <div className="kpi__value" style={{ color: health?.overall === 'ok' ? 'var(--good)' : 'var(--bad)', fontSize: 18, paddingTop: 4 }}>
            {health?.overall ?? '—'}
          </div>
          <div className="kpi__delta flat">{health?.last_updated ?? ''}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Rules</div>
          <div className="kpi__value">{ALERT_RULES.length}</div>
          <div className="kpi__delta flat">all active</div>
        </div>
      </div>

      {/* D12: Budget spike alerts from audit log */}
      <div className="card" style={{ marginBottom: 18 }}>
        <div className="card__head">
          <div className="card__title">Cost spike alerts</div>
          <div className="card__sub">Teams whose daily spend exceeded 3× their 7-day rolling average</div>
        </div>
        <div className="card__body" style={{ padding: 0 }}>
          <table className="tbl">
            <thead>
              <tr><th>Time</th><th>Team</th><th>Daily spend</th><th>vs. Average</th></tr>
            </thead>
            <tbody>
              {spikeAlerts.length === 0 && (
                <tr>
                  <td colSpan={4} style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
                    No cost spike alerts — all teams within normal spending patterns
                  </td>
                </tr>
              )}
              {spikeAlerts.map(a => (
                <tr key={a.id}>
                  <td style={{ color: 'var(--fg-3)', fontSize: 12.5 }}>{new Date(a.timestamp).toLocaleString()}</td>
                  <td style={{ fontWeight: 500 }}>{a.details?.team_name || a.resource_id}</td>
                  <td className="num" style={{ color: 'var(--bad)', fontWeight: 600 }}>${a.details?.daily_spend?.toFixed(2) ?? '—'}</td>
                  <td style={{ color: 'var(--fg-3)', fontSize: 12.5 }}>
                    {a.details?.rolling_avg
                      ? `${((a.details.daily_spend ?? 0) / a.details.rolling_avg).toFixed(1)}× avg ($${a.details.rolling_avg.toFixed(2)}/day)`
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid--2" style={{ gridTemplateColumns: '1.4fr 1fr', alignItems: 'start' }}>
        <div className="card">
          <div className="card__head"><div className="card__title">Active alerts</div><div className="card__sub">live from /system/health</div></div>
          <div className="card__body" style={{ padding: 0 }}>
            {alerts.length === 0 ? (
              <div style={{ padding: 20, textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
                No active alerts — all systems healthy.
              </div>
            ) : (
              <table className="tbl">
                <thead>
                  <tr><th>Severity</th><th>Rule</th><th>Triggered</th><th>Owner</th><th>Status</th><th></th></tr>
                </thead>
                <tbody>
                  {alerts.map((a, i) => (
                    <tr key={i} tabIndex={0} style={{ cursor: 'pointer' }}>
                      <td>{severityPill(a.severity)}</td>
                      <td><div className="cell-2"><span style={{ fontWeight: 500 }}>{a.ruleName}</span><span className="lo">{a.desc}</span></div></td>
                      <td className="mono lo">{a.triggered}</td>
                      <td>{a.owner}</td>
                      <td>{alertStatusPill(a.status)}</td>
                      <td>
                        <Link
                          href={
                            a.btn === 'Review'
                              ? '/admin/quotas'
                              : a.ruleName.toLowerCase().includes('redis') || a.ruleName.toLowerCase().includes('postgres') || a.ruleName.toLowerCase().includes('litellm')
                              ? '/admin/dashboard'
                              : '/admin/requests'
                          }
                          className="btn btn--sm"
                        >
                          {a.btn}
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div className="grid" style={{ gap: 18 }}>
          <div className="card">
            <div className="card__head"><div className="card__title">Rule index</div></div>
            <div className="card__body">
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                {ALERT_RULES.map((r, i) => (
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
              {ALERT_CHANNELS.map((c, i) => (
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
