'use client';

import React, { useRef, useEffect, useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../../../lib/apiClient';
import { LoadingState, ErrorState } from '../../_components/PageStates';

// Role taxonomy (new names)
const ROLES = ['gateway_admin', 'area_owner', 'unit_lead', 'team_admin', 'engineer', 'reporter'] as const;

const ROLE_COLORS: Record<string, string> = {
  gateway_admin: '#F97316',
  platform_admin: '#F97316', // alias
  area_owner: '#F59E0B',
  unit_lead: '#D946EF',
  team_admin: '#6366F1',
  engineer: '#0EA5E9',
  developer: '#0EA5E9', // alias
  reporter: '#8B5CF6',
  viewer: '#8B5CF6', // alias
};

const ROLE_LABELS: Record<string, string> = {
  gateway_admin: 'Gateway Admin',
  platform_admin: 'Gateway Admin',
  area_owner: 'Area Owner',
  unit_lead: 'Unit Lead',
  team_admin: 'Team Admin',
  engineer: 'Engineer',
  developer: 'Engineer',
  reporter: 'Reporter',
  viewer: 'Reporter',
};

function RolePill({ role, muted }: { role: string; muted?: boolean }) {
  const color = ROLE_COLORS[role] ?? '#999';
  const label = ROLE_LABELS[role] ?? role;
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: 10, fontSize: 10,
      fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase' as const,
      background: `${color}${muted ? '18' : '22'}`,
      color: muted ? '#999' : color,
      border: `1px solid ${color}${muted ? '33' : '44'}`,
    }}>
      {label}
    </span>
  );
}

function avatarColor(s: string): string {
  const colors = ['#6366f1', '#8b5cf6', '#ec4899', '#06b6d4', '#10b981', '#f59e0b', '#ef4444'];
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % colors.length;
  return colors[h];
}

function initials(displayName: string, email: string): string {
  const src = displayName || email;
  const parts = src.split(/[\s@.]+/).filter(Boolean);
  return parts.length >= 2 ? (parts[0][0] + parts[1][0]).toUpperCase() : src.slice(0, 2).toUpperCase();
}

interface Assignment {
  id: string;
  subject: 'user' | 'group';
  user_id?: string | null;
  user_email?: string | null;
  user_display_name?: string | null;
  entra_group_id?: string | null;
  entra_group_name?: string | null;
  role: string;
  node_id: string;
  granted_at?: string | null;
  granted_by_email?: string | null;
  inherited?: boolean;
  source_node_name?: string | null;
}

interface SearchResult {
  type: 'user' | 'group';
  id: string;
  label: string;
  sublabel?: string;
}

function SubjectSearchField({
  onSelect,
  disabled,
}: {
  onSelect: (result: SearchResult) => void;
  disabled?: boolean;
}) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [userResults, setUserResults] = useState<SearchResult[]>([]);
  const [groupResults, setGroupResults] = useState<SearchResult[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (query.length < 2) { setOpen(false); return; }
    if (timer.current !== undefined) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      const [users, groups] = await Promise.all([
        apiFetch<{ items: { id: string; email: string; display_name: string }[] }>(
          `/admin/users?search=${encodeURIComponent(query)}&limit=5`
        ).catch(() => ({ items: [] })),
        apiFetch<{ id: string; name: string }[]>(
          `/admin/local-groups?search=${encodeURIComponent(query)}&limit=5`
        ).catch(() => []),
      ]);
      setUserResults((users.items ?? []).map(u => ({
        type: 'user', id: u.id,
        label: u.display_name || u.email, sublabel: u.display_name ? u.email : undefined,
      })));
      setGroupResults((Array.isArray(groups) ? groups : []).map(g => ({
        type: 'group', id: g.id, label: g.name, sublabel: 'Local group',
      })));
      setOpen(true);
    }, 300);
    return () => { if (timer.current !== undefined) clearTimeout(timer.current); };
  }, [query]);

  useEffect(() => {
    function onOutside(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onOutside);
    return () => document.removeEventListener('mousedown', onOutside);
  }, []);

  const hasResults = userResults.length > 0 || groupResults.length > 0;

  function pick(r: SearchResult) {
    onSelect(r);
    setQuery('');
    setOpen(false);
  }

  return (
    <div ref={wrapRef} style={{ position: 'relative', flex: 1 }}>
      <input
        value={query}
        onChange={e => setQuery(e.target.value)}
        placeholder="Search users or groups…"
        disabled={disabled}
        style={{
          width: '100%', boxSizing: 'border-box',
          padding: '7px 10px', fontSize: 12,
          background: 'var(--surface-2)', border: '1px solid var(--rule)',
          borderRadius: 6, color: 'var(--fg-1)', outline: 'none',
        }}
      />
      {open && hasResults && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 30,
          background: 'var(--surface)', border: '1px solid var(--rule)',
          borderRadius: 6, boxShadow: 'var(--shadow-pop)',
          marginTop: 3, maxHeight: 260, overflowY: 'auto',
        }}>
          {userResults.length > 0 && (
            <>
              <div style={{ padding: '5px 10px 2px', fontSize: 10, fontWeight: 600, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Users</div>
              {userResults.map(r => (
                <div
                  key={r.id}
                  onMouseDown={() => pick(r)}
                  style={{ padding: '8px 10px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}
                  onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = 'var(--surface-2)'}
                  onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = ''}
                >
                  <span style={{ width: 26, height: 26, borderRadius: '50%', background: avatarColor(r.id), color: '#fff', fontSize: 10, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    {initials(r.label, r.sublabel || r.id)}
                  </span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--fg-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.label}</div>
                    {r.sublabel && <div style={{ fontSize: 10, color: 'var(--fg-3)' }}>{r.sublabel}</div>}
                  </div>
                </div>
              ))}
            </>
          )}
          {groupResults.length > 0 && (
            <>
              <div style={{ padding: '5px 10px 2px', fontSize: 10, fontWeight: 600, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', borderTop: userResults.length > 0 ? '1px solid var(--rule)' : 'none' }}>Groups</div>
              {groupResults.map(r => (
                <div
                  key={r.id}
                  onMouseDown={() => pick(r)}
                  style={{ padding: '8px 10px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}
                  onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = 'var(--surface-2)'}
                  onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = ''}
                >
                  <span style={{ width: 26, height: 26, borderRadius: 6, background: 'var(--surface-3)', color: 'var(--fg-2)', fontSize: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>👥</span>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--fg-1)' }}>{r.label}</div>
                    <div style={{ fontSize: 10, color: 'var(--fg-3)' }}>Local group</div>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

interface AccessTabProps {
  nodeId: string;
}

export function AccessTab({ nodeId }: AccessTabProps) {
  const queryClient = useQueryClient();
  const [showInherited, setShowInherited] = useState(false);
  const [pending, setPending] = useState<SearchResult | null>(null);
  const [pendingRole, setPendingRole] = useState<string>('engineer');

  const { data: assignments, isLoading, error } = useQuery<Assignment[]>({
    queryKey: ['node-permissions', nodeId, showInherited],
    queryFn: () => apiFetch(`/nodes/${nodeId}/permissions${showInherited ? '?include_inherited=true' : ''}`),
    staleTime: 30_000,
  });

  const addMutation = useMutation({
    mutationFn: (body: { user_id?: string; entra_group_id?: string; role: string }) =>
      apiFetch(`/nodes/${nodeId}/permissions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['node-permissions', nodeId] });
      queryClient.invalidateQueries({ queryKey: ['node', nodeId] });
      setPending(null);
    },
  });

  const removeMutation = useMutation({
    mutationFn: (assignmentId: string) =>
      apiFetch(`/nodes/${nodeId}/permissions/${assignmentId}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['node-permissions', nodeId] });
      queryClient.invalidateQueries({ queryKey: ['node', nodeId] });
    },
  });

  function handleAssign() {
    if (!pending) return;
    const body: { user_id?: string; entra_group_id?: string; role: string } = { role: pendingRole };
    if (pending.type === 'user') body.user_id = pending.id;
    else body.entra_group_id = pending.id;
    addMutation.mutate(body);
  }

  if (isLoading) return <LoadingState rows={4} />;
  if (error) return <ErrorState error={error as Error} />;

  const direct = (assignments ?? []).filter(a => !a.inherited);
  const inherited = (assignments ?? []).filter(a => a.inherited);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Add assignment */}
      <div>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-1)', marginBottom: 8 }}>
          Add permission
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <SubjectSearchField
            disabled={addMutation.isPending}
            onSelect={r => setPending(r)}
          />
          <select
            value={pendingRole}
            onChange={e => setPendingRole(e.target.value)}
            style={{
              padding: '7px 8px', fontSize: 12, background: 'var(--surface-2)',
              border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-1)',
            }}
          >
            {ROLES.map(r => (
              <option key={r} value={r}>{ROLE_LABELS[r]}</option>
            ))}
          </select>
          <button
            onClick={handleAssign}
            disabled={!pending || addMutation.isPending}
            style={{
              padding: '7px 14px', fontSize: 12, fontWeight: 600,
              background: pending ? 'var(--accent)' : 'var(--surface-2)',
              color: pending ? '#fff' : 'var(--fg-3)',
              border: `1px solid ${pending ? 'var(--accent)' : 'var(--rule)'}`,
              borderRadius: 6, cursor: pending ? 'pointer' : 'not-allowed',
            }}
          >
            {addMutation.isPending ? '…' : '+ Assign'}
          </button>
        </div>
        {pending && (
          <div style={{ marginTop: 6, fontSize: 12, color: 'var(--fg-2)' }}>
            Assigning <strong>{pending.label}</strong> as <RolePill role={pendingRole} />
          </div>
        )}
        {addMutation.isError && (
          <div style={{ marginTop: 6, fontSize: 12, color: 'var(--bad)' }}>
            {(addMutation.error as Error).message}
          </div>
        )}
      </div>

      {/* Direct assignments */}
      <div>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-1)', marginBottom: 8 }}>
          Direct assignments ({direct.length})
        </div>
        {direct.length === 0 ? (
          <div style={{ fontSize: 12, color: 'var(--fg-3)', padding: '8px 0' }}>
            No direct permissions on this node yet.
          </div>
        ) : (
          <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 8, overflow: 'hidden' }}>
            {direct.map((a, i) => {
              const isUser = a.subject === 'user';
              const label = isUser ? (a.user_display_name || a.user_email || '') : (a.entra_group_name || a.entra_group_id || '');
              const sub = isUser && a.user_display_name ? a.user_email : undefined;
              const key = isUser ? (a.user_email || a.user_id || '') : (a.entra_group_id || '');
              const bg = isUser ? avatarColor(key) : '#6366f1';
              const ini = isUser ? initials(label, a.user_email || '') : '👥';
              return (
                <div key={a.id} style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '10px 14px',
                  borderBottom: i < direct.length - 1 ? '1px solid var(--rule)' : 'none',
                }}>
                  {isUser ? (
                    <div style={{ width: 32, height: 32, borderRadius: '50%', background: bg, color: '#fff', fontSize: 11, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{ini}</div>
                  ) : (
                    <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--surface-3)', fontSize: 16, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>👥</div>
                  )}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--fg-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</div>
                    {sub && <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>{sub}</div>}
                  </div>
                  <RolePill role={a.role} />
                  <button
                    onClick={() => removeMutation.mutate(a.id)}
                    disabled={removeMutation.isPending}
                    style={{
                      padding: '3px 9px', fontSize: 11, background: 'transparent',
                      border: '1px solid var(--rule)', borderRadius: 4,
                      color: 'var(--bad)', cursor: 'pointer', flexShrink: 0,
                    }}
                  >
                    Remove
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Inherited (collapsed by default) */}
      <div>
        <button
          onClick={() => setShowInherited(v => !v)}
          style={{
            fontSize: 12, fontWeight: 600, color: 'var(--fg-2)',
            background: 'none', border: 'none', cursor: 'pointer', padding: 0,
            display: 'flex', alignItems: 'center', gap: 4,
          }}
        >
          <span style={{ fontSize: 10, color: 'var(--fg-3)', transform: showInherited ? 'rotate(90deg)' : 'none', display: 'inline-block', transition: 'transform 0.15s' }}>▶</span>
          Inherited from ancestors
          {inherited.length > 0 && (
            <span style={{ fontSize: 11, color: 'var(--fg-3)', background: 'var(--surface-2)', borderRadius: 10, padding: '1px 6px' }}>{inherited.length}</span>
          )}
        </button>
        {showInherited && inherited.length > 0 && (
          <div style={{ marginTop: 8, background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 8, overflow: 'hidden' }}>
            {inherited.map((a, i) => {
              const isUser = a.subject === 'user';
              const label = isUser ? (a.user_display_name || a.user_email || '') : (a.entra_group_name || a.entra_group_id || '');
              return (
                <div key={a.id} style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '9px 14px', opacity: 0.7,
                  borderBottom: i < inherited.length - 1 ? '1px solid var(--rule)' : 'none',
                }}>
                  <div style={{ width: 28, height: 28, borderRadius: isUser ? '50%' : 6, background: 'var(--surface-3)', color: 'var(--fg-3)', fontSize: isUser ? 10 : 14, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    {isUser ? initials(label, a.user_email || '') : '👥'}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--fg-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</div>
                    {a.source_node_name && <div style={{ fontSize: 10, color: 'var(--fg-3)' }}>from {a.source_node_name}</div>}
                  </div>
                  <RolePill role={a.role} muted />
                </div>
              );
            })}
          </div>
        )}
        {showInherited && inherited.length === 0 && (
          <div style={{ marginTop: 6, fontSize: 12, color: 'var(--fg-3)' }}>No inherited assignments.</div>
        )}
      </div>
    </div>
  );
}
