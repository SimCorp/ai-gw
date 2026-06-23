'use client';

import React, { useState, useMemo, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { LoadingState, ErrorState } from '../_components/PageStates';
import { OrgNode } from '../_components/nodeTypes';
import { OrgTree } from '../_components/OrgTree';
import { apiFetch, BASE } from '../../../lib/apiClient';

// ── Types ─────────────────────────────────────────────────────────────────

type UserStatus = 'active' | 'pending' | 'suspended';

interface RoleEntry {
  role: string;
  scope_type: string;
  scope_id: string | null;
}

interface User {
  id: string;
  email: string;
  display_name: string;
  status: UserStatus;
  must_change_password: boolean;
  last_login_at: string | null;
  created_at: string;
  roles: RoleEntry[];
  is_contractor?: boolean;
}

interface UsersResponse {
  total: number;
  items: User[];
}

interface Invitation {
  id: string;
  email: string;
  role: string;
  scope_type: string;
  scope_id: string | null;
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
  invited_by_email: string | null;
}

// ── Helpers ───────────────────────────────────────────────────────────────

function formatDate(iso: string | null | undefined) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function formatDateTime(iso: string | null | undefined) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

const AVATAR_COLORS = ['var(--accent)', 'var(--cat-teal)', 'var(--cat-purple)', 'var(--cat-orange)', 'var(--accent)', 'var(--good)', 'var(--cat-coral)'];
function avatarColor(seed: string) {
  let h = 0;
  for (const c of seed) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}
function avatarInitials(u: User) {
  const parts = (u.display_name || u.email).trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return (u.display_name || u.email).slice(0, 2).toUpperCase();
}

const ROLE_META: Record<string, { label: string; color: string }> = {
  platform_admin: { label: 'Platform Admin', color: 'var(--cat-purple)' },
  area_owner:     { label: 'Area Owner',     color: 'var(--accent)' },
  team_admin:     { label: 'Team Admin',     color: 'var(--cat-teal)' },
  developer:      { label: 'Developer',      color: 'var(--good)' },
  viewer:         { label: 'Viewer',         color: 'var(--fg-2)' },
  service_account:{ label: 'Service Acct',  color: 'var(--cat-orange)' },
};

function RoleBadge({ role }: { role: string }) {
  const meta = ROLE_META[role] ?? { label: role, color: 'var(--fg-2)' };
  return (
    <span style={{
      display: 'inline-block', padding: '2px 7px', borderRadius: 4, fontSize: 11, fontWeight: 600,
      background: `color-mix(in srgb, ${meta.color} 13%, transparent)`, color: meta.color, marginRight: 4,
    }}>{meta.label}</span>
  );
}

function ScopedRoleBadge({ role, scopeType, scopeId, nodeMap }: {
  role: string;
  scopeType: string;
  scopeId: string | null;
  nodeMap: Map<string, string>;
}) {
  const meta = ROLE_META[role] ?? { label: role, color: 'var(--fg-2)' };
  const showScope = scopeId !== null && scopeType !== 'global';
  const nodeName = showScope ? (nodeMap.get(scopeId!) ?? scopeId) : null;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'baseline', gap: 3,
      padding: '2px 7px', borderRadius: 4, fontSize: 11, fontWeight: 600,
      background: `color-mix(in srgb, ${meta.color} 13%, transparent)`, color: meta.color, marginRight: 4,
    }}>
      {meta.label}
      {nodeName && (
        <span style={{ fontSize: 10, fontWeight: 400, color: 'var(--fg-3)' }}>@ {nodeName}</span>
      )}
    </span>
  );
}

function StatusPill({ status }: { status: UserStatus }) {
  switch (status) {
    case 'active':    return <span className="pill pill--good"><span className="dot" />Active</span>;
    case 'pending':   return <span className="pill pill--warn"><span className="dot" />Pending</span>;
    case 'suspended': return <span className="pill pill--bad"><span className="dot" />Suspended</span>;
    default:          return <span className="pill"><span className="dot" />{status}</span>;
  }
}

// ── Node tree flattening ──────────────────────────────────────────────────

function flattenTree(node: OrgNode, map: Map<string, string>) {
  map.set(node.id, node.name);
  node.children?.forEach(c => flattenTree(c, map));
}

// ── Invite modal ──────────────────────────────────────────────────────────

function InviteModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('engineer');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ accept_url: string; token: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [selectedNode, setSelectedNode] = useState<OrgNode | null>(null);
  const [showNodePicker, setShowNodePicker] = useState(false);

  const inviteMut = useMutation({
    mutationFn: async () => apiFetch<{ accept_url: string; token: string }>('/auth/invitations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email,
        role,
        scope_type: selectedNode ? selectedNode.type : 'global',
        scope_id: selectedNode?.id ?? null,
      }),
    }),
    onSuccess: (data) => {
      setResult(data);
      qc.invalidateQueries({ queryKey: ['invitations'] });
    },
    onError: (e: Error) => setError(e.message),
  });

  function copy() {
    if (result) {
      navigator.clipboard.writeText(result.accept_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  const overlay: React.CSSProperties = {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
  };
  const modal: React.CSSProperties = {
    background: 'var(--surface)', border: '1px solid var(--rule)',
    borderRadius: 12, padding: 28, width: 460, maxWidth: '90vw',
    boxShadow: 'var(--shadow-pop)',
  };

  return (
    <div style={overlay} onClick={onClose}>
      <div style={modal} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Invite user</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg-3)', fontSize: 18 }}>×</button>
        </div>

        {result ? (
          <div>
            <div style={{
              background: 'var(--good-soft)', border: '1px solid var(--good)',
              borderRadius: 8, padding: '12px 14px', marginBottom: 16, fontSize: 13,
            }}>
              <div style={{ fontWeight: 600, marginBottom: 4, color: 'var(--good)' }}>Invitation created</div>
              <div style={{ color: 'var(--fg-2)' }}>Share this link with {result ? email : ''}. It expires in 48 hours.</div>
            </div>
            <div style={{
              background: 'var(--surface-2)', border: '1px solid var(--rule)',
              borderRadius: 6, padding: '10px 12px', fontSize: 12,
              fontFamily: 'var(--font-mono, monospace)', wordBreak: 'break-all',
              color: 'var(--fg-2)', marginBottom: 12,
            }}>{result.accept_url}</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn--primary" style={{ flex: 1 }} onClick={copy}>
                {copied ? '✓ Copied!' : 'Copy invite link'}
              </button>
              <button className="btn btn--ghost" onClick={onClose}>Done</button>
            </div>
          </div>
        ) : (
          <form onSubmit={e => { e.preventDefault(); setError(null); inviteMut.mutate(); }}>
            {error && (
              <div style={{
                background: 'var(--bad-soft)', border: '1px solid var(--bad)',
                borderRadius: 6, padding: '8px 12px', marginBottom: 14, fontSize: 13, color: 'var(--bad)',
              }}>{error}</div>
            )}
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: 'block', fontSize: 12.5, fontWeight: 500, marginBottom: 6 }}>Email address</label>
              <input
                type="email" required value={email} onChange={e => setEmail(e.target.value)}
                placeholder="user@simcorp.com"
                style={{ width: '100%', boxSizing: 'border-box', padding: '8px 10px', fontSize: 13,
                  background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 6,
                  color: 'var(--fg-1)', fontFamily: 'inherit' }}
              />
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: 'block', fontSize: 12.5, fontWeight: 500, marginBottom: 6 }}>Role</label>
              <select value={role} onChange={e => setRole(e.target.value)}
                style={{ width: '100%', padding: '8px 10px', fontSize: 13,
                  background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 6,
                  color: 'var(--fg-1)', fontFamily: 'inherit' }}>
                <option value="engineer">Engineer</option>
                <option value="reporter">Reporter</option>
                <option value="team_admin">Team Admin</option>
                <option value="area_owner">Area Owner</option>
                <option value="gateway_admin">Gateway Admin</option>
              </select>
            </div>
            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontSize: 12.5, fontWeight: 500, marginBottom: 6 }}>Org scope (optional)</label>
              {!selectedNode && !showNodePicker && (
                <button
                  type="button"
                  className="btn btn--ghost"
                  style={{ fontSize: 12.5 }}
                  onClick={() => setShowNodePicker(true)}
                >
                  Select team (optional)
                </button>
              )}
              {showNodePicker && (
                <div>
                  <div style={{ maxHeight: 300, overflowY: 'auto', marginBottom: 6 }}>
                    <OrgTree
                      onSelect={(n) => { setSelectedNode(n); setShowNodePicker(false); }}
                      selectedId={selectedNode?.id}
                    />
                  </div>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    style={{ fontSize: 12.5 }}
                    onClick={() => setShowNodePicker(false)}
                  >
                    × Cancel
                  </button>
                </div>
              )}
              {selectedNode && !showNodePicker && (
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '4px 10px', borderRadius: 6, fontSize: 12.5,
                  background: 'var(--surface-2)', border: '1px solid var(--rule)' }}>
                  <span style={{ color: 'var(--fg-1)' }}>{selectedNode.name}</span>
                  <button
                    type="button"
                    onClick={() => setSelectedNode(null)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer',
                      color: 'var(--fg-3)', fontSize: 14, lineHeight: 1, padding: 0 }}
                  >×</button>
                </div>
              )}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="submit" className="btn btn--primary" style={{ flex: 1 }} disabled={inviteMut.isPending}>
                {inviteMut.isPending ? 'Creating…' : 'Create invite link'}
              </button>
              <button type="button" className="btn btn--ghost" onClick={onClose}>Cancel</button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────

type TabId = 'users' | 'invitations' | 'service-accounts';

export default function UsersPage() {
  const qc = useQueryClient();
  const searchParams = useSearchParams();
  const [tab, setTab] = useState<TabId>('users');
  const [search, setSearch] = useState(searchParams.get('search') ?? '');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [showInvite, setShowInvite] = useState(false);

  useEffect(() => {
    setSearch(searchParams.get('search') ?? '');
  }, [searchParams]);

  const usersQuery = useQuery<UsersResponse>({
    queryKey: ['admin-users', search, statusFilter],
    queryFn: async () => {
      const params = new URLSearchParams({ limit: '100' });
      if (search) params.set('search', search);
      if (statusFilter) params.set('status', statusFilter);
      return apiFetch(`/admin/users?${params}`);
    },
  });

  const nodesTreeQuery = useQuery<OrgNode[]>({
    queryKey: ['nodes-tree-list'],
    queryFn: () => apiFetch<OrgNode[]>('/nodes/tree').catch(() => []),
  });

  const nodeMap = useMemo(() => {
    const map = new Map<string, string>();
    nodesTreeQuery.data?.forEach(root => flattenTree(root, map));
    return map;
  }, [nodesTreeQuery.data]);

  const invitesQuery = useQuery<Invitation[]>({
    queryKey: ['invitations'],
    queryFn: () => apiFetch<Invitation[]>('/auth/invitations').catch(() => []),
    enabled: tab === 'invitations',
  });

  const serviceAccountsQuery = useQuery<Record<string, unknown>[]>({
    queryKey: ['service-accounts'],
    queryFn: () => apiFetch<Record<string, unknown>[]>('/auth/service-accounts').catch(() => []),
    enabled: tab === 'service-accounts',
  });

  const statusMut = useMutation({
    mutationFn: ({ userId, status }: { userId: string; status: string }) =>
      apiFetch(`/auth/users/${userId}/status?status=${status}`, { method: 'PATCH' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  });

  const forceResetMut = useMutation({
    mutationFn: (userId: string) =>
      apiFetch('/auth/admin/force-password-reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  });

  const revokeInviteMut = useMutation({
    mutationFn: (id: string) => apiFetch(`/auth/invitations/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['invitations'] }),
  });

  const revokeServiceAccountMut = useMutation({
    mutationFn: (id: string) => apiFetch(`/auth/service-accounts/${id}/status?status=revoked`, { method: 'PATCH' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['service-accounts'] }),
  });

  const users = usersQuery.data?.items ?? [];
  const total = usersQuery.data?.total ?? 0;
  const activeCount = users.filter(u => u.status === 'active').length;
  const suspendedCount = users.filter(u => u.status === 'suspended').length;
  const pendingInvites = (invitesQuery.data ?? []).filter(i => !i.accepted_at);

  return (
    <section className="page">
      {showInvite && <InviteModal onClose={() => setShowInvite(false)} />}

      <div className="page__head">
        <div>
          <h1 className="page__title">Users &amp; Access</h1>
          <p className="page__sub">Manage identities, roles, invitations, and service accounts</p>
        </div>
        <button className="btn btn--primary" onClick={() => setShowInvite(true)}>
          + Invite user
        </button>
      </div>

      {/* KPIs */}
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
          <div className="kpi__label">Suspended</div>
          <div className="kpi__value">{suspendedCount}</div>
          <div className="kpi__delta flat" style={{ color: 'var(--bad)' }}>access revoked</div>
        </div>
        <div className="kpi">
          <div className="kpi__label">Pending invites</div>
          <div className="kpi__value">{pendingInvites.length}</div>
          <div className="kpi__delta flat" style={{ color: 'var(--warn)' }}>awaiting signup</div>
        </div>
      </div>

      {/* Tab bar */}
      <div className="seg" style={{ marginBottom: 16 }}>
        {(['users', 'invitations', 'service-accounts'] as TabId[]).map(t => (
          <button key={t} className={tab === t ? 'is-active' : undefined} onClick={() => setTab(t)}>
            {t === 'users' ? 'Users' : t === 'invitations' ? 'Invitations' : 'Service Accounts'}
          </button>
        ))}
      </div>

      {/* ── Users tab ── */}
      {tab === 'users' && (
        <>
          <div className="filters" style={{ marginBottom: 14 }}>
            <div className="seg">
              {[['', 'All'], ['active', 'Active'], ['suspended', 'Suspended']].map(([v, l]) => (
                <button key={v} className={statusFilter === v ? 'is-active' : undefined} onClick={() => setStatusFilter(v)}>{l}</button>
              ))}
            </div>
            <span style={{ flex: 1 }} />
            <div style={{ position: 'relative' }}>
              <input
                type="text" placeholder="Search email or name…" value={search}
                onChange={e => setSearch(e.target.value)}
                style={{ padding: '6px 10px 6px 30px', fontSize: 13, background: 'var(--surface-2)',
                  border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-1)', width: 220, fontFamily: 'inherit' }}
              />
              <span style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--fg-3)', fontSize: 12, pointerEvents: 'none' }}>⌕</span>
            </div>
          </div>

          {usersQuery.isLoading ? <LoadingState rows={8} /> : usersQuery.isError ? (
            <ErrorState error={usersQuery.error as Error} retry={() => usersQuery.refetch()} />
          ) : (
            <div className="card">
              <div className="card__body" style={{ padding: 0 }}>
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>User</th>
                      <th>Roles</th>
                      <th>Status</th>
                      <th>Last login</th>
                      <th>Joined</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map(u => (
                      <tr key={u.id}>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <span style={{
                              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                              width: 30, height: 30, borderRadius: 8, background: avatarColor(u.email),
                              color: '#fff', fontWeight: 700, fontSize: 11, flexShrink: 0,
                            }}>{avatarInitials(u)}</span>
                            <div className="cell-2">
                              <span style={{ fontWeight: 500 }}>{u.email}</span>
                              {u.display_name && <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>{u.display_name}</span>}
                            </div>
                          </div>
                        </td>
                        <td>
                          {u.roles.map(r => <ScopedRoleBadge key={`${r.role}-${r.scope_id}`} role={r.role} scopeType={r.scope_type} scopeId={r.scope_id} nodeMap={nodeMap} />)}
                          {u.is_contractor && (
                            <span style={{
                              display: 'inline-block', padding: '2px 7px', borderRadius: 4,
                              fontSize: 11, fontWeight: 600, marginRight: 4,
                              background: 'var(--warn-soft)', color: 'var(--warn)',
                            }}>Contractor</span>
                          )}
                          {u.must_change_password && (
                            <span style={{ fontSize: 10, color: 'var(--warn)', fontWeight: 600 }}>pw change req.</span>
                          )}
                        </td>
                        <td><StatusPill status={u.status} /></td>
                        <td style={{ fontSize: 12.5, color: 'var(--fg-3)' }}>{formatDateTime(u.last_login_at)}</td>
                        <td style={{ fontSize: 12.5, color: 'var(--fg-3)' }}>{formatDate(u.created_at)}</td>
                        <td>
                          <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
                            {u.status === 'active' ? (
                              <button
                                className="btn btn--sm btn--ghost"
                                style={{ color: 'var(--bad)' }}
                                onClick={() => statusMut.mutate({ userId: u.id, status: 'suspended' })}
                                disabled={statusMut.isPending}
                              >Suspend</button>
                            ) : (
                              <button
                                className="btn btn--sm btn--ghost"
                                style={{ color: 'var(--good)' }}
                                onClick={() => statusMut.mutate({ userId: u.id, status: 'active' })}
                                disabled={statusMut.isPending}
                              >Activate</button>
                            )}
                            <button
                              className="btn btn--sm btn--ghost"
                              style={{ color: 'var(--warn)' }}
                              onClick={() => {
                                if (confirm(`Force password reset for ${u.email}?`)) {
                                  forceResetMut.mutate(u.id);
                                }
                              }}
                              disabled={forceResetMut.isPending}
                              title="Force password reset on next login"
                            >Force reset</button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {users.length === 0 && (
                      <tr><td colSpan={6} style={{ textAlign: 'center', padding: '40px 24px', color: 'var(--fg-3)' }}>No users found.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* ── Invitations tab ── */}
      {tab === 'invitations' && (
        <div className="card">
          <div className="card__body" style={{ padding: 0 }}>
            {invitesQuery.isLoading ? <div style={{ padding: 24 }}><LoadingState rows={4} /></div> : (
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Invited by</th>
                    <th>Expires</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {(invitesQuery.data ?? []).map(inv => (
                    <tr key={inv.id} style={{ opacity: inv.accepted_at ? 0.6 : 1 }}>
                      <td style={{ fontWeight: 500 }}>{inv.email}</td>
                      <td><RoleBadge role={inv.role} /></td>
                      <td style={{ fontSize: 12.5, color: 'var(--fg-3)' }}>{inv.invited_by_email ?? '—'}</td>
                      <td style={{ fontSize: 12.5, color: 'var(--fg-3)' }}>{formatDateTime(inv.expires_at)}</td>
                      <td>
                        {inv.accepted_at
                          ? <span className="pill pill--good"><span className="dot" />Accepted</span>
                          : new Date(inv.expires_at) < new Date()
                            ? <span className="pill pill--bad"><span className="dot" />Expired</span>
                            : <span className="pill pill--warn"><span className="dot" />Pending</span>
                        }
                      </td>
                      <td>
                        {!inv.accepted_at && (
                          <button
                            className="btn btn--sm btn--ghost"
                            style={{ color: 'var(--bad)' }}
                            onClick={() => revokeInviteMut.mutate(inv.id)}
                          >Revoke</button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {(invitesQuery.data ?? []).length === 0 && (
                    <tr><td colSpan={6} style={{ textAlign: 'center', padding: '40px 24px', color: 'var(--fg-3)' }}>
                      No invitations yet. Click <strong>+ Invite user</strong> to send one.
                    </td></tr>
                  )}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* ── Service accounts tab ── */}
      {tab === 'service-accounts' && (
        <div className="card">
          <div className="card__body" style={{ padding: 0 }}>
            {serviceAccountsQuery.isLoading ? <div style={{ padding: 24 }}><LoadingState rows={4} /></div> : (
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Key prefix</th>
                    <th>Team</th>
                    <th>Last used</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {(serviceAccountsQuery.data ?? []).map((sa: Record<string, unknown>) => (
                    <tr key={sa.id as string}>
                      <td>
                        <div className="cell-2">
                          <span style={{ fontWeight: 500 }}>{sa.name as string}</span>
                          {Boolean(sa.description) && <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>{sa.description as string}</span>}
                        </div>
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: 12, color: 'var(--fg-2)' }}>
                        {sa.key_prefix as string}…
                      </td>
                      <td style={{ fontSize: 13, color: 'var(--fg-2)' }}>{(sa.team_name as string) ?? '—'}</td>
                      <td style={{ fontSize: 12.5, color: 'var(--fg-3)' }}>{formatDateTime(sa.last_used_at as string | null)}</td>
                      <td>
                        {sa.status === 'active'
                          ? <span className="pill pill--good"><span className="dot" />Active</span>
                          : sa.status === 'suspended'
                            ? <span className="pill pill--warn"><span className="dot" />Suspended</span>
                            : <span className="pill pill--bad"><span className="dot" />Revoked</span>
                        }
                      </td>
                      <td>
                        {sa.status !== 'revoked' && (
                          <button
                            className="btn btn--sm btn--ghost"
                            style={{ color: 'var(--bad)' }}
                            onClick={() => revokeServiceAccountMut.mutate(sa.id as string)}
                          >Revoke</button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {(serviceAccountsQuery.data ?? []).length === 0 && (
                    <tr><td colSpan={6} style={{ textAlign: 'center', padding: '40px 24px', color: 'var(--fg-3)' }}>
                      No service accounts. Use <code>POST /auth/service-accounts</code> to create one.
                    </td></tr>
                  )}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
