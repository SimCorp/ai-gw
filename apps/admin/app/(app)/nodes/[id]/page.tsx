'use client';

import React, { useState, use } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../../../lib/apiClient';
import { LoadingState, ErrorState } from '../../_components/PageStates';
import { Breadcrumb } from '../../_components/Breadcrumb';
import { ResourceTable } from '../../_components/ResourceTable';
import { OrgNode, TypeBadge, typeBadgeColor } from '../../_components/nodeTypes';
import { PolicyPanel } from './_components/PolicyPanel';
import { BudgetPanel } from './_components/BudgetPanel';
import { PermissionsPanel } from './_components/PermissionsPanel';

// ── Tab types ─────────────────────────────────────────────────────────────────

type Tab = 'overview' | 'policy' | 'budget' | 'permissions';
const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'policy', label: 'Policy' },
  { id: 'budget', label: 'Budget' },
  { id: 'permissions', label: 'Permissions' },
];

// ── Member types ──────────────────────────────────────────────────────────────

interface Member {
  id: string;
  email: string;
  display_name: string;
}

// ── Add-child form ─────────────────────────────────────────────────────────────

function AddChildForm({ parentId, onDone }: { parentId: string; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [type, setType] = useState('team');
  const [color, setColor] = useState('#10B981');

  const createMutation = useMutation({
    mutationFn: () =>
      apiFetch<OrgNode>('/nodes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), type, parent_id: parentId, color }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['node', parentId] });
      queryClient.invalidateQueries({ queryKey: ['node-tree'] });
      onDone();
    },
  });

  return (
    <div style={{
      padding: '16px',
      background: 'var(--surface-2)',
      border: '1px solid var(--rule)',
      borderRadius: 8,
      marginTop: 16,
    }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg-1)', marginBottom: 12 }}>Add child node</div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          placeholder="Name"
          value={name}
          onChange={e => setName(e.target.value)}
          style={{ flex: '2 1 200px', padding: '7px 10px', fontSize: 13, background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 5, color: 'var(--fg-1)' }}
        />
        <select
          value={type}
          onChange={e => setType(e.target.value)}
          style={{ flex: '1 1 120px', padding: '7px 10px', fontSize: 13, background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 5, color: 'var(--fg-1)' }}
        >
          <option value="area">Area</option>
          <option value="unit">Unit</option>
          <option value="team">Team</option>
          <option value="squad">Squad</option>
        </select>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <label style={{ fontSize: 12, color: 'var(--fg-3)' }}>Color:</label>
          <input
            type="color"
            value={color}
            onChange={e => setColor(e.target.value)}
            style={{ width: 32, height: 32, padding: 2, border: '1px solid var(--rule)', borderRadius: 4, background: 'transparent', cursor: 'pointer' }}
          />
        </div>
        <button
          onClick={() => createMutation.mutate()}
          disabled={!name.trim() || createMutation.isPending}
          style={{ padding: '7px 14px', fontSize: 13, background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 5, cursor: 'pointer' }}
        >
          {createMutation.isPending ? 'Creating…' : 'Create'}
        </button>
        <button
          onClick={onDone}
          style={{ padding: '7px 14px', fontSize: 13, background: 'transparent', color: 'var(--fg-3)', border: '1px solid var(--rule)', borderRadius: 5, cursor: 'pointer' }}
        >
          Cancel
        </button>
      </div>
      {createMutation.isError && (
        <div style={{ marginTop: 8, fontSize: 12, color: 'var(--bad)' }}>
          {(createMutation.error as Error).message}
        </div>
      )}
    </div>
  );
}

// ── Overview tab ──────────────────────────────────────────────────────────────

function OverviewTab({ node }: { node: OrgNode }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [showAddChild, setShowAddChild] = useState(false);

  const { data: members } = useQuery<{ total: number; items: Member[] }>({
    queryKey: ['node-members', node.id],
    queryFn: () => apiFetch(`/nodes/${node.id}/members?limit=5`),
    staleTime: 60_000,
  });

  const children = node.children ?? [];
  const childCount = children.length;
  const memberCount = node.member_count ?? members?.total ?? 0;
  const spendMtd = node.spend_mtd;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* KPI row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
        <KpiCard label="Child nodes" value={String(childCount)} />
        <KpiCard label="Direct members" value={String(memberCount)} />
        {spendMtd != null && (
          <KpiCard label="Spend MTD" value={`$${spendMtd.toLocaleString()}`} />
        )}
      </div>

      {/* Child nodes */}
      {childCount > 0 && (
        <section>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg-1)', marginBottom: 10 }}>Child nodes</div>
          <ResourceTable
            nodes={children}
            onNavigate={n => router.push(`/nodes/${n.id}`)}
          />
        </section>
      )}

      {/* Add child form */}
      {showAddChild ? (
        <AddChildForm parentId={node.id} onDone={() => setShowAddChild(false)} />
      ) : (
        <button
          onClick={() => setShowAddChild(true)}
          style={{
            padding: '7px 14px', fontSize: 13, width: 'fit-content',
            background: 'var(--surface-2)', border: '1px solid var(--rule)',
            borderRadius: 5, color: 'var(--fg-1)', cursor: 'pointer',
          }}
        >
          + Add child node
        </button>
      )}

      {/* Members preview */}
      {members && members.items.length > 0 && (
        <section>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg-1)', marginBottom: 10 }}>Members</div>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 8, overflow: 'hidden' }}>
            {members.items.map((m, i) => (
              <div key={m.id} style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '8px 14px',
                borderBottom: i < Math.min(members.items.length, 5) - 1 ? '1px solid var(--rule)' : 'none',
                fontSize: 13, color: 'var(--fg-1)',
              }}>
                <div style={{
                  width: 26, height: 26, borderRadius: '50%', flexShrink: 0,
                  background: avatarColor(m.email),
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 10, fontWeight: 700, color: '#fff',
                }}>
                  {initials(m.display_name || m.email)}
                </div>
                <div>
                  <div style={{ fontWeight: 500 }}>{m.display_name || m.email}</div>
                  <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>{m.email}</div>
                </div>
              </div>
            ))}
          </div>
          {members.total > 5 && (
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--accent)', cursor: 'pointer' }}>
              + {members.total - 5} more members
            </div>
          )}
        </section>
      )}
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <div style={{
      padding: '14px 16px',
      background: 'var(--surface)',
      border: '1px solid var(--rule)',
      borderRadius: 8,
    }}>
      <div className="microlabel" style={{ marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--fg-1)' }}>{value}</div>
    </div>
  );
}

const AVATAR_COLORS = ['var(--accent)', 'var(--cat-teal)', 'var(--cat-purple)', 'var(--cat-orange)', 'var(--cat-magenta)', 'var(--accent)', 'var(--cat-coral)'];
function avatarColor(s: string) {
  let h = 0;
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}
function initials(name: string): string {
  return name.split(/\s+/).map(w => w[0]).join('').toUpperCase().slice(0, 2);
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function NodeDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();

  const activeTab = (searchParams.get('tab') as Tab) ?? 'overview';

  const { data: node, isLoading, error } = useQuery<OrgNode>({
    queryKey: ['node', id],
    queryFn: () => apiFetch(`/nodes/${id}`),
    staleTime: 30_000,
  });

  const deleteMutation = useMutation({
    mutationFn: () => apiFetch(`/nodes/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['node-tree'] });
      const parentId = node?.parent_id;
      if (parentId) {
        router.push(`/nodes/${parentId}`);
      } else {
        router.push('/org');
      }
    },
  });

  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editLocation, setEditLocation] = useState('');

  const editMutation = useMutation({
    mutationFn: () =>
      apiFetch<OrgNode>(`/nodes/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: editName.trim(),
          description: editDescription.trim() || null,
          location: editLocation.trim() || null,
        }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['node', id] });
      queryClient.invalidateQueries({ queryKey: ['node-tree'] });
      setEditing(false);
    },
  });

  if (isLoading) return <LoadingState rows={8} />;
  if (error) return <ErrorState error={error as Error} />;
  if (!node) return null;

  const color = node.color ?? typeBadgeColor(node.type);

  function setTab(tab: Tab) {
    router.push(`/nodes/${id}?tab=${tab}`);
  }

  function handleDelete() {
    if (!confirm(`Delete "${node!.name}" and all its descendants? This cannot be undone.`)) return;
    deleteMutation.mutate();
  }

  return (
    <div>
      {/* Breadcrumb */}
      <Breadcrumb nodeId={id} />

      {/* Node header */}
      <div style={{
        display: 'flex', alignItems: 'flex-start', gap: 16,
        marginBottom: 20, justifyContent: 'space-between', flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{
            width: 40, height: 40, borderRadius: 10,
            background: color, flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 18, color: '#fff', fontWeight: 700,
          }}>
            {node.name.charAt(0).toUpperCase()}
          </div>
          <div>
            <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--fg-1)', display: 'flex', alignItems: 'center', gap: 8 }}>
              {node.name}
              <TypeBadge type={node.type} />
            </div>
            <div style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: 2, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              {node.location && <span>{node.location}</span>}
              <span style={{ fontFamily: 'monospace' }}>{node.slug}</span>
              {node.description && <span>{node.description}</span>}
            </div>
          </div>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
          <button
            onClick={() => setTab('overview')}
            style={{
              padding: '7px 14px', fontSize: 12,
              background: 'var(--accent)', color: '#fff',
              border: 'none', borderRadius: 5, cursor: 'pointer',
            }}
          >
            + Add child
          </button>
          <button
            onClick={() => {
              setEditName(node.name);
              setEditDescription(node.description ?? '');
              setEditLocation(node.location ?? '');
              setEditing(true);
            }}
            style={{
              padding: '7px 14px', fontSize: 12,
              background: 'var(--surface-2)', border: '1px solid var(--rule)',
              borderRadius: 5, color: 'var(--fg-1)', cursor: 'pointer',
            }}
          >
            Edit
          </button>
          <button
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
            style={{
              padding: '7px 14px', fontSize: 12,
              background: 'transparent', border: '1px solid color-mix(in srgb, var(--bad) 27%, transparent)',
              borderRadius: 5, color: 'var(--bad)', cursor: 'pointer',
            }}
          >
            Delete
          </button>
        </div>
      </div>

      {editing && (
        <div style={{ padding: '16px 0', borderTop: '1px solid var(--rule)', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg-1)' }}>Edit node</div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: '2 1 200px' }}>
              <label style={{ fontSize: 11.5, color: 'var(--fg-2)' }}>Name</label>
              <input value={editName} onChange={e => setEditName(e.target.value)}
                style={{ padding: '7px 10px', fontSize: 13, background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 5, color: 'var(--fg-1)' }} />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: '1 1 150px' }}>
              <label style={{ fontSize: 11.5, color: 'var(--fg-2)' }}>Location</label>
              <input value={editLocation} onChange={e => setEditLocation(e.target.value)}
                placeholder="e.g. Copenhagen"
                style={{ padding: '7px 10px', fontSize: 13, background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 5, color: 'var(--fg-1)' }} />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: '3 1 280px' }}>
              <label style={{ fontSize: 11.5, color: 'var(--fg-2)' }}>Description</label>
              <input value={editDescription} onChange={e => setEditDescription(e.target.value)}
                placeholder="Optional description"
                style={{ padding: '7px 10px', fontSize: 13, background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 5, color: 'var(--fg-1)' }} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => editMutation.mutate()} disabled={!editName.trim() || editMutation.isPending}
              style={{ padding: '7px 16px', fontSize: 12, background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 5, cursor: 'pointer' }}>
              {editMutation.isPending ? 'Saving…' : 'Save'}
            </button>
            <button onClick={() => setEditing(false)}
              style={{ padding: '7px 14px', fontSize: 12, background: 'transparent', color: 'var(--fg-3)', border: '1px solid var(--rule)', borderRadius: 5, cursor: 'pointer' }}>
              Cancel
            </button>
          </div>
        </div>
      )}
      {/* Divider */}
      <div style={{ borderBottom: '1px solid var(--rule)', marginBottom: 0 }} />

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--rule)', marginBottom: 24 }}>
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              padding: '10px 18px',
              fontSize: 13,
              fontWeight: activeTab === t.id ? 600 : 400,
              color: activeTab === t.id ? 'var(--accent)' : 'var(--fg-3)',
              background: 'transparent',
              border: 'none',
              borderBottom: activeTab === t.id ? '2px solid var(--accent)' : '2px solid transparent',
              cursor: 'pointer',
              marginBottom: -1,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'overview' && <OverviewTab node={node} />}
      {activeTab === 'policy' && <PolicyPanel nodeId={id} nodeName={node.name} />}
      {activeTab === 'budget' && <BudgetPanel nodeId={id} />}
      {activeTab === 'permissions' && <PermissionsPanel nodeId={id} />}
    </div>
  );
}
