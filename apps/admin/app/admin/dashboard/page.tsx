'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { PageHead, KpiCard, Pill, EmptyState, Button } from '@aigw/ui';
import { Sparkline } from '@aigw/charts';
import { LoadingState, ErrorState } from '../_components/PageStates';
import { apiFetch } from '../../../lib/apiClient';

// ---------------------------------------------------------------------------
// Arc gauge — pure SVG, no extra deps
// ---------------------------------------------------------------------------

interface GaugeProps {
  /** Value in [0, 1] */
  value: number;
  label: string;
  sublabel?: string;
  color?: string;
  size?: number;
}

function ArcGauge({ value, label, sublabel, color = 'var(--accent)', size = 100 }: GaugeProps) {
  const r = 38;
  // Arc spans 220 degrees (from -200 to 40 in SVG angle terms, starting at bottom-left)
  const arcLen = 2 * Math.PI * r;
  const sweep = 220 / 360; // fraction of full circle used for the arc
  const filled = Math.max(0, Math.min(1, value)) * sweep * arcLen;
  const gap = arcLen - filled;
  // Offset: arc starts at 160 degrees from 3-o'clock (i.e. bottom-left)
  const startAngle = 160;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
      <svg width={size} height={size * 0.75} viewBox="0 0 100 78" style={{ overflow: 'visible' }}>
        {/* Track */}
        <circle
          cx="50" cy="58" r={r}
          fill="none"
          stroke="var(--rule)"
          strokeWidth="10"
          strokeDasharray={`${sweep * arcLen} ${arcLen}`}
          strokeDashoffset={0}
          transform={`rotate(${startAngle} 50 58)`}
          strokeLinecap="round"
        />
        {/* Fill */}
        <circle
          cx="50" cy="58" r={r}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeDasharray={`${filled} ${gap + (1 - sweep) * arcLen}`}
          strokeDashoffset={0}
          transform={`rotate(${startAngle} 50 58)`}
          strokeLinecap="round"
          style={{ transition: 'stroke-dasharray 0.5s ease' }}
        />
        {/* Center label */}
        <text x="50" y="54" textAnchor="middle" fill="var(--fg-1)" fontSize="14" fontWeight="600" fontFamily="var(--font-mono)">
          {Math.round(value * 100)}%
        </text>
      </svg>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-1)' }}>{label}</div>
        {sublabel && <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>{sublabel}</div>}
      </div>
    </div>
  );
}

interface GatewayInfo {
  version: string;
  features: string[];
  models: string[];
  config_version: number;
  autoroute: {
    enabled: boolean;
    current_model?: string | null;
    score?: number | null;
    candidates?: string[];
  };
  workflow_runs_today: number;
}

const RANGES = ['1h', '24h', '7d', '30d', '90d'];

// --- API types ---

interface TeamStat {
  team_name: string;
  request_count: number;
  total_tokens: number | null;
  total_cost_usd: number | null;
  cache_hit_pct: number | null;
}

interface ServiceHealth {
  service: string;
  icon: string;
  status: string;
  code: number;
  latency_ms: number;
  error: string | null;
}

interface RedisHealth {
  status: string;
  ping_ms: number;
  used_memory_mb: number;
  connected_clients: number;
  error: string | null;
}

interface PostgresHealth {
  status: string;
  ping_ms: number;
  active_connections: number;
  error: string | null;
}

interface LitellmHealth {
  status: string;
  models_available: number;
  providers_with_keys: string[];
  error: string | null;
}

interface GatewayHealth {
  status: string;
  requests_last_60s: number;
  cache_hit_rate_last_60s: number;
  error: string | null;
}

interface SystemHealth {
  overall: string;
  last_updated: string;
  services: ServiceHealth[];
  redis: RedisHealth;
  postgres: PostgresHealth;
  litellm: LitellmHealth;
  gateway: GatewayHealth;
  recent_errors: string[];
}

interface AuditEntry {
  id: string | number;
  actor: string;
  action: string;
  resource_id: string;
  resource_type: string;
  details: Record<string, unknown> | string | null;
  timestamp: string;
}

// --- helpers ---

function fmtUsd(n: number | null | undefined): string {
  if (n == null) return '€0.00';
  if (n >= 1000) return `€${(n / 1000).toFixed(1)}k`;
  return `€${n.toFixed(2)}`;
}

function fmtCount(n: number): { value: string; unit?: string } {
  if (n >= 1_000_000) return { value: (n / 1_000_000).toFixed(1), unit: 'M' };
  if (n >= 1_000) return { value: (n / 1_000).toFixed(1), unit: 'k' };
  return { value: String(n) };
}

function fmtTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return ts;
  }
}

function statusDotClass(status: string) {
  if (status === 'ok') return 'statusdot statusdot--good';
  if (status === 'degraded') return 'statusdot statusdot--warn';
  return 'statusdot statusdot--bad';
}

function statusPillVariant(status: string): 'good' | 'warn' | 'bad' {
  if (status === 'ok') return 'good';
  if (status === 'degraded') return 'warn';
  return 'bad';
}

function statusLabel(status: string) {
  if (status === 'ok') return 'healthy';
  return status;
}

// Representative model mix — no live per-model breakdown endpoint yet.
const MODEL_MIX = [
  { label: 'claude-sonnet-4.5', pct: 46, color: 'var(--accent)' },
  { label: 'gemini-2.5-pro', pct: 29, color: 'var(--cat-teal)' },
  { label: 'claude-haiku-4.5', pct: 16, color: 'var(--cat-purple)' },
  { label: 'gpt-5 (BYO)', pct: 9, color: 'var(--cat-orange)' },
];

export default function DashboardPage() {
  const [range, setRange] = useState('24h');

  const statsQuery = useQuery<TeamStat[]>({
    queryKey: ['dashboard-stats', range],
    queryFn: () => apiFetch<TeamStat[]>(`/dashboard/stats?range=${range}`),
    staleTime: 30_000,
  });

  const healthQuery = useQuery<SystemHealth>({
    queryKey: ['system-health', range],
    queryFn: () => apiFetch<SystemHealth>('/system/health'),
    staleTime: 15_000,
  });

  const auditQuery = useQuery<AuditEntry[]>({
    queryKey: ['audit-recent'],
    queryFn: () => apiFetch<AuditEntry[]>('/audit?limit=6'),
    staleTime: 30_000,
  });

  const gatewayInfoQuery = useQuery<GatewayInfo>({
    queryKey: ['gateway-info'],
    queryFn: () => apiFetch<GatewayInfo>('/gateway-info'),
    staleTime: 30_000,
  });

  const isLoading = statsQuery.isLoading || healthQuery.isLoading;
  const isError = statsQuery.isError || healthQuery.isError;
  const firstError = (statsQuery.error ?? healthQuery.error) as Error | undefined;

  if (isLoading) return <section className="page"><LoadingState rows={8} /></section>;
  if (isError && firstError) return <section className="page"><ErrorState error={firstError} retry={() => { statsQuery.refetch(); healthQuery.refetch(); }} /></section>;

  const stats: TeamStat[] = statsQuery.data ?? [];
  const health = healthQuery.data;
  const audit: AuditEntry[] = auditQuery.data ?? [];

  // Derived KPIs
  const totalSpend = stats.reduce((s, t) => s + (t.total_cost_usd ?? 0), 0);
  const totalRequests = stats.reduce((s, t) => s + (t.request_count ?? 0), 0);
  const totalTokens = stats.reduce((s, t) => s + (t.total_tokens ?? 0), 0);
  const avgCacheHit = stats.length > 0
    ? stats.reduce((s, t) => s + (t.cache_hit_pct ?? 0), 0) / stats.length
    : 0;

  // Top teams sorted by spend descending
  const topTeams = [...stats].sort((a, b) => (b.total_cost_usd ?? 0) - (a.total_cost_usd ?? 0));
  const maxSpend = (topTeams[0]?.total_cost_usd ?? 0) || 1;

  // Per-team distributions feed the KPI sparklines (real data; no time-series endpoint).
  const requestsSpark = [...stats].map(t => t.request_count ?? 0).sort((a, b) => b - a);
  const spendSpark = topTeams.map(t => t.total_cost_usd ?? 0);
  const cacheSpark = [...stats].map(t => t.cache_hit_pct ?? 0).sort((a, b) => b - a);

  // Gateway stats
  const gateway = health?.gateway;
  const redis = health?.redis;
  const gwInfo = gatewayInfoQuery.data;

  // Services for provider health table
  const services: ServiceHealth[] = health?.services ?? [];

  // Active alerts derived from unhealthy services
  const unhealthyServices = services.filter(s => s.status !== 'ok');

  const requestsFmt = fmtCount(totalRequests);
  const tokensFmt = fmtCount(totalTokens);
  const rangeLabel = range.toUpperCase();
  const healthSub = health
    ? (health.overall === 'ok' ? 'All systems operational' : `System ${health.overall}`)
    : 'Health unavailable';

  return (
    <section className="page">
      <PageHead
        title="Dashboard"
        subtitle={`${healthSub} · org-wide usage and cost · last ${range}`}
        actions={
          <>
            <div className="seg" role="tablist">
              {RANGES.map(r => (
                <button
                  key={r}
                  className={range === r ? 'is-active' : undefined}
                  onClick={() => setRange(r)}
                  aria-pressed={range === r}
                >{r}</button>
              ))}
            </div>
            <Button
              onClick={() => {
                if (!stats.length) return;
                const header = 'Team,Requests,Tokens,Cost (EUR),Cache Hit %';
                const rows = stats.map(t =>
                  [t.team_name, t.request_count, t.total_tokens ?? 0, (t.total_cost_usd ?? 0).toFixed(4), (t.cache_hit_pct ?? 0).toFixed(1)].join(',')
                );
                const csv = [header, ...rows].join('\n');
                const blob = new Blob([csv], { type: 'text/csv' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url; a.download = `gateway-stats-${range}.csv`; a.click();
                URL.revokeObjectURL(url);
              }}
              disabled={stats.length === 0}
            >
              Export
            </Button>
          </>
        }
      />

      <div className="stack">
        {/* KPI row */}
        <div className="kpi-grid" style={{ gridTemplateColumns: 'repeat(5, 1fr)' }}>
          <KpiCard
            className="kpi--trace"
            label={`REQUESTS_${rangeLabel}`}
            value={requestsFmt.value}
            unit={requestsFmt.unit}
            delta={{ direction: 'flat', label: `${stats.length} teams` }}
            sparkline={requestsSpark.length > 0
              ? <Sparkline variant="bar" data={requestsSpark} color="var(--accent)" />
              : undefined}
          />
          <KpiCard
            label={`SPEND_${rangeLabel}`}
            value={fmtUsd(totalSpend)}
            delta={{ direction: 'flat', label: 'per-team distribution' }}
            sparkline={spendSpark.length > 0
              ? <Sparkline variant="bar" data={spendSpark} color="var(--cat-purple)" />
              : undefined}
          />
          <KpiCard
            label="CACHE_HIT_RATE"
            value={avgCacheHit.toFixed(1)}
            unit="%"
            delta={{ direction: 'flat', label: 'avg across teams' }}
            sparkline={cacheSpark.length > 0
              ? <Sparkline variant="bar" data={cacheSpark} color="var(--good)" />
              : undefined}
          />
          <KpiCard
            label={`TOKENS_${rangeLabel}`}
            value={tokensFmt.value}
            unit={tokensFmt.unit}
            delta={{ direction: 'flat', label: 'all teams combined' }}
          />
          <KpiCard
            label="REQUESTS_60S"
            value={gateway?.requests_last_60s ?? '—'}
            delta={{
              direction: 'flat',
              label: `cache hit ${((gateway?.cache_hit_rate_last_60s ?? 0) * 100).toFixed(1)}%`,
            }}
          />
        </div>

        {/* Middle: activity feed + barlists */}
        <div className="split-2">
          <div className="card">
            <div className="card__head">
              <h3 className="card__title">Recent activity</h3>
              <span className="card__sub">latest admin actions</span>
              <div className="card__actions">
                <Link href="/admin/requests" className="btn btn--sm btn--ghost">Requests →</Link>
                <Link href="/admin/audit" className="btn btn--sm btn--ghost">View all →</Link>
              </div>
            </div>
            <div className="card__body card__body--flush">
              {audit.length === 0 ? (
                <EmptyState
                  title="No recent activity"
                  description="Admin actions will appear here as they happen."
                />
              ) : (
                <table className="tbl">
                  <thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Target</th></tr></thead>
                  <tbody>
                    {audit.map(entry => (
                      <tr key={entry.id}>
                        <td className="mono">{fmtTime(entry.timestamp)}</td>
                        <td>{entry.actor}</td>
                        <td>{entry.action}</td>
                        <td className="cell-2">
                          <span><span className="tag">{entry.resource_type}</span></span>
                          {entry.resource_id ? <span className="lo mono">{entry.resource_id}</span> : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          <div className="stack">
            <div className="card">
              <div className="card__head">
                <h3 className="card__title">Top teams · spend</h3>
                <span className="card__sub">last {range}</span>
                <div className="card__actions">
                  <Link href="/admin/org" className="btn btn--sm btn--ghost">View all →</Link>
                </div>
              </div>
              <div className="card__body" style={{ paddingTop: 8 }}>
                {topTeams.length === 0 ? (
                  <EmptyState title="No spend data" description="No team usage recorded in this range." />
                ) : (
                  <div className="barlist">
                    {topTeams.map(t => {
                      const pct = Math.round(((t.total_cost_usd ?? 0) / maxSpend) * 100);
                      return (
                        <div key={t.team_name} className="row">
                          <div className="lbl">
                            <span className="name">{t.team_name}</span>
                            <span className="bar"><i style={{ width: `${pct}%` }}></i></span>
                          </div>
                          <div className="num">{fmtUsd(t.total_cost_usd)}</div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            <div className="card">
              <div className="card__head">
                <h3 className="card__title">Top models</h3>
                <span className="card__sub">representative · live breakdown coming soon</span>
              </div>
              <div className="card__body" style={{ paddingTop: 8 }}>
                <div className="barlist">
                  {MODEL_MIX.map(m => (
                    <div key={m.label} className="row">
                      <div className="lbl">
                        <span className="name mono">{m.label}</span>
                        <span className="bar"><i style={{ width: `${m.pct}%`, background: m.color }}></i></span>
                      </div>
                      <div className="num">{m.pct}%</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* System performance gauges */}
        <div className="card">
          <div className="card__head">
            <h3 className="card__title">System performance</h3>
            <span className="card__sub">5-min rolling · live</span>
          </div>
          <div className="card__body">
            <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap', justifyContent: 'space-around', padding: '8px 0' }}>

              {/* Gauge 1 — Cache hit rate */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, minWidth: 140 }}>
                <ArcGauge
                  value={(gateway?.cache_hit_rate_last_60s ?? 0)}
                  label="Cache hit rate"
                  sublabel={`${((gateway?.cache_hit_rate_last_60s ?? 0) * 100).toFixed(1)}% · last 60s`}
                  color="var(--cat-teal)"
                />
              </div>

              {/* Gauge 2 — Auto-Drive */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, minWidth: 160 }}>
                <ArcGauge
                  value={gwInfo?.autoroute?.score ?? 0}
                  label="Auto-Drive"
                  sublabel={
                    gwInfo?.autoroute?.enabled
                      ? (gwInfo.autoroute.current_model ?? gwInfo.autoroute.candidates?.[0] ?? 'selecting…')
                      : 'disabled'
                  }
                  color={gwInfo?.autoroute?.enabled ? 'var(--accent)' : 'var(--fg-3)'}
                />
                {gwInfo?.autoroute?.enabled && <Pill variant="good">active</Pill>}
                {gwInfo && !gwInfo.autoroute?.enabled && <Pill>off</Pill>}
              </div>

              {/* Gauge 3 — Workflow runs today */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, minWidth: 140 }}>
                {/* Workflow runs expressed as fraction of a soft daily cap (100 runs) for the arc */}
                <ArcGauge
                  value={Math.min(1, (gwInfo?.workflow_runs_today ?? 0) / 100)}
                  label="Workflow runs today"
                  sublabel={gwInfo != null ? `${gwInfo.workflow_runs_today} run${gwInfo.workflow_runs_today !== 1 ? 's' : ''}` : '—'}
                  color="var(--cat-purple)"
                />
              </div>

            </div>

            {/* Config version badge */}
            {gwInfo && (
              <div style={{ marginTop: 12, borderTop: '1px solid var(--rule)', paddingTop: 10, display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
                <span className="microlabel">Gateway <span className="mono">v{gwInfo.version}</span></span>
                <span className="microlabel">Config <span className="mono">#{gwInfo.config_version}</span></span>
                {gwInfo.features.map(f => (
                  <span key={f} className="tag">{f}</span>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Bottom: service health, infrastructure, alerts */}
        <div className="split-3">
          <div className="card">
            <div className="card__head">
              <h3 className="card__title">Service health</h3>
              <span className="card__sub">live</span>
            </div>
            <div className="card__body card__body--flush">
              {services.length === 0 ? (
                <EmptyState title="No service data" description="Health sweep has not reported yet." />
              ) : (
                <table className="tbl">
                  <tbody>
                    {services.map(svc => (
                      <tr key={svc.service}>
                        <td><span className={statusDotClass(svc.status)}></span>{svc.service}</td>
                        <td className="num mono">{svc.latency_ms != null ? `${svc.latency_ms.toFixed(0)}ms` : '—'}</td>
                        <td><Pill variant={statusPillVariant(svc.status)}>{statusLabel(svc.status)}</Pill></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          <div className="card">
            <div className="card__head">
              <h3 className="card__title">Infrastructure</h3>
              <span className="card__sub">live</span>
            </div>
            <div className="card__body">
              <div className="dl">
                <dt>Redis ping</dt><dd>{redis ? `${redis.ping_ms.toFixed(1)}ms` : '—'}</dd>
                <dt>Redis memory</dt><dd>{redis ? `${redis.used_memory_mb.toFixed(1)} MB` : '—'}</dd>
                <dt>Redis clients</dt><dd>{redis?.connected_clients ?? '—'}</dd>
                <dt>Redis status</dt><dd>{redis?.status ?? '—'}</dd>
                <dt>Postgres status</dt><dd>{health?.postgres?.status ?? '—'}</dd>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card__head">
              <h3 className="card__title">Active alerts</h3>
              <span className="card__sub">{unhealthyServices.length} open</span>
              <div className="card__actions">
                <Link href="/admin/approvals" className="btn btn--sm btn--ghost">Approvals →</Link>
                <Link href="/admin/alerts" className="btn btn--sm btn--ghost">View all →</Link>
              </div>
            </div>
            <div className="card__body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {unhealthyServices.length === 0 ? (
                <EmptyState
                  title="All systems healthy"
                  description="No active alerts at this time."
                />
              ) : unhealthyServices.map(svc => {
                const tone = svc.status === 'degraded' ? 'warn' : 'bad';
                return (
                  <div key={svc.service} style={{ display: 'flex', gap: 10, padding: 10, border: '1px solid var(--rule)', borderRadius: 6, background: `var(--${tone}-soft)` }}>
                    <span className={`statusdot statusdot--${tone}`} style={{ marginTop: 5 }}></span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600, fontSize: 12.5 }}>{svc.service} — {svc.status}</div>
                      <div className="muted" style={{ fontSize: 11.5 }}>
                        {svc.error ?? `HTTP ${svc.code} · ${svc.latency_ms != null ? `${svc.latency_ms.toFixed(0)}ms` : 'no latency data'}`}
                      </div>
                    </div>
                    <Link href="/admin/alerts" className="btn btn--sm">Investigate</Link>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
