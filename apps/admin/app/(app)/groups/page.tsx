'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../../lib/apiClient';
import { LoadingState, ErrorState } from '../_components/PageStates';

interface LocalGroup {
  id: string;
  name: string;
  member_count: number;
  created_at: string | null;
}

interface Member {
  id: string;
  email: string;
  display_name: string;
}

function avatarColor(s: string): string {
  const colors = ['#6366f1', '#8b5cf6', '#ec4899', '#06b6d4', '#10b981', '#f59e0b', '#ef4444'];
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % colors.length;
  return colors[h];
}

function initials(name: string, email: string): string {
  const src = name || email;
  const parts = src.split(/[\s@.]+/).filter(Boolean);
  return parts.length >= 2 ? (parts[0][0] + parts[1][0]).toUpperCase() : src.slice(0, 2).toUpperCase();
}

function UserSearchField({ onSelect, disabled }: {
  onSelect: (user: { id: string; email: string; display_name: string }) => void;
  disabled?: boolean;
}) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState<{ id: string; email: string; display_name: string }[]>([]);
  const [open, setOpen] = useState(false);
  const timer = React.useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  React.useEffect(() => {
    if (q.length < 2) { setOpen(false); return; }
    if (timer.current !== undefined) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      const data = await apiFetch<{ items: { id: string; email: string; display_name: string }[] }>(
        `/admin/users?search=${encodeURIComponent(q)}&limit=5`
      ).catch(() => ({ items: [] }));
      setResults(data.items ?? []);
      setOpen(true);
    }, 300);
    return () => { if (timer.current !== undefined) clearTimeout(timer.current); };
  }, [q]);

  return (
    <div style={{ position: 'relative', flex: 1 }}>
      <input
        value={q}
        onChange={e => setQ(e.target.value)}
        placeholder="Search users…"
        disabled={disabled}
        style={{
          width: '100%', boxSizing: 'border-box', padding: '7px 10px', fontSize: 12,
          background: 'var(--surface-2)', border: '1px solid var(--rule)',
          borderRadius: 6, color: 'var(--fg-1)', outline: 'none',
        }}
      />
      {open && results.length > 0 && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 20,
          background: 'var(--surface)', border: '1px solid var(--rule)',
          borderRadius: 6, boxShadow: 'var(--shadow-pop)', marginTop: 3,
        }}>
          {results.map(u => (
            <div
              key={u.id}
              onMouseDown={() => { onSelect(u); setQ(''); setOpen(false); }}
              style={{ padding: '8px 10px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}
              onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = 'var(--surface-2)'}
              onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = ''}
            >
              <div style={{ width: 26, height: 26, borderRadius: '50%', background: avatarColor(u.id), color: '#fff', fontSize: 10, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                {initials(u.display_name, u.email)}
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--fg-1)' }}>{u.display_name || u.email}</div>
                {u.display_name && <div style={{ fontSize: 10, color: 'var(--fg-3)' }}>{u.email}</div>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function GroupRow({ group, onDeleted }: { group: LocalGroup; onDeleted: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const queryClient = useQueryClient();

  const { data: members, isLoading } = useQuery<Member[]>({
    queryKey: ['group-members', group.id],
    queryFn: () => apiFetch(`/admin/local-groups/${group.id}/members`),
    enabled: expanded,
    staleTime: 30_000,
  });

  const addMember = useMutation({
    mutationFn: (userId: string) =>
      apiFetch(`/admin/local-groups/${group.id}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['group-members', group.id] }),
  });

  const removeMember = useMutation({
    mutationFn: (userId: string) =>
      apiFetch(`/admin/local-groups/${group.id}/members/${userId}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['group-members', group.id] }),
  });

  const deleteGroup = useMutation({
    mutationFn: () => apiFetch(`/admin/local-groups/${group.id}`, { method: 'DELETE' }),
    onSuccess: onDeleted,
  });

  return (
    <div style={{ border: '1px solid var(--rule)', borderRadius: 8, overflow: 'hidden', background: 'var(--surface)' }}>
      {/* Row header */}
      <div
        onClick={() => setExpanded(v => !v)}
        style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', cursor: 'pointer' }}
        onMouseEnter={e => (e.currentTarget as HTMLElement).style.background = 'var(--surface-2)'}
        onMouseLeave={e => (e.currentTarget as HTMLElement).style.background = ''}
      >
        <span style={{ fontSize: 10, color: 'var(--fg-3)', transform: expanded ? 'rotate(90deg)' : 'none', display: 'inline-block', transition: 'transform 0.15s', flexShrink: 0 }}>▶</span>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: 'var(--surface-3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, flexShrink: 0 }}>👥</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg-1)' }}>{group.name}</div>
          <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>
            {group.member_count} member{group.member_count !== 1 ? 's' : ''}
          </div>
        </div>
        <span style={{ fontSize: 10, color: 'var(--fg-3)', fontFamily: 'monospace', background: 'var(--surface-2)', padding: '2px 6px', borderRadius: 4, flexShrink: 0 }}>{group.id}</span>
        <button
          onClick={e => {
            e.stopPropagation();
            if (confirm(`Delete group "${group.name}"? This will remove all role assignments for this group.`)) {
              deleteGroup.mutate();
            }
          }}
          disabled={deleteGroup.isPending}
          style={{ padding: '3px 8px', fontSize: 11, background: 'transparent', border: '1px solid var(--rule)', borderRadius: 4, color: 'var(--bad)', cursor: 'pointer', flexShrink: 0 }}
        >
          Delete
        </button>
      </div>

      {/* Expanded members */}
      {expanded && (
        <div style={{ borderTop: '1px solid var(--rule)', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {/* Add member */}
          <div style={{ display: 'flex', gap: 6 }}>
            <UserSearchField
              disabled={addMember.isPending}
              onSelect={u => addMember.mutate(u.id)}
            />
          </div>
          {addMember.isError && (
            <div style={{ fontSize: 12, color: 'var(--bad)' }}>{(addMember.error as Error).message}</div>
          )}

          {isLoading && <LoadingState rows={2} />}
          {!isLoading && (members ?? []).length === 0 && (
            <div style={{ fontSize: 12, color: 'var(--fg-3)' }}>No members yet. Search above to add.</div>
          )}
          {!isLoading && (members ?? []).length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              {(members ?? []).map(m => (
                <div key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0' }}>
                  <div style={{ width: 28, height: 28, borderRadius: '50%', background: avatarColor(m.id), color: '#fff', fontSize: 10, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    {initials(m.display_name, m.email)}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--fg-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.display_name || m.email}</div>
                    {m.display_name && <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>{m.email}</div>}
                  </div>
                  <button
                    onClick={() => removeMember.mutate(m.id)}
                    disabled={removeMember.isPending}
                    style={{ padding: '2px 8px', fontSize: 11, background: 'transparent', border: '1px solid var(--rule)', borderRadius: 4, color: 'var(--bad)', cursor: 'pointer', flexShrink: 0 }}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          )}

          <div style={{ marginTop: 4, padding: '8px 10px', background: 'var(--surface-2)', borderRadius: 6, fontSize: 11, color: 'var(--fg-3)' }}>
            Assign this group a role on any org node via the <strong>Access</strong> tab on that node.
          </div>
        </div>
      )}
    </div>
  );
}

export default function GroupsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');

  const { data: groups, isLoading, error } = useQuery<LocalGroup[]>({
    queryKey: ['local-groups', search],
    queryFn: () => apiFetch(`/admin/local-groups${search ? `?search=${encodeURIComponent(search)}` : ''}`),
    staleTime: 30_000,
  });

  const createGroup = useMutation({
    mutationFn: (name: string) =>
      apiFetch('/admin/local-groups', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['local-groups'] });
      setNewName('');
      setShowCreate(false);
    },
  });

  return (
    <div style={{ maxWidth: 760, margin: '0 auto', padding: '24px 20px' }}>
      {/* Page header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: 'var(--fg-1)', margin: 0 }}>Groups</h1>
          <p style={{ fontSize: 13, color: 'var(--fg-3)', margin: '4px 0 0' }}>
            Local identity groups. Add members and assign them roles on org nodes via each node's Access tab.
          </p>
        </div>
        <button
          onClick={() => setShowCreate(v => !v)}
          style={{
            padding: '8px 14px', fontSize: 12, fontWeight: 600,
            background: 'var(--accent)', color: '#fff',
            border: 'none', borderRadius: 6, cursor: 'pointer',
          }}
        >
          + New group
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <div style={{
          marginBottom: 16, padding: '14px 16px',
          background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 8,
        }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-1)', marginBottom: 8 }}>Create group</div>
          <div style={{ display: 'flex', gap: 6 }}>
            <input
              value={newName}
              onChange={e => setNewName(e.target.value)}
              placeholder="Group name, e.g. Budget Admins"
              autoFocus
              onKeyDown={e => { if (e.key === 'Enter' && newName.trim()) createGroup.mutate(newName.trim()); }}
              style={{
                flex: 1, padding: '7px 10px', fontSize: 12,
                background: 'var(--surface-2)', border: '1px solid var(--rule)',
                borderRadius: 6, color: 'var(--fg-1)', outline: 'none',
              }}
            />
            <button
              onClick={() => createGroup.mutate(newName.trim())}
              disabled={!newName.trim() || createGroup.isPending}
              style={{
                padding: '7px 14px', fontSize: 12, fontWeight: 600,
                background: newName.trim() ? 'var(--accent)' : 'var(--surface-2)',
                color: newName.trim() ? '#fff' : 'var(--fg-3)',
                border: `1px solid ${newName.trim() ? 'var(--accent)' : 'var(--rule)'}`,
                borderRadius: 6, cursor: newName.trim() ? 'pointer' : 'not-allowed',
              }}
            >
              {createGroup.isPending ? 'Creating…' : 'Create'}
            </button>
            <button
              onClick={() => { setShowCreate(false); setNewName(''); }}
              style={{ padding: '7px 10px', fontSize: 12, background: 'var(--surface-2)', border: '1px solid var(--rule)', borderRadius: 6, color: 'var(--fg-2)', cursor: 'pointer' }}
            >
              Cancel
            </button>
          </div>
          {createGroup.isError && (
            <div style={{ marginTop: 6, fontSize: 12, color: 'var(--bad)' }}>{(createGroup.error as Error).message}</div>
          )}
        </div>
      )}

      {/* Search */}
      <div style={{ marginBottom: 14 }}>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search groups…"
          style={{
            width: '100%', boxSizing: 'border-box', padding: '8px 12px', fontSize: 13,
            background: 'var(--surface)', border: '1px solid var(--rule)',
            borderRadius: 7, color: 'var(--fg-1)', outline: 'none',
          }}
        />
      </div>

      {/* List */}
      {isLoading && <LoadingState rows={4} />}
      {error && <ErrorState error={error as Error} />}
      {!isLoading && !error && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {(groups ?? []).length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--fg-3)', fontSize: 13 }}>
              {search ? 'No groups match your search.' : 'No groups yet. Create one above.'}
            </div>
          ) : (
            (groups ?? []).map(g => (
              <GroupRow
                key={g.id}
                group={g}
                onDeleted={() => queryClient.invalidateQueries({ queryKey: ['local-groups'] })}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}
