'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../_components/PageStates';

const BASE = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

type UserStatus = 'active' | 'pending' | 'suspended';
type FilterTab = 'All' | 'Active' | 'Pending' | 'Suspended';

interface Developer {
  id: string;
  email: string;
  display_name: string | null;
  status: UserStatus;
  team_id: string | null;
  team_name?: string | null;
  created_at: string;
}

function formatDate(iso: string | null | undefined) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function statusPill(status: UserStatus) {
  switch (status) {
    case 'active':    return <span className="pill pill--good"><span className="dot" />Active</span>;
    case 'pending':   return <span className="pill pill--warn"><span className="dot" />Pending</span>;
    case 'suspended': return <span className="pill pill--bad"><span className="dot" />Suspended</span>;
    default:          return <span className="pill"><span className="dot" />{status}</span>;
  }
}

function avatarInitials(user: Developer): string {
  if (user.display_name) {
    const parts = user.display_name.trim().split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    return parts[0].slice(0, 2).toUpperCase();
  }
  return user.email.slice(0, 2).toUpperCase();
}

const AVATAR_COLORS = ['#083EA7', '#1D958E', '#4B17B6', '#FB9B2A', '#0A7BD7', '#1A7A3C', '#EF3E4A'];
function avatarColor(seed: string): string {
  let h = 0;
  for (const c of seed) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

// ── Coming soon placeholder ─────────────────────────────────────────────────

function ComingSoon() {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      padding: '64px 24px', color: 'var(--fg-3)', textAlign: 'center',
    }}>
      <div style={{ fontSize: 36, marginBottom: 12 }}>👥</div>
      <p style={{ fontSize: 15, fontWeight: 600, color: 'var(--fg-2)', margin: '0 0 6px' }}>Developer accounts — coming soon</p>
      <p style={{ fontSize: 13, margin: 0, maxWidth: 380 }}>
        The <code style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: 12 }}>/developers</code> endpoint
        has not been deployed yet. Once the backend is updated, users will appear here automatically.
      </p>
    </div>
  );
}

// ── Main page ───────────────────────────────────────────────────────────────

export default function UsersPage() {
  const [tab, setTab] = useState<FilterTab>('All');
  const [search, setSearch] = useState('');

  const devQuery = useQuery<Developer[]>({
    queryKey: ['developers'],
    queryFn: async () => {
      const res = await fetch(`${BASE}/developers`);
      if (res.status === 404) return [];
      if (!res.ok) throw new Error(`Failed to fetch developers: ${res.status}`);
      return res.json();
    },
    retry: (failureCount, error) => {
      // Don't retry 404s — endpoint not yet deployed
      if ((error as Error).message.includes('404')) return false;
      return failureCount < 1;
    },
  });

  if (devQuery.isLoading) return <section className="page"><LoadingState rows={10} /></section>;
  if (devQuery.isError) {
    const msg = (devQuery.error as Error).message;
    if (msg.includes('404')) {
      return (
        <section className="page">
          <div className="page__head">
            <div>
              <h1 className="page__title">Users</h1>
              <p className="page__sub">Developer accounts registered on the platform</p>
            </div>
          </div>
          <div className="card"><div className="card__body"><ComingSoon /></div></div>
        </section>
      );
    }
    return <section className="page"><ErrorState error={devQuery.error as Error} retry={() => devQuery.refetch()} /></section>;
  }

  const developers = devQuery.data ?? [];

  const total = developers.length;
  const activeCount = developers.filter(d => d.status === 'active').length;
  const pendingCount = developers.filter(d => d.status === 'pending').length;
  const suspendedCount = developers.filter(d => d.status === 'suspended').length;

  const searchLower = search.toLowerCase();
  const filtered = developers.filter(d => {
    const matchTab =
      tab === 'All' ||
      (tab === 'Active' && d.status === 'active') ||
      (tab === 'Pending' && d.status === 'pending') ||
      (tab === 'Suspended' && d.status === 'suspended');
    const matchSearch =
      !search ||
      d.email.toLowerCase().includes(searchLower) ||
      (d.display_name ?? '').toLowerCase().includes(searchLower);
    return matchTab && matchSearch;
  });

  return (
    <section className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Users</h1>
          <p className="page__sub">Developer accounts registered on the platform</p>
        </div>
      </div>

      <div className="kpi-grid" style={{ marginBottom: 18 }}>
        <div className="kpi">
          <div className="kpi__label">Total users</div>
          <div className="kpi__value">{total}</div>
          <div className="kpi__delta flat">registered</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Active</div>
          <div className="kpi__value">{activeCount}</div>
          <div className="kpi__delta flat" style={{ color: 'var(--good)' }}>enabled</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Pending</div>
          <div className="kpi__value">{pendingCount}</div>
          <div className="kpi__delta flat" style={{ color: 'var(--warn)' }}>awaiting approval</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Suspended</div>
          <div className="kpi__value">{suspendedCount}</div>
          <div className="kpi__delta flat" style={{ color: 'var(--bad)' }}>access revoked</div>
        </div>
      </div>

      <div className="filters" style={{ marginBottom: 14 }}>
        <div className="seg">
          {(['All', 'Active', 'Pending', 'Suspended'] as FilterTab[]).map(f => (
            <button key={f} className={tab === f ? 'is-active' : undefined} onClick={() => setTab(f)}>{f}</button>
          ))}
        </div>
        <span style={{ flex: 1 }} />
        <div style={{ position: 'relative' }}>
          <input
            type="text"
            placeholder="Search email or name…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{
              padding: '6px 10px 6px 30px', fontSize: 13,
              background: 'var(--surface-2)', border: '1px solid var(--rule)',
              borderRadius: 6, color: 'var(--fg-1)', width: 220,
              fontFamily: 'inherit',
            }}
          />
          <span style={{
            position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
            color: 'var(--fg-3)', fontSize: 12, pointerEvents: 'none',
          }}>⌕</span>
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="card">
          <div className="card__body" style={{ textAlign: 'center', padding: '48px 24px', color: 'var(--fg-3)', fontSize: 13 }}>
            {developers.length === 0 ? <ComingSoon /> : 'No users match the current filter.'}
          </div>
        </div>
      ) : (
        <div className="card">
          <div className="card__body" style={{ padding: 0 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Display name</th>
                  <th>Status</th>
                  <th>Team</th>
                  <th>Joined</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(dev => {
                  const initials = avatarInitials(dev);
                  const color = avatarColor(dev.email);
                  return (
                    <tr key={dev.id}>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <span style={{
                            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                            width: 30, height: 30, borderRadius: 8, background: color,
                            color: '#fff', fontWeight: 700, fontSize: 11, flexShrink: 0,
                          }}>{initials}</span>
                          <div className="cell-2">
                            <span style={{ fontWeight: 500 }}>{dev.email}</span>
                          </div>
                        </div>
                      </td>
                      <td style={{ color: 'var(--fg-2)', fontSize: 13 }}>
                        {dev.display_name ?? <span className="muted">—</span>}
                      </td>
                      <td>{statusPill(dev.status)}</td>
                      <td style={{ fontSize: 13, color: 'var(--fg-2)' }}>
                        {dev.team_name ?? <span className="muted">—</span>}
                      </td>
                      <td style={{ fontSize: 12.5, color: 'var(--fg-3)' }}>{formatDate(dev.created_at)}</td>
                      <td>
                        <a
                          href={`/admin/users/${dev.id}`}
                          className="btn btn--sm btn--ghost"
                          style={{ textDecoration: 'none' }}
                        >
                          View
                        </a>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
