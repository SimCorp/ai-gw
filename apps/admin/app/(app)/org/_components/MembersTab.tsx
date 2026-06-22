'use client';

import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../../../lib/apiClient';
import { LoadingState, ErrorState } from '../../_components/PageStates';
import { UserSearchField } from './UserSearchField';

interface Member {
  id: string;
  node_id: string;
  user_id: string;
  role: string;
  email: string;
  display_name: string;
  created_at: string;
}

function avatarColor(email: string): string {
  const colors = ['#6366f1', '#8b5cf6', '#ec4899', '#06b6d4', '#10b981', '#f59e0b', '#ef4444'];
  let h = 0;
  for (let i = 0; i < email.length; i++) h = (h * 31 + email.charCodeAt(i)) % colors.length;
  return colors[h];
}

function initials(displayName: string, email: string): string {
  const src = displayName || email;
  const parts = src.split(/[\s@.]+/).filter(Boolean);
  return parts.length >= 2 ? (parts[0][0] + parts[1][0]).toUpperCase() : src.slice(0, 2).toUpperCase();
}

interface MembersTabProps {
  nodeId: string;
}

export function MembersTab({ nodeId }: MembersTabProps) {
  const queryClient = useQueryClient();

  const { data: members, isLoading, error } = useQuery<Member[]>({
    queryKey: ['node-members', nodeId],
    queryFn: () => apiFetch(`/nodes/${nodeId}/members?limit=50`),
    staleTime: 30_000,
  });

  const addMutation = useMutation({
    mutationFn: (userId: string) =>
      apiFetch(`/nodes/${nodeId}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['node-members', nodeId] }),
  });

  const removeMutation = useMutation({
    mutationFn: (userId: string) =>
      apiFetch(`/nodes/${nodeId}/members/${userId}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['node-members', nodeId] }),
  });

  if (isLoading) return <LoadingState rows={4} />;
  if (error) return <ErrorState error={error as Error} />;

  const list = members ?? [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--fg-2)', marginBottom: 6 }}>
          Add member by email or name
        </div>
        <UserSearchField
          placeholder="Search by email or name…"
          disabled={addMutation.isPending}
          onSelect={(userId) => addMutation.mutate(userId)}
        />
        {addMutation.isError && (
          <div style={{ marginTop: 6, fontSize: 12, color: 'var(--bad)' }}>
            {(addMutation.error as Error).message}
          </div>
        )}
      </div>

      <div>
        <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--fg-2)', marginBottom: 8 }}>
          {list.length} member{list.length !== 1 ? 's' : ''}
        </div>
        {list.length === 0 ? (
          <div style={{ fontSize: 12, color: 'var(--fg-3)', padding: '12px 0' }}>
            No members yet. Use the field above to add someone.
          </div>
        ) : (
          <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 8, overflow: 'hidden' }}>
            {list.map((m, i) => {
              const bg = avatarColor(m.email);
              const ini = initials(m.display_name, m.email);
              return (
                <div key={m.id} style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '10px 14px',
                  borderBottom: i < list.length - 1 ? '1px solid var(--rule)' : 'none',
                }}>
                  <div style={{
                    width: 32, height: 32, borderRadius: '50%',
                    background: bg, color: '#fff', fontSize: 12, fontWeight: 700,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0,
                  }}>{ini}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--fg-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {m.display_name || m.email}
                    </div>
                    {m.display_name && (
                      <div style={{ fontSize: 11, color: 'var(--fg-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {m.email}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => removeMutation.mutate(m.user_id)}
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
        {removeMutation.isError && (
          <div style={{ marginTop: 6, fontSize: 12, color: 'var(--bad)' }}>
            {(removeMutation.error as Error).message}
          </div>
        )}
      </div>
    </div>
  );
}
