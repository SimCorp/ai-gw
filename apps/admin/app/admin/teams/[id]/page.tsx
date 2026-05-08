'use client';

import React, { use, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { LoadingState, ErrorState } from '../../_components/PageStates';

const BASE = 'http://localhost:8005';

interface Team {
  id: string;
  slug: string;
  name: string;
  created_at: string;
  monthly_budget_usd: number | null;
  budget_alert_pct: number;
  budget_action: string;
}

interface ApiKey {
  id: string;
  team_id: string;
  name: string;
  key_hash: string;
  revoked_at: string | null;
  monthly_budget_usd: number | null;
  project_id: string | null;
  created_at: string;
}

interface Member {
  id: string;
  team_id: string;
  user_id: string;
  role: string;
  joined_at: string | null;
  developer_id: string | null;
}

interface DashboardStat {
  team_name: string;
  request_count: number | null;
  total_tokens: number | null;
  total_cost_usd: number | null;
  cache_hit_pct: number | null;
}

interface AuditRow {
  id: string;
  actor: string;
  action: string;
  resource_id: string;
  resource_type: string;
  details: Record<string, unknown> | null;
  timestamp: string;
}

const TABS = ['overview', 'keys', 'policies', 'members', 'audit'] as const;
type Tab = typeof TABS[number];

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch { return iso; }
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch { return iso; }
}

function formatCost(usd: number | null | undefined): string {
  if (usd == null) return '$0.00';
  if (usd === 0) return '$0.00';
  if (usd < 0.01) return `$${usd.toFixed(6)}`;
  if (usd < 1) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

function initials2(s: string) {
  return s.split(/[-._\s]/).filter(Boolean).slice(0, 2).map(p => p[0]).join('').toUpperCase();
}

const COLORS = ['#083EA7','#1D958E','#4B17B6','#FB9B2A','#9D2E7B','#0A7BD7','#1A1D31','#EF3E4A'];
function avatarColor(seed: string): string {
  let h = 0;
  for (const c of seed) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return COLORS[h % COLORS.length];
}

export default function TeamDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [tab, setTab] = useState<Tab>('overview');
  const [newKeyValue, setNewKeyValue] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const teamQuery = useQuery<Team>({
    queryKey: ['team', id],
    queryFn: () => fetch(`${BASE}/teams/${id}`).then(r => {
      if (!r.ok) throw new Error(`Team not found (${r.status})`);
      return r.json();
    }),
  });

  const keysQuery = useQuery<ApiKey[]>({
    queryKey: ['team-keys', id],
    queryFn: () => fetch(`${BASE}/teams/${id}/keys`).then(r => {
      if (!r.ok) throw new Error(`Failed to fetch keys: ${r.status}`);
      return r.json();
    }),
  });

  const membersQuery = useQuery<Member[]>({
    queryKey: ['team-members', id],
    queryFn: () => fetch(`${BASE}/teams/${id}/members`).then(r => {
      if (!r.ok) throw new Error(`Failed to fetch members: ${r.status}`);
      return r.json();
    }),
  });

  const statsQuery = useQuery<DashboardStat[]>({
    queryKey: ['dashboard-stats'],
    queryFn: () => fetch(`${BASE}/dashboard/stats`).then(r => {
      if (!r.ok) throw new Error(`Failed to fetch stats: ${r.status}`);
      return r.json();
    }),
    staleTime: 30_000,
  });

  const auditQuery = useQuery<AuditRow[]>({
    queryKey: ['team-audit', id],
    queryFn: () => fetch(`${BASE}/audit?resource_id=${id}&limit=50`).then(r => {
      if (!r.ok) throw new Error(`Failed to fetch audit: ${r.status}`);
      return r.json();
    }),
    enabled: tab === 'audit',
  });

  if (teamQuery.isLoading) return <section className="page"><LoadingState rows={8} /></section>;
  if (teamQuery.isError) return <section className="page"><ErrorState error={teamQuery.error as Error} retry={() => teamQuery.refetch()} /></section>;

  const team = teamQuery.data!;
  const keys = keysQuery.data ?? [];
  const members = membersQuery.data ?? [];
  const stats = Array.isArray(statsQuery.data) ? statsQuery.data : [];
  const stat = stats.find(s => s.team_name === team.name) ?? null;
  const auditRows = auditQuery.data ?? [];

  const activeKeys = keys.filter(k => !k.revoked_at);

  const budgetPct = stat?.total_cost_usd != null && team.monthly_budget_usd
    ? Math.min(Math.round((stat.total_cost_usd / team.monthly_budget_usd) * 100), 100)
    : null;

  async function handleIssueKey() {
    const name = window.prompt('API key name:');
    if (!name?.trim()) return;
    const res = await fetch(`${BASE}/teams/${id}/keys`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim() }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      window.alert(`Failed to create key: ${(err as {detail?: string}).detail ?? res.status}`);
      return;
    }
    const data = await res.json() as { key: string };
    setNewKeyValue(data.key);
    queryClient.invalidateQueries({ queryKey: ['team-keys', id] });
  }

  async function handleRevokeKey(keyId: string, keyName: string) {
    if (!window.confirm(`Revoke key "${keyName}"? This cannot be undone.`)) return;
    const res = await fetch(`${BASE}/teams/${id}/keys/${keyId}`, { method: 'DELETE' });
    if (!res.ok) {
      window.alert(`Failed to revoke key: ${res.status}`);
      return;
    }
    queryClient.invalidateQueries({ queryKey: ['team-keys', id] });
  }

  return (
    <section className="page">
      {/* New key reveal banner */}
      {newKeyValue && (
        <div style={{
          background: 'var(--warn-soft, rgba(249,115,22,0.08))',
          border: '1px solid var(--warn, #f97316)',
          borderRadius: 8, padding: '12px 16px', marginBottom: 16,
          display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
        }}>
          <span style={{ color: 'var(--warn)', fontWeight: 600, fontSize: 13 }}>
            Save this key — shown once only:
          </span>
          <code className="mono" style={{ flex: 1, fontSize: 13, wordBreak: 'break-all' }}>{newKeyValue}</code>
          <button className="btn btn--sm" onClick={() => {
            navigator.clipboard.writeText(newKeyValue).catch(() => {});
          }}>Copy</button>
          <button className="btn btn--sm btn--ghost" onClick={() => setNewKeyValue(null)}>Dismiss</button>
        </div>
      )}

      <div className="page__head">
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <span style={{
            display: 'grid', placeItems: 'center',
            width: 36, height: 36, borderRadius: 8,
            background: avatarColor(team.name),
            color: '#fff', fontWeight: 700, fontSize: 13,
          }}>{initials2(team.name)}</span>
          <div>
            <h1 className="page__title">
              {team.name}
              <span style={{ color: 'var(--fg-3)', fontWeight: 400, fontSize: 13, marginLeft: 8 }} className="mono">
                {team.id.slice(0, 8)}
              </span>
            </h1>
            <p className="page__sub">
              Slug <strong>{team.slug}</strong> · {activeKeys.length} active key{activeKeys.length !== 1 ? 's' : ''} · created {formatDate(team.created_at)}
            </p>
          </div>
        </div>
        <div className="page__actions">
          <button className="btn">Edit</button>
          <button className="btn btn--primary" onClick={handleIssueKey}>+ Issue API key</button>
        </div>
      </div>

      {/* Minimet strip */}
      <div className="minimet-row" style={{ marginBottom: 18 }}>
        <div className="minimet">
          <div className="minimet__l">Spend MTD</div>
          <div className="minimet__v">{formatCost(stat?.total_cost_usd)}</div>
        </div>
        <div className="minimet">
          <div className="minimet__l">Budget cap</div>
          <div className="minimet__v">
            {team.monthly_budget_usd != null ? `$${team.monthly_budget_usd}` : 'None'}
          </div>
        </div>
        <div className="minimet">
          <div className="minimet__l">Budget used</div>
          <div className="minimet__v">{budgetPct != null ? `${budgetPct}%` : '—'}</div>
        </div>
        <div className="minimet">
          <div className="minimet__l">Requests</div>
          <div className="minimet__v">{(stat?.request_count ?? 0).toLocaleString()}</div>
        </div>
        <div className="minimet">
          <div className="minimet__l">Cache hit</div>
          <div className="minimet__v">
            {stat?.cache_hit_pct != null ? `${Math.round(stat.cache_hit_pct)}` : '—'}
            <span className="unit">%</span>
          </div>
        </div>
        <div className="minimet">
          <div className="minimet__l">Tokens</div>
          <div className="minimet__v">
            {stat?.total_tokens != null ? (stat.total_tokens >= 1000 ? `${(stat.total_tokens / 1000).toFixed(1)}k` : stat.total_tokens.toString()) : '—'}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <nav className="tabbar">
        {(['overview', 'keys', 'policies', 'members', 'audit'] as Tab[]).map(t => (
          <a key={t} href={`#${t}`}
            className={tab === t ? 'is-active' : undefined}
            onClick={e => { e.preventDefault(); setTab(t); }}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
            {t === 'keys' && <span className="tag" style={{ marginLeft: 6 }}>{activeKeys.length}</span>}
            {t === 'members' && <span className="tag" style={{ marginLeft: 6 }}>{members.length}</span>}
          </a>
        ))}
      </nav>
      <div style={{ height: 18 }} />

      {/* ── OVERVIEW ── */}
      {tab === 'overview' && (
        <>
          <div className="split-2" style={{ marginBottom: 16 }}>
            <div className="card">
              <div className="card__head">
                <h3 className="card__title">Spend</h3>
                <span className="card__sub">month-to-date{team.monthly_budget_usd != null ? ` · vs $${team.monthly_budget_usd} cap` : ''}</span>
              </div>
              <div className="card__body">
                <svg viewBox="0 0 600 180" preserveAspectRatio="none" style={{ width: '100%', height: 180, display: 'block' }}>
                  <g stroke="var(--rule)" strokeWidth="1">
                    <line x1="0" y1="20" x2="600" y2="20"/>
                    <line x1="0" y1="70" x2="600" y2="70"/>
                    <line x1="0" y1="120" x2="600" y2="120"/>
                    <line x1="0" y1="160" x2="600" y2="160"/>
                  </g>
                  {team.monthly_budget_usd != null && (
                    <line x1="0" y1="38" x2="600" y2="38" stroke="var(--bad)" strokeWidth="1" strokeDasharray="4 3"/>
                  )}
                  <g fill="var(--sc-blue)">
                    {Array.from({ length: 30 }).map((_, i) => {
                      const v = Math.min(8 + i * 0.5 + (i % 4) * 0.8, 26);
                      const h = v * 4.5; const x = 4 + i * 20; const y = 160 - h;
                      return <rect key={i} x={x} y={y} width="14" height={h} rx="2"/>;
                    })}
                  </g>
                </svg>
                <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                  Decorative trend · MTD spend: <strong>{formatCost(stat?.total_cost_usd)}</strong>
                </p>
              </div>
            </div>

            <div className="card">
              <div className="card__head"><h3 className="card__title">Summary</h3></div>
              <div className="card__body">
                <div className="dl">
                  <dt>Team ID</dt><dd className="mono" style={{ fontSize: 12 }}>{team.id}</dd>
                  <dt>Slug</dt><dd className="mono">{team.slug}</dd>
                  <dt>Created</dt><dd>{formatDate(team.created_at)}</dd>
                  <dt>Monthly cap</dt><dd>{team.monthly_budget_usd != null ? `$${team.monthly_budget_usd}` : 'Unlimited'}</dd>
                  <dt>Alert at</dt><dd>{Math.round(team.budget_alert_pct * 100)}%</dd>
                  <dt>Over-budget action</dt><dd>{team.budget_action}</dd>
                  <dt>Active keys</dt><dd>{activeKeys.length}</dd>
                  <dt>Members</dt><dd>{members.length}</dd>
                </div>
              </div>
            </div>
          </div>

          <div className="split-3">
            <div className="card">
              <div className="card__head"><h3 className="card__title">Usage</h3><span className="card__sub">all-time</span></div>
              <div className="card__body">
                <div className="dl">
                  <dt>Total requests</dt><dd>{(stat?.request_count ?? 0).toLocaleString()}</dd>
                  <dt>Total tokens</dt><dd>{(stat?.total_tokens ?? 0).toLocaleString()}</dd>
                  <dt>Total cost</dt><dd>{formatCost(stat?.total_cost_usd)}</dd>
                  <dt>Cache hit rate</dt><dd>{stat?.cache_hit_pct != null ? `${Math.round(stat.cache_hit_pct)}%` : '—'}</dd>
                </div>
              </div>
            </div>
            <div className="card">
              <div className="card__head"><h3 className="card__title">Budget</h3></div>
              <div className="card__body">
                <div className="dl">
                  <dt>Cap</dt><dd>{team.monthly_budget_usd != null ? `$${team.monthly_budget_usd} / mo` : 'No limit'}</dd>
                  <dt>Used</dt><dd>{budgetPct != null ? `${budgetPct}%` : '—'}</dd>
                  <dt>Action</dt><dd>{team.budget_action}</dd>
                  <dt>Alert threshold</dt><dd>{Math.round(team.budget_alert_pct * 100)}%</dd>
                </div>
              </div>
            </div>
            <div className="card">
              <div className="card__head"><h3 className="card__title">Keys</h3></div>
              <div className="card__body">
                <div className="dl">
                  <dt>Active</dt><dd>{activeKeys.length}</dd>
                  <dt>Revoked</dt><dd>{keys.filter(k => k.revoked_at).length}</dd>
                  <dt>Total</dt><dd>{keys.length}</dd>
                </div>
                <button className="btn btn--sm btn--primary" style={{ marginTop: 14 }} onClick={handleIssueKey}>+ Issue key</button>
              </div>
            </div>
          </div>
        </>
      )}

      {/* ── KEYS ── */}
      {tab === 'keys' && (
        <div className="card">
          <div className="card__head">
            <h3 className="card__title">API keys</h3>
            <span className="card__sub">{activeKeys.length} active · {keys.filter(k => k.revoked_at).length} revoked</span>
            <div className="card__actions">
              <button className="btn btn--primary btn--sm" onClick={handleIssueKey}>+ Issue key</button>
            </div>
          </div>
          <div className="card__body" style={{ padding: 0 }}>
            {keysQuery.isLoading ? (
              <div style={{ padding: 24 }}><LoadingState rows={3} /></div>
            ) : (
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Key hash</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th>Budget cap</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {keys.length === 0 ? (
                    <tr><td colSpan={6} style={{ textAlign: 'center', padding: 32, color: 'var(--fg-3)' }}>
                      No keys yet · <button className="btn btn--sm btn--ghost" onClick={handleIssueKey}>Issue first key</button>
                    </td></tr>
                  ) : keys.map(k => (
                    <tr key={k.id}>
                      <td><strong>{k.name}</strong></td>
                      <td><span className="mono" style={{ fontSize: 12 }}>{k.key_hash.slice(0, 12)}…</span></td>
                      <td>
                        {k.revoked_at
                          ? <span className="pill pill--bad"><span className="dot"></span>revoked</span>
                          : <span className="pill pill--good"><span className="dot"></span>active</span>}
                      </td>
                      <td>{formatDate(k.created_at)}</td>
                      <td>{k.monthly_budget_usd != null ? `$${k.monthly_budget_usd}` : '—'}</td>
                      <td>
                        {!k.revoked_at && (
                          <button className="btn btn--sm btn--ghost" onClick={() => handleRevokeKey(k.id, k.name)}>
                            Revoke
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* ── POLICIES ── */}
      {tab === 'policies' && (
        <div>
          <div className="split-2" style={{ marginBottom: 16 }}>
            <div className="card">
              <div className="card__head">
                <h3 className="card__title">Budget policy</h3>
                <div className="card__actions"><button className="btn btn--sm">Edit</button></div>
              </div>
              <div className="card__body">
                <div className="dl">
                  <dt>Monthly cap</dt><dd>{team.monthly_budget_usd != null ? `$${team.monthly_budget_usd}` : 'No limit'}</dd>
                  <dt>Alert threshold</dt><dd>{Math.round(team.budget_alert_pct * 100)}%</dd>
                  <dt>Over-budget action</dt>
                  <dd>
                    {team.budget_action === 'block'
                      ? <span className="pill pill--bad">block requests</span>
                      : <span className="pill pill--warn">alert only</span>}
                  </dd>
                  <dt>Current spend</dt><dd>{formatCost(stat?.total_cost_usd)}</dd>
                  <dt>Budget used</dt><dd>{budgetPct != null ? `${budgetPct}%` : '—'}</dd>
                </div>
              </div>
            </div>
            <div className="card">
              <div className="card__head">
                <h3 className="card__title">Access policy</h3>
                <div className="card__actions"><button className="btn btn--sm">Edit</button></div>
              </div>
              <div className="card__body">
                <div className="dl">
                  <dt>Status</dt><dd><span className="pill pill--good"><span className="dot"></span>Active</span></dd>
                  <dt>Allowed models</dt><dd>All configured models</dd>
                  <dt>Rate limit</dt><dd>Per-key default</dd>
                </div>
                <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>
                  Fine-grained model and rate policies can be set via the <Link href="/admin/policies" style={{ color: 'var(--sc-link)' }}>Policies page</Link>.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── MEMBERS ── */}
      {tab === 'members' && (
        <div className="card">
          <div className="card__head">
            <h3 className="card__title">Members</h3>
            <span className="card__sub">{members.length} member{members.length !== 1 ? 's' : ''}</span>
            <div className="card__actions"><button className="btn btn--primary btn--sm">+ Add member</button></div>
          </div>
          <div className="card__body" style={{ padding: 0 }}>
            {membersQuery.isLoading ? (
              <div style={{ padding: 24 }}><LoadingState rows={3} /></div>
            ) : members.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--fg-3)', fontSize: 13 }}>
                No members yet
              </div>
            ) : (
              <table className="tbl">
                <thead>
                  <tr><th>User ID</th><th>Role</th><th>Joined</th><th>Developer ID</th><th></th></tr>
                </thead>
                <tbody>
                  {members.map(m => (
                    <tr key={m.id}>
                      <td><span className="mono" style={{ fontSize: 12 }}>{m.user_id ?? '—'}</span></td>
                      <td>
                        {m.role === 'owner'
                          ? <span className="pill pill--info">Owner</span>
                          : m.role === 'maintainer'
                            ? <span className="pill">Maintainer</span>
                            : <span className="pill">Member</span>}
                      </td>
                      <td>{formatDate(m.joined_at)}</td>
                      <td><span className="mono muted" style={{ fontSize: 11 }}>{m.developer_id ? m.developer_id.slice(0, 8) + '…' : '—'}</span></td>
                      <td><button className="btn btn--sm btn--ghost">⋯</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* ── AUDIT ── */}
      {tab === 'audit' && (
        <div className="card">
          <div className="card__head">
            <h3 className="card__title">Audit log</h3>
            <span className="card__sub">events for this team</span>
            <div className="card__actions">
              <Link href="/admin/audit" className="btn btn--sm btn--ghost">Full audit log →</Link>
            </div>
          </div>
          <div className="card__body" style={{ padding: 0 }}>
            {auditQuery.isLoading ? (
              <div style={{ padding: 24 }}><LoadingState rows={5} /></div>
            ) : auditRows.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--fg-3)', fontSize: 13 }}>
                No audit events for this team yet
              </div>
            ) : (
              <table className="tbl">
                <thead>
                  <tr><th>Time</th><th>Actor</th><th>Action</th><th>Resource</th></tr>
                </thead>
                <tbody>
                  {auditRows.map(row => (
                    <tr key={row.id}>
                      <td><span className="mono" style={{ fontSize: 12 }}>{formatTime(row.timestamp)}</span></td>
                      <td style={{ fontSize: 12 }}>{row.actor}</td>
                      <td><span className="pill" style={{ fontSize: 11 }}>{row.action}</span></td>
                      <td style={{ fontSize: 12 }}>
                        <span className="muted">{row.resource_type}</span>
                        {row.resource_id && <span className="mono" style={{ fontSize: 11, marginLeft: 6 }}>{row.resource_id.slice(0, 8)}…</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
