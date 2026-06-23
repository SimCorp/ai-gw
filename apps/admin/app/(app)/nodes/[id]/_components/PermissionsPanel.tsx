'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../../../../lib/apiClient';
import { LoadingState, ErrorState } from '../../../_components/PageStates';

interface RoleAssignment {
  id: string;
  entra_group_id: string;
  entra_group_name: string | null;
  role: string;
  granted_at: string;
}

const ROLE_OPTIONS = [
  'platform_admin',
  'area_owner',
  'unit_lead',
  'team_admin',
  'developer',
  'viewer',
];

const ROLE_COLORS: Record<string, string> = {
  platform_admin: 'var(--cat-coral)',
  area_owner: 'var(--cat-orange)',
  unit_lead: 'var(--cat-magenta)',
  team_admin: 'var(--accent)',
  developer: 'var(--cat-teal)',
  viewer: 'var(--cat-purple)',
};

const ROLE_LABELS: Record<string, string> = {
  platform_admin: 'Platform Admin',
  area_owner: 'Area Owner',
  unit_lead: 'Unit Lead',
  team_admin: 'Team Admin',
  developer: 'Developer',
  viewer: 'Viewer',
};

function RolePill({ role }: { role: string }) {
  const color = ROLE_COLORS[role] ?? 'var(--fg-3)';
  return (
    <span style={{
      display: 'inline-block', padding: '2px 7px',
      borderRadius: 10, fontSize: 11, fontWeight: 600,
      background: `color-mix(in srgb, ${color} 13%, transparent)`, color, border: `1px solid color-mix(in srgb, ${color} 27%, transparent)`,
    }}>
      {ROLE_LABELS[role] ?? role}
    </span>
  );
}

interface PermissionsPanelProps {
  nodeId: string;
}

export function PermissionsPanel({ nodeId }: PermissionsPanelProps) {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [groupId, setGroupId] = useState('');
  const [groupName, setGroupName] = useState('');
  const [role, setRole] = useState('developer');

  const { data, isLoading, error } = useQuery<RoleAssignment[]>({
    queryKey: ['node-permissions', nodeId],
    queryFn: () => apiFetch(`/nodes/${nodeId}/permissions`),
    staleTime: 30_000,
  });

  const addMutation = useMutation({
    mutationFn: (body: { entra_group_id: string; entra_group_name: string; role: string }) =>
      apiFetch(`/nodes/${nodeId}/permissions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['node-permissions', nodeId] });
      setShowForm(false);
      setGroupId('');
      setGroupName('');
      setRole('developer');
    },
  });

  const removeMutation = useMutation({
    mutationFn: (assignmentId: string) =>
      apiFetch(`/nodes/${nodeId}/permissions/${assignmentId}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['node-permissions', nodeId] });
    },
  });

  if (isLoading) return <LoadingState rows={4} />;
  if (error) return <ErrorState error={error as Error} />;

  const assignments = data ?? [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Inherited note */}
      <div style={{
        padding: '10px 14px', fontSize: 12, color: 'var(--fg-3)',
        background: 'var(--surface-2)', border: '1px solid var(--rule)',
        borderRadius: 7, borderLeft: '3px solid var(--accent)',
      }}>
        Access inherited from ancestor nodes is not shown here — manage it on those nodes.
      </div>

      {/* Assignment list */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg-1)' }}>
            Entra groups on this node
          </div>
          <button
            onClick={() => setShowForm(v => !v)}
            style={{
              padding: '5px 12px', fontSize: 12,
              background: 'var(--accent)', color: '#fff',
              border: 'none', borderRadius: 5, cursor: 'pointer',
            }}
          >
            + Assign Entra group
          </button>
        </div>

        {showForm && (
          <div style={{
            display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center',
            padding: '12px 14px', background: 'var(--surface-2)',
            border: '1px solid var(--rule)', borderRadius: 7, marginBottom: 12,
          }}>
            <input
              placeholder="Entra group ID (UUID)"
              value={groupId}
              onChange={e => setGroupId(e.target.value)}
              style={{ flex: '2 1 220px', padding: '6px 10px', fontSize: 12, background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 5, color: 'var(--fg-1)', fontFamily: 'monospace' }}
            />
            <input
              placeholder="Display name (optional)"
              value={groupName}
              onChange={e => setGroupName(e.target.value)}
              style={{ flex: '2 1 180px', padding: '6px 10px', fontSize: 12, background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 5, color: 'var(--fg-1)' }}
            />
            <select
              value={role}
              onChange={e => setRole(e.target.value)}
              style={{ flex: '1 1 140px', padding: '6px 10px', fontSize: 12, background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 5, color: 'var(--fg-1)' }}
            >
              {ROLE_OPTIONS.map(r => (
                <option key={r} value={r}>{ROLE_LABELS[r] ?? r}</option>
              ))}
            </select>
            <button
              onClick={() => addMutation.mutate({ entra_group_id: groupId.trim(), entra_group_name: groupName.trim(), role })}
              disabled={!groupId.trim() || addMutation.isPending}
              style={{ padding: '6px 12px', fontSize: 12, background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 5, cursor: 'pointer' }}
            >
              Save
            </button>
            <button
              onClick={() => setShowForm(false)}
              style={{ padding: '6px 12px', fontSize: 12, background: 'transparent', color: 'var(--fg-3)', border: '1px solid var(--rule)', borderRadius: 5, cursor: 'pointer' }}
            >
              Cancel
            </button>
          </div>
        )}

        {assignments.length === 0 && !showForm ? (
          <div style={{ fontSize: 12, color: 'var(--fg-3)', padding: '12px 0' }}>
            No Entra groups assigned to this node.
          </div>
        ) : (
          <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 8, overflow: 'hidden' }}>
            {assignments.map((a, i) => (
              <div key={a.id} style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '10px 14px',
                borderBottom: i < assignments.length - 1 ? '1px solid var(--rule)' : 'none',
              }}>
                {/* Group icon */}
                <span style={{ fontSize: 16, flexShrink: 0 }}>&#x1F465;</span>
                {/* Name + ID */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--fg-1)' }}>
                    {a.entra_group_name ?? 'Unnamed group'}
                  </div>
                  <div style={{
                    fontSize: 11, color: 'var(--fg-3)',
                    fontFamily: 'monospace',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    maxWidth: 320,
                  }}>
                    {a.entra_group_id}
                  </div>
                </div>
                {/* Role */}
                <RolePill role={a.role} />
                {/* Remove */}
                <button
                  onClick={() => removeMutation.mutate(a.id)}
                  disabled={removeMutation.isPending}
                  style={{
                    padding: '3px 9px', fontSize: 11, background: 'transparent',
                    border: '1px solid var(--rule)', borderRadius: 4,
                    color: 'var(--bad)', cursor: 'pointer',
                  }}
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}

        {(addMutation.isError || removeMutation.isError) && (
          <div style={{ marginTop: 8, fontSize: 12, color: 'var(--bad)' }}>
            {((addMutation.error ?? removeMutation.error) as Error).message}
          </div>
        )}
      </div>
    </div>
  );
}
