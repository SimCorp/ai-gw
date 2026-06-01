'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
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

function ArcGauge({ value, label, sublabel, color = 'var(--sc-blue)', size = 100 }: GaugeProps) {
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

function statusPillClass(status: string) {
  if (status === 'ok') return 'pill pill--good';
  if (status === 'degraded') return 'pill pill--warn';
  return 'pill pill--bad';
}

function statusLabel(status: string) {
  if (status === 'ok') return 'healthy';
  return status;
}

export default function DashboardPage() {
  const [range, setRange] = useState('24h');

  const statsQuery = useQuery<TeamStat[]>({
    queryKey: ['dashboard-stats'],
    queryFn: () => apiFetch<TeamStat[]>('/dashboard/stats'),
    staleTime: 30_000,
  });

  const healthQuery = useQuery<SystemHealth>({
    queryKey: ['system-health'],
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

  // Gateway stats
  const gateway = health?.gateway;
  const redis = health?.redis;
  const gwInfo = gatewayInfoQuery.data;

  // Services for provider health table
  const services: ServiceHealth[] = health?.services ?? [];

  // Active alerts derived from unhealthy services
  const unhealthyServices = services.filter(s => s.status !== 'ok');

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Platform overview</h1>
          <p className="page__sub">Org-wide usage, cost, and health · last 24 hours</p>
        </div>
        <div className="page__actions">
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
          <button className="btn">Export</button>
        </div>
      </div>

      {/* KPI row 1 */}
      <div className="kpi-grid" style={{ marginBottom: 16 }}>
        <div className="kpi">
          <div className="kpi__label">Total spend</div>
          <div className="kpi__value">{fmtUsd(totalSpend)}</div>
          <div className="kpi__delta flat">{stats.length} teams · all time</div>
          <svg className="spark kpi__spark" viewBox="0 0 100 28" preserveAspectRatio="none">
            <path d="M0,18 L10,16 L20,20 L30,12 L40,15 L50,9 L60,13 L70,8 L80,11 L90,6 L100,9" fill="none" stroke="var(--sc-blue)" strokeWidth="1.5"/>
            <path d="M0,18 L10,16 L20,20 L30,12 L40,15 L50,9 L60,13 L70,8 L80,11 L90,6 L100,9 L100,28 L0,28 Z" fill="var(--sc-blue)" opacity="0.08"/>
          </svg>
        </div>
        <div className="kpi">
          <div className="kpi__label">Cache hit rate</div>
          <div className="kpi__value">{avgCacheHit.toFixed(1)}<span className="unit">%</span></div>
          <div className="kpi__delta flat">avg across teams</div>
          <svg className="spark kpi__spark" viewBox="0 0 100 28" preserveAspectRatio="none">
            <path d="M0,22 L10,20 L20,18 L30,16 L40,14 L50,12 L60,11 L70,9 L80,7 L90,5 L100,4" fill="none" stroke="var(--good)" strokeWidth="1.5"/>
            <path d="M0,22 L10,20 L20,18 L30,16 L40,14 L50,12 L60,11 L70,9 L80,7 L90,5 L100,4 L100,28 L0,28 Z" fill="var(--good)" opacity="0.10"/>
          </svg>
        </div>
        <div className="kpi">
          <div className="kpi__label">Requests</div>
          <div className="kpi__value">
            {totalRequests >= 1_000_000
              ? <>{(totalRequests / 1_000_000).toFixed(2)}<span className="unit">M</span></>
              : totalRequests >= 1_000
              ? <>{(totalRequests / 1_000).toFixed(1)}<span className="unit">k</span></>
              : <>{totalRequests}</>}
          </div>
          <div className="kpi__delta flat">total · all teams</div>
          <svg className="spark kpi__spark" viewBox="0 0 100 28" preserveAspectRatio="none">
            <path d="M0,15 L8,18 L16,12 L24,16 L32,10 L40,14 L48,8 L56,12 L64,6 L72,10 L80,5 L88,9 L100,4" fill="none" stroke="var(--sc-purple)" strokeWidth="1.5"/>
          </svg>
        </div>
        <div className="kpi">
          <div className="kpi__label">Requests last 60s</div>
          <div className="kpi__value">{gateway?.requests_last_60s ?? '—'}</div>
          <div className="kpi__delta flat">cache hit {((gateway?.cache_hit_rate_last_60s ?? 0) * 100).toFixed(1)}%</div>
          <svg className="spark kpi__spark" viewBox="0 0 100 28" preserveAspectRatio="none">
            <path d="M0,14 L10,16 L20,12 L30,15 L40,11 L50,14 L60,12 L70,15 L80,13 L90,16 L100,14" fill="none" stroke="var(--fg-2)" strokeWidth="1.5"/>
          </svg>
        </div>
      </div>

      {/* KPI row 2 */}
      <div className="kpi-grid" style={{ gridTemplateColumns: 'repeat(4,1fr)', marginBottom: 20 }}>
        <div className="kpi">
          <div className="kpi__label">Total tokens</div>
          <div className="kpi__value">
            {totalTokens >= 1_000_000
              ? <>{(totalTokens / 1_000_000).toFixed(1)}<span className="unit">M</span></>
              : totalTokens >= 1_000
              ? <>{(totalTokens / 1_000).toFixed(1)}<span className="unit">k</span></>
              : <>{totalTokens}</>}
          </div>
          <div className="kpi__delta flat">all teams combined</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Redis memory</div>
          <div className="kpi__value">{redis ? `${redis.used_memory_mb.toFixed(0)}` : '—'}<span className="unit">MB</span></div>
          <div className="kpi__delta flat">{redis ? `ping ${redis.ping_ms.toFixed(1)}ms` : 'unavailable'}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">System status</div>
          <div className="kpi__value" style={{ color: health?.overall === 'ok' ? 'var(--good)' : 'var(--bad)', fontSize: 18, paddingTop: 4 }}>
            {health?.overall ?? '—'}
          </div>
          <div className="kpi__delta flat">{health?.last_updated ?? ''}</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Teams tracked</div>
          <div className="kpi__value">{stats.length}</div>
          <div className="kpi__delta flat">with spend data</div>
        </div>
      </div>

      {/* System Performance gauges */}
      <div className="card" style={{ marginBottom: 16 }}>
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
                color="var(--sc-teal)"
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
                color={gwInfo?.autoroute?.enabled ? 'var(--sc-blue)' : 'var(--fg-3)'}
              />
              {gwInfo?.autoroute?.enabled && (
                <span className="pill pill--good" style={{ fontSize: 10 }}>active</span>
              )}
              {gwInfo && !gwInfo.autoroute?.enabled && (
                <span className="pill" style={{ fontSize: 10 }}>off</span>
              )}
            </div>

            {/* Gauge 3 — Workflow runs today */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, minWidth: 140 }}>
              {/* Workflow runs expressed as fraction of a soft daily cap (100 runs) for the arc */}
              <ArcGauge
                value={Math.min(1, (gwInfo?.workflow_runs_today ?? 0) / 100)}
                label="Workflow runs today"
                sublabel={gwInfo != null ? `${gwInfo.workflow_runs_today} run${gwInfo.workflow_runs_today !== 1 ? 's' : ''}` : '—'}
                color="var(--sc-purple)"
              />
            </div>

          </div>

          {/* Config version badge */}
          {gwInfo && (
            <div style={{ marginTop: 12, borderTop: '1px solid var(--rule)', paddingTop: 10, display: 'flex', gap: 16, fontSize: 11.5, color: 'var(--fg-3)', flexWrap: 'wrap' }}>
              <span>Gateway <span className="mono">v{gwInfo.version}</span></span>
              <span>Config version <span className="mono">#{gwInfo.config_version}</span></span>
              {gwInfo.features.map(f => (
                <span key={f} className="tag">{f}</span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Charts row */}
      <div className="split-2" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="card__head">
            <h3 className="card__title">Request volume &amp; cache hits</h3>
            <span className="card__sub">stacked, requests/min</span>
            <div className="card__actions">
              <span className="pill"><span className="dot" style={{ background: 'var(--sc-blue)' }}></span>Provider</span>
              <span className="pill"><span className="dot" style={{ background: 'var(--sc-teal)' }}></span>Cache hit</span>
            </div>
          </div>
          <div className="card__body">
            <svg viewBox="0 0 800 240" preserveAspectRatio="none" style={{ width: '100%', height: 240, display: 'block' }}>
              <g stroke="var(--rule)" strokeWidth="1">
                <line x1="40" y1="20" x2="780" y2="20"/><line x1="40" y1="70" x2="780" y2="70"/>
                <line x1="40" y1="120" x2="780" y2="120"/><line x1="40" y1="170" x2="780" y2="170"/><line x1="40" y1="220" x2="780" y2="220"/>
              </g>
              <g fill="var(--fg-3)" fontSize="10" fontFamily="var(--font-mono)">
                <text x="36" y="24" textAnchor="end">120</text><text x="36" y="74" textAnchor="end">90</text>
                <text x="36" y="124" textAnchor="end">60</text><text x="36" y="174" textAnchor="end">30</text><text x="36" y="224" textAnchor="end">0</text>
              </g>
              <path d="M40,170 L80,150 L120,140 L160,155 L200,130 L240,135 L280,110 L320,115 L360,95 L400,100 L440,80 L480,90 L520,70 L560,85 L600,60 L640,75 L680,55 L720,72 L760,50 L780,60 L780,220 L40,220 Z" fill="var(--sc-blue)" opacity="0.85"/>
              <path d="M40,150 L80,135 L120,125 L160,138 L200,115 L240,118 L280,95 L320,100 L360,80 L400,86 L440,65 L480,75 L520,55 L560,68 L600,42 L640,58 L680,38 L720,55 L760,32 L780,42 L780,60 L760,50 L720,72 L680,55 L640,75 L600,60 L560,85 L520,70 L480,90 L440,80 L400,100 L360,95 L320,115 L280,110 L240,135 L200,130 L160,155 L120,140 L80,150 L40,170 Z" fill="var(--sc-teal)" opacity="0.85"/>
              <g fill="var(--fg-3)" fontSize="10" fontFamily="var(--font-mono)">
                <text x="40" y="234">06:00</text><text x="225" y="234">12:00</text>
                <text x="410" y="234">18:00</text><text x="600" y="234">00:00</text>
                <text x="760" y="234" textAnchor="end">now</text>
              </g>
            </svg>
          </div>
        </div>

        <div className="card">
          <div className="card__head">
            <h3 className="card__title">Top teams · spend</h3>
            <span className="card__sub">all time</span>
            <div className="card__actions">
              <Link href="/admin/org" className="btn btn--sm btn--ghost">View all →</Link>
            </div>
          </div>
          <div className="card__body" style={{ paddingTop: 8 }}>
            {topTeams.length === 0 ? (
              <div className="muted" style={{ fontSize: 13 }}>No spend data available.</div>
            ) : (
              <div className="barlist">
                {topTeams.map(t => {
                  const barPct = maxSpend > 0 ? Math.round((1 - (t.total_cost_usd ?? 0) / maxSpend) * 100) : 100;
                  return (
                    <div key={t.team_name} className="row">
                      <div className="lbl">
                        <span className="name">{t.team_name}</span>
                        <span className="bar"><i style={{ right: `${barPct}%` }}></i></span>
                      </div>
                      <div className="num">{fmtUsd(t.total_cost_usd)}</div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 3-col row */}
      <div className="split-3" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="card__head"><h3 className="card__title">Model mix</h3><span className="card__sub">by spend</span></div>
          <div className="card__body">
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <svg viewBox="0 0 80 80" width="100" height="100" style={{ flexShrink: 0 }}>
                <circle cx="40" cy="40" r="32" fill="none" stroke="var(--rule)" strokeWidth="14"/>
                <circle cx="40" cy="40" r="32" fill="none" stroke="var(--sc-blue)" strokeWidth="14" strokeDasharray="92 200" strokeDashoffset="0" transform="rotate(-90 40 40)"/>
                <circle cx="40" cy="40" r="32" fill="none" stroke="var(--sc-teal)" strokeWidth="14" strokeDasharray="58 200" strokeDashoffset="-92" transform="rotate(-90 40 40)"/>
                <circle cx="40" cy="40" r="32" fill="none" stroke="var(--sc-purple)" strokeWidth="14" strokeDasharray="32 200" strokeDashoffset="-150" transform="rotate(-90 40 40)"/>
                <circle cx="40" cy="40" r="32" fill="none" stroke="var(--sc-orange)" strokeWidth="14" strokeDasharray="19 200" strokeDashoffset="-182" transform="rotate(-90 40 40)"/>
              </svg>
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12 }}>
                {[
                  { color: 'var(--sc-blue)', label: 'claude-sonnet-4.5', pct: '46%' },
                  { color: 'var(--sc-teal)', label: 'gemini-2.5-pro', pct: '29%' },
                  { color: 'var(--sc-purple)', label: 'claude-haiku-4.5', pct: '16%' },
                  { color: 'var(--sc-orange)', label: 'gpt-5 (BYO)', pct: '9%' },
                ].map(m => (
                  <div key={m.label} style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span><span className="statusdot" style={{ background: m.color, boxShadow: 'none' }}></span>{m.label}</span>
                    <span className="mono">{m.pct}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card__head"><h3 className="card__title">Provider health</h3><span className="card__sub">live</span></div>
          <div className="card__body" style={{ padding: 0 }}>
            {services.length === 0 ? (
              <div className="muted" style={{ fontSize: 13, padding: 12 }}>No service data available.</div>
            ) : (
              <table className="tbl">
                <tbody>
                  {services.map(svc => (
                    <tr key={svc.service}>
                      <td><span className={statusDotClass(svc.status)}></span>{svc.service}</td>
                      <td className="num mono">{svc.latency_ms != null ? `${svc.latency_ms.toFixed(0)}ms` : '—'}</td>
                      <td><span className={statusPillClass(svc.status)}>{statusLabel(svc.status)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card__head"><h3 className="card__title">Infrastructure</h3><span className="card__sub">live</span></div>
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
      </div>

      {/* Bottom row */}
      <div className="split-2">
        <div className="card">
          <div className="card__head">
            <h3 className="card__title">Recent activity</h3>
            <div className="card__actions"><Link href="/admin/audit" className="btn btn--sm btn--ghost">Audit log →</Link></div>
          </div>
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Target</th></tr></thead>
              <tbody>
                {audit.length === 0 ? (
                  <tr><td colSpan={4} className="muted" style={{ textAlign: 'center', padding: 12 }}>No recent activity.</td></tr>
                ) : audit.map(entry => (
                  <tr key={entry.id}>
                    <td className="mono">{fmtTime(entry.timestamp)}</td>
                    <td>{entry.actor}</td>
                    <td>{entry.action}</td>
                    <td>
                      <span className="tag">{entry.resource_type}</span>
                      {entry.resource_id ? ` · ${entry.resource_id}` : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <div className="card__head">
            <h3 className="card__title">Active alerts</h3>
            <span className="card__sub">{unhealthyServices.length} open</span>
          </div>
          <div className="card__body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {unhealthyServices.length === 0 ? (
              <div style={{ display: 'flex', gap: 10, padding: 10, border: '1px solid var(--rule)', borderRadius: 6, background: 'var(--good-soft)' }}>
                <span className="statusdot statusdot--good" style={{ marginTop: 5 }}></span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 12.5 }}>All systems healthy</div>
                  <div className="muted" style={{ fontSize: 11.5 }}>No active alerts at this time.</div>
                </div>
              </div>
            ) : unhealthyServices.map(svc => {
              const color = svc.status === 'degraded' ? 'warn' : 'bad';
              return (
                <div key={svc.service} style={{ display: 'flex', gap: 10, padding: 10, border: '1px solid var(--rule)', borderRadius: 6, background: `var(--${color}-soft)` }}>
                  <span className={`statusdot statusdot--${color}`} style={{ marginTop: 5 }}></span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 12.5 }}>{svc.service} — {svc.status}</div>
                    <div className="muted" style={{ fontSize: 11.5 }}>
                      {svc.error ?? `HTTP ${svc.code} · ${svc.latency_ms != null ? `${svc.latency_ms.toFixed(0)}ms` : 'no latency data'}`}
                    </div>
                  </div>
                  <button className="btn btn--sm">Investigate</button>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
