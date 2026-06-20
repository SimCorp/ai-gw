'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { EmptyState } from '../_components/PageStates';

const BASE = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

type Period = '7d' | '30d' | '90d' | 'mtd' | 'all';
type GroupBy = 'area' | 'team' | 'model';

interface AreaRow {
  area_id: string;
  area_name: string;
  area_color: string;
  request_count: number;
  total_tokens: number;
  total_cost_usd: number;
  cache_hit_pct: number;
}

interface TeamRow {
  team_id: string;
  team_name: string;
  area_id: string;
  area_name: string;
  area_color: string;
  request_count: number;
  total_tokens: number;
  total_cost_usd: number;
  cache_hit_pct: number;
}

interface ModelRow {
  model: string;
  request_count: number;
  total_tokens: number;
  total_cost_usd: number;
}

type ReportRow = AreaRow | TeamRow | ModelRow;

function formatCost(usd: number): string {
  if (usd === 0) return '€0.00';
  if (usd < 0.01) return `€${usd.toFixed(4)}`;
  return `€${usd.toFixed(2)}`;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function CacheBar({ pct }: { pct: number }) {
  const clamped = Math.min(Math.max(pct, 0), 100);
  const color = clamped >= 30 ? 'var(--good)' : clamped >= 15 ? 'var(--warn)' : 'var(--bad)';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span className="mono" style={{ fontSize: 12, minWidth: 36 }}>{clamped.toFixed(1)}%</span>
      <span style={{
        display: 'inline-block', width: 48, height: 4,
        background: 'var(--surface-soft)', borderRadius: 2,
        position: 'relative', overflow: 'hidden',
      }}>
        <span style={{
          position: 'absolute', inset: `0 ${100 - clamped}% 0 0`,
          background: color, borderRadius: 2,
        }} />
      </span>
    </div>
  );
}

function ColorDot({ color }: { color: string }) {
  return (
    <span style={{
      display: 'inline-block', width: 8, height: 8, borderRadius: 2,
      background: color, flexShrink: 0, marginRight: 6,
    }} />
  );
}

function KpiStrip({ rows, groupBy }: { rows: ReportRow[]; groupBy: GroupBy }) {
  if (groupBy === 'model') return null;

  const typed = rows as (AreaRow | TeamRow)[];
  const totalCost = typed.reduce((s, r) => s + r.total_cost_usd, 0);
  const totalRequests = typed.reduce((s, r) => s + r.request_count, 0);
  const totalTokens = typed.reduce((s, r) => s + r.total_tokens, 0);
  const avgCacheHit = typed.length > 0
    ? typed.reduce((s, r) => s + r.cache_hit_pct, 0) / typed.length
    : 0;

  return (
    <div className="kpi-grid" style={{ marginBottom: 18 }}>
      <div className="kpi">
        <div className="kpi__label">Total cost</div>
        <div className="kpi__value">{formatCost(totalCost)}</div>
        <div className="kpi__delta flat">selected period</div>
      </div>
      <div className="kpi">
        <div className="kpi__label">Total requests</div>
        <div className="kpi__value">{totalRequests.toLocaleString()}</div>
        <div className="kpi__delta flat">gateway calls</div>
      </div>
      <div className="kpi">
        <div className="kpi__label">Total tokens</div>
        <div className="kpi__value">{formatTokens(totalTokens)}</div>
        <div className="kpi__delta flat">in + out</div>
      </div>
      <div className="kpi">
        <div className="kpi__label">Avg cache hit</div>
        <div className="kpi__value">{avgCacheHit.toFixed(1)}%</div>
        <div className="kpi__delta flat">semantic cache</div>
      </div>
    </div>
  );
}

function AreaTable({ rows }: { rows: AreaRow[] }) {
  const totalCost = rows.reduce((s, r) => s + r.total_cost_usd, 0);
  return (
    <div className="card">
      <div className="card__body" style={{ padding: 0 }}>
        <table className="tbl">
          <thead>
            <tr>
              <th>Area</th>
              <th className="num">Requests</th>
              <th className="num">Tokens</th>
              <th className="num">Cost</th>
              <th>Cache hit</th>
              <th className="num">Share</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => {
              const share = totalCost > 0 ? (r.total_cost_usd / totalCost) * 100 : 0;
              return (
                <tr key={r.area_id}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center' }}>
                      <ColorDot color={r.area_color} />
                      <span style={{ fontWeight: 500 }}>{r.area_name}</span>
                    </div>
                  </td>
                  <td className="num mono">{r.request_count.toLocaleString()}</td>
                  <td className="num mono">{formatTokens(r.total_tokens)}</td>
                  <td className="num mono" style={{ fontWeight: 500 }}>{formatCost(r.total_cost_usd)}</td>
                  <td><CacheBar pct={r.cache_hit_pct} /></td>
                  <td className="num mono">{share.toFixed(1)}%</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TeamTable({ rows }: { rows: TeamRow[] }) {
  const totalCost = rows.reduce((s, r) => s + r.total_cost_usd, 0);

  // Group by area
  const areaOrder: string[] = [];
  const byArea = new Map<string, TeamRow[]>();
  for (const r of rows) {
    if (!byArea.has(r.area_id)) {
      areaOrder.push(r.area_id);
      byArea.set(r.area_id, []);
    }
    byArea.get(r.area_id)!.push(r);
  }

  return (
    <div className="card">
      <div className="card__body" style={{ padding: 0 }}>
        <table className="tbl">
          <thead>
            <tr>
              <th>Area</th>
              <th>Team</th>
              <th className="num">Requests</th>
              <th className="num">Tokens</th>
              <th className="num">Cost</th>
              <th>Cache hit</th>
              <th className="num">Share</th>
            </tr>
          </thead>
          <tbody>
            {areaOrder.map(areaId => {
              const areaRows = byArea.get(areaId)!;
              const firstRow = areaRows[0];
              return (
                <React.Fragment key={areaId}>
                  <tr style={{ background: 'var(--surface-2)' }}>
                    <td colSpan={7} style={{ padding: '6px 12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center' }}>
                        <ColorDot color={firstRow.area_color} />
                        <span style={{ fontWeight: 600, fontSize: 12.5, color: 'var(--fg-2)' }}>
                          {firstRow.area_name}
                        </span>
                      </div>
                    </td>
                  </tr>
                  {areaRows.map(r => {
                    const share = totalCost > 0 ? (r.total_cost_usd / totalCost) * 100 : 0;
                    return (
                      <tr key={r.team_id}>
                        <td></td>
                        <td style={{ fontWeight: 500 }}>{r.team_name}</td>
                        <td className="num mono">{r.request_count.toLocaleString()}</td>
                        <td className="num mono">{formatTokens(r.total_tokens)}</td>
                        <td className="num mono" style={{ fontWeight: 500 }}>{formatCost(r.total_cost_usd)}</td>
                        <td><CacheBar pct={r.cache_hit_pct} /></td>
                        <td className="num mono">{share.toFixed(1)}%</td>
                      </tr>
                    );
                  })}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ModelTable({ rows }: { rows: ModelRow[] }) {
  const totalCost = rows.reduce((s, r) => s + r.total_cost_usd, 0);
  return (
    <div className="card">
      <div className="card__body" style={{ padding: 0 }}>
        <table className="tbl">
          <thead>
            <tr>
              <th>Model</th>
              <th className="num">Requests</th>
              <th className="num">Tokens</th>
              <th className="num">Cost</th>
              <th className="num">Share</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => {
              const share = totalCost > 0 ? (r.total_cost_usd / totalCost) * 100 : 0;
              return (
                <tr key={r.model}>
                  <td><span className="mono" style={{ fontWeight: 500 }}>{r.model}</span></td>
                  <td className="num mono">{r.request_count.toLocaleString()}</td>
                  <td className="num mono">{formatTokens(r.total_tokens)}</td>
                  <td className="num mono" style={{ fontWeight: 500 }}>{formatCost(r.total_cost_usd)}</td>
                  <td className="num mono">{share.toFixed(1)}%</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function isAllZeros(rows: ReportRow[]): boolean {
  return rows.every(r => r.total_cost_usd === 0 && r.request_count === 0);
}

export default function ReportsPage() {
  const [period, setPeriod] = useState<Period>('30d');
  const [groupBy, setGroupBy] = useState<GroupBy>('area');

  const reportQuery = useQuery<ReportRow[]>({
    queryKey: ['cost-report', groupBy, period],
    queryFn: () =>
      fetch(`${BASE}/reports/cost?group_by=${groupBy}&period=${period}`)
        .then(r => {
          if (!r.ok) throw new Error(`Failed to fetch report: ${r.status}`);
          return r.json();
        }),
    staleTime: 60_000,
  });

  const rows = reportQuery.data ?? [];

  const PERIODS: { value: Period; label: string }[] = [
    { value: '7d', label: '7d' },
    { value: '30d', label: '30d' },
    { value: '90d', label: '90d' },
    { value: 'mtd', label: 'MTD' },
    { value: 'all', label: 'All' },
  ];

  const GROUPS: { value: GroupBy; label: string }[] = [
    { value: 'area', label: 'Area' },
    { value: 'team', label: 'Team' },
    { value: 'model', label: 'Model' },
  ];

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Cost Reports</h1>
          <p className="page__sub">Spending breakdown by area, team, and model</p>
        </div>
      </div>

      <div className="filters" style={{ marginBottom: 18 }}>
        <div className="seg">
          {PERIODS.map(p => (
            <button
              key={p.value}
              className={period === p.value ? 'is-active' : undefined}
              onClick={() => setPeriod(p.value)}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="seg">
          {GROUPS.map(g => (
            <button
              key={g.value}
              className={groupBy === g.value ? 'is-active' : undefined}
              onClick={() => setGroupBy(g.value)}
            >
              {g.label}
            </button>
          ))}
        </div>
      </div>

      {reportQuery.isLoading && (
        <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--fg-3)', fontSize: 13 }}>
          Loading report…
        </div>
      )}

      {reportQuery.isError && (
        <div style={{ padding: '32px 0', textAlign: 'center', color: 'var(--bad)', fontSize: 13 }}>
          Failed to load report. {(reportQuery.error as Error).message}
        </div>
      )}

      {!reportQuery.isLoading && !reportQuery.isError && (
        <>
          {rows.length === 0 || isAllZeros(rows) ? (
            <EmptyState message="No cost data for this period. Requests appear here once the gateway processes traffic." />
          ) : (
            <>
              <KpiStrip rows={rows} groupBy={groupBy} />
              {groupBy === 'area' && <AreaTable rows={rows as AreaRow[]} />}
              {groupBy === 'team' && <TeamTable rows={rows as TeamRow[]} />}
              {groupBy === 'model' && <ModelTable rows={rows as ModelRow[]} />}
            </>
          )}
        </>
      )}
    </section>
  );
}
